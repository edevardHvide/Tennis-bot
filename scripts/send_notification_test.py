"""
Send a single test notification email to one recipient, using the real
notifications/email_builder.py + weather lookup. Bypasses the Lambda matcher
so it doesn't fan out to other users.

Usage:
    python scripts/send_notification_test.py
"""

import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import boto3
from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "lambdas" / "notifications"))

from email_builder import build_notification_email  # noqa: E402
from weather import make_weather_lookup             # noqa: E402
from facilities import get_weather_region           # noqa: E402

RECIPIENT = "edevard.hvide@gmail.com"

RACKET_MATCHES = [
    {
        "userId": RECIPIENT,
        "preferenceId": "test",
        "facilityId": "frogner",
        "sport": "tennis",
        "date": "2026-05-15",
        "courts": [
            {"time_slot": "17:00-18:00", "court_name": "Court 1 (test)"},
            {"time_slot": "19:00-20:00", "court_name": "Court 2 (test)"},
        ],
    },
    {
        "userId": RECIPIENT,
        "preferenceId": "test",
        "facilityId": "frogner",
        "sport": "tennis",
        "date": "2026-05-16",
        "courts": [
            {"time_slot": "16:00-17:00", "court_name": "Court 3 (test)"},
        ],
    },
]

GOLF_MATCHES = [
    {
        "userId": RECIPIENT,
        "preferenceId": "test-golf",
        "facilityId": "grini",
        "sport": "golf",
        "date": "2026-05-16",
        "courts": [
            {"time_slot": "09:30", "court_name": "4 spots (845,-)"},
            {"time_slot": "11:00", "court_name": "2 spots (845,-)"},
        ],
    },
    {
        "userId": RECIPIENT,
        "preferenceId": "test-golf",
        "facilityId": "onsoy",
        "sport": "golf",
        "date": "2026-05-17",
        "courts": [
            {"time_slot": "10:30", "court_name": "3 spots (695,-)"},
        ],
    },
]


def _send(subject: str, html_body: str, text_body: str, env: dict) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = env["EMAIL_FROM"]
    msg["To"] = RECIPIENT
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    with smtplib.SMTP(env["SMTP_HOST"], int(env["SMTP_PORT"]), timeout=30) as server:
        server.starttls()
        server.login(env["SMTP_USER"], env["SMTP_PASS"])
        server.sendmail(env["EMAIL_FROM"], [RECIPIENT], msg.as_string())


def main() -> None:
    env = dotenv_values(REPO_ROOT / ".env")
    os.environ.setdefault("EMAIL_FROM", env.get("EMAIL_FROM", ""))

    dynamo = boto3.Session(profile_name="tennis-bot", region_name="eu-north-1").resource("dynamodb")
    weather_table = dynamo.Table("tennis-weather")
    weather_lookup = make_weather_lookup(weather_table, get_weather_region)

    racket = build_notification_email(RECIPIENT, RACKET_MATCHES, weather_lookup=weather_lookup, sport_group="racket")
    _send("[TEST RACKET] " + racket["subject"], racket["html_body"], racket["text_body"], env)
    print(f"Sent RACKET test email — {racket['subject']}")

    golf = build_notification_email(RECIPIENT, GOLF_MATCHES, weather_lookup=weather_lookup, sport_group="golf")
    _send("[TEST GOLF] " + golf["subject"], golf["html_body"], golf["text_body"], env)
    print(f"Sent GOLF test email — {golf['subject']}")


if __name__ == "__main__":
    main()
