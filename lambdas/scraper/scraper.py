"""
Matchi.se availability scraper — no CLI dependencies.

Ported from fetch_available_slots() in check_availability.py.

Includes retry logic with exponential backoff for transient HTTP errors.
"""

import logging
import time

import requests
from bs4 import BeautifulSoup
from facilities import SPORT_CODES

logger = logging.getLogger(__name__)

MATCHI_SCHEDULE_URL = "https://www.matchi.se/book/schedule"

MAX_RETRIES = 3
BACKOFF_BASE = 1  # seconds


def fetch_available_slots(
    facility_id: int, date_str: str, sport: str = "tennis"
) -> dict[str, list[str]]:
    """Fetch available slots for a specific facility, date, and sport.

    Retries up to MAX_RETRIES times with exponential backoff (1s, 2s, 4s) on
    HTTP errors or request timeouts.

    Args:
        facility_id: Matchi integer facility ID.
        date_str: Date in YYYY-MM-DD format.
        sport: Sport name (e.g. "tennis", "padel"). Mapped to Matchi sport code.

    Returns:
        Dict mapping time-slot label (e.g. "17:00-18:00") to a list of court
        names available in that slot.  Returns an empty dict when there are no
        available slots or when the page cannot be fetched.

    Raises:
        requests.RequestException: after all retry attempts are exhausted.
    """
    sport_code = str(SPORT_CODES.get(sport, 1))
    params = {
        "wl": "",
        "facilityId": facility_id,
        "date": date_str,
        "sport": sport_code,
    }

    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(MATCHI_SCHEDULE_URL, params=params, timeout=30)
            response.raise_for_status()
            return parse_slots_from_html(response.text)
        except (requests.RequestException, requests.Timeout) as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                # Back off longer on 429 rate-limit responses
                if hasattr(exc, 'response') and exc.response is not None and exc.response.status_code == 429:
                    sleep_time = BACKOFF_BASE * (2 ** (attempt + 2))  # 4s, 8s
                else:
                    sleep_time = BACKOFF_BASE * (2 ** attempt)        # 1s, 2s
                logger.warning(
                    "Fetch attempt %d/%d failed for facility %s date %s: %s. "
                    "Retrying in %ds...",
                    attempt + 1, MAX_RETRIES, facility_id, date_str,
                    exc, sleep_time,
                )
                time.sleep(sleep_time)
            else:
                logger.error(
                    "All %d fetch attempts failed for facility %s date %s: %s",
                    MAX_RETRIES, facility_id, date_str, exc,
                )
    raise last_exc


def parse_slots_from_html(html: str) -> dict[str, list[str]]:
    """Parse a Matchi schedule HTML page and return available slot data.

    Exposed separately so unit tests can inject fixture HTML without making
    real HTTP requests.

    Args:
        html: Raw HTML string of the Matchi schedule page.

    Returns:
        Dict mapping time-slot label to list of court names.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Available slots are <td class="slot free"> elements.
    # The `title` attribute contains <br>-separated parts:
    #   [0] unused header text
    #   [1] court name  (e.g. "Bane 3")
    #   [2] time slot label  (e.g. "17:00-18:00")
    available_slots = soup.find_all("td", class_="slot free")

    time_slot_dict: dict[str, list[str]] = {}

    for slot in available_slots:
        title = slot.get("title", "")
        parts = title.split("<br>")
        if len(parts) < 3:
            # Unexpected format — skip rather than crash.
            continue

        court = parts[1].strip()
        time_label = parts[2].strip()

        if not court or not time_label:
            continue

        time_slot_dict.setdefault(time_label, []).append(court)

    return time_slot_dict
