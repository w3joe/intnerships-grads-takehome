"""Boundary examples and independent checks of coverage ownership."""

import copy
import random
import unittest
from datetime import datetime, timedelta, timezone

from scheduler import render_schedule


START = datetime(2026, 11, 6, 17, tzinfo=timezone.utc)


def timestamp(days=0, hours=0, minutes=0):
    instant = START + timedelta(days=days, hours=hours, minutes=minutes)
    return instant.isoformat().replace("+00:00", "Z")


def entry(user, start, end):
    return {"user": user, "start_at": start, "end_at": end}


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.schedule = {
            "users": ["alice", "bob", "charlie"],
            "handover_start_at": timestamp(),
            "handover_interval_days": 7,
        }

    def render(self, overrides=None, start=None, until=None):
        return render_schedule(
            self.schedule,
            [] if overrides is None else overrides,
            timestamp() if start is None else start,
            timestamp(14) if until is None else until,
        )

    def test_readme_example(self):
        overrides = [entry("charlie", timestamp(3), timestamp(3, 5))]
        self.assertEqual(self.render(overrides), [
            entry("alice", timestamp(), timestamp(3)),
            entry("charlie", timestamp(3), timestamp(3, 5)),
            entry("alice", timestamp(3, 5), timestamp(7)),
            entry("bob", timestamp(7), timestamp(14)),
        ])

    def test_rotation_wraps_to_first_user(self):
        self.assertEqual(self.render(until=timestamp(28)), [
            entry("alice", timestamp(), timestamp(7)),
            entry("bob", timestamp(7), timestamp(14)),
            entry("charlie", timestamp(14), timestamp(21)),
            entry("alice", timestamp(21), timestamp(28)),
        ])

    def test_query_clips_both_ends(self):
        self.assertEqual(self.render(start=timestamp(2), until=timestamp(8)), [
            entry("alice", timestamp(2), timestamp(7)),
            entry("bob", timestamp(7), timestamp(8)),
        ])

    def test_later_query_keeps_original_rotation(self):
        self.assertEqual(self.render(start=timestamp(7001), until=timestamp(7002)), [
            entry("bob", timestamp(7001), timestamp(7002)),
        ])

    def test_override_crosses_multiple_handovers_and_rotation_resumes(self):
        overrides = [entry("dana", timestamp(6), timestamp(15))]
        self.assertEqual(self.render(overrides, until=timestamp(16)), [
            entry("alice", timestamp(), timestamp(6)),
            entry("dana", timestamp(6), timestamp(15)),
            entry("charlie", timestamp(15), timestamp(16)),
        ])

    def test_override_covering_query_is_clipped(self):
        overrides = [entry("dana", timestamp(1), timestamp(20))]
        self.assertEqual(
            self.render(overrides, start=timestamp(2), until=timestamp(14)),
            [entry("dana", timestamp(2), timestamp(14))],
        )

    def test_override_clips_at_query_start(self):
        overrides = [entry("dana", timestamp(1), timestamp(3))]
        self.assertEqual(self.render(overrides, timestamp(2), timestamp(4)), [
            entry("dana", timestamp(2), timestamp(3)),
            entry("alice", timestamp(3), timestamp(4)),
        ])

    def test_override_clips_at_query_end(self):
        overrides = [entry("dana", timestamp(3), timestamp(5))]
        self.assertEqual(self.render(overrides, until=timestamp(4)), [
            entry("alice", timestamp(), timestamp(3)),
            entry("dana", timestamp(3), timestamp(4)),
        ])

    def test_adjacent_unsorted_overrides_at_handover(self):
        overrides = [
            entry("erin", timestamp(7), timestamp(8)),
            entry("dana", timestamp(6), timestamp(7)),
        ]
        self.assertEqual(self.render(overrides, timestamp(6), timestamp(9)), [
            entry("dana", timestamp(6), timestamp(7)),
            entry("erin", timestamp(7), timestamp(8)),
            entry("bob", timestamp(8), timestamp(9)),
        ])

    def test_overrides_touching_query_are_excluded(self):
        overrides = [
            entry("dana", timestamp(1), timestamp(2)),
            entry("erin", timestamp(4), timestamp(5)),
        ]
        self.assertEqual(self.render(overrides, timestamp(2), timestamp(4)), [
            entry("alice", timestamp(2), timestamp(4)),
        ])

    def test_same_owner_segments_are_merged(self):
        overrides = [entry("alice", timestamp(1), timestamp(3))]
        self.assertEqual(self.render(overrides, until=timestamp(7)), [
            entry("alice", timestamp(), timestamp(7)),
        ])

    def test_single_user_handovers_are_merged(self):
        self.schedule["users"] = ["alice"]
        self.assertEqual(self.render(until=timestamp(28)), [
            entry("alice", timestamp(), timestamp(28)),
        ])

    def test_adjacent_overrides_with_same_owner_are_merged(self):
        overrides = [
            entry("dana", timestamp(1), timestamp(2)),
            entry("dana", timestamp(2), timestamp(3)),
        ]
        self.assertEqual(self.render(overrides, timestamp(1), timestamp(3)), [
            entry("dana", timestamp(1), timestamp(3)),
        ])

    def test_empty_and_pre_schedule_queries(self):
        for start, until in [
            (timestamp(1), timestamp(1)),
            (timestamp(-2), timestamp(-1)),
            (timestamp(-1), timestamp()),
        ]:
            with self.subTest(start=start, until=until):
                self.assertEqual(self.render(start=start, until=until), [])

    def test_query_crossing_schedule_start(self):
        self.assertEqual(self.render(start=timestamp(-1), until=timestamp(1)), [
            entry("alice", timestamp(), timestamp(1)),
        ])

    def test_offset_timestamps_are_normalised_to_utc(self):
        self.schedule["handover_start_at"] = "2026-11-06T19:00:00+02:00"
        overrides = [entry(
            "dana", "2026-11-07T18:00:00+01:00", "2026-11-07T20:00:00+02:00"
        )]
        self.assertEqual(self.render(
            overrides, "2026-11-07T12:00:00-05:00", "2026-11-07T21:00:00+02:00"
        ), [
            entry("dana", timestamp(1), timestamp(1, 1)),
            entry("alice", timestamp(1, 1), timestamp(1, 2)),
        ])

    def test_fractional_seconds_are_preserved(self):
        start = "2026-11-06T17:00:00.125Z"
        end = "2026-11-06T17:00:00.250Z"
        self.assertEqual(self.render(start=start, until=end), [
            entry("alice", "2026-11-06T17:00:00.125000Z",
                  "2026-11-06T17:00:00.250000Z"),
        ])

    def test_daily_rotation_across_month_boundary(self):
        self.schedule["handover_interval_days"] = 1
        self.assertEqual(self.render(start=timestamp(24), until=timestamp(27)), [
            entry("alice", timestamp(24), timestamp(25)),
            entry("bob", timestamp(25), timestamp(26)),
            entry("charlie", timestamp(26), timestamp(27)),
        ])

    def test_inputs_are_not_mutated(self):
        overrides = [
            entry("dana", timestamp(3), timestamp(4)),
            entry("erin", timestamp(1), timestamp(2)),
        ]
        original = copy.deepcopy((self.schedule, overrides))
        self.render(overrides)
        self.assertEqual((self.schedule, overrides), original)

    def test_invalid_schedules(self):
        invalid = [None, [], {}]
        invalid.extend({**self.schedule, "users": users} for users in [
            [], "alice", [""], ["  "], [1],
        ])
        invalid.extend({**self.schedule, "handover_interval_days": days} for days in [
            0, -1, True, 1.5, "7", 10**20,
        ])
        invalid.extend({**self.schedule, "handover_start_at": start} for start in [
            "invalid", "2026-11-06T17:00:00", None,
        ])
        for schedule in invalid:
            with self.subTest(schedule=schedule):
                with self.assertRaises(ValueError):
                    render_schedule(schedule, [], timestamp(), timestamp(1))

    def test_invalid_overrides(self):
        valid = entry("dana", timestamp(1), timestamp(2))
        for overrides in [
            None, {}, [None], [{}],
            [{**valid, "user": ""}],
            [{**valid, "start_at": "invalid"}],
            [{**valid, "end_at": timestamp(1)}],
            [{**valid, "end_at": timestamp()}],
            [entry("dana", timestamp(-1), timestamp(1))],
            [valid, entry("erin", timestamp(1, 1), timestamp(3))],
        ]:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    render_schedule(self.schedule, overrides, timestamp(), timestamp(14))

    def test_invalid_query_boundaries(self):
        for start, until in [
            (timestamp(2), timestamp(1)),
            ("invalid", timestamp(1)),
            (timestamp(), "2026-11-07T17:00:00"),
            (None, timestamp(1)),
        ]:
            with self.subTest(start=start, until=until):
                with self.assertRaises(ValueError):
                    render_schedule(self.schedule, [], start, until)

    def test_seeded_scenarios_against_hourly_reference(self):
        # The reference assigns ownership one hour at a time, independently of
        # the production boundary-partition algorithm. All generated edges are
        # on hour boundaries so every ownership transition is checked.
        rng = random.Random(2026)
        for case in range(50):
            interval_days = rng.randint(1, 7)
            self.schedule["handover_interval_days"] = interval_days
            overrides = []
            hour = rng.randint(0, 24)
            while hour < 24 * 21:
                end = hour + rng.randint(1, 48)
                overrides.append(entry(
                    rng.choice(["alice", "bob", "charlie", "dana"]),
                    timestamp(hours=hour), timestamp(hours=end),
                ))
                hour = end + rng.randint(0, 48)
            rng.shuffle(overrides)
            query_start = rng.randint(-24, 24 * 7)
            query_end = query_start + rng.randint(1, 24 * 14)
            result = self.render(
                overrides, timestamp(hours=query_start), timestamp(hours=query_end)
            )
            with self.subTest(case=case):
                if query_end <= 0:
                    self.assertEqual(result, [])
                    continue
                self.assertEqual(result[0]["start_at"], timestamp(hours=max(0, query_start)))
                self.assertEqual(result[-1]["end_at"], timestamp(hours=query_end))
                for previous, current in zip(result, result[1:]):
                    self.assertEqual(previous["end_at"], current["start_at"])
                    self.assertNotEqual(previous["user"], current["user"])
                actual_owners = []
                for shift in result:
                    start = datetime.fromisoformat(shift["start_at"])
                    end = datetime.fromisoformat(shift["end_at"])
                    self.assertLess(start, end)
                    actual_owners.extend([shift["user"]] * ((end - start) // timedelta(hours=1)))
                expected_owners = []
                for hour in range(max(0, query_start), query_end):
                    instant = timestamp(hours=hour)
                    user = self.schedule["users"][(hour // (interval_days * 24)) % 3]
                    for override in overrides:
                        if override["start_at"] <= instant < override["end_at"]:
                            user = override["user"]
                            break
                    expected_owners.append(user)
                self.assertEqual(actual_owners, expected_owners)


if __name__ == "__main__":
    unittest.main()
