#!/usr/bin/env python3
"""
Festival ticket availability monitor.

Runs on a cron schedule. Checks festival ticket availability using the
Playwright-based scraper, compares against previous state in DynamoDB,
and sends email alerts when tickets become available.

Uses the same SMTP/SES email engine as the tennis notifications Lambda.

Usage:
    python3 scripts/festival_monitor.py
    python3 scripts/festival_monitor.py --dry-run    # don't send emails or write to DynamoDB

Environment variables (via .env file):
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM
    AWS_PROFILE (or IAM role on EC2)
"""

import json
import logging
import os
import smtplib
import sys
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# Add repo root to path so we can import festivals.py and the scraper
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import boto3
from botocore.exceptions import ClientError

from festivals import FESTIVALS
from ticketmaster_scraper import scrape

# ---------------------------------------------------------------------------
# Load .env if present
# ---------------------------------------------------------------------------

_ENV_FILE = REPO_ROOT / ".env"
if _ENV_FILE.exists():
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip("'\""))

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REGION = os.environ.get("AWS_REGION", "eu-north-1")
AVAILABILITY_TABLE = os.environ.get("FESTIVAL_AVAILABILITY_TABLE", "festival-availability")
SUBSCRIPTIONS_TABLE = os.environ.get("FESTIVAL_SUBSCRIPTIONS_TABLE", "festival-subscriptions")

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")
SES_FROM_EMAIL = os.environ.get("SES_FROM_EMAIL", "")

WEBAPP_URL = "https://availabilitymonitor.club"

# Dedup: don't re-notify a user within this window
NOTIFY_COOLDOWN = timedelta(hours=24)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("festival_monitor")

# ---------------------------------------------------------------------------
# DynamoDB
# ---------------------------------------------------------------------------

_dynamodb = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        profile = os.environ.get("AWS_PROFILE")
        session = boto3.Session(profile_name=profile, region_name=REGION)
        _dynamodb = session.resource("dynamodb")
    return _dynamodb


def _availability_table():
    return _get_dynamodb().Table(AVAILABILITY_TABLE)


def _subscriptions_table():
    return _get_dynamodb().Table(SUBSCRIPTIONS_TABLE)


# ---------------------------------------------------------------------------
# Email engine (same pattern as lambdas/notifications/handler.py:130-181)
# ---------------------------------------------------------------------------

_ses_client = None


def _get_ses():
    global _ses_client
    if _ses_client is None:
        profile = os.environ.get("AWS_PROFILE")
        session = boto3.Session(profile_name=profile, region_name=REGION)
        _ses_client = session.client("ses")
    return _ses_client


def _send_smtp_email(recipient: str, subject: str, html_body: str, text_body: str) -> bool:
    """Send an email via SMTP (e.g. Gmail). Returns True on success."""
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
        log.error("SMTP send failed: recipient=%s error=%s", recipient, exc)
        return False


def _send_ses_email(recipient: str, subject: str, html_body: str, text_body: str) -> bool:
    """Send an email via SES. Returns True on success."""
    if not SES_FROM_EMAIL:
        log.warning("SES_FROM_EMAIL not configured — skipping email to %s", recipient)
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
        log.error("SES send failed: recipient=%s error=%s", recipient, exc)
        return False


def _send_email(recipient: str, subject: str, html_body: str, text_body: str) -> bool:
    """Send via SMTP if configured, otherwise fall back to SES."""
    if SMTP_HOST:
        return _send_smtp_email(recipient, subject, html_body, text_body)
    return _send_ses_email(recipient, subject, html_body, text_body)


# ---------------------------------------------------------------------------
# Email content
# ---------------------------------------------------------------------------

def _build_festival_email(festival: dict) -> tuple[str, str, str]:
    """Build subject, HTML body, and plain text body for a festival alert."""
    name = festival["name"]
    url = festival["url"]
    location = festival.get("location", "")
    dates = festival.get("dates", "")

    subject = f"Resale tickets spotted! {name}"

    html_body = f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0; padding:0; background-color:#faf5ee; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:520px; margin:0 auto; padding:32px 20px;">

    <div style="background:linear-gradient(135deg, #f59e0b 0%, #d97706 100%); border-radius:12px 12px 0 0; padding:28px 24px; text-align:center;">
      <div style="font-size:32px; margin-bottom:8px;">🎫</div>
      <h1 style="margin:0; color:#fff; font-size:22px; font-weight:700;">Tickets Available!</h1>
    </div>

    <div style="background:#ffffff; border:1px solid #e5e0d5; border-top:none; border-radius:0 0 12px 12px; padding:28px 24px;">
      <p style="margin:0 0 4px; font-size:18px; font-weight:600; color:#1a1a1a;">{name}</p>
      <p style="margin:0 0 20px; font-size:14px; color:#6b6b6b;">{dates} · {location}</p>

      <p style="margin:0 0 24px; font-size:15px; line-height:1.6; color:#333;">
        Resale tickets have appeared on the ticket page. Act fast — they may not last long!
      </p>

      <div style="text-align:center; margin:0 0 24px;">
        <a href="{url}" style="display:inline-block; background:#f59e0b; color:#fff; font-weight:600; font-size:15px; text-decoration:none; padding:14px 32px; border-radius:8px;">
          Go to Ticket Page →
        </a>
      </div>

      <hr style="border:none; border-top:1px solid #eee; margin:24px 0;" />

      <p style="margin:0; font-size:12px; color:#999; text-align:center;">
        This is an automated alert from
        <a href="{WEBAPP_URL}" style="color:#d97706; text-decoration:none;">Availability Monitor</a> (beta).
        <br />Manage your alerts at {WEBAPP_URL}
      </p>
    </div>
  </div>
</body>
</html>"""

    text_body = f"""\
TICKETS AVAILABLE — {name}

{dates} · {location}

Resale tickets have appeared on the ticket page!
Act fast — they may not last long.

Go to ticket page: {url}

---
Automated alert from Availability Monitor (beta)
Manage your alerts: {WEBAPP_URL}
"""

    return subject, html_body, text_body


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def load_previous_state(festival_id: str) :
    """Load previous availability state from DynamoDB."""
    try:
        resp = _availability_table().get_item(Key={"festivalId": festival_id})
        return resp.get("Item")
    except Exception as exc:
        log.warning("Failed to load state for %s: %s", festival_id, exc)
        return None


def save_state(festival_id: str, result: dict):
    """Persist current availability state to DynamoDB."""
    _availability_table().put_item(Item={
        "festivalId": festival_id,
        "ticketAvailable": result.get("ticket_available"),
        "ticketStatusText": result.get("ticket_status_text", "Unknown"),
        "lastCheckedAt": datetime.now(timezone.utc).isoformat(),
        "rawSignals": result.get("raw_signals", []),
        "platform": result.get("platform", "unknown"),
    })


def get_subscribers(festival_id: str) :
    """Get all users subscribed to this festival with enabled=True."""
    try:
        # Scan the table filtering by festivalId and enabled
        # For a small beta with few users, scan is fine
        resp = _subscriptions_table().scan(
            FilterExpression="festivalId = :fid AND enabled = :en",
            ExpressionAttributeValues={
                ":fid": festival_id,
                ":en": True,
            },
        )
        return resp.get("Items", [])
    except Exception as exc:
        log.warning("Failed to get subscribers for %s: %s", festival_id, exc)
        return []


def should_notify(sub: dict) -> bool:
    """Check if we should notify this subscriber (cooldown check)."""
    last = sub.get("lastNotifiedAt")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
        return datetime.now(timezone.utc) - last_dt > NOTIFY_COOLDOWN
    except (ValueError, TypeError):
        return True


def record_notification(user_id: str, festival_id: str):
    """Update lastNotifiedAt on the subscription record."""
    try:
        _subscriptions_table().update_item(
            Key={"userId": user_id, "festivalId": festival_id},
            UpdateExpression="SET lastNotifiedAt = :ts",
            ExpressionAttributeValues={
                ":ts": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:
        log.warning("Failed to record notification: user=%s festival=%s error=%s",
                     user_id, festival_id, exc)


def check_festival(festival_id: str, config: dict, dry_run: bool = False) :
    """Check a single festival and send alerts if tickets appeared."""
    log.info("Checking %s (%s)", config["name"], config["url"])

    # Scrape current state
    result = scrape(config["url"], headed=False)
    current_available = result.get("ticket_available")
    status_text = result.get("ticket_status_text", "Unknown")

    log.info("  Status: %s (available=%s)", status_text, current_available)

    # Load previous state
    prev = load_previous_state(festival_id)
    prev_available = prev.get("ticketAvailable") if prev else None

    # Save new state
    if not dry_run:
        save_state(festival_id, result)

    # Check for state change: tickets became available
    tickets_appeared = (current_available is True) and (prev_available is not True)

    summary = {
        "festivalId": festival_id,
        "name": config["name"],
        "previousAvailable": prev_available,
        "currentAvailable": current_available,
        "statusText": status_text,
        "ticketsAppeared": tickets_appeared,
        "emailsSent": 0,
    }

    if not tickets_appeared:
        if current_available is True and prev_available is True:
            log.info("  Still available (no new alert needed)")
        else:
            log.info("  No change — tickets still %s", status_text.lower())
        return summary

    # Tickets appeared! Notify subscribers.
    log.info("  TICKETS APPEARED! Notifying subscribers...")

    subscribers = get_subscribers(festival_id)
    log.info("  %d subscriber(s) found", len(subscribers))

    subject, html_body, text_body = _build_festival_email(config)

    for sub in subscribers:
        user_id = sub["userId"]

        if not should_notify(sub):
            log.info("  Skipping %s (notified recently)", user_id)
            continue

        if dry_run:
            log.info("  [DRY RUN] Would email %s", user_id)
            summary["emailsSent"] += 1
            continue

        if _send_email(user_id, subject, html_body, text_body):
            log.info("  Emailed %s", user_id)
            record_notification(user_id, festival_id)
            summary["emailsSent"] += 1
        else:
            log.error("  Failed to email %s", user_id)

    return summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Festival ticket monitor")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't send emails or write to DynamoDB")
    args = parser.parse_args()

    log.info("=" * 50)
    log.info("Festival Ticket Monitor")
    log.info("=" * 50)

    summaries = []
    for fid, config in FESTIVALS.items():
        try:
            summary = check_festival(fid, config, dry_run=args.dry_run)
            summaries.append(summary)
        except Exception as exc:
            log.error("Failed to check %s: %s", fid, exc)
            summaries.append({
                "festivalId": fid,
                "name": config["name"],
                "error": str(exc),
            })

    log.info("")
    log.info("=" * 50)
    log.info("SUMMARY")
    log.info("=" * 50)
    for s in summaries:
        if "error" in s:
            log.error("  [!] %s — ERROR: %s", s["name"], s["error"])
        else:
            icon = {True: "✓", False: "✗"}.get(s["currentAvailable"], "?")
            log.info("  [%s] %s — %s (emails: %d)",
                     icon, s["name"], s["statusText"], s["emailsSent"])


if __name__ == "__main__":
    main()
