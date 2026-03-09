"""
Preference matching — compare scraper diff against user preferences.

A court in the diff matches a preference when:
  1. The facility key matches.
  2. The date string appears in the preference's date list.
  3. The slot start time falls within [timeFrom, timeTo).
"""


def _slot_start_time(time_slot: str) -> str:
    """Extract the start time from a time slot label like '17:00-18:00'.

    Returns the start portion (e.g. '17:00').  If the label is malformed
    the whole string is returned so that comparisons safely fail-closed.
    """
    return time_slot.split("-")[0].strip()


def match_preferences(
    diff: dict[str, dict[str, dict[str, list[str]]]],
    preferences: list[dict],
) -> list[dict]:
    """Match scraper diff against user preferences.

    Args:
        diff: facility_key -> date_str -> time_slot -> [court_name]
        preferences: list of preference dicts from DynamoDB, each with:
            userId, preferenceId, facilityId, dates (list of YYYY-MM-DD),
            timeFrom, timeTo.

    Returns:
        List of match dicts::

            {
                "userId": str,
                "preferenceId": str,
                "facilityId": str,
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
        pref_dates: list[str] = pref.get("dates", [])
        time_from: str = pref.get("timeFrom", "00:00")
        time_to: str = pref.get("timeTo", "23:59")
        user_id: str = pref.get("userId", "")
        preference_id: str = pref.get("preferenceId", "")

        # Check if this facility exists in the diff
        facility_diff = diff.get(facility_id)
        if not facility_diff:
            continue

        for date_str in pref_dates:
            date_diff = facility_diff.get(date_str)
            if not date_diff:
                continue

            matched_courts: list[dict] = []
            for time_slot, court_names in date_diff.items():
                start = _slot_start_time(time_slot)
                if start >= time_from and start < time_to:
                    for court_name in court_names:
                        matched_courts.append({
                            "time_slot": time_slot,
                            "court_name": court_name,
                        })

            if matched_courts:
                matches.append({
                    "userId": user_id,
                    "preferenceId": preference_id,
                    "facilityId": facility_id,
                    "date": date_str,
                    "courts": matched_courts,
                })

    return matches
