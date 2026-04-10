"""
Harvard Recreation Innosoft Fusion scraper.

Fetches lesson availability from:
  GET https://membership.gocrimson.com/Program/GetProgramInstances?programID=...

Availability ground truth: .spots-tag p text (NOT ClassSize arithmetic).
"""

import json
import logging
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

PROGRAM_URL = "https://membership.gocrimson.com/Program/GetProgramInstances"

MAX_RETRIES = 3
BACKOFF_BASE = 1  # seconds

_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_lesson_instances(program_id: str) -> list:
    """Fetch lesson availability from Harvard Rec Innosoft Fusion endpoint.

    Retries up to MAX_RETRIES times with exponential backoff on HTTP errors.

    Args:
        program_id: Innosoft Fusion program GUID, e.g.
            "a20e7ae2-fedc-4a8e-a7c3-236695040c63"

    Returns:
        List of available lesson dicts with keys: date, time_slot, location.

    Raises:
        requests.HTTPError: On non-200 HTTP response after all retries.
        ValueError: If #ApptInfo input is missing from the HTML response.
    """
    session = requests.Session()
    session.headers.update(_BROWSER_HEADERS)

    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(PROGRAM_URL, params={"programID": program_id}, timeout=30)
            resp.raise_for_status()  # Never swallow HTTP errors — surface as Lambda error
            return parse_harvard_availability(resp.text)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                sleep_time = BACKOFF_BASE * (2 ** attempt)  # 1s, 2s
                logger.warning(
                    "Fetch attempt %d/%d failed: %s. Retrying in %ds...",
                    attempt + 1, MAX_RETRIES, exc, sleep_time,
                )
                time.sleep(sleep_time)
            else:
                logger.error("All %d fetch attempts failed: %s", MAX_RETRIES, exc)
    raise last_exc


def parse_harvard_availability(html: str) -> list:
    """Parse Innosoft Fusion HTML response.

    Availability ground truth is .spots-tag p text — NOT ClassSize arithmetic.
    ClassSize - NumberRegistered does not account for holds and pending payments.

    Filters out past-dated lessons (StartDate <= now) even if they show spots.

    Args:
        html: Raw HTML string from GetProgramInstances endpoint.

    Returns:
        List of available lesson dicts:
            [{"date": "YYYY-MM-DD", "time_slot": "HH:MM-HH:MM", "location": "..."}]

    Raises:
        ValueError: If #ApptInfo input is not found in the HTML.
    """
    soup = BeautifulSoup(html, "html.parser")

    appt_input = soup.find("input", {"id": "ApptInfo"})
    if not appt_input or not appt_input.get("value"):
        raise ValueError(
            "ApptInfo input not found in HTML response — "
            "Innosoft Fusion page structure may have changed"
        )

    appointments = json.loads(appt_input["value"])
    spot_tags = soup.find_all(class_="spots-tag")

    now = datetime.now(timezone.utc)
    available = []

    for i, appt in enumerate(appointments):
        # Parse start datetime — Innosoft returns ISO format (no timezone, treat as UTC)
        start_dt = datetime.fromisoformat(appt["StartDate"])
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)

        # Filter past-dated lessons — server may not close them promptly
        if start_dt <= now:
            continue

        # Availability ground truth: .spots-tag p text at same index as appointment
        is_available = False
        if i < len(spot_tags):
            p = spot_tags[i].find("p")
            if p:
                text = p.get_text(strip=True).lower()
                # Available = contains "spot" AND NOT "no spots" AND NOT "waitlist"
                is_available = (
                    "spot" in text
                    and "no spots" not in text
                    and "waitlist" not in text
                )

        if not is_available:
            continue

        end_dt = datetime.fromisoformat(appt["EndDate"])
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)

        available.append({
            "date": start_dt.strftime("%Y-%m-%d"),
            "time_slot": f"{start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')}",
            "location": appt.get("Location", ""),
        })

    return available
