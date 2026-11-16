"""Render an on-call rotation by partitioning time at ownership boundaries."""

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


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

    boundaries = {start, until}
    # Jump directly into the rotation rather than replaying earlier shifts.
    first_handover = (start - schedule_start) // duration + 1
    last_handover = (until - schedule_start) // duration
    for shift_number in range(first_handover, last_handover + 1):
        handover = schedule_start + shift_number * duration
        if handover < until:
            boundaries.add(handover)

    relevant_overrides = [
        override
        for override in parsed_overrides
        if override.start_at < until and override.end_at > start
    ]
    for override in relevant_overrides:
        boundaries.add(max(start, override.start_at))
        boundaries.add(min(until, override.end_at))

    ordered = sorted(boundaries)
    override_starts = [override.start_at for override in relevant_overrides]
    shifts: list[_Shift] = []
    for left, right in zip(ordered, ordered[1:]):
        # Ownership cannot change between these boundaries. Half-open intervals
        # mean that an override ending at left is no longer active.
        shift_number = (left - schedule_start) // duration
        user = users[shift_number % len(users)]
        # With non-overlapping overrides, only the latest start at or before
        # left can cover this interval. It may already have ended, leaving a gap.
        override_index = bisect_right(override_starts, left) - 1
        if override_index >= 0:
            override = relevant_overrides[override_index]
            if left < override.end_at:
                user = override.user
        if shifts and shifts[-1].user == user:
            shifts[-1] = _Shift(user, shifts[-1].start_at, right)
        else:
            shifts.append(_Shift(user, left, right))

    return [
        {
            "user": shift.user,
            "start_at": _format_timestamp(shift.start_at),
            "end_at": _format_timestamp(shift.end_at),
        }
        for shift in shifts
    ]
