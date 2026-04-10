"""
Tests for lambdas/harvard-scraper/scraper.py and handler.py.
All tests skipped until implementation exists (Plan 03 removes @skip).
"""
import sys
import os
import json
import pathlib
import unittest
import pytest
from unittest.mock import MagicMock, patch

HARVARD_SCRAPER_DIR = os.path.join(os.path.dirname(__file__), "..", "lambdas", "harvard-scraper")
FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"

# Use importlib to load harvard-scraper modules by absolute path, avoiding
# sys.path collisions with lambdas/notifications/handler.py when running
# both test files together (pytest collects in alphabetical order).
import importlib.util as _ilu

def _load_mod(name):
    """Import a module from lambdas/harvard-scraper/ by file path."""
    fp = os.path.join(os.path.abspath(HARVARD_SCRAPER_DIR), f"{name}.py")
    if not os.path.isfile(fp):
        return None
    # Ensure harvard-scraper dir is on path for sibling imports (e.g. handler imports scraper)
    _abs = os.path.abspath(HARVARD_SCRAPER_DIR)
    if _abs not in sys.path:
        sys.path.insert(0, _abs)
    # Force fresh load regardless of what's cached
    spec = _ilu.spec_from_file_location(name, fp, submodule_search_locations=[])
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod  # register BEFORE exec so sibling imports resolve
    spec.loader.exec_module(mod)
    return mod

if os.path.isdir(HARVARD_SCRAPER_DIR):
    # Pre-load to ensure correct modules are cached
    _load_mod("diff")
    _load_mod("scraper")
    _load_mod("handler")


class TestFetchLessonInstances(unittest.TestCase):
    """Tests for fetch_lesson_instances() — SCRP-01."""

    def test_fetches_correct_url_and_params(self):
        """Assert requests.Session.get called with the correct URL and params."""
        from scraper import fetch_lesson_instances

        with patch("requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = (FIXTURES_DIR / "harvard_available.html").read_text()
            mock_session.get.return_value = mock_resp

            fetch_lesson_instances("test-id")

            mock_session.get.assert_called_once()
            call_kwargs = mock_session.get.call_args
            args, kwargs = call_kwargs
            url = args[0] if args else kwargs.get("url", "")
            params = kwargs.get("params", {})
            self.assertIn("GetProgramInstances", url)
            self.assertIn("membership.gocrimson.com", url)
            self.assertEqual(params.get("programID"), "test-id")

    def test_raises_on_http_error(self):
        """Mock 500 response — assert raises requests.HTTPError from raise_for_status()."""
        import requests
        from scraper import fetch_lesson_instances

        with patch("requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_resp = MagicMock()
            mock_resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
            mock_session.get.return_value = mock_resp

            with self.assertRaises(requests.HTTPError):
                fetch_lesson_instances("test-id")

    def test_returns_list_of_dicts(self):
        """Mock 200 with available fixture — assert result is a list."""
        from scraper import fetch_lesson_instances

        with patch("requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = (FIXTURES_DIR / "harvard_available.html").read_text()
            mock_resp.raise_for_status.return_value = None
            mock_session.get.return_value = mock_resp

            result = fetch_lesson_instances("test-id")

            self.assertIsInstance(result, list)


class TestParseHarvardAvailability(unittest.TestCase):
    """Tests for parse_harvard_availability() — SCRP-02."""

    def test_available_lesson_extracted(self):
        """Available fixture returns a list with the correct date, time_slot, location."""
        from scraper import parse_harvard_availability

        html = (FIXTURES_DIR / "harvard_available.html").read_text()
        result = parse_harvard_availability(html)

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        lesson = result[0]
        self.assertIn("date", lesson)
        self.assertIn("time_slot", lesson)
        self.assertIn("location", lesson)
        self.assertEqual(lesson["date"], "2026-05-01")
        self.assertEqual(lesson["time_slot"], "09:00-10:00")
        self.assertEqual(lesson["location"], "Indoor Tennis Court 6")

    def test_html_text_overrides_json_math(self):
        """Unavailable fixture: .spots-tag 'No spots available' — result must be empty list."""
        from scraper import parse_harvard_availability

        html = (FIXTURES_DIR / "harvard_unavailable.html").read_text()
        result = parse_harvard_availability(html)

        self.assertEqual(result, [])

    def test_missing_apptinfo_raises(self):
        """HTML without #ApptInfo input raises ValueError."""
        from scraper import parse_harvard_availability

        with self.assertRaises(ValueError):
            parse_harvard_availability("<html><body></body></html>")

    def test_past_lessons_excluded(self):
        """Past-dated fixture: StartDate in the past — result must be empty list."""
        from scraper import parse_harvard_availability

        html = (FIXTURES_DIR / "harvard_past_dated.html").read_text()
        result = parse_harvard_availability(html)

        self.assertEqual(result, [])


class TestSnapshotStorage(unittest.TestCase):
    """Tests for load_snapshot() and save_snapshot() — SCRP-03."""

    def test_save_snapshot_uses_harvard_composite_key(self):
        """save_snapshot calls table.put_item with facilityId='harvard#tennis'."""
        from handler import save_snapshot

        mock_table = MagicMock()
        save_snapshot(
            mock_table,
            "harvard#tennis",
            "2026-05-01",
            {"09:00-10:00": ["Indoor Tennis Court 6"]},
        )

        mock_table.put_item.assert_called_once()
        call_kwargs = mock_table.put_item.call_args
        item = call_kwargs[1]["Item"] if call_kwargs[1] else call_kwargs[0][0]["Item"]
        self.assertEqual(item["facilityId"], "harvard#tennis")
        self.assertEqual(item["date"], "2026-05-01")

    def test_load_snapshot_returns_empty_on_miss(self):
        """load_snapshot returns {} when DynamoDB get_item has no Item key."""
        from handler import load_snapshot

        mock_table = MagicMock()
        mock_table.get_item.return_value = {}

        result = load_snapshot(mock_table, "harvard#tennis", "2026-05-01")

        self.assertEqual(result, {})


class TestColdStart(unittest.TestCase):
    """Tests for the cold-start seeding guard — SCRP-05."""

    def test_no_notification_on_first_run(self):
        """On first run (empty DynamoDB), notifications Lambda must NOT be invoked."""
        from handler import lambda_handler

        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No previous snapshot

        mock_lambda_client = MagicMock()

        with patch("handler.fetch_lesson_instances") as mock_fetch, \
             patch("handler._get_dynamodb") as mock_dynamo, \
             patch("handler._get_lambda_client") as mock_get_lc:

            mock_fetch.return_value = [
                {
                    "date": "2026-05-01",
                    "time_slot": "09:00-10:00",
                    "location": "Indoor Tennis Court 6",
                }
            ]
            mock_dynamo.return_value.Table.return_value = mock_table
            mock_get_lc.return_value = mock_lambda_client

            lambda_handler({"source": "aws.events"}, None)

            mock_lambda_client.invoke.assert_not_called()

    def test_notification_on_second_run_new_slot(self):
        """Second run with a new slot: notifications Lambda MUST be invoked with harvard#tennis."""
        from handler import lambda_handler

        # First call: empty snapshot (baseline). Second: new slot appears.
        slot_data = json.dumps({"09:00-10:00": ["Indoor Tennis Court 6"]})
        call_count = {"n": 0}

        def mock_get_item(Key):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return {}  # First run: no previous snapshot
            return {"Item": {"facilityId": "harvard#tennis", "date": "2026-05-01", "slots": "{}"}}

        mock_table = MagicMock()
        mock_table.get_item.side_effect = mock_get_item
        mock_lambda_client = MagicMock()

        with patch("handler.fetch_lesson_instances") as mock_fetch, \
             patch("handler._get_dynamodb") as mock_dynamo, \
             patch("handler._get_lambda_client") as mock_get_lc:

            mock_fetch.return_value = [
                {
                    "date": "2026-05-01",
                    "time_slot": "09:00-10:00",
                    "location": "Indoor Tennis Court 6",
                }
            ]
            mock_dynamo.return_value.Table.return_value = mock_table
            mock_get_lc.return_value = mock_lambda_client

            # Simulate second run: previous snapshot shows empty slots
            mock_table.get_item.return_value = {
                "Item": {"facilityId": "harvard#tennis", "date": "2026-05-01", "slots": "{}"}
            }

            lambda_handler({"source": "aws.events"}, None)

            mock_lambda_client.invoke.assert_called_once()
            payload_str = mock_lambda_client.invoke.call_args[1]["Payload"]
            payload = json.loads(payload_str)
            self.assertIn("diff", payload)
            self.assertIn("harvard#tennis", str(payload["diff"]))


if __name__ == "__main__":
    unittest.main()
