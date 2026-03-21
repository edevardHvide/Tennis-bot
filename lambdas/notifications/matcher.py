"""
Preference matching — compare scraper diff against user preferences.

A court in the diff matches a preference when:
  1. The composite key (facilityId#sport) matches.
  2. The day-of-week for the diff date is in the preference's day list.
  3. The slot start time falls within [timeFrom, timeTo).
  4. If courtType is set, the court name matches the filter.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from facilities import get_matchi_id, get_display_name, SPORT_CODES

OSLO_TZ = ZoneInfo("Europe/Oslo")


def _slot_start_time(time_slot: str) -> str:
    """Extract the start time from a time slot label like '17:00-18:00'.

    Returns the start portion (e.g. '17:00').  If the label is malformed
    the whole string is returned so that comparisons safely fail-closed.
    """
    return time_slot.split("-")[0].strip()


def _is_past_slot(date_str: str, time_slot: str) -> bool:
    """Return True if the slot's start time is in the past (Europe/Oslo)."""
    start = _slot_start_time(time_slot)
    try:
        slot_dt = datetime.strptime(f"{date_str} {start}", "%Y-%m-%d %H:%M")
        slot_dt = slot_dt.replace(tzinfo=OSLO_TZ)
        return slot_dt <= datetime.now(OSLO_TZ)
    except ValueError:
        return False


def _court_type_matches(court_name: str, court_type: str | None) -> bool:
    """Check if a court name matches the requested court type filter.

    Args:
        court_name: the court name string from the diff.
        court_type: "single", "double", or None (no filter).

    Returns:
        True if the court should be included.
    """
    if not court_type:
        return True
    name_lower = court_name.lower()
    if court_type == "single":
        return "single" in name_lower
    if court_type == "double":
        return "single" not in name_lower
    # Unknown court type — no filtering
    return True


def match_preferences(
    diff: dict[str, dict[str, dict[str, list[str]]]],
    preferences: list[dict],
    blacklisted_dates: dict[str, set[str]] | None = None,
) -> list[dict]:
    """Match scraper diff against user preferences.

    Args:
        diff: composite_key -> date_str -> time_slot -> [court_name]
              where composite_key is "facilityId#sport" (e.g. "ota#padel").
        preferences: list of preference dicts from DynamoDB, each with:
            userId, preferenceId, facilityId, dates (list of day names,
            e.g. ["monday", "wednesday"]), timeFrom, timeTo,
            sport (optional, defaults to "tennis"),
            courtType (optional).

    Returns:
        List of match dicts::

            {
                "userId": str,
                "preferenceId": str,
                "facilityId": str,
                "sport": str,
                "date": str,           # YYYY-MM-DD
                "courts": [
                    {"time_slot": str, "court_name": str},
                    ...
                ],
            }

        One entry per (user, preference, facility, date) combination that
        has at least one matching court.
    """
    if not diff or not preferences:
        return []

    matches: list[dict] = []

    for pref in preferences:
        facility_id: str = pref.get("facilityId", "")
        sport: str = pref.get("sport", "tennis")
        court_type: str | None = pref.get("courtType")
        pref_dates: list[str] = pref.get("dates", [])
        time_from: str = pref.get("timeFrom", "00:00")
        time_to: str = pref.get("timeTo", "23:59")
        user_id: str = pref.get("userId", "")
        preference_id: str = pref.get("preferenceId", "")

        # Construct composite key to look up in the diff
        composite_key = f"{facility_id}#{sport}"

        # Check if this facility+sport exists in the diff
        facility_diff = diff.get(composite_key)
        if not facility_diff:
            continue

        # Iterate over diff dates and check if the day-of-week matches
        for date_str, date_diff in facility_diff.items():
            # Convert diff date (YYYY-MM-DD) to a day-of-week name
            try:
                day_name = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A").lower()
            except ValueError:
                # Malformed date in diff — skip safely
                continue

            if day_name not in pref_dates:
                continue

            # Skip dates the user has blacklisted
            if blacklisted_dates and date_str in blacklisted_dates.get(user_id, set()):
                continue

            matched_courts: list[dict] = []
            for time_slot, court_names in date_diff.items():
                if _is_past_slot(date_str, time_slot):
                    continue
                start = _slot_start_time(time_slot)
                if start >= time_from and start < time_to:
                    for court_name in court_names:
                        if _court_type_matches(court_name, court_type):
                            matched_courts.append({
                                "time_slot": time_slot,
                                "court_name": court_name,
                            })

            if matched_courts:
                matches.append({
                    "userId": user_id,
                    "preferenceId": preference_id,
                    "facilityId": facility_id,
                    "sport": sport,
                    "date": date_str,
                    "courts": matched_courts,
                })

    return matches
