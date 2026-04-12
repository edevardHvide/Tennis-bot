"""Tests for golf scraper components."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "lambdas",
        "golf-scraper",
    ),
)

from facilities import facilities, get_golfbox_config, get_facilities_for_sport


# --- Task 1: Facility config tests ---


def test_onsoy_in_facilities():
    assert "onsoy" in facilities
    assert facilities["onsoy"]["matchi_id"] is None
    assert "golf" in facilities["onsoy"]["sports"]


def test_get_golfbox_config_returns_guids():
    config = get_golfbox_config("onsoy")
    assert config is not None
    assert "resource_guid" in config
    assert "club_guid" in config


def test_get_golfbox_config_returns_none_for_matchi():
    config = get_golfbox_config("ota")
    assert config is None


def test_get_facilities_for_sport_golf():
    golf_facilities = get_facilities_for_sport("golf")
    assert "onsoy" in golf_facilities
    assert "ota" not in golf_facilities


# --- Task 2: Parser tests ---

from parser import parse_grid_html

FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "golfbox_onsoy_grid.html"
)


def test_parse_grid_returns_dict():
    with open(FIXTURE_PATH) as f:
        html = f.read()
    result = parse_grid_html(html)
    assert isinstance(result, dict)
    assert len(result) > 0  # Should have at least some slots


def test_parse_grid_time_format():
    with open(FIXTURE_PATH) as f:
        html = f.read()
    result = parse_grid_html(html)
    for time_key in result.keys():
        assert ":" in time_key  # HH:MM format
        parts = time_key.split(":")
        assert len(parts) == 2
        assert 0 <= int(parts[0]) <= 23
        assert 0 <= int(parts[1]) <= 59


def test_parse_grid_slot_format():
    with open(FIXTURE_PATH) as f:
        html = f.read()
    result = parse_grid_html(html)
    for time_key, slots in result.items():
        assert isinstance(slots, list)
        for slot in slots:
            assert "spot" in slot


def test_parse_grid_empty_html():
    result = parse_grid_html("<html><body></body></html>")
    assert result == {}


def test_parse_grid_spots_count():
    """Verify that spots are between 1 and 4."""
    with open(FIXTURE_PATH) as f:
        html = f.read()
    result = parse_grid_html(html)
    for time_key, slots in result.items():
        for slot in slots:
            # Extract number from "N spots (price)" or "N spot (price)"
            num = int(slot.split(" ")[0])
            assert 1 <= num <= 4


# --- Task 3: Scraper client tests ---

from scraper import GolfBoxClient, build_grid_url


def test_build_grid_url():
    url = build_grid_url(
        resource_guid="884D570B-7F66-4ECD-88E2-215E3B386422",
        club_guid="A85DA1E0-B469-4702-BDBC-4E8972EC50A9",
        date_str="2026-04-11",
    )
    assert "Ressource_GUID" in url
    assert "884D570B" in url
    assert "20260411T060000" in url


def test_golfbox_client_login_success(monkeypatch):
    """Test login with mocked HTTP response."""
    import requests

    class MockResponse:
        status_code = 302
        headers = {"Location": "/site/my_golfbox/myFrontPage.asp"}
        cookies = requests.cookies.RequestsCookieJar()

    class MockSession:
        cookies = requests.cookies.RequestsCookieJar()

        def post(self, *args, **kwargs):
            return MockResponse()

        def get(self, *args, **kwargs):
            resp = MockResponse()
            resp.status_code = 200
            resp.text = "<html></html>"
            return resp

    client = GolfBoxClient(username="test", password="test")
    monkeypatch.setattr(client, "_session", MockSession())
    client.login()
    assert client._logged_in is True


# --- Task 4: Diff logic tests ---

from handler import _extract_spots, _compute_new_slots


def test_extract_spots_parses_spot_count():
    assert _extract_spots("3 spots (845,-)") == 3
    assert _extract_spots("1 spot (845,-)") == 1
    assert _extract_spots("4 spots") == 4


def test_extract_spots_returns_zero_on_no_match():
    assert _extract_spots("Tee 5") == 0
    assert _extract_spots("") == 0


def test_compute_new_slots_brand_new_tee_included():
    """A tee time not seen previously should be emitted."""
    prev = {}
    current = {"07:00": ["3 spots (845,-)"]}
    assert _compute_new_slots(prev, current) == {"07:00": ["3 spots (845,-)"]}


def test_compute_new_slots_spots_increased_included():
    """Spots going 2 -> 3 should be emitted (user hadn't seen 3-spot state)."""
    prev = {"07:00": ["2 spots (845,-)"]}
    current = {"07:00": ["3 spots (845,-)"]}
    assert _compute_new_slots(prev, current) == {"07:00": ["3 spots (845,-)"]}


def test_compute_new_slots_spots_decreased_excluded():
    """Spots going 4 -> 3 must NOT emit — user already saw the 4-spot state."""
    prev = {"07:00": ["4 spots (845,-)"]}
    current = {"07:00": ["3 spots (845,-)"]}
    assert _compute_new_slots(prev, current) == {}


def test_compute_new_slots_spots_unchanged_excluded():
    """Same spot count on both sides is not a new state."""
    prev = {"07:00": ["3 spots (845,-)"]}
    current = {"07:00": ["3 spots (845,-)"]}
    assert _compute_new_slots(prev, current) == {}


def test_compute_new_slots_four_to_three_user_scenario():
    """User scenario: minSpots=3, tee degrades 4->3, no notification."""
    prev = {
        "07:00": ["4 spots (845,-)"],
        "07:09": ["4 spots (845,-)"],
    }
    current = {
        "07:00": ["3 spots (845,-)"],  # degraded — excluded
        "07:09": ["4 spots (845,-)"],  # unchanged — excluded
    }
    assert _compute_new_slots(prev, current) == {}


def test_compute_new_slots_two_to_three_user_scenario():
    """User scenario: spots 2->3, should notify (user hadn't seen 3-spot yet)."""
    prev = {"07:00": ["2 spots (845,-)"]}
    current = {"07:00": ["3 spots (845,-)"]}
    assert _compute_new_slots(prev, current) == {"07:00": ["3 spots (845,-)"]}


def test_compute_new_slots_description_without_spots_uses_raw_diff():
    """Fallback to raw set-diff when description lacks a spot count."""
    prev = {"07:00": ["Tee 5"]}
    current = {"07:00": ["Tee 5", "Tee 6"]}
    assert _compute_new_slots(prev, current) == {"07:00": ["Tee 6"]}


def test_golfbox_client_login_failure(monkeypatch):
    """Test login failure returns False."""
    import requests

    class MockResponse:
        status_code = 200
        headers = {}
        cookies = requests.cookies.RequestsCookieJar()

    class MockSession:
        cookies = requests.cookies.RequestsCookieJar()

        def post(self, *args, **kwargs):
            return MockResponse()

    client = GolfBoxClient(username="test", password="wrong")
    monkeypatch.setattr(client, "_session", MockSession())
    result = client.login()
    assert result is False
    assert client._logged_in is False
