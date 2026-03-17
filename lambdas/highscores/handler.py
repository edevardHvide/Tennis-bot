"""
Highscores Lambda — global leaderboard for the snake minigame.

Routes
------
POST /highscores   → submit_score()
GET  /highscores   → get_highscores()
"""

import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import boto3

# ── Configuration ────────────────────────────────────────────────────────────

USERS_TABLE = os.environ.get("USERS_TABLE", "tennis-users")
HIGHSCORES_TABLE = os.environ.get("HIGHSCORES_TABLE", "tennis-highscores")

MAX_SCORE = 999
RATE_LIMIT_SECONDS = 10
TOP_N = 20

# ── AWS helpers ──────────────────────────────────────────────────────────────

_dynamodb_resource = None


def _get_dynamodb():
    global _dynamodb_resource
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource(
            "dynamodb", region_name=os.environ.get("AWS_REGION", "eu-north-1")
        )
    return _dynamodb_resource


# ── Response helpers ─────────────────────────────────────────────────────────

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Content-Type": "application/json",
}


def _ok(body, status=200):
    return {"statusCode": status, "headers": CORS_HEADERS, "body": json.dumps({"data": body})}


def _created(body):
    return _ok(body, status=201)


def _error(message, status=400):
    return {"statusCode": status, "headers": CORS_HEADERS, "body": json.dumps({"error": message})}


# ── Logging ──────────────────────────────────────────────────────────────────

def _log(level, message, **extra):
    entry = {"level": level, "message": message, **extra}
    print(json.dumps(entry, default=str))


# ── Decimal serialisation helper ─────────────────────────────────────────────

def _decimal_to_int(obj):
    """Convert Decimal values from DynamoDB to int for JSON serialisation."""
    if isinstance(obj, Decimal):
        return int(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_int(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_int(i) for i in obj]
    return obj


# ── Endpoints ────────────────────────────────────────────────────────────────

def submit_score(event):
    """POST /highscores — submit a game score."""
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _error("Invalid JSON body")

    user_id = (body.get("userId") or "").strip()
    player_name = (body.get("playerName") or "").strip()
    score = body.get("score")

    # Validate required fields
    if not user_id:
        return _error("userId is required")
    if not player_name:
        return _error("playerName is required")
    if score is None:
        return _error("score is required")
    try:
        score = int(score)
    except (ValueError, TypeError):
        return _error("score must be a number")
    if score < 0:
        return _error("score must be non-negative")
    if score > MAX_SCORE:
        score = MAX_SCORE

    db = _get_dynamodb()
    users_table = db.Table(USERS_TABLE)
    highscores_table = db.Table(HIGHSCORES_TABLE)

    # Check user exists
    user_resp = users_table.get_item(Key={"userId": user_id})
    user = user_resp.get("Item")
    if not user:
        return _error("User not found", status=404)

    # Rate limit: check lastScoreAt
    last_score_at = user.get("lastScoreAt")
    if last_score_at:
        try:
            last_dt = datetime.fromisoformat(last_score_at)
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=RATE_LIMIT_SECONDS)
            if last_dt > cutoff:
                return _error("Please wait a few seconds before submitting another score", status=429)
        except (ValueError, TypeError):
            pass  # malformed timestamp, allow the request

    now = datetime.now(timezone.utc).isoformat()
    score_id = str(uuid.uuid4())

    # Save score
    score_item = {
        "leaderboard": "GLOBAL",
        "scoreId": score_id,
        "userId": user_id,
        "playerName": player_name,
        "score": score,
        "createdAt": now,
    }
    highscores_table.put_item(Item=score_item)

    # Update rate limit timestamp on user
    users_table.update_item(
        Key={"userId": user_id},
        UpdateExpression="SET lastScoreAt = :ts",
        ExpressionAttributeValues={":ts": now},
    )

    _log("info", "Score submitted", scoreId=score_id, userId=user_id, score=score)

    return _created({
        "scoreId": score_id,
        "message": "Score submitted successfully",
    })


def get_highscores(event):
    """GET /highscores — return top scores."""
    db = _get_dynamodb()
    highscores_table = db.Table(HIGHSCORES_TABLE)

    # Scan all items, handling pagination
    items = []
    scan_kwargs = {
        "FilterExpression": "leaderboard = :lb",
        "ExpressionAttributeValues": {":lb": "GLOBAL"},
    }
    while True:
        response = highscores_table.scan(**scan_kwargs)
        items.extend(response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            break
        scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    # Sort by score descending, take top N
    items.sort(key=lambda x: int(x.get("score", 0)), reverse=True)
    top_items = items[:TOP_N]

    # Convert Decimal values for JSON serialisation
    top_items = _decimal_to_int(top_items)

    return _ok(top_items)


# ── Router ───────────────────────────────────────────────────────────────────

def lambda_handler(event, context):
    http_method = event.get("httpMethod", "")
    resource = event.get("resource", "")

    _log("info", "Incoming request", method=http_method, resource=resource)

    try:
        if http_method == "POST" and resource == "/highscores":
            return submit_score(event)
        if http_method == "GET" and resource == "/highscores":
            return get_highscores(event)
        if http_method == "OPTIONS":
            return _ok({"message": "OK"})
        return _error(f"No route for {http_method} {resource}", status=404)
    except Exception as exc:
        _log("error", "Unhandled exception", error=repr(exc))
        return _error("Internal server error", status=500)
