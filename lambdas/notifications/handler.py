"""
AWS Lambda handler — Notification Engine (multi-sport).

Supports tennis, padel, and other sports defined in ``facilities.py``.
The scraper diff uses composite keys (``facilityId#sport``) and preferences
include a ``sport`` field (defaulting to ``"tennis"`` for backwards
compatibility).

Responsibilities:
1. Receive the scraper's diff output (new courts per facility+sport/date).
2. Query DynamoDB ``tennis-preferences`` to find all user preferences.
3. Match each user's preferences against the diff (facility + sport + date
   + time window + optional court type filter).
4. Deduplicate against ``tennis-notifications`` to avoid re-sending.
5. Send email via AWS SES for every matched, non-duplicate notification.
6. Record sent notifications in ``tennis-notifications`` with 24h TTL.

Environment variables:
  AWS_REGION         (default eu-north-1)
  NOTIFICATIONS_TABLE (default tennis-notifications)
  PREFS_TABLE        (default tennis-preferences)
  USERS_TABLE        (default tennis-users)
  SES_FROM_EMAIL     (fallback SES sender if SMTP is not configured)
  SMTP_HOST          (e.g. smtp.gmail.com — if set, SMTP is used instead of SES)
  SMTP_PORT          (default 587)
  SMTP_USER          (SMTP login username)
  SMTP_PASS          (SMTP login password)
  EMAIL_FROM         (sender address for SMTP)
  LOG_LEVEL          (default INFO)
"""

import json
import logging
import os
import smtplib
import sys
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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
WEATHER_TABLE = os.environ.get("WEATHER_TABLE", "tennis-weather")
SES_FROM_EMAIL = os.environ.get("SES_FROM_EMAIL", "")

# SMTP configuration (takes priority over SES when SMTP_HOST is set)
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")

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


def _send_smtp_email(recipient: str, subject: str, html_body: str, text_body: str) -> bool:
    """Send an email via SMTP (e.g. Gmail).  Returns True on success."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = recipient
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(EMAIL_FROM, [recipient], msg.as_string())
        return True
    except Exception as exc:
        _log("error", "SMTP send failed",
             recipient=recipient, error=str(exc))
        return False


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


def _send_email(recipient: str, subject: str, html_body: str, text_body: str) -> bool:
    """Send an email via SMTP if configured, otherwise fall back to SES."""
    if SMTP_HOST:
        return _send_smtp_email(recipient, subject, html_body, text_body)
    return _send_ses_email(recipient, subject, html_body, text_body)


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
    from email_builder import build_notification_email, sport_group_for  # noqa: PLC0415
    from weather import make_weather_lookup                          # noqa: PLC0415
    from facilities import get_weather_region                        # noqa: PLC0415

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
    weather_table = dynamo.Table(WEATHER_TABLE)
    weather_lookup = make_weather_lookup(weather_table, get_weather_region)

    # Step 1 — Load all preferences
    preferences = _scan_all_preferences(prefs_table)
    _log("info", "Loaded preferences", count=len(preferences))

    # Step 1b — Load blacklisted dates per user
    users_table = dynamo.Table(USERS_TABLE)
    user_ids = {p["userId"] for p in preferences if p.get("userId")}
    blacklisted_dates: dict[str, set[str]] = {}
    for uid in user_ids:
        result = users_table.get_item(Key={"userId": uid})
        dates = result.get("Item", {}).get("blacklistedDates", [])
        if dates:
            blacklisted_dates[uid] = set(dates)

    # Step 2 — Match preferences against diff
    matches = match_preferences(diff, preferences, blacklisted_dates)
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
        # Partition this user's matches by sport-group so a golfer never gets
        # racket vocabulary and vice versa. One email per non-empty group.
        by_group: dict[str, list[dict]] = {}
        for m in user_match_list:
            group = sport_group_for(m.get("sport", "tennis"))
            by_group.setdefault(group, []).append(m)

        for group, group_matches in by_group.items():
            email = build_notification_email(
                user_id, group_matches,
                weather_lookup=weather_lookup,
                sport_group=group,
            )
            success = _send_email(
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
