"""
End-to-end smoke tests for the full availability pipeline.

Exercises: raw HTML -> parse -> diff -> match preferences -> dedup -> send email.
Uses moto to mock DynamoDB + SES — no real AWS calls are made.

Run with:
    python -m pytest tests/test_e2e_pipeline.py -v
"""

import importlib
import os
import sys

import boto3
import pytest
from moto import mock_aws

# ---------------------------------------------------------------------------
# Import strategy — avoids handler.py name collision between lambdas
# ---------------------------------------------------------------------------

# 1. Add scraper dir and import scraper functions
SCRAPER_DIR = os.path.join(os.path.dirname(__file__), "..", "lambdas", "scraper")
sys.path.insert(0, SCRAPER_DIR)
from scraper import parse_slots_from_html  # noqa: E402
from diff import build_new_courts_diff  # noqa: E402

# 2. Remove scraper dir, add notifications dir
sys.path.remove(SCRAPER_DIR)
NOTIFICATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "lambdas", "notifications")
sys.path.insert(0, NOTIFICATIONS_DIR)

# 3. Add repo root for facilities.py
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

# 2026-06-01 is a Monday
TEST_DATE = "2026-06-01"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_fixture(filename: str) -> str:
    """Read HTML fixture from tests/fixtures/."""
    path = os.path.join(os.path.dirname(__file__), "fixtures", filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


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
        "dates": dates or ["monday"],
        "timeFrom": time_from,
        "timeTo": time_to,
        "sport": sport,
    }
    if court_type:
        item["courtType"] = court_type
    table.put_item(Item=item)


def _build_frogner_diff() -> dict:
    """Parse frogner before/after fixtures and return the diff."""
    before_html = _load_fixture("matchi_frogner_before.html")
    after_html = _load_fixture("matchi_frogner_after.html")

    before_slots = parse_slots_from_html(before_html)
    after_slots = parse_slots_from_html(after_html)

    before_snapshot = {"frogner#tennis": {TEST_DATE: before_slots}}
    after_snapshot = {"frogner#tennis": {TEST_DATE: after_slots}}

    return build_new_courts_diff(after_snapshot, before_snapshot)


def _build_padel_diff() -> dict:
    """Parse OTA padel before/after fixtures and return the diff."""
    before_html = _load_fixture("matchi_ota_padel_before.html")
    after_html = _load_fixture("matchi_ota_padel_after.html")

    before_slots = parse_slots_from_html(before_html)
    after_slots = parse_slots_from_html(after_html)

    before_snapshot = {"ota#padel": {TEST_DATE: before_slots}}
    after_snapshot = {"ota#padel": {TEST_DATE: after_slots}}

    return build_new_courts_diff(after_snapshot, before_snapshot)


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
# Tests
# ---------------------------------------------------------------------------


class TestE2EPipeline:
    def test_new_court_triggers_email(self, dynamo):
        """Full pipeline: HTML parse -> diff -> match -> dedup -> email sent."""
        import handler as h

        diff = _build_frogner_diff()
        # Verify the diff contains what we expect: Bane 2 at 17:00-18:00
        assert "frogner#tennis" in diff
        assert TEST_DATE in diff["frogner#tennis"]
        assert "17:00-18:00" in diff["frogner#tennis"][TEST_DATE]
        assert "Bane 2" in diff["frogner#tennis"][TEST_DATE]["17:00-18:00"]

        _add_user(dynamo, "alice@test.com")
        _add_preference(
            dynamo,
            user_id="alice@test.com",
            preference_id="p1",
            facility_id="frogner",
            dates=["monday"],
            time_from="17:00",
            time_to="22:00",
            sport="tennis",
        )

        response = h.lambda_handler({"diff": diff}, None)
        assert response["summary"]["emails_sent"] == 1

    def test_wrong_day_no_email(self, dynamo):
        """Preference for Tuesday should not match a Monday diff."""
        import handler as h

        diff = _build_frogner_diff()

        _add_user(dynamo, "alice@test.com")
        _add_preference(
            dynamo,
            user_id="alice@test.com",
            preference_id="p1",
            facility_id="frogner",
            dates=["tuesday"],
            time_from="17:00",
            time_to="22:00",
            sport="tennis",
        )

        response = h.lambda_handler({"diff": diff}, None)
        assert response["summary"]["emails_sent"] == 0

    def test_outside_time_window_no_email(self, dynamo):
        """Preference for 08:00-10:00 should not match a 17:00 diff."""
        import handler as h

        diff = _build_frogner_diff()

        _add_user(dynamo, "alice@test.com")
        _add_preference(
            dynamo,
            user_id="alice@test.com",
            preference_id="p1",
            facility_id="frogner",
            dates=["monday"],
            time_from="08:00",
            time_to="10:00",
            sport="tennis",
        )

        response = h.lambda_handler({"diff": diff}, None)
        assert response["summary"]["emails_sent"] == 0

    def test_dedup_blocks_second_run(self, dynamo):
        """Running the handler twice with same diff should dedup the second."""
        import handler as h

        diff = _build_frogner_diff()

        _add_user(dynamo, "alice@test.com")
        _add_preference(
            dynamo,
            user_id="alice@test.com",
            preference_id="p1",
            facility_id="frogner",
            dates=["monday"],
            time_from="17:00",
            time_to="22:00",
            sport="tennis",
        )

        # First run — email sent
        r1 = h.lambda_handler({"diff": diff}, None)
        assert r1["summary"]["emails_sent"] == 1

        # Second run — dedup blocks
        r2 = h.lambda_handler({"diff": diff}, None)
        assert r2["summary"]["emails_sent"] == 0
        assert r2["summary"]["matches_after_dedup"] == 0

    def test_padel_single_filter(self, dynamo):
        """courtType=single should only match Padel Single courts."""
        import handler as h

        diff = _build_padel_diff()
        # Verify diff contains both single and double courts
        assert "ota#padel" in diff

        _add_user(dynamo, "alice@test.com")
        _add_preference(
            dynamo,
            user_id="alice@test.com",
            preference_id="p1",
            facility_id="ota",
            dates=["monday"],
            time_from="17:00",
            time_to="22:00",
            sport="padel",
            court_type="single",
        )

        response = h.lambda_handler({"diff": diff}, None)
        assert response["summary"]["emails_sent"] == 1
        # Verify only 1 match (the single court), not double courts
        assert response["summary"]["matches_after_dedup"] == 1

    def test_padel_double_filter(self, dynamo):
        """courtType=double should match Padel Double courts but not single."""
        import handler as h

        diff = _build_padel_diff()

        _add_user(dynamo, "alice@test.com")
        _add_preference(
            dynamo,
            user_id="alice@test.com",
            preference_id="p1",
            facility_id="ota",
            dates=["monday"],
            time_from="17:00",
            time_to="22:00",
            sport="padel",
            court_type="double",
        )

        response = h.lambda_handler({"diff": diff}, None)
        assert response["summary"]["emails_sent"] == 1
        assert response["summary"]["matches_after_dedup"] == 1

    def test_multi_facility_multi_user(self, dynamo):
        """Multiple users with different prefs across facilities get emails."""
        import handler as h

        frogner_diff = _build_frogner_diff()
        padel_diff = _build_padel_diff()

        # Merge diffs
        combined_diff = {**frogner_diff, **padel_diff}

        # User 1: frogner tennis
        _add_user(dynamo, "alice@test.com")
        _add_preference(
            dynamo,
            user_id="alice@test.com",
            preference_id="p1",
            facility_id="frogner",
            dates=["monday"],
            time_from="17:00",
            time_to="22:00",
            sport="tennis",
        )

        # User 2: OTA padel single
        _add_user(dynamo, "bob@test.com")
        _add_preference(
            dynamo,
            user_id="bob@test.com",
            preference_id="p2",
            facility_id="ota",
            dates=["monday"],
            time_from="17:00",
            time_to="22:00",
            sport="padel",
            court_type="single",
        )

        # User 3: OTA padel double
        _add_user(dynamo, "carol@test.com")
        _add_preference(
            dynamo,
            user_id="carol@test.com",
            preference_id="p3",
            facility_id="ota",
            dates=["monday"],
            time_from="17:00",
            time_to="22:00",
            sport="padel",
            court_type="double",
        )

        response = h.lambda_handler({"diff": combined_diff}, None)
        assert response["summary"]["emails_sent"] == 3

    def test_identical_snapshots_no_diff(self, dynamo):
        """Parsing the same HTML as before and after should produce empty diff."""
        import handler as h

        html = _load_fixture("matchi_frogner_before.html")
        slots = parse_slots_from_html(html)

        snapshot = {"frogner#tennis": {TEST_DATE: slots}}
        diff = build_new_courts_diff(snapshot, snapshot)

        assert diff == {}

        _add_user(dynamo, "alice@test.com")
        _add_preference(
            dynamo,
            user_id="alice@test.com",
            preference_id="p1",
            facility_id="frogner",
            dates=["monday"],
            time_from="17:00",
            time_to="22:00",
            sport="tennis",
        )

        response = h.lambda_handler({"diff": diff}, None)
        assert response["summary"]["emails_sent"] == 0
