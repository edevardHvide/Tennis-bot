"""
Lambda handler for the Availability Monitor Preferences API.

Routing:
  POST   /users                                    -> create_user
  GET    /users/{userId}/preferences               -> list_preferences
  POST   /users/{userId}/preferences               -> create_preference
  PUT    /users/{userId}/preferences/{preferenceId}  -> update_preference
  DELETE /users/{userId}/preferences/{preferenceId}  -> delete_preference
  GET    /users/{userId}/availability               -> get_availability

DynamoDB tables (eu-north-1):
  tennis-users        PK: userId
  tennis-preferences  PK: userId, SK: preferenceId
  tennis-availability PK: facilityId (composite), SK: date
"""

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

OSLO_TZ = ZoneInfo("Europe/Oslo")

import boto3
from boto3.dynamodb.conditions import Key

from facilities import facilities, get_display_name, get_sports

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REGION = os.environ.get("AWS_REGION", "eu-north-1")
USERS_TABLE = os.environ.get("USERS_TABLE", "tennis-users")
PREFS_TABLE = os.environ.get("PREFS_TABLE", "tennis-preferences")
AVAILABILITY_TABLE = os.environ.get("AVAILABILITY_TABLE", "tennis-availability")

VALID_FACILITY_IDS = set(facilities.keys())
VALID_SPORTS = {"tennis", "padel"}
VALID_COURT_TYPES = {"double", "single"}
VALID_DAY_NAMES = {
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
}

# ---------------------------------------------------------------------------
# DynamoDB resource (module-level for connection reuse across invocations)
# ---------------------------------------------------------------------------

_dynamodb = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=REGION)
    return _dynamodb


def _users_table():
    return _get_dynamodb().Table(USERS_TABLE)


def _prefs_table():
    return _get_dynamodb().Table(PREFS_TABLE)


def _availability_table():
    return _get_dynamodb().Table(AVAILABILITY_TABLE)


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Content-Type": "application/json",
}


def _ok(body, status=200):
    return {
        "statusCode": status,
        "headers": CORS_HEADERS,
        "body": json.dumps({"data": body}),
    }


def _created(body):
    return _ok(body, status=201)


def _error(message, status=400):
    return {
        "statusCode": status,
        "headers": CORS_HEADERS,
        "body": json.dumps({"error": message}),
    }


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def _validate_email(value: str) -> str | None:
    """Return error message or None if valid."""
    if not value or not _EMAIL_RE.match(value):
        return f"Invalid email address: {value!r}"
    return None


def _validate_time(value: str, field: str) -> str | None:
    if not value or not _TIME_RE.match(value):
        return f"{field} must be in HH:MM format, got {value!r}"
    h, m = value.split(":")
    if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
        return f"{field} has invalid hours/minutes: {value!r}"
    return None


def _validate_day_name(value: str) -> str | None:
    """Return error message or None if value is a valid day-of-week name."""
    if value.lower() not in VALID_DAY_NAMES:
        return (
            f"Invalid day name: {value!r}; "
            f"must be one of {sorted(VALID_DAY_NAMES)}"
        )
    return None


def _validate_preference_body(body: dict) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    errors = []

    facility_id = body.get("facilityId")
    if not facility_id:
        errors.append("facilityId is required")
    elif facility_id not in VALID_FACILITY_IDS:
        errors.append(
            f"facilityId {facility_id!r} is not valid; "
            f"must be one of {sorted(VALID_FACILITY_IDS)}"
        )

    # Sport validation (optional, defaults to "tennis")
    sport = body.get("sport", "tennis")
    if sport not in VALID_SPORTS:
        errors.append(
            f"sport {sport!r} is not valid; must be one of {sorted(VALID_SPORTS)}"
        )
    elif facility_id and facility_id in VALID_FACILITY_IDS:
        facility_sports = get_sports(facility_id)
        if sport not in facility_sports:
            errors.append(
                f"facility {facility_id!r} does not support sport {sport!r}; "
                f"supported sports: {facility_sports}"
            )

    # Court type validation (optional, only valid for padel)
    court_type = body.get("courtType")
    if court_type is not None:
        if sport != "padel":
            errors.append("courtType is only valid when sport is 'padel'")
        elif court_type not in VALID_COURT_TYPES:
            errors.append(
                f"courtType {court_type!r} is not valid; "
                f"must be one of {sorted(VALID_COURT_TYPES)}"
            )

    dates = body.get("dates")
    if not dates:
        errors.append("dates is required and must be a non-empty list")
    elif not isinstance(dates, list) or len(dates) == 0:
        errors.append("dates must be a non-empty array")
    else:
        for d in dates:
            err = _validate_day_name(d)
            if err:
                errors.append(err)

    time_from = body.get("timeFrom")
    time_to = body.get("timeTo")

    if not time_from:
        errors.append("timeFrom is required")
    else:
        err = _validate_time(time_from, "timeFrom")
        if err:
            errors.append(err)

    if not time_to:
        errors.append("timeTo is required")
    else:
        err = _validate_time(time_to, "timeTo")
        if err:
            errors.append(err)

    if not errors and time_from and time_to:
        if time_from >= time_to:
            errors.append(f"timeFrom ({time_from}) must be earlier than timeTo ({time_to})")

    return errors


# ---------------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------------


def _user_exists(user_id: str) -> bool:
    result = _users_table().get_item(Key={"userId": user_id})
    return "Item" in result


# ---------------------------------------------------------------------------
# Endpoint implementations
# ---------------------------------------------------------------------------


def create_user(event: dict) -> dict:
    """POST /users"""
    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return _error("Request body must be valid JSON")

    user_id = body.get("userId", "").strip()
    name = body.get("name", "").strip()

    if err := _validate_email(user_id):
        return _error(err)
    if not name:
        return _error("name is required")

    table = _users_table()

    # Check for existing user
    existing = table.get_item(Key={"userId": user_id})
    if "Item" in existing:
        return _error(f"User {user_id!r} already exists", status=409)

    now = datetime.now(timezone.utc).isoformat()
    item = {"userId": user_id, "name": name, "createdAt": now}
    table.put_item(Item=item)

    return _created(item)


def list_preferences(event: dict, user_id: str) -> dict:
    """GET /users/{userId}/preferences"""
    if not _user_exists(user_id):
        return _error(f"User {user_id!r} not found", status=404)

    result = _prefs_table().query(
        KeyConditionExpression=Key("userId").eq(user_id)
    )
    return _ok(result.get("Items", []))


def create_preference(event: dict, user_id: str) -> dict:
    """POST /users/{userId}/preferences"""
    if not _user_exists(user_id):
        return _error(f"User {user_id!r} not found", status=404)

    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return _error("Request body must be valid JSON")

    errors = _validate_preference_body(body)
    if errors:
        return _error("; ".join(errors))

    now = datetime.now(timezone.utc).isoformat()
    preference_id = str(uuid.uuid4())
    sport = body.get("sport", "tennis")
    item = {
        "userId": user_id,
        "preferenceId": preference_id,
        "facilityId": body["facilityId"],
        "sport": sport,
        "dates": [d.lower() for d in body["dates"]],
        "timeFrom": body["timeFrom"],
        "timeTo": body["timeTo"],
        "createdAt": now,
        "updatedAt": now,
    }
    if sport == "padel" and "courtType" in body:
        item["courtType"] = body["courtType"]
    _prefs_table().put_item(Item=item)

    return _created(item)


def update_preference(event: dict, user_id: str, preference_id: str) -> dict:
    """PUT /users/{userId}/preferences/{preferenceId}"""
    if not _user_exists(user_id):
        return _error(f"User {user_id!r} not found", status=404)

    existing = _prefs_table().get_item(
        Key={"userId": user_id, "preferenceId": preference_id}
    )
    if "Item" not in existing:
        return _error(
            f"Preference {preference_id!r} not found for user {user_id!r}",
            status=404,
        )

    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return _error("Request body must be valid JSON")

    errors = _validate_preference_body(body)
    if errors:
        return _error("; ".join(errors))

    now = datetime.now(timezone.utc).isoformat()
    sport = body.get("sport", "tennis")
    item = {
        "userId": user_id,
        "preferenceId": preference_id,
        "facilityId": body["facilityId"],
        "sport": sport,
        "dates": [d.lower() for d in body["dates"]],
        "timeFrom": body["timeFrom"],
        "timeTo": body["timeTo"],
        "createdAt": existing["Item"]["createdAt"],
        "updatedAt": now,
    }
    if sport == "padel" and "courtType" in body:
        item["courtType"] = body["courtType"]
    _prefs_table().put_item(Item=item)

    return _ok(item)


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_blacklist_dates(dates: list) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    errors = []
    today = datetime.now(OSLO_TZ).date()
    max_date = today + timedelta(days=14)

    for d in dates:
        if not isinstance(d, str) or not _DATE_RE.match(d):
            errors.append(f"Invalid date format: {d!r}; must be YYYY-MM-DD")
            continue
        try:
            parsed = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            errors.append(f"Invalid date: {d!r}")
            continue
        if parsed < today:
            errors.append(f"Date {d!r} is in the past")
        elif parsed > max_date:
            errors.append(f"Date {d!r} is more than 14 days in the future")

    return errors


def get_blacklist(event: dict, user_id: str) -> dict:
    """GET /users/{userId}/blacklist"""
    if not _user_exists(user_id):
        return _error(f"User {user_id!r} not found", status=404)

    result = _users_table().get_item(Key={"userId": user_id})
    dates = list(result.get("Item", {}).get("blacklistedDates", []))
    return _ok({"blacklistedDates": sorted(dates)})


def update_blacklist(event: dict, user_id: str) -> dict:
    """PUT /users/{userId}/blacklist"""
    if not _user_exists(user_id):
        return _error(f"User {user_id!r} not found", status=404)

    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return _error("Request body must be valid JSON")

    dates = body.get("blacklistedDates")
    if dates is None:
        return _error("blacklistedDates is required")
    if not isinstance(dates, list):
        return _error("blacklistedDates must be an array")

    errors = _validate_blacklist_dates(dates)
    if errors:
        return _error("; ".join(errors))

    unique_dates = sorted(set(dates))
    _users_table().update_item(
        Key={"userId": user_id},
        UpdateExpression="SET blacklistedDates = :d",
        ExpressionAttributeValues={":d": unique_dates},
    )
    return _ok({"blacklistedDates": unique_dates})


def delete_preference(event: dict, user_id: str, preference_id: str) -> dict:
    """DELETE /users/{userId}/preferences/{preferenceId}"""
    if not _user_exists(user_id):
        return _error(f"User {user_id!r} not found", status=404)

    existing = _prefs_table().get_item(
        Key={"userId": user_id, "preferenceId": preference_id}
    )
    if "Item" not in existing:
        return _error(
            f"Preference {preference_id!r} not found for user {user_id!r}",
            status=404,
        )

    _prefs_table().delete_item(
        Key={"userId": user_id, "preferenceId": preference_id}
    )

    return _ok({"deleted": True})


WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

SCRAPER_INTERVAL_MINUTES = 15


def get_availability(event: dict, user_id: str) -> dict:
    """GET /users/{userId}/availability

    Returns court availability for the next 7 days, filtered by the user's
    preferences (facility, sport, day-of-week, time window, court type).
    Includes freshness metadata per facility.
    """
    if not _user_exists(user_id):
        return _error(f"User {user_id!r} not found", status=404)

    prefs = _prefs_table().query(
        KeyConditionExpression=Key("userId").eq(user_id)
    ).get("Items", [])

    if not prefs:
        return _ok({"days": [], "facilities": [], "freshness": {}})

    now_oslo = datetime.now(OSLO_TZ)
    today = now_oslo.date()
    avail_table = _availability_table()

    # Collect unique facility#sport keys and build preference lookup
    facility_sport_keys = set()
    for p in prefs:
        sport = p.get("sport", "tennis")
        key = f"{p['facilityId']}#{sport}"
        facility_sport_keys.add(key)

    # Query availability for each facility#sport for the next 7 days
    raw_availability = {}  # {facility#sport: {date: slots_dict}}
    freshness = {}  # {facility#sport: {updatedAt, ...}}

    for fs_key in facility_sport_keys:
        raw_availability[fs_key] = {}
        for day_offset in range(7):
            date_str = (today + timedelta(days=day_offset)).isoformat()
            result = avail_table.get_item(
                Key={"facilityId": fs_key, "date": date_str}
            )
            if "Item" in result:
                item = result["Item"]
                slots_raw = item.get("slots", "{}")
                try:
                    slots = json.loads(slots_raw) if isinstance(slots_raw, str) else slots_raw
                except (json.JSONDecodeError, TypeError):
                    slots = {}
                raw_availability[fs_key][date_str] = slots
                updated_at = item.get("updatedAt", "")
                if fs_key not in freshness or updated_at > freshness.get(fs_key, {}).get("updatedAt", ""):
                    freshness[fs_key] = {"updatedAt": updated_at}

    # Build calendar: 7 days, each with matched slots
    days = []
    for day_offset in range(7):
        date_obj = today + timedelta(days=day_offset)
        date_str = date_obj.isoformat()
        weekday = WEEKDAY_NAMES[date_obj.weekday()]

        day_slots = []  # slots for this day across all preferences

        for p in prefs:
            pref_days = [d.lower() for d in p.get("dates", [])]
            if weekday not in pref_days:
                continue

            sport = p.get("sport", "tennis")
            fs_key = f"{p['facilityId']}#{sport}"
            time_from = p.get("timeFrom", "00:00")
            time_to = p.get("timeTo", "23:59")
            court_type = p.get("courtType")

            date_slots = raw_availability.get(fs_key, {}).get(date_str, {})

            for time_slot, courts in sorted(date_slots.items()):
                slot_start = time_slot.split("-")[0].strip()
                if slot_start < time_from or slot_start >= time_to:
                    continue

                for court_name in courts:
                    # Court type filtering for padel
                    if court_type:
                        is_single = "single" in court_name.lower()
                        if court_type == "single" and not is_single:
                            continue
                        if court_type == "double" and is_single:
                            continue

                    day_slots.append({
                        "facilityId": p["facilityId"],
                        "sport": sport,
                        "timeSlot": time_slot,
                        "courtName": court_name,
                    })

        days.append({
            "date": date_str,
            "weekday": weekday,
            "slots": day_slots,
        })

    # Build facility list for legend
    facility_info = []
    seen = set()
    for p in prefs:
        fid = p["facilityId"]
        if fid not in seen:
            seen.add(fid)
            try:
                display = get_display_name(fid)
            except KeyError:
                display = fid
            facility_info.append({"facilityId": fid, "displayName": display})

    # Compute next update time (scraper runs every 15 min)
    minutes_since = now_oslo.minute % SCRAPER_INTERVAL_MINUTES
    next_update = now_oslo.replace(second=0, microsecond=0) + timedelta(
        minutes=SCRAPER_INTERVAL_MINUTES - minutes_since
    )

    return _ok({
        "days": days,
        "facilities": facility_info,
        "freshness": {k: v for k, v in freshness.items()},
        "nextUpdateAt": next_update.isoformat(),
        "generatedAt": now_oslo.isoformat(),
    })


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context) -> dict:
    """Main Lambda entry point — route by httpMethod + resource."""
    http_method = event.get("httpMethod", "")
    resource = event.get("resource", "")
    path_params = event.get("pathParameters") or {}

    user_id = path_params.get("userId", "")
    preference_id = path_params.get("preferenceId", "")

    try:
        if http_method == "POST" and resource == "/users":
            return create_user(event)

        if http_method == "GET" and resource == "/users/{userId}/preferences":
            return list_preferences(event, user_id)

        if http_method == "POST" and resource == "/users/{userId}/preferences":
            return create_preference(event, user_id)

        if http_method == "PUT" and resource == "/users/{userId}/preferences/{preferenceId}":
            return update_preference(event, user_id, preference_id)

        if http_method == "DELETE" and resource == "/users/{userId}/preferences/{preferenceId}":
            return delete_preference(event, user_id, preference_id)

        if http_method == "GET" and resource == "/users/{userId}/availability":
            return get_availability(event, user_id)

        if http_method == "GET" and resource == "/users/{userId}/blacklist":
            return get_blacklist(event, user_id)

        if http_method == "PUT" and resource == "/users/{userId}/blacklist":
            return update_blacklist(event, user_id)

        return _error(f"No route for {http_method} {resource}", status=404)

    except Exception as exc:  # noqa: BLE001
        print(f"Unhandled exception: {exc!r}")
        return _error("Internal server error", status=500)
