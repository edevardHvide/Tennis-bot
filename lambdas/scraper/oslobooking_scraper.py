"""Oslo kommune booking platform scraper.

Fetches availability for public booking assets hosted on
``booking.oslo.kommune.no``. The backend exposes a public JSON API — no
authentication, cookies or CSRF tokens required.

Endpoint (verified 2026-04-12):

    GET https://api.booking.oslo.kommune.no/api/bookableasset/availabletime
        ?bookableAssetId={uuid}&date=YYYY-MM-DD&duration=PT1H

Response shape:

    [{"start":"09:00:00","end":"10:00:00","id":null}, ...]

Quirks:

* The API returns start times on a **30-minute stride** (09:00, 09:30,
  10:00, ...). Each entry still represents a 1-hour booking slot, but the
  overlapping starts would show up as duplicate ``09:00-10:00`` /
  ``09:30-10:30`` notifications. We filter to on-the-hour starts only so
  the output matches Matchi's 1-hour semantics.
* An empty array is a valid response (e.g. date before today, or beyond
  the 7-day booking horizon). Callers must not treat ``[]`` as an error.
* The API is served over a CDN and has been observed responding in
  <500ms. Retry/backoff mirrors ``scraper.py`` for symmetry.

Output shape intentionally matches :func:`scraper.fetch_available_slots`
so that downstream diff / notification code is source-agnostic::

    {"09:00-10:00": ["Padelbane"], "10:00-11:00": ["Padelbane"]}
"""

import logging
import time

import requests

logger = logging.getLogger(__name__)

OSLOBOOKING_API = (
    "https://api.booking.oslo.kommune.no/api/bookableasset/availabletime"
)

MAX_RETRIES = 3
BACKOFF_BASE = 1  # seconds


def fetch_available_slots(
    bookable_asset_id: str,
    date_str: str,
    court_name: str = "Padelbane",
    duration: str = "PT1H",
) -> dict[str, list[str]]:
    """Fetch available slots for a single Oslo kommune bookable asset.

    Retries up to :data:`MAX_RETRIES` times with exponential backoff
    (1s, 2s, 4s) on HTTP errors or timeouts.

    Args:
        bookable_asset_id: UUID of the bookable asset.
        date_str: Date in YYYY-MM-DD format.
        court_name: Display name returned with each slot (the API has no
            concept of multiple courts on this asset — it is always the
            same physical resource).
        duration: ISO-8601 booking duration. The kommune platform
            supports values from ``PT15M`` up to several hours. Default
            1 hour keeps parity with Matchi.

    Returns:
        Dict mapping time-slot label (e.g. ``"17:00-18:00"``) to a list
        containing ``court_name``. Empty dict when there is no
        availability.

    Raises:
        requests.RequestException: after all retry attempts are exhausted.
    """
    params = {
        "bookableAssetId": bookable_asset_id,
        "date": date_str,
        "duration": duration,
    }

    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(OSLOBOOKING_API, params=params, timeout=30)
            response.raise_for_status()
            return parse_slots_from_json(response.json(), court_name)
        except (requests.RequestException, requests.Timeout, ValueError) as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                if (
                    hasattr(exc, "response")
                    and exc.response is not None
                    and exc.response.status_code == 429
                ):
                    sleep_time = BACKOFF_BASE * (2 ** (attempt + 2))  # 4s, 8s
                else:
                    sleep_time = BACKOFF_BASE * (2 ** attempt)  # 1s, 2s
                logger.warning(
                    "Fetch attempt %d/%d failed for asset %s date %s: %s. "
                    "Retrying in %ds...",
                    attempt + 1, MAX_RETRIES, bookable_asset_id, date_str,
                    exc, sleep_time,
                )
                time.sleep(sleep_time)
            else:
                logger.error(
                    "All %d fetch attempts failed for asset %s date %s: %s",
                    MAX_RETRIES, bookable_asset_id, date_str, exc,
                )
    raise last_exc


def parse_slots_from_json(
    payload: list, court_name: str = "Padelbane"
) -> dict[str, list[str]]:
    """Parse an availableTime JSON payload into the Matchi-shaped dict.

    Only slots that start on the hour (minutes == 0) are kept; the API
    otherwise emits overlapping 30-minute-stride starts that would create
    duplicate notifications.

    Args:
        payload: Decoded JSON response body (a list of ``{start, end,
            id}`` dicts).
        court_name: Name to attach to each slot in the output.

    Returns:
        Dict mapping ``"HH:MM-HH:MM"`` labels to ``[court_name]``.
    """
    if not isinstance(payload, list):
        return {}

    time_slot_dict: dict[str, list[str]] = {}
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        start = entry.get("start", "")
        end = entry.get("end", "")
        if not start or not end:
            continue

        # Keep only on-the-hour starts (skip 09:30, 10:30, ...). The
        # kommune API emits overlapping 30-min-stride starts that would
        # otherwise produce duplicate notifications.
        if len(start) < 5 or start[3:5] != "00":
            continue

        label = f"{start[:5]}-{end[:5]}"
        time_slot_dict.setdefault(label, []).append(court_name)

    return time_slot_dict
