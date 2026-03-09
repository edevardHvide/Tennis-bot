"""
AWS Lambda handler — Notification Engine.

Responsibilities:
1. Receive the scraper's diff output (new courts per facility/date).
2. Query DynamoDB ``tennis-preferences`` to find all user preferences.
3. Match each user's preferences against the diff.
4. Deduplicate against ``tennis-notifications`` to avoid re-sending.
5. Send email via AWS SES for every matched, non-duplicate notification.
6. Record sent notifications in ``tennis-notifications`` with 24h TTL.

Environment variables:
  AWS_REGION         (default eu-north-1)
  NOTIFICATIONS_TABLE (default tennis-notifications)
  PREFS_TABLE        (default tennis-preferences)
  USERS_TABLE        (default tennis-users)
  SES_FROM_EMAIL     (required — verified SES sender)
  LOG_LEVEL          (default INFO)
"""

import json
import logging
import os
import sys
import time

import boto3
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# Logging — structured JSON to CloudWatch
# ---------------------------------------------------------------------------

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)


def _log(level: str, message: str, **extra) -> None:
    """Emit a structured JSON log line."""
    record = {
        "level": level,
        "message": message,
        **extra,
    }
    getattr(logger, level.lower(), logger.info)(json.dumps(record))


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AWS_REGION = os.environ.get("AWS_REGION", "eu-north-1")
NOTIFICATIONS_TABLE = os.environ.get("NOTIFICATIONS_TABLE", "tennis-notifications")
PREFS_TABLE = os.environ.get("PREFS_TABLE", "tennis-preferences")
USERS_TABLE = os.environ.get("USERS_TABLE", "tennis-users")
SES_FROM_EMAIL = os.environ.get("SES_FROM_EMAIL", "")

# ---------------------------------------------------------------------------
# Lazy AWS resource initialisation
# ---------------------------------------------------------------------------

_dynamodb_resource = None
_ses_client = None


def _get_dynamodb():
    """Return a boto3 DynamoDB resource, creating it once per container."""
    global _dynamodb_resource
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb_resource


def _get_ses():
    """Return a boto3 SES client, creating it once per container."""
    global _ses_client
    if _ses_client is None:
        _ses_client = boto3.client("ses", region_name=AWS_REGION)
    return _ses_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scan_all_preferences(table) -> list[dict]:
    """Scan the preferences table and return all items.

    Handles pagination transparently.
    """
    items: list[dict] = []
    response = table.scan()
    items.extend(response.get("Items", []))

    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response.get("Items", []))

    return items


def _send_ses_email(recipient: str, subject: str, html_body: str, text_body: str) -> bool:
    """Send an email via SES.  Returns True on success, False on failure."""
    if not SES_FROM_EMAIL:
        _log("warning", "SES_FROM_EMAIL not configured — skipping email",
             recipient=recipient)
        return False

    try:
        _get_ses().send_email(
            Source=SES_FROM_EMAIL,
            Destination={"ToAddresses": [recipient]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Html": {"Data": html_body, "Charset": "UTF-8"},
                    "Text": {"Data": text_body, "Charset": "UTF-8"},
                },
            },
        )
        return True
    except ClientError as exc:
        _log("error", "SES send_email failed",
             recipient=recipient, error=str(exc))
        return False


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------


def lambda_handler(event: dict, context) -> dict:
    """AWS Lambda handler entry point.

    Args:
        event:   Dict with a ``diff`` key containing the scraper output
                 (facility_key -> date_str -> time_slot -> [court_name]).
        context: Lambda runtime context.

    Returns:
        Dict with statusCode and summary stats.
    """
    invocation_start = time.monotonic()

    _log("info", "Notification Lambda invoked",
         region=AWS_REGION, notifications_table=NOTIFICATIONS_TABLE,
         prefs_table=PREFS_TABLE)

    # Lazy imports from sibling modules
    from matcher import match_preferences          # noqa: PLC0415
    from dedup import filter_already_notified, record_notifications  # noqa: PLC0415
    from email_builder import build_notification_email               # noqa: PLC0415

    diff = event.get("diff", {})

    if not diff:
        _log("info", "Empty diff — nothing to notify")
        return {
            "statusCode": 200,
            "summary": {
                "preferences_scanned": 0,
                "matches_found": 0,
                "matches_after_dedup": 0,
                "emails_sent": 0,
                "notifications_recorded": 0,
                "duration_ms": 0,
            },
        }

    dynamo = _get_dynamodb()
    prefs_table = dynamo.Table(PREFS_TABLE)
    notif_table = dynamo.Table(NOTIFICATIONS_TABLE)

    # Step 1 — Load all preferences
    preferences = _scan_all_preferences(prefs_table)
    _log("info", "Loaded preferences", count=len(preferences))

    # Step 2 — Match preferences against diff
    matches = match_preferences(diff, preferences)
    _log("info", "Preference matching complete", matches=len(matches))

    # Step 3 — Deduplicate
    filtered_matches = filter_already_notified(matches, notif_table)
    _log("info", "Deduplication complete",
         before=len(matches), after=len(filtered_matches))

    # Step 4 — Group by user and send emails
    user_matches: dict[str, list[dict]] = {}
    for match in filtered_matches:
        user_matches.setdefault(match["userId"], []).append(match)

    emails_sent = 0
    for user_id, user_match_list in user_matches.items():
        email = build_notification_email(user_id, user_match_list)
        success = _send_ses_email(
            recipient=user_id,
            subject=email["subject"],
            html_body=email["html_body"],
            text_body=email["text_body"],
        )
        if success:
            emails_sent += 1

    _log("info", "Emails sent", count=emails_sent)

    # Step 5 — Record notifications
    recorded = record_notifications(filtered_matches, notif_table)
    _log("info", "Notifications recorded", count=recorded)

    total_duration_ms = round((time.monotonic() - invocation_start) * 1000)

    _log("info", "Notification Lambda complete",
         emails_sent=emails_sent,
         notifications_recorded=recorded,
         duration_ms=total_duration_ms)

    return {
        "statusCode": 200,
        "summary": {
            "preferences_scanned": len(preferences),
            "matches_found": len(matches),
            "matches_after_dedup": len(filtered_matches),
            "emails_sent": emails_sent,
            "notifications_recorded": recorded,
            "duration_ms": total_duration_ms,
        },
    }
