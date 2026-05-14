"""
Unit tests for the shared weather module and email weather integration.

No AWS calls — tests use stub objects for the DynamoDB Table.
"""

from __future__ import annotations

import os
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import weather  # noqa: E402

import importlib.util


def _load_email_builder(lambda_name: str):
    """Load email_builder.py from a specific Lambda dir under a unique module name.

    Avoids the notif/newsletter namespace collision (both files share the
    same module name).
    """
    path = os.path.join(REPO_ROOT, "lambdas", lambda_name, "email_builder.py")
    spec = importlib.util.spec_from_file_location(f"{lambda_name}_email_builder", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# symbol_to_emoji
# ---------------------------------------------------------------------------


def test_symbol_to_emoji_strips_day_night_suffix():
    assert weather.symbol_to_emoji("clearsky_day") == "☀️"
    assert weather.symbol_to_emoji("clearsky_night") == "☀️"
    assert weather.symbol_to_emoji("partlycloudy_polartwilight") == "⛅"


def test_symbol_to_emoji_unknown_falls_back():
    assert weather.symbol_to_emoji("totally_made_up") == "🌡️"
    assert weather.symbol_to_emoji(None) == "🌡️"
    assert weather.symbol_to_emoji("") == "🌡️"


def test_symbol_to_emoji_rain_family():
    assert weather.symbol_to_emoji("rain") == "🌧️"
    assert weather.symbol_to_emoji("lightrain") == "🌦️"
    assert weather.symbol_to_emoji("heavyrainandthunder") == "⛈️"


# ---------------------------------------------------------------------------
# expand_to_hourly_buckets
# ---------------------------------------------------------------------------


def _entry(time_iso: str, temp: float, symbol: str, key: str = "next_1_hours") -> dict:
    return {
        "time": time_iso,
        "data": {
            "instant": {"details": {"air_temperature": temp}},
            key: {"summary": {"symbol_code": symbol}},
        },
    }


def test_expand_propagates_between_entries():
    """A 6-hour summary should fill all 6 hourly buckets until the next entry."""
    series = [
        _entry("2026-05-14T12:00:00Z", 14.0, "clearsky_day", key="next_6_hours"),
        _entry("2026-05-14T18:00:00Z", 11.0, "partlycloudy_day", key="next_6_hours"),
    ]
    buckets = weather.expand_to_hourly_buckets(series, horizon_days=20)
    # First entry at 12:00 UTC = 14:00 Oslo (summer); should fill 14..19 Oslo (6 hours)
    # plus second entry at 18:00 UTC = 20:00 Oslo for one bucket
    hours = [b["hour_iso"][-5:] for b in buckets]
    assert "14:00" in hours
    assert "15:00" in hours
    assert "19:00" in hours
    assert "20:00" in hours


def test_expand_respects_horizon():
    far = _entry("2099-01-01T00:00:00Z", 0.0, "cloudy")
    near = _entry("2026-05-14T12:00:00Z", 5.0, "rain")
    buckets = weather.expand_to_hourly_buckets([near, far], horizon_days=11)
    # The far-future entry should be cut by horizon — only near survives
    assert all("2099" not in b["hour_iso"] for b in buckets)


def test_expand_drops_entries_without_symbol_or_temp():
    series = [
        {
            "time": "2026-05-14T12:00:00Z",
            "data": {"instant": {"details": {}}},
        },
    ]
    assert weather.expand_to_hourly_buckets(series, horizon_days=2) == []


# ---------------------------------------------------------------------------
# make_weather_lookup
# ---------------------------------------------------------------------------


class _StubTable:
    def __init__(self, items: dict):
        self.items = items
        self.calls = 0

    def get_item(self, Key):
        self.calls += 1
        item = self.items.get((Key["region"], Key["hourIso"]))
        return {"Item": item} if item else {}


def _region_resolver(facility):
    return {"frogner": "oslo", "bergentennisarena": "bergen"}.get(facility)


def test_lookup_returns_weather_for_known_slot():
    table = _StubTable({
        ("oslo", "2026-05-14T17:00"): {
            "region": "oslo", "hourIso": "2026-05-14T17:00",
            "symbol": "clearsky_day", "temp": 14.2,
        },
    })
    lookup = weather.make_weather_lookup(table, _region_resolver)
    out = lookup("frogner", "2026-05-14", "17:00-18:00")
    assert out is not None
    assert out["temp"] == 14.2
    assert out["symbol"] == "clearsky_day"
    assert out["emoji"] == "☀️"


def test_lookup_returns_none_for_missing_slot():
    table = _StubTable({})
    lookup = weather.make_weather_lookup(table, _region_resolver)
    assert lookup("frogner", "2099-01-01", "17:00-18:00") is None


def test_lookup_returns_none_for_unmapped_facility():
    table = _StubTable({})
    lookup = weather.make_weather_lookup(table, _region_resolver)
    assert lookup("harvard", "2026-05-14", "17:00-18:00") is None


def test_lookup_memoises_region_and_hour():
    table = _StubTable({})
    lookup = weather.make_weather_lookup(table, _region_resolver)
    lookup("frogner", "2026-05-14", "17:00-18:00")
    lookup("frogner", "2026-05-14", "17:00-18:00")
    lookup("frogner", "2026-05-14", "17:00-18:00")
    assert table.calls == 1, "expected memoised lookups to hit the table once"


def test_lookup_swallows_errors():
    class _Broken:
        def get_item(self, Key):
            raise RuntimeError("dynamodb is down")
    lookup = weather.make_weather_lookup(_Broken(), _region_resolver)
    # Should NOT raise — weather is decorative.
    assert lookup("frogner", "2026-05-14", "17:00-18:00") is None


# ---------------------------------------------------------------------------
# Email-builder integration
# ---------------------------------------------------------------------------


def test_notification_email_renders_weather_inline():
    notif_builder = _load_email_builder("notifications")

    matches = [{
        "userId": "test@example.com",
        "preferenceId": "p1",
        "facilityId": "frogner",
        "sport": "tennis",
        "date": "2026-05-14",
        "courts": [{"time_slot": "17:00-18:00", "court_name": "Court 1"}],
    }]

    def lookup(fk, date, ts):
        return {"temp": 14.0, "symbol": "clearsky_day", "emoji": "☀️"}

    email = notif_builder.build_notification_email("test@example.com", matches, weather_lookup=lookup)
    assert "☀️" in email["html_body"]
    assert "14°C" in email["html_body"]
    assert "☀️" in email["text_body"]


def test_notification_email_works_without_weather():
    notif_builder = _load_email_builder("notifications")
    matches = [{
        "userId": "test@example.com",
        "preferenceId": "p1",
        "facilityId": "frogner",
        "sport": "tennis",
        "date": "2026-05-14",
        "courts": [{"time_slot": "17:00-18:00", "court_name": "Court 1"}],
    }]
    email = notif_builder.build_notification_email("test@example.com", matches)
    assert "Court 1" in email["html_body"]
    assert "17:00-18:00" in email["html_body"]
    # Without lookup, no temperature should appear.
    assert "°C" not in email["html_body"]


def test_notification_email_renders_day_of_week():
    """2026-05-14 is a Thursday — should render as 'Thursday, 14 May'."""
    notif_builder = _load_email_builder("notifications")
    matches = [{
        "userId": "test@example.com",
        "preferenceId": "p1",
        "facilityId": "frogner",
        "sport": "tennis",
        "date": "2026-05-14",
        "courts": [{"time_slot": "17:00-18:00", "court_name": "Court 1"}],
    }]
    email = notif_builder.build_notification_email("test@example.com", matches)
    assert "Thursday" in email["html_body"]
    assert "14 May" in email["html_body"]
    assert "Thursday" in email["text_body"]


def test_newsletter_email_renders_weather_inline():
    newsletter_builder = _load_email_builder("newsletter")
    matches = [{
        "userId": "test@example.com",
        "preferenceId": "p1",
        "facilityId": "frogner",
        "sport": "tennis",
        "date": "2026-05-18",
        "courts": [{"time_slot": "17:00-18:00", "court_name": "Court 1"}],
    }]

    def lookup(fk, date, ts):
        assert fk == "frogner", "newsletter should pass bare facility key"
        return {"temp": 8.0, "symbol": "rain", "emoji": "🌧️"}

    email = newsletter_builder.build_newsletter_email(
        "test@example.com", matches, "2026-05-18", "2026-05-24",
        weather_lookup=lookup,
    )
    assert "🌧️" in email["html_body"]
    assert "8°C" in email["html_body"]
