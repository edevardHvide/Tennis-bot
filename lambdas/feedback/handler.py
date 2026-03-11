"""
Feedback Lambda — creates GitHub issues from user feature requests.

Routes
------
POST /feedback   → create_feedback()
"""

import json
import os
import uuid
from datetime import datetime, timezone, timedelta

import boto3
import requests as http_requests

# ── Configuration ────────────────────────────────────────────────────────────

USERS_TABLE = os.environ.get("USERS_TABLE", "tennis-users")
FEEDBACK_TABLE = os.environ.get("FEEDBACK_TABLE", "tennis-feedback")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "edevardHvide/Tennis-bot")

TITLE_MAX_LEN = 200
DESCRIPTION_MAX_LEN = 2000
RATE_LIMIT_MINUTES = 5

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
    "Access-Control-Allow-Methods": "POST,OPTIONS",
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


# ── Endpoint ─────────────────────────────────────────────────────────────────

def create_feedback(event):
    """POST /feedback — submit a feature request."""
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _error("Invalid JSON body")

    user_id = (body.get("userId") or "").strip()
    title = (body.get("title") or "").strip()
    description = (body.get("description") or "").strip()

    # Validate required fields
    if not user_id:
        return _error("userId is required")
    if not title:
        return _error("title is required")
    if not description:
        return _error("description is required")
    if len(title) > TITLE_MAX_LEN:
        return _error(f"title must be at most {TITLE_MAX_LEN} characters")
    if len(description) > DESCRIPTION_MAX_LEN:
        return _error(f"description must be at most {DESCRIPTION_MAX_LEN} characters")

    db = _get_dynamodb()
    users_table = db.Table(USERS_TABLE)
    feedback_table = db.Table(FEEDBACK_TABLE)

    # Check user exists
    user_resp = users_table.get_item(Key={"userId": user_id})
    user = user_resp.get("Item")
    if not user:
        return _error("User not found", status=404)

    # Rate limit: check lastFeedbackAt
    last_feedback = user.get("lastFeedbackAt")
    if last_feedback:
        try:
            last_dt = datetime.fromisoformat(last_feedback)
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=RATE_LIMIT_MINUTES)
            if last_dt > cutoff:
                return _error("Please wait a few minutes before submitting another request", status=429)
        except (ValueError, TypeError):
            pass  # malformed timestamp, allow the request

    now = datetime.now(timezone.utc).isoformat()
    feedback_id = str(uuid.uuid4())

    # Save to DynamoDB as backup
    feedback_item = {
        "feedbackId": feedback_id,
        "userId": user_id,
        "title": title,
        "description": description,
        "createdAt": now,
        "githubIssueUrl": None,
    }
    feedback_table.put_item(Item=feedback_item)

    # Create GitHub issue
    github_issue_url = None
    if GITHUB_TOKEN:
        try:
            gh_response = http_requests.post(
                f"https://api.github.com/repos/{GITHUB_REPO}/issues",
                headers={
                    "Authorization": f"Bearer {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github+json",
                },
                json={
                    "title": title,
                    "body": f"**Submitted by:** {user_id}\n\n{description}",
                    "labels": ["feature-request"],
                },
                timeout=10,
            )
            if gh_response.status_code == 201:
                github_issue_url = gh_response.json().get("html_url")
                feedback_table.update_item(
                    Key={"feedbackId": feedback_id},
                    UpdateExpression="SET githubIssueUrl = :url",
                    ExpressionAttributeValues={":url": github_issue_url},
                )
                _log("info", "GitHub issue created", url=github_issue_url)
            else:
                _log("error", "GitHub API error",
                     status=gh_response.status_code,
                     response=gh_response.text[:500])
        except Exception as exc:
            _log("error", "GitHub API request failed", error=str(exc))
    else:
        _log("warn", "GITHUB_TOKEN not set, skipping issue creation")

    # Update rate limit timestamp on user
    users_table.update_item(
        Key={"userId": user_id},
        UpdateExpression="SET lastFeedbackAt = :ts",
        ExpressionAttributeValues={":ts": now},
    )

    return _created({
        "feedbackId": feedback_id,
        "message": "Feature request submitted successfully",
        "githubIssueUrl": github_issue_url,
    })


# ── Router ───────────────────────────────────────────────────────────────────

def lambda_handler(event, context):
    http_method = event.get("httpMethod", "")
    resource = event.get("resource", "")

    _log("info", "Incoming request", method=http_method, resource=resource)

    try:
        if http_method == "POST" and resource == "/feedback":
            return create_feedback(event)
        if http_method == "OPTIONS":
            return _ok({"message": "OK"})
        return _error(f"No route for {http_method} {resource}", status=404)
    except Exception as exc:
        _log("error", "Unhandled exception", error=repr(exc))
        return _error("Internal server error", status=500)
