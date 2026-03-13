"""
Unit tests for the Notification Engine Lambda (multi-sport).

Uses moto to mock DynamoDB and SES — no real AWS calls are made.

Run with:
    pip install pytest moto[dynamodb,ses] boto3
    pytest tests/test_notifications.py -v
"""

import hashlib
import importlib
import json
import os
import sys
import time

import boto3
import pytest
from moto import mock_aws

# ---------------------------------------------------------------------------
# Ensure the handler module can be imported regardless of working directory
# ---------------------------------------------------------------------------

HANDLER_DIR = os.path.join(os.path.dirname(__file__), "..", "lambdas", "notifications")
if HANDLER_DIR not in sys.path:
    sys.path.insert(0, HANDLER_DIR)

# Ensure repo root is on sys.path so ``from facilities import ...`` works
REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, os.path.abspath(REPO_ROOT))


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGION = "eu-north-1"
NOTIFICATIONS_TABLE = "tennis-notifications"
PREFS_TABLE = "tennis-preferences"
USERS_TABLE = "tennis-users"
SES_FROM_EMAIL = "bot@tennis.test"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    """Set environment variables before each test."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_REGION", REGION)
    monkeypatch.setenv("NOTIFICATIONS_TABLE", NOTIFICATIONS_TABLE)
    monkeypatch.setenv("PREFS_TABLE", PREFS_TABLE)
    monkeypatch.setenv("USERS_TABLE", USERS_TABLE)
    monkeypatch.setenv("SES_FROM_EMAIL", SES_FROM_EMAIL)


@pytest.fixture()
def dynamo():
    """Spin up moto-mocked DynamoDB with all three tables, verify SES, yield resource."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name=REGION)

        # tennis-users
        client.create_table(
            TableName=USERS_TABLE,
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # tennis-preferences (PK: userId, SK: preferenceId)
        client.create_table(
            TableName=PREFS_TABLE,
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "preferenceId", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "preferenceId", "KeyType": "RANGE"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # tennis-notifications (PK: notificationId)
        client.create_table(
            TableName=NOTIFICATIONS_TABLE,
            AttributeDefinitions=[
                {"AttributeName": "notificationId", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "notificationId", "KeyType": "HASH"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Verify SES sender
        ses = boto3.client("ses", region_name=REGION)
        ses.verify_email_identity(EmailAddress=SES_FROM_EMAIL)

        # Reload handler so it picks up mocked resources
        import handler as h

        importlib.reload(h)
        h._dynamodb_resource = None
        h._ses_client = None

        yield boto3.resource("dynamodb", region_name=REGION)

        h._dynamodb_resource = None
        h._ses_client = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _add_user(dynamo_resource, user_id: str, name: str = "Test User") -> None:
    table = dynamo_resource.Table(USERS_TABLE)
    table.put_item(Item={"userId": user_id, "name": name})


def _add_preference(
    dynamo_resource,
    user_id: str,
    preference_id: str,
    facility_id: str = "frogner",
    dates: list[str] | None = None,
    time_from: str = "17:00",
    time_to: str = "22:00",
    sport: str = "tennis",
    court_type: str | None = None,
) -> None:
    table = dynamo_resource.Table(PREFS_TABLE)
    item = {
        "userId": user_id,
        "preferenceId": preference_id,
        "facilityId": facility_id,
        "dates": dates or ["monday"],  # 2026-06-01 is a Monday
        "timeFrom": time_from,
        "timeTo": time_to,
        "sport": sport,
    }
    if court_type:
        item["courtType"] = court_type
    table.put_item(Item=item)


def _sample_diff(
    facility: str = "frogner",
    sport: str = "tennis",
    date: str = "2026-06-01",
    time_slot: str = "17:00-18:00",
    courts: list[str] | None = None,
) -> dict:
    composite_key = f"{facility}#{sport}"
    return {
        composite_key: {
            date: {
                time_slot: courts or ["Court 1"],
            },
        },
    }


def _dedup_key(user_id, facility_id, sport, date, time_slot, court_name):
    raw = f"{user_id}|{facility_id}|{sport}|{date}|{time_slot}|{court_name}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ===========================================================================
# Matcher tests
# ===========================================================================


class TestMatcher:
    def test_facility_match(self):
        from matcher import match_preferences

        diff = _sample_diff()  # date=2026-06-01 is Monday
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                "sport": "tennis",
                "dates": ["monday"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 1
        assert matches[0]["facilityId"] == "frogner"
        assert matches[0]["sport"] == "tennis"

    def test_no_match_wrong_facility(self):
        from matcher import match_preferences

        diff = _sample_diff(facility="ota")
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                "sport": "tennis",
                "dates": ["monday"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 0

    def test_no_match_wrong_sport(self):
        """Tennis preference should not match padel diff."""
        from matcher import match_preferences

        diff = _sample_diff(facility="ota", sport="padel")
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "ota",
                "sport": "tennis",
                "dates": ["monday"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 0

    def test_padel_sport_match(self):
        """Padel preference should match padel diff."""
        from matcher import match_preferences

        diff = _sample_diff(facility="ota", sport="padel")  # 2026-06-01 = Monday
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "ota",
                "sport": "padel",
                "dates": ["monday"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 1
        assert matches[0]["sport"] == "padel"

    def test_sport_defaults_to_tennis(self):
        """Preference without sport field defaults to tennis."""
        from matcher import match_preferences

        diff = _sample_diff(facility="frogner", sport="tennis")
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                # no sport field — should default to tennis
                "dates": ["monday"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 1
        assert matches[0]["sport"] == "tennis"

    def test_day_name_match(self):
        """Preference with matching day name should match diff date."""
        from matcher import match_preferences

        # 2026-06-01 is Monday, 2026-06-02 is Tuesday
        diff = _sample_diff(date="2026-06-01")
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                "sport": "tennis",
                "dates": ["monday", "tuesday"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 1
        assert matches[0]["date"] == "2026-06-01"

    def test_no_match_wrong_day(self):
        """Diff on Monday should not match a preference for Tuesday."""
        from matcher import match_preferences

        diff = _sample_diff(date="2026-06-01")  # Monday
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                "sport": "tennis",
                "dates": ["tuesday"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 0

    def test_time_window_match(self):
        from matcher import match_preferences

        diff = _sample_diff(time_slot="18:00-19:00")
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                "sport": "tennis",
                "dates": ["monday"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 1

    def test_no_match_outside_time_window(self):
        from matcher import match_preferences

        diff = _sample_diff(time_slot="08:00-09:00")
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                "sport": "tennis",
                "dates": ["monday"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 0

    def test_time_window_boundary_start_inclusive(self):
        """Slot start == timeFrom should match."""
        from matcher import match_preferences

        diff = _sample_diff(time_slot="17:00-18:00")
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                "sport": "tennis",
                "dates": ["monday"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 1

    def test_time_window_boundary_end_exclusive(self):
        """Slot start == timeTo should NOT match (exclusive)."""
        from matcher import match_preferences

        diff = _sample_diff(time_slot="22:00-23:00")
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                "sport": "tennis",
                "dates": ["monday"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 0

    def test_empty_diff_returns_empty(self):
        from matcher import match_preferences

        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                "sport": "tennis",
                "dates": ["monday"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences({}, prefs)
        assert matches == []

    def test_no_preferences_returns_empty(self):
        from matcher import match_preferences

        diff = _sample_diff()
        matches = match_preferences(diff, [])
        assert matches == []

    def test_multiple_courts_in_match(self):
        from matcher import match_preferences

        diff = _sample_diff(courts=["Court 1", "Court 2", "Court 3"])
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                "sport": "tennis",
                "dates": ["monday"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 1
        assert len(matches[0]["courts"]) == 3

    # -- Court type filtering tests --

    def test_court_type_single_filters_correctly(self):
        """courtType 'single' should only match courts with 'single' in the name."""
        from matcher import match_preferences

        diff = _sample_diff(
            facility="ota", sport="padel",
            courts=["Padel Single 1", "Padel Double 2", "Padel Court 3"],
        )
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "ota",
                "sport": "padel",
                "courtType": "single",
                "dates": ["monday"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 1
        assert len(matches[0]["courts"]) == 1
        assert matches[0]["courts"][0]["court_name"] == "Padel Single 1"

    def test_court_type_double_filters_correctly(self):
        """courtType 'double' should exclude courts with 'single' in the name."""
        from matcher import match_preferences

        diff = _sample_diff(
            facility="ota", sport="padel",
            courts=["Padel Single 1", "Padel Double 2", "Padel Court 3"],
        )
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "ota",
                "sport": "padel",
                "courtType": "double",
                "dates": ["monday"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 1
        assert len(matches[0]["courts"]) == 2
        court_names = [c["court_name"] for c in matches[0]["courts"]]
        assert "Padel Double 2" in court_names
        assert "Padel Court 3" in court_names

    def test_no_court_type_matches_all(self):
        """No courtType set should match all courts."""
        from matcher import match_preferences

        diff = _sample_diff(
            facility="ota", sport="padel",
            courts=["Padel Single 1", "Padel Double 2", "Padel Court 3"],
        )
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "ota",
                "sport": "padel",
                "dates": ["monday"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 1
        assert len(matches[0]["courts"]) == 3

    def test_court_type_single_case_insensitive(self):
        """Court type filtering should be case-insensitive."""
        from matcher import match_preferences

        diff = _sample_diff(
            facility="ota", sport="padel",
            courts=["Padel SINGLE 1", "Padel Double 2"],
        )
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "ota",
                "sport": "padel",
                "courtType": "single",
                "dates": ["monday"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 1
        assert matches[0]["courts"][0]["court_name"] == "Padel SINGLE 1"

    def test_past_slots_are_filtered_out(self):
        """Slots in the past (Oslo time) should not match."""
        from matcher import match_preferences

        # Use yesterday's date — all slots should be filtered
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        yesterday = (
            datetime.now(ZoneInfo("Europe/Oslo")) - timedelta(days=1)
        ).strftime("%Y-%m-%d")
        # yesterday was some day-of-week; use that day name in prefs
        day_name = datetime.strptime(yesterday, "%Y-%m-%d").strftime("%A").lower()

        diff = _sample_diff(date=yesterday, time_slot="20:00-21:00")
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                "sport": "tennis",
                "dates": [day_name],
                "timeFrom": "00:00",
                "timeTo": "23:59",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 0

    def test_future_slots_are_not_filtered(self):
        """Slots in the future should still match normally."""
        from matcher import match_preferences

        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        tomorrow = (
            datetime.now(ZoneInfo("Europe/Oslo")) + timedelta(days=1)
        ).strftime("%Y-%m-%d")
        day_name = datetime.strptime(tomorrow, "%Y-%m-%d").strftime("%A").lower()

        diff = _sample_diff(date=tomorrow, time_slot="17:00-18:00")
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                "sport": "tennis",
                "dates": [day_name],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 1


# ===========================================================================
# Dedup tests
# ===========================================================================


class TestDedup:
    def test_new_courts_pass_through(self, dynamo):
        from dedup import filter_already_notified

        table = dynamo.Table(NOTIFICATIONS_TABLE)
        matches = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                "sport": "tennis",
                "date": "2026-06-01",
                "courts": [{"time_slot": "17:00-18:00", "court_name": "Court 1"}],
            }
        ]
        result = filter_already_notified(matches, table)
        assert len(result) == 1
        assert len(result[0]["courts"]) == 1

    def test_already_notified_court_filtered(self, dynamo):
        from dedup import filter_already_notified

        table = dynamo.Table(NOTIFICATIONS_TABLE)
        key = _dedup_key("alice@test.com", "frogner", "tennis", "2026-06-01", "17:00-18:00", "Court 1")
        table.put_item(
            Item={
                "notificationId": key,
                "userId": "alice@test.com",
                "ttl": int(time.time()) + 86400,
            }
        )

        matches = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                "sport": "tennis",
                "date": "2026-06-01",
                "courts": [{"time_slot": "17:00-18:00", "court_name": "Court 1"}],
            }
        ]
        result = filter_already_notified(matches, table)
        assert len(result) == 0

    def test_different_sport_not_deduped(self, dynamo):
        """Same court at same facility but different sport should not be deduped."""
        from dedup import filter_already_notified

        table = dynamo.Table(NOTIFICATIONS_TABLE)
        # Record a tennis notification
        key = _dedup_key("alice@test.com", "ota", "tennis", "2026-06-01", "17:00-18:00", "Court 1")
        table.put_item(
            Item={
                "notificationId": key,
                "userId": "alice@test.com",
                "ttl": int(time.time()) + 86400,
            }
        )

        # Now check padel for the same court — should pass through
        matches = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "ota",
                "sport": "padel",
                "date": "2026-06-01",
                "courts": [{"time_slot": "17:00-18:00", "court_name": "Court 1"}],
            }
        ]
        result = filter_already_notified(matches, table)
        assert len(result) == 1

    def test_record_notifications_writes_items(self, dynamo):
        from dedup import record_notifications

        table = dynamo.Table(NOTIFICATIONS_TABLE)
        matches = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                "sport": "tennis",
                "date": "2026-06-01",
                "courts": [
                    {"time_slot": "17:00-18:00", "court_name": "Court 1"},
                    {"time_slot": "18:00-19:00", "court_name": "Court 2"},
                ],
            }
        ]
        count = record_notifications(matches, table)
        assert count == 2

        # Verify items exist
        key1 = _dedup_key("alice@test.com", "frogner", "tennis", "2026-06-01", "17:00-18:00", "Court 1")
        resp = table.get_item(Key={"notificationId": key1})
        assert "Item" in resp
        assert "ttl" in resp["Item"]

    def test_sport_defaults_to_tennis_in_dedup(self, dynamo):
        """Match dict without sport field should default to tennis for dedup."""
        from dedup import filter_already_notified

        table = dynamo.Table(NOTIFICATIONS_TABLE)
        # Record a tennis notification
        key = _dedup_key("alice@test.com", "frogner", "tennis", "2026-06-01", "17:00-18:00", "Court 1")
        table.put_item(
            Item={
                "notificationId": key,
                "userId": "alice@test.com",
                "ttl": int(time.time()) + 86400,
            }
        )

        # Match without sport field — should default to tennis and be deduped
        matches = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                "date": "2026-06-01",
                "courts": [{"time_slot": "17:00-18:00", "court_name": "Court 1"}],
            }
        ]
        result = filter_already_notified(matches, table)
        assert len(result) == 0


# ===========================================================================
# Email builder tests
# ===========================================================================


class TestEmailBuilder:
    def test_subject_single_court(self):
        from email_builder import build_notification_email

        matches = [
            {
                "facilityId": "frogner",
                "date": "2026-06-01",
                "courts": [{"time_slot": "17:00-18:00", "court_name": "Court 1"}],
            }
        ]
        email = build_notification_email("alice@test.com", matches)
        assert "1 new court" in email["subject"]
        assert "courts" not in email["subject"]  # singular

    def test_subject_plural_courts(self):
        from email_builder import build_notification_email

        matches = [
            {
                "facilityId": "frogner",
                "date": "2026-06-01",
                "courts": [
                    {"time_slot": "17:00-18:00", "court_name": "Court 1"},
                    {"time_slot": "18:00-19:00", "court_name": "Court 2"},
                ],
            }
        ]
        email = build_notification_email("alice@test.com", matches)
        assert "2 new courts" in email["subject"]

    def test_subject_branding(self):
        """Subject should use 'Availability Monitor' branding."""
        from email_builder import build_notification_email

        matches = [
            {
                "facilityId": "frogner",
                "date": "2026-06-01",
                "courts": [{"time_slot": "17:00-18:00", "court_name": "Court 1"}],
            }
        ]
        email = build_notification_email("alice@test.com", matches)
        assert "Availability Monitor" in email["subject"]
        assert "Tennis Bot" not in email["subject"]

    def test_html_contains_general_matchi_link(self):
        from email_builder import build_notification_email

        matches = [
            {
                "facilityId": "frogner",
                "date": "2026-06-01",
                "courts": [{"time_slot": "17:00-18:00", "court_name": "Court 1"}],
            }
        ]
        email = build_notification_email("alice@test.com", matches)
        assert "https://www.matchi.se" in email["html_body"]
        assert "Take me to Matchi" in email["html_body"]
        assert "facilityId=" not in email["html_body"]

    def test_html_contains_preferences_link(self):
        from email_builder import build_notification_email

        matches = [
            {
                "facilityId": "ota",
                "sport": "padel",
                "date": "2026-06-01",
                "courts": [{"time_slot": "17:00-18:00", "court_name": "Padel 1"}],
            }
        ]
        email = build_notification_email("alice@test.com", matches)
        assert "https://availabilitymonitor.club" in email["html_body"]
        assert "Update your preferences" in email["html_body"]

    def test_text_body_contains_court_info(self):
        from email_builder import build_notification_email

        matches = [
            {
                "facilityId": "ota",
                "date": "2026-06-01",
                "courts": [{"time_slot": "19:00-20:00", "court_name": "Center Court"}],
            }
        ]
        email = build_notification_email("alice@test.com", matches)
        assert "Center Court" in email["text_body"]
        assert "19:00-20:00" in email["text_body"]
        assert "OTA" in email["text_body"]

    def test_text_body_branding(self):
        """Text body footer should use 'Availability Monitor' branding."""
        from email_builder import build_notification_email

        matches = [
            {
                "facilityId": "frogner",
                "date": "2026-06-01",
                "courts": [{"time_slot": "17:00-18:00", "court_name": "Court 1"}],
            }
        ]
        email = build_notification_email("alice@test.com", matches)
        assert "Availability Monitor" in email["text_body"]
        assert "Tennis Bot" not in email["text_body"]

    def test_email_has_all_keys(self):
        from email_builder import build_notification_email

        matches = [
            {
                "facilityId": "frogner",
                "date": "2026-06-01",
                "courts": [{"time_slot": "17:00-18:00", "court_name": "Court 1"}],
            }
        ]
        email = build_notification_email("alice@test.com", matches)
        assert "subject" in email
        assert "html_body" in email
        assert "text_body" in email


# ===========================================================================
# Full handler integration tests
# ===========================================================================


class TestHandler:
    def test_empty_diff_returns_early(self, dynamo):
        import handler as h

        response = h.lambda_handler({"diff": {}}, None)
        assert response["statusCode"] == 200
        assert response["summary"]["matches_found"] == 0
        assert response["summary"]["emails_sent"] == 0

    def test_no_diff_key_returns_early(self, dynamo):
        import handler as h

        response = h.lambda_handler({}, None)
        assert response["statusCode"] == 200
        assert response["summary"]["preferences_scanned"] == 0

    def test_end_to_end_with_matching_preference(self, dynamo):
        import handler as h

        _add_user(dynamo, "alice@test.com")
        _add_preference(
            dynamo,
            user_id="alice@test.com",
            preference_id="p1",
            facility_id="frogner",
            dates=["monday"],  # 2026-06-01 is Monday
            time_from="17:00",
            time_to="22:00",
            sport="tennis",
        )

        diff = _sample_diff()
        response = h.lambda_handler({"diff": diff}, None)

        assert response["statusCode"] == 200
        assert response["summary"]["preferences_scanned"] == 1
        assert response["summary"]["matches_found"] == 1
        assert response["summary"]["matches_after_dedup"] == 1
        assert response["summary"]["emails_sent"] == 1
        assert response["summary"]["notifications_recorded"] == 1

    def test_no_match_yields_zero_emails(self, dynamo):
        import handler as h

        _add_user(dynamo, "bob@test.com")
        _add_preference(
            dynamo,
            user_id="bob@test.com",
            preference_id="p2",
            facility_id="ota",
            dates=["monday"],  # 2026-06-01 is Monday
            sport="tennis",
        )

        diff = _sample_diff(facility="frogner")
        response = h.lambda_handler({"diff": diff}, None)

        assert response["statusCode"] == 200
        assert response["summary"]["matches_found"] == 0
        assert response["summary"]["emails_sent"] == 0

    def test_dedup_prevents_second_email(self, dynamo):
        import handler as h

        _add_user(dynamo, "alice@test.com")
        _add_preference(
            dynamo,
            user_id="alice@test.com",
            preference_id="p1",
            facility_id="frogner",
            dates=["monday"],  # 2026-06-01 is Monday
            time_from="17:00",
            time_to="22:00",
            sport="tennis",
        )

        diff = _sample_diff()

        # First invocation
        r1 = h.lambda_handler({"diff": diff}, None)
        assert r1["summary"]["emails_sent"] == 1

        # Second invocation with same diff — dedup should prevent email
        r2 = h.lambda_handler({"diff": diff}, None)
        assert r2["summary"]["matches_found"] == 1
        assert r2["summary"]["matches_after_dedup"] == 0
        assert r2["summary"]["emails_sent"] == 0

    def test_response_has_duration_ms(self, dynamo):
        import handler as h

        response = h.lambda_handler({"diff": _sample_diff()}, None)
        assert "duration_ms" in response["summary"]
        assert isinstance(response["summary"]["duration_ms"], int)

    def test_end_to_end_padel(self, dynamo):
        """End-to-end test with padel sport."""
        import handler as h

        _add_user(dynamo, "alice@test.com")
        _add_preference(
            dynamo,
            user_id="alice@test.com",
            preference_id="p1",
            facility_id="ota",
            dates=["monday"],  # 2026-06-01 is Monday
            time_from="17:00",
            time_to="22:00",
            sport="padel",
        )

        diff = _sample_diff(facility="ota", sport="padel")
        response = h.lambda_handler({"diff": diff}, None)

        assert response["statusCode"] == 200
        assert response["summary"]["matches_found"] == 1
        assert response["summary"]["emails_sent"] == 1
