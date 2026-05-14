"""
AWS Lambda handler — Weekly Newsletter.

Responsibilities:
1. Compute the coming week (next Monday → Sunday).
2. Read full availability from DynamoDB ``tennis-availability`` for all
   facilities and all 7 days.
3. Match against user preferences using the shared ``matcher`` module.
4. Send one summary email per user via AWS SES.
5. If ``NEWSLETTER_TEST_RECIPIENT`` is set, restrict delivery to that address.

Environment variables:
  AWS_REGION              (default eu-north-1)
  AVAILABILITY_TABLE      (default tennis-availability)
  PREFS_TABLE             (default tennis-preferences)
  USERS_TABLE             (default tennis-users)
  SES_FROM_EMAIL          (fallback SES sender if SMTP is not configured)
  SMTP_HOST               (e.g. smtp.gmail.com — if set, SMTP is used instead of SES)
  SMTP_PORT               (default 587)
  SMTP_USER               (SMTP login username)
  SMTP_PASS               (SMTP login password)
  EMAIL_FROM              (sender address for SMTP)
  NEWSLETTER_TEST_RECIPIENT  (optional — restrict to single recipient)
  LOG_LEVEL               (default INFO)
"""

import datetime
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
AVAILABILITY_TABLE = os.environ.get("AVAILABILITY_TABLE", "tennis-availability")
PREFS_TABLE = os.environ.get("PREFS_TABLE", "tennis-preferences")
USERS_TABLE = os.environ.get("USERS_TABLE", "tennis-users")
WEATHER_TABLE = os.environ.get("WEATHER_TABLE", "tennis-weather")
SES_FROM_EMAIL = os.environ.get("SES_FROM_EMAIL", "")
NEWSLETTER_TEST_RECIPIENT = os.environ.get("NEWSLETTER_TEST_RECIPIENT", "")

# SMTP configuration (takes priority over SES when SMTP_HOST is set)
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")

from facilities import facilities, get_sports

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


def _compute_next_week() -> list[str]:
    """Return 7 date strings (Mon–Sun) for the coming week.

    "Coming week" means the next Monday from today through the following
    Sunday.  If today is Monday, it returns *next* Monday (7 days out).
    """
    today = datetime.date.today()
    days_until_monday = (7 - today.weekday()) % 7 or 7
    monday = today + datetime.timedelta(days=days_until_monday)
    return [
        (monday + datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(7)
    ]


def _load_availability(table, dates: list[str]) -> dict:
    """Read full availability from DynamoDB for all facilities and dates.

    Iterates over every (facility, sport) pair and uses the composite key
    ``"facility#sport"`` when querying DynamoDB.  The returned dict is keyed
    by the same composite key so it feeds directly into the matcher.

    Returns:
        Dict matching the diff format: composite_key -> date_str -> time_slot -> [court_name]
    """
    availability: dict[str, dict[str, dict[str, list[str]]]] = {}

    for facility_key in facilities:
        for sport in get_sports(facility_key):
            composite_key = f"{facility_key}#{sport}"
            for date_str in dates:
                try:
                    response = table.get_item(
                        Key={"facilityId": composite_key, "date": date_str}
                    )
                    item = response.get("Item")
                    if item and "slots" in item:
                        slots = json.loads(item["slots"])
                        if slots:
                            availability.setdefault(composite_key, {})[date_str] = slots
                except ClientError as exc:
                    _log("warning", "Failed to load availability",
                         facility=composite_key, date=date_str, error=str(exc))

    return availability


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
        event:   Lambda invocation event (unused — runs on a schedule).
        context: Lambda runtime context.

    Returns:
        Dict with statusCode and summary stats.
    """
    invocation_start = time.monotonic()

    _log("info", "Newsletter Lambda invoked",
         region=AWS_REGION, availability_table=AVAILABILITY_TABLE,
         prefs_table=PREFS_TABLE)

    from matcher import match_preferences              # noqa: PLC0415
    from email_builder import build_newsletter_email, sport_group_for  # noqa: PLC0415
    from weather import make_weather_lookup            # noqa: PLC0415
    from facilities import get_weather_region          # noqa: PLC0415

    dynamo = _get_dynamodb()
    weather_table = dynamo.Table(WEATHER_TABLE)
    weather_lookup = make_weather_lookup(weather_table, get_weather_region)

    # Step 1 — Compute coming week dates
    week_dates = _compute_next_week()
    week_start = week_dates[0]
    week_end = week_dates[-1]

    _log("info", "Week range", start=week_start, end=week_end)

    # Step 2 — Load availability
    avail_table = dynamo.Table(AVAILABILITY_TABLE)
    availability = _load_availability(avail_table, week_dates)

    total_slots = sum(
        len(courts)
        for dates_map in availability.values()
        for slots in dates_map.values()
        for courts in slots.values()
    )
    _log("info", "Loaded availability", facilities=len(availability), total_slots=total_slots)

    if not availability:
        _log("info", "No availability data — nothing to send")
        return {
            "statusCode": 200,
            "summary": {
                "availability_slots": 0,
                "preferences_scanned": 0,
                "matches_found": 0,
                "emails_sent": 0,
                "duration_ms": 0,
            },
        }

    # Step 3 — Load preferences
    prefs_table = dynamo.Table(PREFS_TABLE)
    preferences = _scan_all_preferences(prefs_table)
    _log("info", "Loaded preferences", count=len(preferences))

    if not preferences:
        _log("info", "No preferences — nothing to send")
        return {
            "statusCode": 200,
            "summary": {
                "availability_slots": total_slots,
                "preferences_scanned": 0,
                "matches_found": 0,
                "emails_sent": 0,
                "duration_ms": round((time.monotonic() - invocation_start) * 1000),
            },
        }

    # Step 4 — Match preferences against availability
    matches = match_preferences(availability, preferences)
    _log("info", "Matching complete", matches=len(matches))

    # Step 5 — Group by user
    user_matches: dict[str, list[dict]] = {}
    for match in matches:
        user_matches.setdefault(match["userId"], []).append(match)

    # Step 6 — Test mode filter
    if NEWSLETTER_TEST_RECIPIENT:
        _log("info", "Test mode — restricting to recipient",
             recipient=NEWSLETTER_TEST_RECIPIENT)
        if NEWSLETTER_TEST_RECIPIENT in user_matches:
            user_matches = {NEWSLETTER_TEST_RECIPIENT: user_matches[NEWSLETTER_TEST_RECIPIENT]}
        else:
            user_matches = {}

    # Step 7 — Send emails (one per sport-group per user)
    emails_sent = 0
    for user_id, user_match_list in user_matches.items():
        by_group: dict[str, list[dict]] = {}
        for m in user_match_list:
            group = sport_group_for(m.get("sport", "tennis"))
            by_group.setdefault(group, []).append(m)

        for group, group_matches in by_group.items():
            email = build_newsletter_email(
                user_id, group_matches, week_start, week_end,
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

    total_duration_ms = round((time.monotonic() - invocation_start) * 1000)

    _log("info", "Newsletter Lambda complete",
         emails_sent=emails_sent,
         duration_ms=total_duration_ms)

    return {
        "statusCode": 200,
        "summary": {
            "availability_slots": total_slots,
            "preferences_scanned": len(preferences),
            "matches_found": len(matches),
            "users_matched": len(user_matches),
            "emails_sent": emails_sent,
            "week_start": week_start,
            "week_end": week_end,
            "duration_ms": total_duration_ms,
        },
    }
