"""
Unit tests for slot logic in check_availability.py.

Covers: get_date_range, parse_dates_list, parse_between_time_range,
_filter_slots_by_between, has_changes, get_slot_changes, and the
rolling-window behaviour introduced to detect new courts that "drop"
for a brand-new day (typically exactly 7 days ahead on Matchi.se).
"""

import datetime
import sys
import os
import unittest

# Make check_availability importable when pytest is run from the repo root
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from check_availability import (  # noqa: E402
    get_date_range,
    parse_dates_list,
    parse_between_time_range,
    _filter_slots_by_between,
    has_changes,
    get_slot_changes,
)


# ---------------------------------------------------------------------------
# Tests: get_date_range
# ---------------------------------------------------------------------------

class TestGetDateRange(unittest.TestCase):
    def test_zero_days_returns_today_only(self):
        today = datetime.date.today()
        result = get_date_range(0)
        self.assertEqual(result, [today])

    def test_two_days_ahead(self):
        today = datetime.date.today()
        result = get_date_range(2)
        expected = [today, today + datetime.timedelta(1), today + datetime.timedelta(2)]
        self.assertEqual(result, expected)

    def test_explicit_start_date(self):
        start = datetime.date(2025, 1, 15)
        result = get_date_range(2, start_date=start)
        self.assertEqual(result, [
            datetime.date(2025, 1, 15),
            datetime.date(2025, 1, 16),
            datetime.date(2025, 1, 17),
        ])

    def test_negative_raises(self):
        with self.assertRaises(ValueError):
            get_date_range(-1)


# ---------------------------------------------------------------------------
# Tests: parse_dates_list
# ---------------------------------------------------------------------------

class TestParseDatesList(unittest.TestCase):
    def test_single_date(self):
        result = parse_dates_list("2025-08-20")
        self.assertEqual(result, [datetime.date(2025, 8, 20)])

    def test_multiple_dates_sorted(self):
        result = parse_dates_list("2025-08-20,2025-08-15")
        self.assertEqual(result, [
            datetime.date(2025, 8, 15),
            datetime.date(2025, 8, 20),
        ])

    def test_duplicates_deduplicated(self):
        result = parse_dates_list("2025-01-10,2025-01-10")
        self.assertEqual(result, [datetime.date(2025, 1, 10)])


# ---------------------------------------------------------------------------
# Tests: parse_between_time_range
# ---------------------------------------------------------------------------

class TestParseBetweenTimeRange(unittest.TestCase):
    def test_hour_only(self):
        start, end = parse_between_time_range("17-22")
        self.assertEqual(start, datetime.time(17, 0))
        self.assertEqual(end, datetime.time(22, 0))

    def test_hhmm_format(self):
        start, end = parse_between_time_range("17:30-22:00")
        self.assertEqual(start, datetime.time(17, 30))
        self.assertEqual(end, datetime.time(22, 0))


# ---------------------------------------------------------------------------
# Tests: _filter_slots_by_between
# ---------------------------------------------------------------------------

class TestFilterSlotsByBetween(unittest.TestCase):
    SLOTS = {
        "16:00-17:00": ["Court 1"],
        "17:00-18:00": ["Court 2"],
        "20:00-21:00": ["Court 3"],
        "22:00-23:00": ["Court 4"],
    }

    def _between(self, start_h, end_h):
        return (datetime.time(start_h, 0), datetime.time(end_h, 0))

    def test_filters_outside_slots(self):
        result = _filter_slots_by_between(self.SLOTS, self._between(17, 22))
        self.assertIn("17:00-18:00", result)
        self.assertIn("20:00-21:00", result)
        self.assertNotIn("16:00-17:00", result)
        self.assertNotIn("22:00-23:00", result)

    def test_no_filter_returns_all(self):
        result = _filter_slots_by_between(self.SLOTS, None)
        self.assertEqual(result, self.SLOTS)


# ---------------------------------------------------------------------------
# Tests: has_changes
# ---------------------------------------------------------------------------

class TestHasChanges(unittest.TestCase):
    def _slots(self, courts):
        """Build a minimal slot dict for facility 'frogner' on a fixed date."""
        d = datetime.date(2025, 8, 20)
        return {"frogner": {d: {"17:00-18:00": courts}}}

    def test_empty_previous_returns_false(self):
        self.assertFalse(has_changes(self._slots(["Court 1"]), {}))

    def test_identical_returns_false(self):
        s = self._slots(["Court 1"])
        self.assertFalse(has_changes(s, s))

    def test_new_court_detected(self):
        prev = self._slots(["Court 1"])
        curr = self._slots(["Court 1", "Court 2"])
        self.assertTrue(has_changes(curr, prev))

    def test_new_date_in_window_detected(self):
        """When a brand-new date (e.g. 7 days ahead) enters the rolling window,
        has_changes must return True so the loop triggers a notification."""
        d1 = datetime.date(2025, 8, 20)
        d2 = datetime.date(2025, 8, 27)  # New day entering the window

        previous = {"frogner": {d1: {"17:00-18:00": ["Court 1"]}}}
        current = {
            "frogner": {
                d1: {"17:00-18:00": ["Court 1"]},
                d2: {"17:00-18:00": ["Court A"]},  # New day's courts
            }
        }
        self.assertTrue(has_changes(current, previous))


# ---------------------------------------------------------------------------
# Tests: get_slot_changes — rolling-window new-day detection
# ---------------------------------------------------------------------------

class TestGetSlotChangesNewDay(unittest.TestCase):
    """Verify that all courts on a brand-new date are returned as 'new'."""

    def test_brand_new_date_all_courts_are_new(self):
        """When a date was not present in previous_slots (it just entered the
        7-day booking window), every available court on that day should be
        detected as a new court."""
        new_date = datetime.date(2025, 8, 27)

        current = {
            "frogner": {
                new_date: {
                    "17:00-18:00": ["Court 1", "Court 2"],
                    "18:00-19:00": ["Court 3"],
                }
            }
        }
        # previous_slots has no entry for new_date (it wasn't in the window)
        previous = {"frogner": {}}

        new_courts, removed_courts = get_slot_changes(
            current, previous, "frogner", new_date
        )

        self.assertIn(("17:00-18:00", "Court 1"), new_courts)
        self.assertIn(("17:00-18:00", "Court 2"), new_courts)
        self.assertIn(("18:00-19:00", "Court 3"), new_courts)
        self.assertEqual(removed_courts, set())

    def test_existing_courts_not_reported_as_new_on_next_poll(self):
        """After the first detection the same courts must NOT be reported again,
        ensuring no duplicate notifications."""
        date = datetime.date(2025, 8, 27)
        slots = {
            "frogner": {
                date: {
                    "17:00-18:00": ["Court 1"],
                }
            }
        }

        # Second poll: current == previous (no change)
        new_courts, removed_courts = get_slot_changes(
            slots, slots, "frogner", date
        )

        self.assertEqual(new_courts, set())
        self.assertEqual(removed_courts, set())

    def test_between_filter_applied_before_comparison(self):
        """Courts outside the --between window must not appear in new_courts
        because _filter_slots_by_between strips them before get_slot_changes
        is called."""
        date = datetime.date(2025, 8, 27)
        between = (datetime.time(17, 0), datetime.time(22, 0))

        raw_current = {
            "frogner": {
                date: {
                    "15:00-16:00": ["Court X"],   # outside window
                    "17:00-18:00": ["Court 1"],   # inside window
                }
            }
        }
        # Simulate the filtering that run_monitor applies before diffing
        filtered_slots = {
            k: {
                d: _filter_slots_by_between(v, between)
                for d, v in fac.items()
            }
            for k, fac in raw_current.items()
        }

        previous = {"frogner": {date: {}}}

        new_courts, _ = get_slot_changes(filtered_slots, previous, "frogner", date)

        time_slots_reported = {ts for ts, _ in new_courts}
        self.assertIn("17:00-18:00", time_slots_reported)
        self.assertNotIn("15:00-16:00", time_slots_reported)


if __name__ == "__main__":
    unittest.main()
