#!/usr/bin/env python3
"""
Smoke test for the full availability pipeline.

Usage:
    python scripts/smoke_test.py                                              # Local (moto)
    python scripts/smoke_test.py --live --recipient alice@example.com         # Live AWS
    python scripts/smoke_test.py --live --profile tennis-bot --recipient x    # Live + profile
"""

import argparse
import importlib
import json
import os
import sys
import uuid

# ---------------------------------------------------------------------------
# Path setup — same strategy as the e2e tests
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(SCRIPT_DIR, "..")
SCRAPER_DIR = os.path.join(REPO_ROOT, "lambdas", "scraper")
NOTIFICATIONS_DIR = os.path.join(REPO_ROOT, "lambdas", "notifications")
FIXTURES_DIR = os.path.join(REPO_ROOT, "tests", "fixtures")

# Repo root must be on path first so facilities.py is importable
if os.path.abspath(REPO_ROOT) not in sys.path:
    sys.path.insert(0, os.path.abspath(REPO_ROOT))

sys.path.insert(0, SCRAPER_DIR)
from scraper import parse_slots_from_html  # noqa: E402
from diff import build_new_courts_diff  # noqa: E402

sys.path.remove(SCRAPER_DIR)
sys.path.insert(0, NOTIFICATIONS_DIR)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGION = "eu-north-1"
NOTIFICATIONS_TABLE = "tennis-notifications"
PREFS_TABLE = "tennis-preferences"
USERS_TABLE = "tennis-users"
SES_FROM_EMAIL = "bot@tennis.test"
TEST_DATE = "2026-06-01"  # Monday


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_fixture(filename: str) -> str:
    path = os.path.join(FIXTURES_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _step(num: int, desc: str) -> None:
    print(f"\n{'='*60}")
    print(f"  Step {num}: {desc}")
    print(f"{'='*60}")


def _pass(msg: str) -> None:
    print(f"  [PASS] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


# ---------------------------------------------------------------------------
# Local mode (moto)
# ---------------------------------------------------------------------------


def run_local() -> bool:
    """Run the full pipeline locally with moto mocks. Returns True on success."""
    import boto3
    from moto import mock_aws

    results: list[bool] = []

    with mock_aws():
        # Setup environment
        os.environ["AWS_DEFAULT_REGION"] = REGION
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_SECURITY_TOKEN"] = "testing"
        os.environ["AWS_SESSION_TOKEN"] = "testing"
        os.environ["AWS_REGION"] = REGION
        os.environ["NOTIFICATIONS_TABLE"] = NOTIFICATIONS_TABLE
        os.environ["PREFS_TABLE"] = PREFS_TABLE
        os.environ["USERS_TABLE"] = USERS_TABLE
        os.environ["SES_FROM_EMAIL"] = SES_FROM_EMAIL

        # Create DynamoDB tables
        client = boto3.client("dynamodb", region_name=REGION)
        client.create_table(
            TableName=USERS_TABLE,
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
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

        ses = boto3.client("ses", region_name=REGION)
        ses.verify_email_identity(EmailAddress=SES_FROM_EMAIL)

        dynamo = boto3.resource("dynamodb", region_name=REGION)

        import handler as h
        importlib.reload(h)
        h._dynamodb_resource = None
        h._ses_client = None

        # -- Step 1: Parse HTML fixtures --
        _step(1, "Parse HTML fixtures")

        before_html = _load_fixture("matchi_frogner_before.html")
        after_html = _load_fixture("matchi_frogner_after.html")

        before_slots = parse_slots_from_html(before_html)
        after_slots = parse_slots_from_html(after_html)

        before_count = sum(len(v) for v in before_slots.values())
        after_count = sum(len(v) for v in after_slots.values())

        print(f"  Before: {before_count} courts across {len(before_slots)} time slots")
        print(f"  After:  {after_count} courts across {len(after_slots)} time slots")

        if after_count > before_count:
            _pass(f"After has more courts ({after_count} > {before_count})")
            results.append(True)
        else:
            _fail(f"Expected after to have more courts than before")
            results.append(False)

        # -- Step 2: Compute diff --
        _step(2, "Compute diff")

        before_snapshot = {"frogner#tennis": {TEST_DATE: before_slots}}
        after_snapshot = {"frogner#tennis": {TEST_DATE: after_slots}}
        diff = build_new_courts_diff(after_snapshot, before_snapshot)

        print(f"  Diff: {json.dumps(diff, indent=2)}")

        if "frogner#tennis" in diff and "Bane 2" in diff["frogner#tennis"].get(TEST_DATE, {}).get("17:00-18:00", []):
            _pass("Diff contains Bane 2 at 17:00-18:00")
            results.append(True)
        else:
            _fail("Expected Bane 2 at 17:00-18:00 in diff")
            results.append(False)

        # -- Step 3: Seed test user + preference --
        _step(3, "Seed test user and preference")

        dynamo.Table(USERS_TABLE).put_item(
            Item={"userId": "smoketest@test.com", "name": "Smoke Test User"}
        )
        dynamo.Table(PREFS_TABLE).put_item(
            Item={
                "userId": "smoketest@test.com",
                "preferenceId": "smoke-test-p1",
                "facilityId": "frogner",
                "dates": ["monday"],
                "timeFrom": "17:00",
                "timeTo": "22:00",
                "sport": "tennis",
            }
        )
        _pass("User and preference seeded")
        results.append(True)

        # -- Step 4: Run notifications handler --
        _step(4, "Run notifications handler (first invocation)")

        r1 = h.lambda_handler({"diff": diff}, None)
        print(f"  Response: {json.dumps(r1['summary'], indent=2)}")

        if r1["summary"]["emails_sent"] == 1:
            _pass(f"Email sent (emails_sent={r1['summary']['emails_sent']})")
            results.append(True)
        else:
            _fail(f"Expected 1 email, got {r1['summary']['emails_sent']}")
            results.append(False)

        # -- Step 5: Re-run and verify dedup --
        _step(5, "Re-run handler (verify dedup)")

        r2 = h.lambda_handler({"diff": diff}, None)
        print(f"  Response: {json.dumps(r2['summary'], indent=2)}")

        if r2["summary"]["emails_sent"] == 0 and r2["summary"]["matches_after_dedup"] == 0:
            _pass("Dedup blocked second email")
            results.append(True)
        else:
            _fail(f"Expected 0 emails and 0 matches_after_dedup, got emails_sent={r2['summary']['emails_sent']}, matches_after_dedup={r2['summary']['matches_after_dedup']}")
            results.append(False)

        # Cleanup handler state
        h._dynamodb_resource = None
        h._ses_client = None

    # -- Summary --
    print(f"\n{'='*60}")
    passed = sum(results)
    total = len(results)
    if all(results):
        print(f"  SMOKE TEST PASSED ({passed}/{total} checks)")
    else:
        print(f"  SMOKE TEST FAILED ({passed}/{total} checks passed)")
    print(f"{'='*60}\n")

    return all(results)


# ---------------------------------------------------------------------------
# Live mode
# ---------------------------------------------------------------------------


def run_live(recipient: str, profile: str | None = None, cleanup: bool = True) -> bool:
    """Run against live AWS. Returns True on success."""
    import boto3
    from datetime import datetime, timedelta

    print("\n" + "!" * 60)
    print("  WARNING: Running against LIVE AWS")
    print("  This will invoke the real tennis-notifications Lambda")
    print(f"  Email will be sent to: {recipient}")
    print("!" * 60)

    session = boto3.Session(profile_name=profile, region_name=REGION) if profile else boto3.Session(region_name=REGION)
    dynamo = session.resource("dynamodb", region_name=REGION)
    lambda_client = session.client("lambda", region_name=REGION)

    # Find next Monday
    today = datetime.now()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)
    next_monday_str = next_monday.strftime("%Y-%m-%d")
    day_name = "monday"

    smoke_pref_id = f"smoke-test-{uuid.uuid4().hex[:8]}"
    smoke_user_id = recipient

    created_items: list[dict] = []

    try:
        # -- Step 1: Seed test preference --
        _step(1, "Seed test preference in DynamoDB")

        prefs_table = dynamo.Table(PREFS_TABLE)
        pref_item = {
            "userId": smoke_user_id,
            "preferenceId": smoke_pref_id,
            "facilityId": "frogner",
            "dates": [day_name],
            "timeFrom": "17:00",
            "timeTo": "22:00",
            "sport": "tennis",
        }
        prefs_table.put_item(Item=pref_item)
        created_items.append(("pref", smoke_user_id, smoke_pref_id))
        _pass(f"Preference created: {smoke_pref_id}")

        # -- Step 2: Build synthetic diff --
        _step(2, "Build synthetic diff")

        diff = {
            "frogner#tennis": {
                next_monday_str: {
                    "17:00-18:00": ["Bane 2 (Smoke Test)"],
                },
            },
        }
        print(f"  Diff: {json.dumps(diff, indent=2)}")
        _pass("Synthetic diff built")

        # -- Step 3: Invoke Lambda --
        _step(3, "Invoke tennis-notifications Lambda")

        response = lambda_client.invoke(
            FunctionName="tennis-notifications",
            Payload=json.dumps({"diff": diff}),
        )
        payload = json.loads(response["Payload"].read())
        print(f"  Lambda response: {json.dumps(payload, indent=2)}")

        summary = payload.get("summary", {})
        if summary.get("matches_found", 0) >= 1 and summary.get("emails_sent", 0) >= 1:
            _pass(f"Email sent (matches={summary['matches_found']}, emails={summary['emails_sent']})")
        else:
            _fail(f"Expected at least 1 match and 1 email: {summary}")
            return False

        # -- Step 4: Verify dedup record --
        _step(4, "Verify dedup record in DynamoDB")

        notif_table = dynamo.Table(NOTIFICATIONS_TABLE)
        scan = notif_table.scan(
            FilterExpression="userId = :uid",
            ExpressionAttributeValues={":uid": smoke_user_id},
        )
        dedup_items = scan.get("Items", [])
        print(f"  Found {len(dedup_items)} dedup record(s)")

        if dedup_items:
            _pass("Dedup record written")
            for item in dedup_items:
                created_items.append(("dedup", item["notificationId"]))
        else:
            _fail("No dedup record found")

        # -- Step 5: Check inbox --
        _step(5, "Check your inbox")
        print(f"  Please check {recipient} for the smoke test email.")
        print("  The email should contain 'Bane 2 (Smoke Test)' at 17:00-18:00.")

        return True

    finally:
        if cleanup:
            print(f"\n  Cleaning up smoke test data...")
            for item in created_items:
                try:
                    if item[0] == "pref":
                        prefs_table.delete_item(
                            Key={"userId": item[1], "preferenceId": item[2]}
                        )
                        print(f"  Deleted preference: {item[2]}")
                    elif item[0] == "dedup":
                        notif_table.delete_item(
                            Key={"notificationId": item[1]}
                        )
                        print(f"  Deleted dedup record: {item[1]}")
                except Exception as e:
                    print(f"  Cleanup warning: {e}")
        else:
            print("\n  Skipping cleanup (--no-cleanup). Remember to clean up manually!")
            for item in created_items:
                print(f"    {item}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test for the availability pipeline")
    parser.add_argument("--live", action="store_true", help="Run against live AWS (default: local with moto)")
    parser.add_argument("--recipient", type=str, help="Email recipient for live mode (required with --live)")
    parser.add_argument("--profile", type=str, help="AWS profile name for live mode")
    parser.add_argument("--no-cleanup", action="store_true", help="Skip cleanup of test data in live mode")

    args = parser.parse_args()

    if args.live:
        if not args.recipient:
            parser.error("--recipient is required with --live")
        success = run_live(args.recipient, args.profile, cleanup=not args.no_cleanup)
    else:
        success = run_local()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
