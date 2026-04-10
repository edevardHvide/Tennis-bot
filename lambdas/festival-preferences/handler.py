"""
Lambda handler for the Festival Ticket Monitoring API (beta).

Totally isolated from the tennis/padel preferences pipeline.

Routing:
  GET  /festivals                                -> list_festivals
  GET  /users/{userId}/festivals                 -> list_subscriptions
  PUT  /users/{userId}/festivals/{festivalId}    -> toggle_subscription

DynamoDB tables (eu-north-1):
  festival-availability   PK: festivalId
  festival-subscriptions  PK: userId, SK: festivalId
  tennis-users            PK: userId  (read-only, for auth validation)
"""

import json
import logging
import os
import re
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

from festivals import FESTIVALS

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REGION = os.environ.get("AWS_REGION", "eu-north-1")
USERS_TABLE = os.environ.get("USERS_TABLE", "tennis-users")
AVAILABILITY_TABLE = os.environ.get("FESTIVAL_AVAILABILITY_TABLE", "festival-availability")
SUBSCRIPTIONS_TABLE = os.environ.get("FESTIVAL_SUBSCRIPTIONS_TABLE", "festival-subscriptions")

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logger = logging.getLogger(__name__)
logger.setLevel(LOG_LEVEL)

# ---------------------------------------------------------------------------
# DynamoDB (module-level for connection reuse)
# ---------------------------------------------------------------------------

_dynamodb = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=REGION)
    return _dynamodb


def _users_table():
    return _get_dynamodb().Table(USERS_TABLE)


def _availability_table():
    return _get_dynamodb().Table(AVAILABILITY_TABLE)


def _subscriptions_table():
    return _get_dynamodb().Table(SUBSCRIPTIONS_TABLE)


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


def _error(message, status=400):
    return {
        "statusCode": status,
        "headers": CORS_HEADERS,
        "body": json.dumps({"error": message}),
    }


def _log(level: str, message: str, **extra):
    record = {"level": level, "message": message, **extra}
    getattr(logger, level.lower())(json.dumps(record))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _user_exists(user_id: str) -> bool:
    resp = _users_table().get_item(Key={"userId": user_id})
    return "Item" in resp


# ---------------------------------------------------------------------------
# Route: GET /festivals
# ---------------------------------------------------------------------------

def list_festivals(event):
    """Return all festivals with their current availability status."""
    # Load live availability from DynamoDB
    availability = {}
    for fid in FESTIVALS:
        try:
            resp = _availability_table().get_item(Key={"festivalId": fid})
            if "Item" in resp:
                availability[fid] = resp["Item"]
        except Exception as exc:
            _log("warning", "Failed to load availability", festivalId=fid, error=str(exc))

    festivals = []
    for fid, config in FESTIVALS.items():
        avail = availability.get(fid, {})
        festivals.append({
            "festivalId": fid,
            "name": config["name"],
            "dates": config["dates"],
            "location": config["location"],
            "platform": config["platform"],
            "url": config["url"],
            "ticketAvailable": avail.get("ticketAvailable"),
            "ticketStatusText": avail.get("ticketStatusText", "Not checked yet"),
            "lastCheckedAt": avail.get("lastCheckedAt"),
        })

    return _ok(festivals)


# ---------------------------------------------------------------------------
# Route: GET /users/{userId}/festivals
# ---------------------------------------------------------------------------

def list_subscriptions(event):
    """Return user's festival subscriptions."""
    user_id = event["pathParameters"]["userId"]

    if not _EMAIL_RE.match(user_id):
        return _error("Invalid email address", 400)

    if not _user_exists(user_id):
        return _error("User not found", 404)

    resp = _subscriptions_table().query(
        KeyConditionExpression=Key("userId").eq(user_id),
    )

    subs = [
        {
            "festivalId": item["festivalId"],
            "enabled": item.get("enabled", False),
        }
        for item in resp.get("Items", [])
        if item["festivalId"] in FESTIVALS  # skip stale entries
    ]

    return _ok(subs)


# ---------------------------------------------------------------------------
# Route: PUT /users/{userId}/festivals/{festivalId}
# ---------------------------------------------------------------------------

def toggle_subscription(event):
    """Enable or disable festival monitoring for a user."""
    user_id = event["pathParameters"]["userId"]
    festival_id = event["pathParameters"]["festivalId"]

    if not _EMAIL_RE.match(user_id):
        return _error("Invalid email address", 400)

    if festival_id not in FESTIVALS:
        return _error(f"Unknown festival: {festival_id}", 400)

    if not _user_exists(user_id):
        return _error("User not found", 404)

    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return _error("Invalid JSON body", 400)

    enabled = body.get("enabled", True)
    if not isinstance(enabled, bool):
        return _error("'enabled' must be a boolean", 400)

    now = datetime.now(timezone.utc).isoformat()

    _subscriptions_table().put_item(Item={
        "userId": user_id,
        "festivalId": festival_id,
        "enabled": enabled,
        "updatedAt": now,
    })

    _log("info", "Festival subscription toggled",
         userId=user_id, festivalId=festival_id, enabled=enabled)

    return _ok({"festivalId": festival_id, "enabled": enabled})


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """Route incoming API Gateway requests."""
    method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method", "")
    path = event.get("path") or event.get("rawPath", "")

    # OPTIONS (CORS preflight)
    if method == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": {
                **CORS_HEADERS,
                "Access-Control-Allow-Methods": "GET, PUT, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            },
            "body": "",
        }

    try:
        # GET /festivals
        if method == "GET" and path == "/festivals":
            return list_festivals(event)

        # GET /users/{userId}/festivals
        if method == "GET" and "/users/" in path and path.endswith("/festivals"):
            return list_subscriptions(event)

        # PUT /users/{userId}/festivals/{festivalId}
        if method == "PUT" and "/users/" in path and "/festivals/" in path:
            return toggle_subscription(event)

        return _error(f"Not found: {method} {path}", 404)

    except Exception as exc:
        _log("error", "Unhandled exception", error=str(exc), path=path, method=method)
        return _error("Internal server error", 500)
