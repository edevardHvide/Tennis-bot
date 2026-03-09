"""
Unit tests for the Notification Engine Lambda (Phase 4).

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
) -> None:
    table = dynamo_resource.Table(PREFS_TABLE)
    table.put_item(
        Item={
            "userId": user_id,
            "preferenceId": preference_id,
            "facilityId": facility_id,
            "dates": dates or ["2026-06-01"],
            "timeFrom": time_from,
            "timeTo": time_to,
        }
    )


def _sample_diff(
    facility: str = "frogner",
    date: str = "2026-06-01",
    time_slot: str = "17:00-18:00",
    courts: list[str] | None = None,
) -> dict:
    return {
        facility: {
            date: {
                time_slot: courts or ["Court 1"],
            },
        },
    }


def _dedup_key(user_id, facility_id, date, time_slot, court_name):
    raw = f"{user_id}|{facility_id}|{date}|{time_slot}|{court_name}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ===========================================================================
# Matcher tests
# ===========================================================================


class TestMatcher:
    def test_facility_match(self):
        from matcher import match_preferences

        diff = _sample_diff()
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                "dates": ["2026-06-01"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 1
        assert matches[0]["facilityId"] == "frogner"

    def test_no_match_wrong_facility(self):
        from matcher import match_preferences

        diff = _sample_diff(facility="ota")
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                "dates": ["2026-06-01"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 0

    def test_date_match(self):
        from matcher import match_preferences

        diff = _sample_diff(date="2026-06-01")
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                "dates": ["2026-06-01", "2026-06-02"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 1
        assert matches[0]["date"] == "2026-06-01"

    def test_no_match_wrong_date(self):
        from matcher import match_preferences

        diff = _sample_diff(date="2026-06-01")
        prefs = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
                "dates": ["2026-06-02"],
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
                "dates": ["2026-06-01"],
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
                "dates": ["2026-06-01"],
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
                "dates": ["2026-06-01"],
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
                "dates": ["2026-06-01"],
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
                "dates": ["2026-06-01"],
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
                "dates": ["2026-06-01"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
            }
        ]
        matches = match_preferences(diff, prefs)
        assert len(matches) == 1
        assert len(matches[0]["courts"]) == 3


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
        key = _dedup_key("alice@test.com", "frogner", "2026-06-01", "17:00-18:00", "Court 1")
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
                "date": "2026-06-01",
                "courts": [{"time_slot": "17:00-18:00", "court_name": "Court 1"}],
            }
        ]
        result = filter_already_notified(matches, table)
        assert len(result) == 0

    def test_record_notifications_writes_items(self, dynamo):
        from dedup import record_notifications

        table = dynamo.Table(NOTIFICATIONS_TABLE)
        matches = [
            {
                "userId": "alice@test.com",
                "preferenceId": "p1",
                "facilityId": "frogner",
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
        key1 = _dedup_key("alice@test.com", "frogner", "2026-06-01", "17:00-18:00", "Court 1")
        resp = table.get_item(Key={"notificationId": key1})
        assert "Item" in resp
        assert "ttl" in resp["Item"]


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

    def test_html_contains_booking_url(self):
        from email_builder import build_notification_email

        matches = [
            {
                "facilityId": "frogner",
                "date": "2026-06-01",
                "courts": [{"time_slot": "17:00-18:00", "court_name": "Court 1"}],
            }
        ]
        email = build_notification_email("alice@test.com", matches)
        assert "facilityId=2259" in email["html_body"]
        assert "date=2026-06-01" in email["html_body"]

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
            dates=["2026-06-01"],
            time_from="17:00",
            time_to="22:00",
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
            dates=["2026-06-01"],
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
            dates=["2026-06-01"],
            time_from="17:00",
            time_to="22:00",
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
