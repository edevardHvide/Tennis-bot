"""
Matchi.se availability scraper — no CLI dependencies.

Ported from fetch_available_slots() in check_availability.py.
"""

import requests
from bs4 import BeautifulSoup

MATCHI_SCHEDULE_URL = "https://www.matchi.se/book/schedule"


def fetch_available_slots(facility_id: int, date_str: str) -> dict[str, list[str]]:
    """Fetch available slots for a specific facility and date.

    Args:
        facility_id: Matchi integer facility ID.
        date_str: Date in YYYY-MM-DD format.

    Returns:
        Dict mapping time-slot label (e.g. "17:00-18:00") to a list of court
        names available in that slot.  Returns an empty dict when there are no
        available slots or when the page cannot be fetched.

    Raises:
        requests.HTTPError: on a non-2xx HTTP response.
    """
    params = {
        "wl": "",
        "facilityId": facility_id,
        "date": date_str,
        "sport": "1",
    }

    response = requests.get(MATCHI_SCHEDULE_URL, params=params, timeout=30)
    response.raise_for_status()

    return parse_slots_from_html(response.text)


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
