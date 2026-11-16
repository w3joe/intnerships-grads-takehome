"""Render an on-call rotation by processing chronological ownership events."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import groupby


@dataclass(frozen=True)
class _Shift:
    user: str
    start_at: datetime
    end_at: datetime


def _parse_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a timestamp string with a timezone")
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("missing timezone")
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as error:
        raise ValueError(
            f"{label} must be a valid timestamp with a timezone"
        ) from error


def _parse_schedule(value: object) -> tuple[list[str], datetime, timedelta]:
    if not isinstance(value, dict):
        raise ValueError("schedule must be a JSON object")
    users = value.get("users")
    if not isinstance(users, list) or not users or any(
        not isinstance(user, str) or not user.strip() for user in users
    ):
        raise ValueError("schedule.users must be a nonempty array of nonempty strings")
    start = _parse_timestamp(
        value.get("handover_start_at"), "schedule.handover_start_at"
    )
    days = value.get("handover_interval_days")
    if type(days) is not int or days <= 0:
        raise ValueError("schedule.handover_interval_days must be a positive integer")
    try:
        duration = timedelta(days=days)
    except OverflowError as error:
        raise ValueError("schedule.handover_interval_days is too large") from error
    return users, start, duration


def _parse_overrides(value: object, schedule_start: datetime) -> list[_Shift]:
    if not isinstance(value, list):
        raise ValueError("overrides must be a JSON array")
    overrides = []
    for index, item in enumerate(value):
        label = f"overrides[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{label} must be a JSON object")
        user = item.get("user")
        if not isinstance(user, str) or not user.strip():
            raise ValueError(f"{label}.user must be a nonempty string")
        start = _parse_timestamp(item.get("start_at"), f"{label}.start_at")
        end = _parse_timestamp(item.get("end_at"), f"{label}.end_at")
        if start >= end:
            raise ValueError(f"{label}.end_at must be after start_at")
        if start < schedule_start:
            raise ValueError(f"{label}.start_at must be at or after the schedule start")
        overrides.append(_Shift(user, start, end))
    overrides.sort(key=lambda override: override.start_at)
    for previous, current in zip(overrides, overrides[1:]):
        if previous.end_at > current.start_at:
            raise ValueError("overrides must not overlap")
    return overrides


def _format_timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def render_schedule(
    schedule: object,
    overrides: object,
    from_time: str,
    until_time: str,
) -> list[dict[str, str]]:
    """Return JSON-ready coverage for [from_time, until_time).

    Inputs are decoded JSON and timezone-aware ISO 8601 timestamp strings.
    This function performs no I/O and does not mutate its inputs. Invalid inputs
    raise ValueError. Overrides replace coverage without moving the rotation.
    """
    users, schedule_start, duration = _parse_schedule(schedule)
    parsed_overrides = _parse_overrides(overrides, schedule_start)
    start = _parse_timestamp(from_time, "from")
    until = _parse_timestamp(until_time, "until")
    if start > until:
        raise ValueError("until must be at or after from")
    start = max(start, schedule_start)
    if start >= until:
        return []

    first_shift = (start - schedule_start) // duration
    base_user = users[first_shift % len(users)]
    # At equal timestamps, apply override ends, handovers, then override starts.
    # Explicit priorities encode that ordering. Emit the previous interval
    # before applying the events, preserving [start, end) ownership.
    end_event, handover_event, start_event, finish_event = range(4)
    events = [(start, handover_event, base_user), (until, finish_event, "")]
    last_handover = (until - schedule_start) // duration
    for shift_number in range(first_shift + 1, last_handover + 1):
        handover = schedule_start + shift_number * duration
        if handover < until:
            events.append((handover, handover_event, users[shift_number % len(users)]))
    for override in parsed_overrides:
        if override.end_at <= start:
            continue
        if override.start_at >= until:
            break
        events.append((max(start, override.start_at), start_event, override.user))
        events.append((min(until, override.end_at), end_event, ""))
    events.sort()

    shifts: list[_Shift] = []
    covering_user = None
    cursor = start
    for instant, simultaneous in groupby(events, key=lambda event: event[0]):
        if cursor < instant:
            user = covering_user if covering_user is not None else base_user
            if shifts and shifts[-1].user == user:
                shifts[-1] = _Shift(user, shifts[-1].start_at, instant)
            else:
                shifts.append(_Shift(user, cursor, instant))
        for _, kind, user in simultaneous:
            if kind == end_event:
                covering_user = None
            elif kind == handover_event:
                base_user = user
            elif kind == start_event:
                covering_user = user
        cursor = instant

    return [
        {
            "user": shift.user,
            "start_at": _format_timestamp(shift.start_at),
            "end_at": _format_timestamp(shift.end_at),
        }
        for shift in shifts
    ]
