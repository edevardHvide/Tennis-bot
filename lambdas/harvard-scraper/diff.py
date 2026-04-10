"""
Slot diffing utilities — ported from check_availability.py.

Compares two snapshots of the form:
    dict[facility_key, dict[date_str, dict[time_slot_label, list[court_name]]]]

and returns only the *new* courts (additions), ignoring removals.
"""


# ---------------------------------------------------------------------------
# Type alias (Python 3.9+ compatible — no X | Y syntax needed at runtime)
# ---------------------------------------------------------------------------
# SnapshotDay  = dict[time_slot_label, list[court_name]]
# SnapshotDate = dict[date_str, SnapshotDay]
# Snapshot     = dict[facility_key, SnapshotDate]


def has_changes(current: dict, previous: dict) -> bool:
    """Return True if *current* differs from *previous*.

    When *previous* is empty (first run) this always returns False so that
    we do not fire a spurious "everything is new" alert on cold start.

    Args:
        current:  New availability snapshot.
        previous: Previous availability snapshot (may be empty on first run).

    Returns:
        True when there is at least one difference.
    """
    if not previous:
        return False
    return current != previous


def get_slot_changes(
    current: dict,
    previous: dict,
    facility_key: str,
    date_str: str,
) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """Return (new_courts, removed_courts) for a single facility+date pair.

    Each element in the returned sets is a ``(time_slot_label, court_name)``
    tuple.

    Args:
        current:      Full current snapshot.
        previous:     Full previous snapshot.
        facility_key: Lowercase facility key, e.g. ``"frogner"``.
        date_str:     Date string in YYYY-MM-DD format.

    Returns:
        Tuple of (new_courts, removed_courts) where each is a set of
        (time_slot_label, court_name) tuples.
    """
    current_day = current.get(facility_key, {}).get(date_str, {})
    previous_day = previous.get(facility_key, {}).get(date_str, {})

    current_set: set[tuple[str, str]] = set()
    previous_set: set[tuple[str, str]] = set()

    for time_slot, courts in current_day.items():
        for court in courts:
            current_set.add((time_slot, court))

    for time_slot, courts in previous_day.items():
        for court in courts:
            previous_set.add((time_slot, court))

    new_courts = current_set - previous_set
    removed_courts = previous_set - current_set

    return new_courts, removed_courts


def build_new_courts_diff(
    current: dict,
    previous: dict,
) -> dict[str, dict[str, dict[str, list[str]]]]:
    """Compute the full diff and return only newly appeared courts.

    Iterates over every facility and date in *current* and collects slots
    that were not present in *previous*.

    Args:
        current:  New availability snapshot.
        previous: Previous availability snapshot.

    Returns:
        Nested dict: facility_key -> date_str -> time_slot -> [court_names].
        Only entries with at least one new court are included.
    """
    diff: dict[str, dict[str, dict[str, list[str]]]] = {}

    for facility_key, dates in current.items():
        facility_diff: dict[str, dict[str, list[str]]] = {}

        for date_str in dates:
            new_courts, _ = get_slot_changes(current, previous, facility_key, date_str)

            if not new_courts:
                continue

            # Group new courts by time slot.
            time_to_courts: dict[str, list[str]] = {}
            for time_slot, court in sorted(new_courts):
                time_to_courts.setdefault(time_slot, []).append(court)

            if time_to_courts:
                facility_diff[date_str] = time_to_courts

        if facility_diff:
            diff[facility_key] = facility_diff

    return diff
