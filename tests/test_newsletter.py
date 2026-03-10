"""
Unit tests for the Weekly Newsletter Lambda (#58).

Uses moto to mock DynamoDB and SES — no real AWS calls are made.

Run with:
    pip install pytest moto[dynamodb,ses] boto3
    pytest tests/test_newsletter.py -v
"""

import datetime
import importlib
import json
import os
import sys

import boto3
import pytest
from moto import mock_aws

# ---------------------------------------------------------------------------
# Ensure the handler module can be imported regardless of working directory
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
HANDLER_DIR = os.path.join(REPO_ROOT, "lambdas", "newsletter")
NEWSLETTER_PKG_DIR = os.path.join(REPO_ROOT, "lambdas", "newsletter", "package")
# matcher.py lives in the newsletter package dir (copied from notifications at
# deploy time).  For tests we add it so the import resolves with the correct
# day-of-week-based matcher used by the newsletter Lambda.
# HANDLER_DIR must sit at index 0 so handler.py and email_builder.py are found
# there first.  Repo root is needed for facilities.py.
for _dir in (REPO_ROOT, NEWSLETTER_PKG_DIR, HANDLER_DIR):
    if _dir not in sys.path:
        sys.path.insert(0, _dir)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGION = "eu-north-1"
AVAILABILITY_TABLE = "tennis-availability"
PREFS_TABLE = "tennis-preferences"
USERS_TABLE = "tennis-users"
SES_FROM_EMAIL = "bot@tennis.test"

# Fixed "today" = Tuesday 2026-03-10 → next Monday = 2026-03-16
FIXED_TODAY = datetime.date(2026, 3, 10)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    """Set environment variables and fix module imports before each test."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_REGION", REGION)
    monkeypatch.setenv("AVAILABILITY_TABLE", AVAILABILITY_TABLE)
    monkeypatch.setenv("PREFS_TABLE", PREFS_TABLE)
    monkeypatch.setenv("USERS_TABLE", USERS_TABLE)
    monkeypatch.setenv("SES_FROM_EMAIL", SES_FROM_EMAIL)
    # Clear test recipient by default
    monkeypatch.delenv("NEWSLETTER_TEST_RECIPIENT", raising=False)

    # Evict cached modules so imports resolve from the newsletter dir
    # (not from notifications dir if test_notifications ran first).
    for mod_name in ("handler", "email_builder", "matcher"):
        if mod_name in sys.modules:
            del sys.modules[mod_name]


@pytest.fixture()
def dynamo(monkeypatch):
    """Spin up moto-mocked DynamoDB with required tables, verify SES, yield resource."""
    # Pin datetime.date.today so week computation is deterministic
    class FakeDate(datetime.date):
        @classmethod
        def today(cls):
            return FIXED_TODAY

    monkeypatch.setattr(datetime, "date", FakeDate)

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

        # tennis-availability (PK: facilityId, SK: date)
        client.create_table(
            TableName=AVAILABILITY_TABLE,
            AttributeDefinitions=[
                {"AttributeName": "facilityId", "AttributeType": "S"},
                {"AttributeName": "date", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "facilityId", "KeyType": "HASH"},
                {"AttributeName": "date", "KeyType": "RANGE"},
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
    facility_id: str = "ota",
    days: list[str] | None = None,
    time_from: str = "17:00",
    time_to: str = "22:00",
    sport: str = "tennis",
) -> None:
    table = dynamo_resource.Table(PREFS_TABLE)
    table.put_item(
        Item={
            "userId": user_id,
            "preferenceId": preference_id,
            "facilityId": facility_id,
            "dates": days or ["monday"],
            "timeFrom": time_from,
            "timeTo": time_to,
            "sport": sport,
        }
    )


def _seed_availability(
    dynamo_resource,
    facility: str,
    date: str,
    slots: dict[str, list[str]],
) -> None:
    """Write an availability snapshot to the tennis-availability table."""
    table = dynamo_resource.Table(AVAILABILITY_TABLE)
    table.put_item(
        Item={
            "facilityId": facility,
            "date": date,
            "slots": json.dumps(slots),
        }
    )


def _get_ses_send_count() -> int:
    """Return the number of emails sent via mocked SES."""
    ses = boto3.client("ses", region_name=REGION)
    stats = ses.get_send_statistics()
    data_points = stats.get("SendDataPoints", [])
    return sum(dp.get("DeliveryAttempts", 0) for dp in data_points)


# ===========================================================================
# Handler integration tests
# ===========================================================================


class TestHandler:
    def test_no_availability_sends_no_emails(self, dynamo):
        """No availability data → no emails sent."""
        import handler as h

        _add_user(dynamo, "alice@test.com")
        _add_preference(dynamo, "alice@test.com", "p1")

        response = h.lambda_handler({}, None)
        assert response["statusCode"] == 200
        assert response["summary"]["emails_sent"] == 0

    def test_no_preferences_sends_no_emails(self, dynamo):
        """Availability exists but no preferences → no emails."""
        import handler as h

        # 2026-03-16 is next Monday from FIXED_TODAY
        _seed_availability(dynamo, "ota#tennis", "2026-03-16", {
            "17:00-18:00": ["Tennis 1"],
        })

        response = h.lambda_handler({}, None)
        assert response["statusCode"] == 200
        assert response["summary"]["preferences_scanned"] == 0
        assert response["summary"]["emails_sent"] == 0

    def test_matching_preference_sends_email(self, dynamo):
        """Availability + matching preference → 1 email sent."""
        import handler as h

        _add_user(dynamo, "alice@test.com")
        _add_preference(
            dynamo, "alice@test.com", "p1",
            facility_id="ota", days=["monday"],
            time_from="17:00", time_to="22:00",
        )
        _seed_availability(dynamo, "ota#tennis", "2026-03-16", {
            "17:00-18:00": ["Tennis 5 Lexus"],
        })

        response = h.lambda_handler({}, None)
        assert response["statusCode"] == 200
        assert response["summary"]["matches_found"] >= 1
        assert response["summary"]["emails_sent"] == 1

    def test_no_match_wrong_time(self, dynamo):
        """Availability outside preference time window → no emails."""
        import handler as h

        _add_user(dynamo, "alice@test.com")
        _add_preference(
            dynamo, "alice@test.com", "p1",
            facility_id="ota", days=["monday"],
            time_from="17:00", time_to="22:00",
        )
        _seed_availability(dynamo, "ota#tennis", "2026-03-16", {
            "08:00-09:00": ["Tennis 1"],
        })

        response = h.lambda_handler({}, None)
        assert response["statusCode"] == 200
        assert response["summary"]["matches_found"] == 0
        assert response["summary"]["emails_sent"] == 0

    def test_no_match_wrong_day(self, dynamo):
        """Availability on a day not in preference → no emails."""
        import handler as h

        _add_user(dynamo, "alice@test.com")
        _add_preference(
            dynamo, "alice@test.com", "p1",
            facility_id="ota", days=["friday"],
            time_from="17:00", time_to="22:00",
        )
        # 2026-03-16 is Monday, preference is Friday only
        _seed_availability(dynamo, "ota#tennis", "2026-03-16", {
            "17:00-18:00": ["Tennis 1"],
        })

        response = h.lambda_handler({}, None)
        assert response["statusCode"] == 200
        assert response["summary"]["matches_found"] == 0
        assert response["summary"]["emails_sent"] == 0

    def test_test_mode_only_sends_to_test_recipient(self, dynamo, monkeypatch):
        """NEWSLETTER_TEST_RECIPIENT filters to single recipient."""
        import handler as h

        monkeypatch.setenv("NEWSLETTER_TEST_RECIPIENT", "alice@test.com")
        importlib.reload(h)
        h._dynamodb_resource = None
        h._ses_client = None

        _add_user(dynamo, "alice@test.com")
        _add_user(dynamo, "bob@test.com")
        _add_preference(dynamo, "alice@test.com", "p1",
                        facility_id="ota", days=["monday"])
        _add_preference(dynamo, "bob@test.com", "p2",
                        facility_id="ota", days=["monday"])
        _seed_availability(dynamo, "ota#tennis", "2026-03-16", {
            "17:00-18:00": ["Tennis 1"],
        })

        response = h.lambda_handler({}, None)
        assert response["statusCode"] == 200
        assert response["summary"]["emails_sent"] == 1
        assert response["summary"]["users_matched"] == 1

    def test_multiple_users_each_get_email(self, dynamo):
        """Two users with matching preferences → 2 emails."""
        import handler as h

        _add_user(dynamo, "alice@test.com")
        _add_user(dynamo, "bob@test.com")
        _add_preference(dynamo, "alice@test.com", "p1",
                        facility_id="ota", days=["monday"])
        _add_preference(dynamo, "bob@test.com", "p2",
                        facility_id="ota", days=["monday"])
        _seed_availability(dynamo, "ota#tennis", "2026-03-16", {
            "17:00-18:00": ["Tennis 1"],
        })

        response = h.lambda_handler({}, None)
        assert response["statusCode"] == 200
        assert response["summary"]["emails_sent"] == 2

    def test_response_has_week_range(self, dynamo):
        """Response summary includes week_start and week_end."""
        import handler as h

        _seed_availability(dynamo, "ota#tennis", "2026-03-16", {
            "17:00-18:00": ["Tennis 1"],
        })
        _add_preference(dynamo, "alice@test.com", "p1",
                        facility_id="ota", days=["monday"])

        response = h.lambda_handler({}, None)
        assert response["summary"]["week_start"] == "2026-03-16"
        assert response["summary"]["week_end"] == "2026-03-22"


# ===========================================================================
# Email builder tests
# ===========================================================================


class TestEmailBuilder:
    def test_subject_contains_week_range(self):
        from email_builder import build_newsletter_email

        matches = [
            {
                "facilityId": "ota#tennis",
                "date": "2026-03-16",
                "courts": [{"time_slot": "17:00-18:00", "court_name": "Tennis 1"}],
            }
        ]
        email = build_newsletter_email("alice@test.com", matches, "2026-03-16", "2026-03-22")
        assert "16 Mar" in email["subject"]
        assert "22 Mar" in email["subject"]

    def test_subject_slot_count(self):
        from email_builder import build_newsletter_email

        matches = [
            {
                "facilityId": "ota#tennis",
                "date": "2026-03-16",
                "courts": [
                    {"time_slot": "17:00-18:00", "court_name": "Tennis 1"},
                    {"time_slot": "18:00-19:00", "court_name": "Tennis 2"},
                ],
            }
        ]
        email = build_newsletter_email("alice@test.com", matches, "2026-03-16", "2026-03-22")
        assert "2 court slots" in email["subject"]

    def test_subject_singular_slot(self):
        from email_builder import build_newsletter_email

        matches = [
            {
                "facilityId": "ota#tennis",
                "date": "2026-03-16",
                "courts": [{"time_slot": "17:00-18:00", "court_name": "Tennis 1"}],
            }
        ]
        email = build_newsletter_email("alice@test.com", matches, "2026-03-16", "2026-03-22")
        assert "1 court slot " in email["subject"]
        assert "slots" not in email["subject"]

    def test_html_groups_by_day(self):
        from email_builder import build_newsletter_email

        matches = [
            {
                "facilityId": "ota#tennis",
                "date": "2026-03-16",
                "courts": [{"time_slot": "17:00-18:00", "court_name": "Tennis 1"}],
            },
            {
                "facilityId": "ota#tennis",
                "date": "2026-03-18",
                "courts": [{"time_slot": "19:00-20:00", "court_name": "Tennis 2"}],
            },
        ]
        email = build_newsletter_email("alice@test.com", matches, "2026-03-16", "2026-03-22")
        html = email["html_body"]

        # Day headings should appear in chronological order
        assert "Monday, 16 Mar" in html
        assert "Wednesday, 18 Mar" in html
        # Monday should appear before Wednesday
        assert html.index("Monday, 16 Mar") < html.index("Wednesday, 18 Mar")

    def test_html_contains_court_info(self):
        from email_builder import build_newsletter_email

        matches = [
            {
                "facilityId": "ota#tennis",
                "date": "2026-03-16",
                "courts": [{"time_slot": "17:00-18:00", "court_name": "Tennis 5 Lexus"}],
            }
        ]
        email = build_newsletter_email("alice@test.com", matches, "2026-03-16", "2026-03-22")
        assert "Tennis 5 Lexus" in email["html_body"]
        assert "17:00-18:00" in email["html_body"]
        assert "OTA" in email["html_body"]

    def test_html_contains_booking_url(self):
        from email_builder import build_newsletter_email

        matches = [
            {
                "facilityId": "ota#tennis",
                "date": "2026-03-16",
                "courts": [{"time_slot": "17:00-18:00", "court_name": "Tennis 1"}],
            }
        ]
        email = build_newsletter_email("alice@test.com", matches, "2026-03-16", "2026-03-22")
        assert "facilityId=1779" in email["html_body"]
        assert "date=2026-03-16" in email["html_body"]
        assert "sport=1" in email["html_body"]

    def test_html_contains_padel_booking_url(self):
        from email_builder import build_newsletter_email

        matches = [
            {
                "facilityId": "ota#padel",
                "date": "2026-03-16",
                "courts": [{"time_slot": "17:00-18:00", "court_name": "Padel 1"}],
            }
        ]
        email = build_newsletter_email("alice@test.com", matches, "2026-03-16", "2026-03-22")
        assert "facilityId=1779" in email["html_body"]
        assert "sport=5" in email["html_body"]
        assert "OTA" in email["html_body"]

    def test_text_body_contains_court_info(self):
        from email_builder import build_newsletter_email

        matches = [
            {
                "facilityId": "ota#tennis",
                "date": "2026-03-16",
                "courts": [{"time_slot": "19:00-20:00", "court_name": "Center Court"}],
            }
        ]
        email = build_newsletter_email("alice@test.com", matches, "2026-03-16", "2026-03-22")
        assert "Center Court" in email["text_body"]
        assert "19:00-20:00" in email["text_body"]
        assert "OTA" in email["text_body"]

    def test_email_has_all_keys(self):
        from email_builder import build_newsletter_email

        matches = [
            {
                "facilityId": "ota#tennis",
                "date": "2026-03-16",
                "courts": [{"time_slot": "17:00-18:00", "court_name": "Tennis 1"}],
            }
        ]
        email = build_newsletter_email("alice@test.com", matches, "2026-03-16", "2026-03-22")
        assert "subject" in email
        assert "html_body" in email
        assert "text_body" in email

    def test_rebranded_subject_and_footer(self):
        from email_builder import build_newsletter_email

        matches = [
            {
                "facilityId": "ota#tennis",
                "date": "2026-03-16",
                "courts": [{"time_slot": "17:00-18:00", "court_name": "Tennis 1"}],
            }
        ]
        email = build_newsletter_email("alice@test.com", matches, "2026-03-16", "2026-03-22")
        assert "Availability Monitor" in email["subject"]
        assert "Tennis Bot" not in email["subject"]
        assert "Availability Monitor Weekly Newsletter" in email["html_body"]
        assert "Availability Monitor Weekly Newsletter" in email["text_body"]
        assert "Your Week Ahead" in email["html_body"]
        assert "Your Week Ahead" in email["text_body"]
