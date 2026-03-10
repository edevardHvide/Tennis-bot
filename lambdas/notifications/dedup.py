"""
Deduplication — prevent re-notifying users about courts they already know about.

Uses the ``tennis-notifications`` DynamoDB table with a 24-hour TTL so that
duplicates expire automatically after one day.
"""

import hashlib
import time

from botocore.exceptions import ClientError

NOTIFICATION_TTL_SECONDS = 86400  # 24 hours


def _dedup_key(user_id: str, facility_id: str, sport: str, date: str, time_slot: str, court_name: str) -> str:
    """Generate a deterministic SHA-256 dedup key for a notification.

    The key is a hash of (userId, facilityId, sport, date, time_slot, court_name).
    """
    raw = f"{user_id}|{facility_id}|{sport}|{date}|{time_slot}|{court_name}"
    return hashlib.sha256(raw.encode()).hexdigest()


def filter_already_notified(
    matches: list[dict],
    table,
) -> list[dict]:
    """Remove courts the user has already been notified about.

    Args:
        matches: list of match dicts from ``matcher.match_preferences``.
        table: boto3 DynamoDB Table resource for ``tennis-notifications``.

    Returns:
        Filtered matches list with only new (non-duplicate) courts.
        Matches whose court list becomes empty are dropped entirely.
    """
    filtered: list[dict] = []

    for match in matches:
        sport = match.get("sport", "tennis")
        new_courts: list[dict] = []
        for court in match["courts"]:
            key = _dedup_key(
                match["userId"],
                match["facilityId"],
                sport,
                match["date"],
                court["time_slot"],
                court["court_name"],
            )
            try:
                response = table.get_item(Key={"notificationId": key})
                if "Item" not in response:
                    new_courts.append(court)
            except ClientError:
                # On error, err on the side of notifying.
                new_courts.append(court)

        if new_courts:
            filtered.append({**match, "courts": new_courts})

    return filtered


def record_notifications(
    matches: list[dict],
    table,
) -> int:
    """Write notification records to DynamoDB with 24h TTL.

    Args:
        matches: list of match dicts (already filtered by dedup).
        table: boto3 DynamoDB Table resource for ``tennis-notifications``.

    Returns:
        Number of notification records written.
    """
    ttl = int(time.time()) + NOTIFICATION_TTL_SECONDS
    count = 0

    for match in matches:
        sport = match.get("sport", "tennis")
        for court in match["courts"]:
            key = _dedup_key(
                match["userId"],
                match["facilityId"],
                sport,
                match["date"],
                court["time_slot"],
                court["court_name"],
            )
            try:
                table.put_item(
                    Item={
                        "notificationId": key,
                        "userId": match["userId"],
                        "facilityId": match["facilityId"],
                        "date": match["date"],
                        "timeSlot": court["time_slot"],
                        "courtName": court["court_name"],
                        "ttl": ttl,
                    }
                )
                count += 1
            except ClientError:
                # Best-effort — log and continue.
                pass

    return count
