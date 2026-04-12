"""
AWS Lambda handler — Harvard Recreation Lesson Availability Scraper.

Responsibilities:
1. Fetch lesson availability from Harvard Rec Innosoft Fusion endpoint.
2. For each date with available lessons, load previous DynamoDB snapshot.
3. Diff against new snapshot to find newly available lessons.
4. Write new snapshot back to DynamoDB.
5. If diff is non-empty and this is NOT a first run, invoke notifications Lambda.

DynamoDB table: tennis-availability
  PK (facilityId): "harvard#tennis"
  SK (date):       "YYYY-MM-DD"
  Attribute:       slots (JSON string of time_slot -> [location])

Environment variables:
  HARVARD_PROGRAM_ID      -- Innosoft Fusion course GUID (required)
  DYNAMODB_TABLE          -- DynamoDB table name (default: tennis-availability)
  NOTIFICATIONS_FUNCTION  -- Notifications Lambda function name or ARN
  AWS_REGION              -- AWS region (default: eu-north-1)
  LOG_LEVEL               -- Logging level (default: INFO)
"""

import datetime
import json
import logging
import os
import sys
import time

import boto3
from botocore.exceptions import ClientError

# Top-level import so tests can patch handler.fetch_lesson_instances directly.
from scraper import fetch_lesson_instances  # noqa: E402
from diff import build_new_courts_diff      # noqa: E402

# ---------------------------------------------------------------------------
# Logging — structured JSON to CloudWatch (mirrors lambdas/scraper/handler.py)
# ---------------------------------------------------------------------------

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)


def _log(level: str, message: str, **extra) -> None:
    """Emit a structured JSON log line."""
    record = {"level": level, "message": message, **extra}
    getattr(logger, level.lower(), logger.info)(json.dumps(record))


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HARVARD_PROGRAM_ID = os.environ.get("HARVARD_PROGRAM_ID", "a20e7ae2-fedc-4a8e-a7c3-236695040c63")
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "tennis-availability")
AWS_REGION = os.environ.get("AWS_REGION", "eu-north-1")
NOTIFICATIONS_FUNCTION = os.environ.get("NOTIFICATIONS_FUNCTION", "")

COMPOSITE_KEY = "harvard#tennis"

# ---------------------------------------------------------------------------
# Lazy boto3 init (mirrors lambdas/scraper/handler.py — reuses warm container)
# ---------------------------------------------------------------------------

_dynamodb_resource = None
_lambda_client = None


def _get_dynamodb():
    global _dynamodb_resource
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb_resource


def _get_lambda_client():
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client("lambda", region_name=AWS_REGION)
    return _lambda_client


# ---------------------------------------------------------------------------
# DynamoDB helpers (schema identical to tennis-availability — copy from matchi handler)
# ---------------------------------------------------------------------------

def load_snapshot(table, facility_key: str, date_str: str) -> dict:
    """Load a single facility+date snapshot from DynamoDB. Returns {} on miss."""
    try:
        response = table.get_item(Key={"facilityId": facility_key, "date": date_str})
        item = response.get("Item")
        if item and "slots" in item:
            return json.loads(item["slots"])
    except ClientError as exc:
        _log("error", "DynamoDB get_item failed",
             facility=facility_key, date=date_str, error=str(exc))
    return {}


def _snapshot_record_exists(table, facility_key: str, date_str: str) -> bool:
    """Return True if a DynamoDB record exists for this facility+date key, else False.

    Used for the cold-start guard — distinguishes 'no record' (first run)
    from 'record with empty slots' (second run where previous was empty).
    """
    try:
        response = table.get_item(Key={"facilityId": facility_key, "date": date_str})
        return response.get("Item") is not None
    except ClientError:
        return False


def save_snapshot(table, facility_key: str, date_str: str, slots: dict) -> None:
    """Persist a single facility+date snapshot to DynamoDB."""
    try:
        table.put_item(Item={
            "facilityId": facility_key,
            "date": date_str,
            "slots": json.dumps(slots),
            "updatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
    except ClientError as exc:
        _log("error", "DynamoDB put_item failed",
             facility=facility_key, date=date_str, error=str(exc))


# ---------------------------------------------------------------------------
# Core scraper loop
# ---------------------------------------------------------------------------

def _build_slots_by_date(lessons: list) -> dict:
    """Group parsed lessons into { date: { time_slot: [location] } }."""
    by_date: dict = {}
    for lesson in lessons:
        date = lesson["date"]
        ts = lesson["time_slot"]
        loc = lesson["location"]
        by_date.setdefault(date, {}).setdefault(ts, []).append(loc)
    return by_date


def run_scraper(program_id: str, table, lambda_client, notifications_function: str) -> dict:
    """Fetch, diff, snapshot, and optionally notify.

    Returns the diff dict (may be empty).
    """
    lessons = fetch_lesson_instances(program_id)
    _log("info", "Fetched lesson instances", count=len(lessons), program_id=program_id)

    current_by_date = _build_slots_by_date(lessons)

    # Build full snapshot structures for diff
    current_snapshot: dict = {COMPOSITE_KEY: current_by_date}
    previous_snapshot: dict = {COMPOSITE_KEY: {}}

    # Track whether ANY previous record existed in DynamoDB.
    # Cold-start guard: if no records exist for any date in the current snapshot,
    # this is the baseline (first) run — do NOT fire alerts.
    any_previous_record_existed = False

    # Load previous snapshot for each date that has current availability.
    # load_snapshot is called first (slots data), then _snapshot_record_exists
    # checks existence separately — necessary to correctly detect cold-start
    # when previous snapshot exists but had empty slots.
    for date_str in current_by_date:
        prev = load_snapshot(table, COMPOSITE_KEY, date_str)
        previous_snapshot[COMPOSITE_KEY][date_str] = prev
        if _snapshot_record_exists(table, COMPOSITE_KEY, date_str):
            any_previous_record_existed = True

    # Save current snapshot for all dates
    for date_str, slots in current_by_date.items():
        save_snapshot(table, COMPOSITE_KEY, date_str, slots)

    # build_new_courts_diff computes new slots regardless of cold-start;
    # the cold-start guard is applied before invoking notifications.
    diff = build_new_courts_diff(current_snapshot, previous_snapshot)

    if diff:
        _log("info", "New lesson slots detected", diff_keys=list(diff.keys()))
    else:
        _log("info", "No new lesson slots — skipping notification invocation")

    # Cold-start guard: only invoke notifications if:
    # 1. diff is non-empty
    # 2. at least one previous record existed in DynamoDB (not a first run)
    if diff and any_previous_record_existed:
        try:
            _log("info", "Invoking notifications Lambda", function=notifications_function)
            lambda_client.invoke(
                FunctionName=notifications_function,
                InvocationType="Event",  # async — do not wait for response
                Payload=json.dumps({"diff": diff}),
            )
        except ClientError as exc:
            _log("error", "Failed to invoke notifications Lambda",
                 function=notifications_function, error=str(exc))
    elif diff and not any_previous_record_existed:
        _log("info", "Cold-start detected — saving baseline snapshot without alerting")
    if diff and not notifications_function:
        _log("warning", "NOTIFICATIONS_FUNCTION not configured — invoked with empty function name")

    return diff


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context) -> dict:
    """AWS Lambda handler entry point."""
    invocation_start = time.monotonic()
    _log("info", "Harvard scraper Lambda invoked",
         program_id=HARVARD_PROGRAM_ID, table=DYNAMODB_TABLE, region=AWS_REGION)

    table = _get_dynamodb().Table(DYNAMODB_TABLE)

    try:
        diff = run_scraper(
            program_id=HARVARD_PROGRAM_ID,
            table=table,
            lambda_client=_get_lambda_client(),
            notifications_function=NOTIFICATIONS_FUNCTION,
        )
    except Exception as exc:
        _log("error", "Harvard scraper Lambda failed", error=str(exc))
        raise

    total_duration_ms = round((time.monotonic() - invocation_start) * 1000)
    total_new_lessons = sum(
        len(courts)
        for dates_map in diff.values()
        for slots in dates_map.values()
        for courts in slots.values()
    )

    _log("info", "Harvard scraper Lambda complete",
         total_new_lessons=total_new_lessons,
         duration_ms=total_duration_ms)

    return {
        "statusCode": 200,
        "diff": diff,
        "summary": {
            "total_new_lessons": total_new_lessons,
            "duration_ms": total_duration_ms,
        },
    }
