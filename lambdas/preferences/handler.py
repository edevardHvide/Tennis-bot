"""
Lambda handler for the Availability Monitor Preferences API.

Routing:
  POST   /users                                    -> create_user
  GET    /users/{userId}/preferences               -> list_preferences
  POST   /users/{userId}/preferences               -> create_preference
  PUT    /users/{userId}/preferences/{preferenceId}  -> update_preference
  DELETE /users/{userId}/preferences/{preferenceId}  -> delete_preference

DynamoDB tables (eu-north-1):
  tennis-users        PK: userId
  tennis-preferences  PK: userId, SK: preferenceId
"""

import json
import os
import re
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

from facilities import facilities, get_sports

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REGION = os.environ.get("AWS_REGION", "eu-north-1")
USERS_TABLE = os.environ.get("USERS_TABLE", "tennis-users")
PREFS_TABLE = os.environ.get("PREFS_TABLE", "tennis-preferences")

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

        return _error(f"No route for {http_method} {resource}", status=404)

    except Exception as exc:  # noqa: BLE001
        print(f"Unhandled exception: {exc!r}")
        return _error("Internal server error", status=500)
