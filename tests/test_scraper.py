"""
Unit tests for lambdas/scraper/scraper.py and lambdas/scraper/diff.py.

All tests run without network access — HTTP responses are mocked or fixture
HTML is injected directly.
"""

import sys
import os
import textwrap
import unittest
from unittest.mock import MagicMock, patch

# Ensure the scraper package is importable when pytest is run from the repo root.
SCRAPER_DIR = os.path.join(os.path.dirname(__file__), "..", "lambdas", "scraper")
if SCRAPER_DIR not in sys.path:
    sys.path.insert(0, os.path.abspath(SCRAPER_DIR))

from scraper import parse_slots_from_html, fetch_available_slots  # noqa: E402
from diff import has_changes, get_slot_changes, build_new_courts_diff  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture HTML helpers
# ---------------------------------------------------------------------------

def _make_slot_td(part0: str, court: str, time_label: str) -> str:
    """Return an HTML <td class="slot free"> string with the given title parts."""
    title = f"{part0}<br>{court}<br>{time_label}"
    return f'<td class="slot free" title="{title}"></td>'


FIXTURE_HTML_TEMPLATE = textwrap.dedent("""\
    <html><body><table>
    {slots}
    </table></body></html>
""")


# ---------------------------------------------------------------------------
# Tests: parse_slots_from_html / fetch_available_slots
# ---------------------------------------------------------------------------

class TestParseSlots(unittest.TestCase):
    """Tests for scraper.parse_slots_from_html."""

    def test_empty_page_returns_empty_dict(self):
        html = "<html><body><table></table></body></html>"
        result = parse_slots_from_html(html)
        self.assertEqual(result, {})

    def test_single_slot(self):
        slot = _make_slot_td("Tilgjengelig", "Bane 1", "17:00-18:00")
        html = FIXTURE_HTML_TEMPLATE.format(slots=slot)
        result = parse_slots_from_html(html)
        self.assertEqual(result, {"17:00-18:00": ["Bane 1"]})

    def test_multiple_courts_same_time_slot(self):
        slots = "\n".join([
            _make_slot_td("Tilgjengelig", "Bane 1", "17:00-18:00"),
            _make_slot_td("Tilgjengelig", "Bane 3", "17:00-18:00"),
        ])
        html = FIXTURE_HTML_TEMPLATE.format(slots=slots)
        result = parse_slots_from_html(html)
        self.assertIn("17:00-18:00", result)
        self.assertCountEqual(result["17:00-18:00"], ["Bane 1", "Bane 3"])

    def test_multiple_time_slots(self):
        slots = "\n".join([
            _make_slot_td("X", "Bane 1", "17:00-18:00"),
            _make_slot_td("X", "Bane 2", "18:00-19:00"),
            _make_slot_td("X", "Bane 3", "18:00-19:00"),
        ])
        html = FIXTURE_HTML_TEMPLATE.format(slots=slots)
        result = parse_slots_from_html(html)
        self.assertEqual(sorted(result.keys()), ["17:00-18:00", "18:00-19:00"])
        self.assertEqual(result["17:00-18:00"], ["Bane 1"])
        self.assertCountEqual(result["18:00-19:00"], ["Bane 2", "Bane 3"])

    def test_td_without_free_class_is_ignored(self):
        """Booked / reserved slots must not appear in output."""
        booked_td = '<td class="slot booked" title="Booked<br>Bane 1<br>17:00-18:00"></td>'
        html = FIXTURE_HTML_TEMPLATE.format(slots=booked_td)
        result = parse_slots_from_html(html)
        self.assertEqual(result, {})

    def test_malformed_title_skipped(self):
        """Slots where the title has fewer than 3 parts are skipped gracefully."""
        malformed_td = '<td class="slot free" title="OnlyOnePart"></td>'
        html = FIXTURE_HTML_TEMPLATE.format(slots=malformed_td)
        result = parse_slots_from_html(html)
        self.assertEqual(result, {})

    def test_whitespace_stripped_from_court_and_time(self):
        slot = _make_slot_td("  Label  ", "  Bane 2  ", "  09:00-10:00  ")
        html = FIXTURE_HTML_TEMPLATE.format(slots=slot)
        result = parse_slots_from_html(html)
        self.assertIn("09:00-10:00", result)
        self.assertEqual(result["09:00-10:00"], ["Bane 2"])

    def test_time_labels_not_normalised(self):
        """Time-slot labels must be preserved exactly as they appear in HTML."""
        raw_label = "9-10"
        slot = _make_slot_td("X", "Bane 1", raw_label)
        html = FIXTURE_HTML_TEMPLATE.format(slots=slot)
        result = parse_slots_from_html(html)
        self.assertIn(raw_label, result)


class TestFetchAvailableSlots(unittest.TestCase):
    """Tests for scraper.fetch_available_slots (mocked HTTP)."""

    def _make_mock_response(self, html: str):
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_calls_correct_url_and_params(self):
        slot = _make_slot_td("X", "Bane 1", "17:00-18:00")
        html = FIXTURE_HTML_TEMPLATE.format(slots=slot)

        with patch("scraper.requests.get") as mock_get:
            mock_get.return_value = self._make_mock_response(html)
            result = fetch_available_slots(facility_id=2259, date_str="2025-08-20")

        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        params = kwargs.get("params") or mock_get.call_args[0][1]
        # params may be positional or keyword depending on call site
        call_kwargs = mock_get.call_args
        all_args = call_kwargs[0]
        all_kwargs = call_kwargs[1]
        passed_params = all_kwargs.get("params", all_args[1] if len(all_args) > 1 else {})
        self.assertEqual(passed_params["facilityId"], 2259)
        self.assertEqual(passed_params["date"], "2025-08-20")
        self.assertEqual(passed_params["sport"], "1")

    def test_returns_parsed_slots(self):
        slot = _make_slot_td("X", "Bane 5", "20:00-21:00")
        html = FIXTURE_HTML_TEMPLATE.format(slots=slot)

        with patch("scraper.requests.get") as mock_get:
            mock_get.return_value = self._make_mock_response(html)
            result = fetch_available_slots(facility_id=1779, date_str="2025-08-21")

        self.assertEqual(result, {"20:00-21:00": ["Bane 5"]})

    def test_raises_on_http_error(self):
        import requests as req_lib

        with patch("scraper.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.side_effect = req_lib.HTTPError("404")
            mock_get.return_value = mock_resp

            with self.assertRaises(req_lib.HTTPError):
                fetch_available_slots(facility_id=9999, date_str="2025-01-01")


# ---------------------------------------------------------------------------
# Tests: has_changes
# ---------------------------------------------------------------------------

class TestHasChanges(unittest.TestCase):
    """Tests for diff.has_changes."""

    def test_empty_previous_returns_false(self):
        current = {"frogner": {"2025-08-20": {"17:00-18:00": ["Bane 1"]}}}
        self.assertFalse(has_changes(current, {}))

    def test_identical_snapshots_returns_false(self):
        snapshot = {"frogner": {"2025-08-20": {"17:00-18:00": ["Bane 1"]}}}
        self.assertFalse(has_changes(snapshot, snapshot))

    def test_new_court_detected(self):
        previous = {"frogner": {"2025-08-20": {"17:00-18:00": ["Bane 1"]}}}
        current = {"frogner": {"2025-08-20": {"17:00-18:00": ["Bane 1", "Bane 2"]}}}
        self.assertTrue(has_changes(current, previous))

    def test_removed_court_detected(self):
        previous = {"frogner": {"2025-08-20": {"17:00-18:00": ["Bane 1", "Bane 2"]}}}
        current = {"frogner": {"2025-08-20": {"17:00-18:00": ["Bane 1"]}}}
        self.assertTrue(has_changes(current, previous))

    def test_both_empty_returns_false(self):
        self.assertFalse(has_changes({}, {}))


# ---------------------------------------------------------------------------
# Tests: get_slot_changes
# ---------------------------------------------------------------------------

class TestGetSlotChanges(unittest.TestCase):
    """Tests for diff.get_slot_changes."""

    def _make_snapshots(self, current_slots, previous_slots):
        current = {"frogner": {"2025-08-20": current_slots}}
        previous = {"frogner": {"2025-08-20": previous_slots}}
        return current, previous

    def test_no_changes(self):
        slots = {"17:00-18:00": ["Bane 1"]}
        current, previous = self._make_snapshots(slots, slots)
        new_c, removed_c = get_slot_changes(current, previous, "frogner", "2025-08-20")
        self.assertEqual(new_c, set())
        self.assertEqual(removed_c, set())

    def test_one_new_court(self):
        previous = {"17:00-18:00": ["Bane 1"]}
        current = {"17:00-18:00": ["Bane 1", "Bane 2"]}
        curr_snap, prev_snap = self._make_snapshots(current, previous)
        new_c, removed_c = get_slot_changes(curr_snap, prev_snap, "frogner", "2025-08-20")
        self.assertIn(("17:00-18:00", "Bane 2"), new_c)
        self.assertNotIn(("17:00-18:00", "Bane 1"), new_c)
        self.assertEqual(removed_c, set())

    def test_one_removed_court(self):
        previous = {"17:00-18:00": ["Bane 1", "Bane 2"]}
        current = {"17:00-18:00": ["Bane 1"]}
        curr_snap, prev_snap = self._make_snapshots(current, previous)
        new_c, removed_c = get_slot_changes(curr_snap, prev_snap, "frogner", "2025-08-20")
        self.assertEqual(new_c, set())
        self.assertIn(("17:00-18:00", "Bane 2"), removed_c)

    def test_new_time_slot_entirely(self):
        previous = {"17:00-18:00": ["Bane 1"]}
        current = {"17:00-18:00": ["Bane 1"], "18:00-19:00": ["Bane 3"]}
        curr_snap, prev_snap = self._make_snapshots(current, previous)
        new_c, _ = get_slot_changes(curr_snap, prev_snap, "frogner", "2025-08-20")
        self.assertIn(("18:00-19:00", "Bane 3"), new_c)

    def test_missing_facility_treated_as_empty(self):
        current = {"ota": {"2025-08-20": {"17:00-18:00": ["Bane 1"]}}}
        previous = {}
        new_c, removed_c = get_slot_changes(current, previous, "ota", "2025-08-20")
        # previous is empty so all courts are "new"
        self.assertIn(("17:00-18:00", "Bane 1"), new_c)
        self.assertEqual(removed_c, set())

    def test_missing_date_treated_as_empty(self):
        current = {"frogner": {"2025-08-21": {"17:00-18:00": ["Bane 1"]}}}
        previous = {"frogner": {"2025-08-20": {"17:00-18:00": ["Bane 1"]}}}
        new_c, removed_c = get_slot_changes(current, previous, "frogner", "2025-08-21")
        self.assertIn(("17:00-18:00", "Bane 1"), new_c)


# ---------------------------------------------------------------------------
# Tests: build_new_courts_diff
# ---------------------------------------------------------------------------

class TestBuildNewCourtsDiff(unittest.TestCase):
    """Tests for diff.build_new_courts_diff."""

    def test_empty_previous_all_courts_new(self):
        current = {
            "frogner": {
                "2025-08-20": {"17:00-18:00": ["Bane 1"]},
            }
        }
        diff = build_new_courts_diff(current, {})
        self.assertIn("frogner", diff)
        self.assertIn("2025-08-20", diff["frogner"])
        self.assertIn("17:00-18:00", diff["frogner"]["2025-08-20"])
        self.assertIn("Bane 1", diff["frogner"]["2025-08-20"]["17:00-18:00"])

    def test_no_new_courts_returns_empty(self):
        snapshot = {
            "frogner": {
                "2025-08-20": {"17:00-18:00": ["Bane 1"]},
            }
        }
        diff = build_new_courts_diff(snapshot, snapshot)
        self.assertEqual(diff, {})

    def test_only_new_courts_in_diff(self):
        previous = {
            "frogner": {
                "2025-08-20": {"17:00-18:00": ["Bane 1"]},
            }
        }
        current = {
            "frogner": {
                "2025-08-20": {"17:00-18:00": ["Bane 1", "Bane 2"]},
            }
        }
        diff = build_new_courts_diff(current, previous)
        courts = diff["frogner"]["2025-08-20"]["17:00-18:00"]
        self.assertIn("Bane 2", courts)
        self.assertNotIn("Bane 1", courts)

    def test_multiple_facilities_and_dates(self):
        previous = {
            "frogner": {"2025-08-20": {"17:00-18:00": ["Bane 1"]}},
            "ota":     {"2025-08-20": {"18:00-19:00": ["Bane A"]}},
        }
        current = {
            "frogner": {
                "2025-08-20": {"17:00-18:00": ["Bane 1", "Bane 2"]},
                "2025-08-21": {"09:00-10:00": ["Bane 3"]},
            },
            "ota": {
                "2025-08-20": {"18:00-19:00": ["Bane A"]},  # unchanged
            },
        }
        diff = build_new_courts_diff(current, previous)

        # frogner 2025-08-20: Bane 2 is new
        self.assertIn("Bane 2", diff["frogner"]["2025-08-20"]["17:00-18:00"])
        # frogner 2025-08-21: entirely new date
        self.assertIn("Bane 3", diff["frogner"]["2025-08-21"]["09:00-10:00"])
        # ota unchanged — should not appear in diff
        self.assertNotIn("ota", diff)

    def test_removed_courts_not_in_diff(self):
        """build_new_courts_diff tracks new courts only, not removals."""
        previous = {
            "frogner": {"2025-08-20": {"17:00-18:00": ["Bane 1", "Bane 2"]}},
        }
        current = {
            "frogner": {"2025-08-20": {"17:00-18:00": ["Bane 1"]}},
        }
        diff = build_new_courts_diff(current, previous)
        # No new courts — diff must be empty
        self.assertEqual(diff, {})


if __name__ == "__main__":
    unittest.main()
