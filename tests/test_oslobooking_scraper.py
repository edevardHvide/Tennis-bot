"""Tests for the Oslo kommune booking platform scraper."""
import json
import os
import sys
from unittest.mock import patch, MagicMock

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "lambdas",
        "scraper",
    ),
)

from facilities import facilities, get_oslobooking_config, get_facilities_for_sport
from oslobooking_scraper import (
    fetch_available_slots,
    parse_slots_from_json,
    MAX_RETRIES,
)


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name: str):
    with open(os.path.join(FIXTURE_DIR, name)) as f:
        return json.load(f)


# --- facilities config ---------------------------------------------------


def test_rivertz_in_facilities():
    assert "rivertz" in facilities
    assert facilities["rivertz"]["matchi_id"] is None
    assert "padel" in facilities["rivertz"]["sports"]


def test_get_oslobooking_config_returns_asset_id():
    config = get_oslobooking_config("rivertz")
    assert config is not None
    assert config["bookable_asset_id"] == "7ad1690a-e5d3-4ec2-885b-54c27d3d2741"
    assert config["days_ahead"] == 7


def test_get_oslobooking_config_returns_none_for_matchi():
    assert get_oslobooking_config("ota") is None


def test_get_oslobooking_config_returns_none_for_missing():
    assert get_oslobooking_config("does-not-exist") is None


def test_rivertz_included_in_padel_facilities():
    padel_facilities = get_facilities_for_sport("padel")
    assert "rivertz" in padel_facilities


# --- parser --------------------------------------------------------------


def test_parse_available_fixture_hourly_only():
    payload = _load_fixture("oslobooking_rivertz_available.json")
    result = parse_slots_from_json(payload, court_name="Padelbane")
    # Fixture has 09:00, 09:30, 10:00 — only on-the-hour starts survive.
    assert result == {
        "09:00-10:00": ["Padelbane"],
        "10:00-11:00": ["Padelbane"],
    }


def test_parse_empty_fixture_returns_empty_dict():
    payload = _load_fixture("oslobooking_rivertz_empty.json")
    assert parse_slots_from_json(payload) == {}


def test_parse_non_list_payload_returns_empty():
    assert parse_slots_from_json({"error": "boom"}) == {}
    assert parse_slots_from_json(None) == {}


def test_parse_skips_entries_missing_fields():
    payload = [
        {"start": "09:00:00", "end": "10:00:00", "id": None},
        {"start": "", "end": "11:00:00", "id": None},
        {"id": None},
    ]
    result = parse_slots_from_json(payload, court_name="Court")
    assert result == {"09:00-10:00": ["Court"]}


def test_parse_uses_custom_court_name():
    payload = [{"start": "14:00:00", "end": "15:00:00", "id": None}]
    result = parse_slots_from_json(payload, court_name="Rivertz padel")
    assert result == {"14:00-15:00": ["Rivertz padel"]}


# --- fetch (mocked network) ---------------------------------------------


def _mock_response(status=200, json_payload=None):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_payload if json_payload is not None else []
    return resp


def test_fetch_returns_parsed_slots():
    payload = _load_fixture("oslobooking_rivertz_available.json")
    with patch("oslobooking_scraper.requests.get",
               return_value=_mock_response(json_payload=payload)) as mock_get:
        result = fetch_available_slots("abc-uuid", "2026-04-14")

    assert result == {
        "09:00-10:00": ["Padelbane"],
        "10:00-11:00": ["Padelbane"],
    }
    # Verify query params sent to the API.
    kwargs = mock_get.call_args.kwargs
    assert kwargs["params"]["bookableAssetId"] == "abc-uuid"
    assert kwargs["params"]["date"] == "2026-04-14"
    assert kwargs["params"]["duration"] == "PT1H"


def test_fetch_retries_then_succeeds():
    good = _mock_response(json_payload=[])
    with patch("oslobooking_scraper.requests.get",
               side_effect=[requests.ConnectionError("boom"), good]), \
         patch("oslobooking_scraper.time.sleep"):
        result = fetch_available_slots("abc", "2026-04-14")
    assert result == {}


def test_fetch_raises_after_max_retries():
    with patch("oslobooking_scraper.requests.get",
               side_effect=requests.ConnectionError("boom")), \
         patch("oslobooking_scraper.time.sleep"):
        with pytest.raises(requests.ConnectionError):
            fetch_available_slots("abc", "2026-04-14")


@pytest.mark.integration
def test_live_rivertz_availability():
    """Hit the real Oslo kommune API — skipped unless integration tests enabled."""
    result = fetch_available_slots(
        "7ad1690a-e5d3-4ec2-885b-54c27d3d2741",
        # The API returns [] for dates outside the 7-day booking window,
        # so use tomorrow to maximise the chance of a non-empty response
        # without being flaky on dates that happen to be fully booked.
        __import__("datetime").date.today().isoformat(),
    )
    assert isinstance(result, dict)
    for label, courts in result.items():
        assert "-" in label
        assert courts == ["Padelbane"]
