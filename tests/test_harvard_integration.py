"""
Harvard-specific integration tests — TDD RED phase for Plan 02-01.

These tests define the contract for NOTF-02, NOTF-03, NOTF-04, PREF-04 before
implementation.

Written as a SEPARATE file (not appended to test_notifications.py) because
the existing file uses Python 3.10+ union syntax (list[str] | None) that
fails to collect on Python 3.9.

Run with:
    python3 -m pytest tests/test_harvard_integration.py -v
"""

import hashlib
import importlib
import os
import sys
import time

import boto3
import pytest
from moto import mock_aws

# ---------------------------------------------------------------------------
# Path setup — mirror test_notifications.py path insertion
# ---------------------------------------------------------------------------

HANDLER_DIR = os.path.join(os.path.dirname(__file__), "..", "lambdas", "notifications")
if HANDLER_DIR not in sys.path:
    sys.path.insert(0, HANDLER_DIR)

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
# Local dedup key helper (mirrors dedup._dedup_key)
# ---------------------------------------------------------------------------


def _dedup_key(user_id, facility_id, sport, date, time_slot, court_name):
    raw = f"{user_id}|{facility_id}|{sport}|{date}|{time_slot}|{court_name}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ===========================================================================
# TestEmailBuilderHarvard — NOTF-02 / NOTF-03 (RED: fail until implementation)
# ===========================================================================


class TestEmailBuilderHarvard:
    """Tests verifying Harvard-specific CTA in notification emails.

    These tests are in RED state — they will fail until email_builder.py
    is updated (Plan 02-02) to use gocrimson.com for Harvard.
    """

    def _harvard_match(self):
        return {
            "userId": "alice@example.com",
            "preferenceId": "pref-uuid",
            "facilityId": "harvard",
            "sport": "tennis",
            "date": "2026-04-14",
            "courts": [{"time_slot": "10:00-11:00", "court_name": "Indoor Tennis Court 6"}],
        }

    def test_harvard_cta_links_to_gocrimson(self):
        """NOTF-02: CTA button in Harvard email must link to gocrimson.com."""
        from email_builder import build_notification_email

        result = build_notification_email("alice@example.com", [self._harvard_match()])
        assert "gocrimson.com" in result["html_body"]
        assert "Register at Harvard Rec" in result["html_body"]

    def test_harvard_cta_does_not_say_take_me_to_matchi(self):
        """NOTF-02: Harvard email must NOT say 'Take me to Matchi'."""
        from email_builder import build_notification_email

        result = build_notification_email("alice@example.com", [self._harvard_match()])
        assert "Take me to Matchi" not in result["html_body"]

    def test_harvard_plain_text_contains_gocrimson_url(self):
        """NOTF-03: Plain-text body of Harvard email must contain gocrimson.com URL."""
        from email_builder import build_notification_email

        result = build_notification_email("alice@example.com", [self._harvard_match()])
        assert "gocrimson.com" in result["text_body"]


# ===========================================================================
# TestMatchPreferencesHarvard — PREF-04 (GREEN: passes immediately)
# ===========================================================================


class TestMatchPreferencesHarvard:
    """Tests verifying matcher produces correct match for harvard#tennis composite key.

    These tests verify PREF-04 — should pass immediately because the matcher
    already handles composite keys generically.
    """

    def test_harvard_composite_key_match(self):
        """PREF-04: matcher must match harvard#tennis composite key."""
        from matcher import match_preferences

        # 2026-04-14 is a Tuesday — use tuesday in prefs
        diff = {
            "harvard#tennis": {
                "2026-04-14": {
                    "10:00-11:00": ["Indoor Tennis Court 6"],
                }
            }
        }
        prefs = [{
            "userId": "alice@example.com",
            "preferenceId": "pref-001",
            "facilityId": "harvard",
            "sport": "tennis",
            "dates": ["tuesday"],
            "timeFrom": "09:00",
            "timeTo": "12:00",
        }]
        results = match_preferences(diff, prefs)
        assert len(results) == 1
        assert results[0]["facilityId"] == "harvard"
        assert results[0]["sport"] == "tennis"
        assert results[0]["courts"][0]["court_name"] == "Indoor Tennis Court 6"

    def test_harvard_no_match_wrong_facility(self):
        """Preference for harvard should not match frogner diff."""
        from matcher import match_preferences

        diff = {"frogner#tennis": {"2026-04-14": {"10:00-11:00": ["Court 1"]}}}
        prefs = [{"userId": "alice@example.com", "preferenceId": "p1",
                  "facilityId": "harvard", "sport": "tennis",
                  "dates": ["tuesday"], "timeFrom": "09:00", "timeTo": "12:00"}]
        assert match_preferences(diff, prefs) == []


# ===========================================================================
# TestDedupHarvard — NOTF-04 (GREEN: passes immediately)
# ===========================================================================


class TestDedupHarvard:
    """Tests verifying dedup handles harvard slots correctly.

    These tests verify NOTF-04 — should pass immediately because dedup
    already incorporates facilityId in the hash.
    """

    def test_harvard_dedup_key_is_stable(self):
        """NOTF-04: Dedup key for harvard slot must be deterministic SHA-256."""
        from dedup import _dedup_key as real_dedup_key

        key1 = real_dedup_key("u@x.com", "harvard", "tennis", "2026-04-14", "10:00-11:00", "Indoor Tennis Court 6")
        key2 = real_dedup_key("u@x.com", "harvard", "tennis", "2026-04-14", "10:00-11:00", "Indoor Tennis Court 6")
        assert key1 == key2
        assert len(key1) == 64  # SHA-256 hex

    def test_harvard_dedup_prevents_second_alert(self, dynamo):
        """NOTF-04: filter_already_notified must suppress second harvard alert."""
        from dedup import filter_already_notified, _dedup_key as real_dedup_key

        key = real_dedup_key("alice@example.com", "harvard", "tennis",
                             "2026-04-14", "10:00-11:00", "Indoor Tennis Court 6")
        notif_table = dynamo.Table(NOTIFICATIONS_TABLE)
        notif_table.put_item(Item={"notificationId": key, "ttl": int(time.time()) + 86400})

        match = {
            "userId": "alice@example.com",
            "preferenceId": "pref-001",
            "facilityId": "harvard",
            "sport": "tennis",
            "date": "2026-04-14",
            "courts": [{"time_slot": "10:00-11:00", "court_name": "Indoor Tennis Court 6"}],
        }
        result = filter_already_notified([match], notif_table)
        assert result == []  # Already notified — no second alert
