"""
AWS Lambda handler — Court Availability Scraper.

Responsibilities:
1. Fetch availability for all active facilities and the next 14 days.
2. For each facility+date, load the previous snapshot from DynamoDB.
3. Diff against the new snapshot to find only newly available courts.
4. Write the new snapshot back to DynamoDB.
5. Return the diff result as JSON.

DynamoDB table: tennis-availability
  PK (partition key): facilityId  (string, e.g. "frogner")
  SK (sort key):      date        (string, YYYY-MM-DD)
  Attribute:          slots       (JSON string of time_slot -> [court_name])
"""

import datetime
import json
import logging
import os
import sys
import time

import boto3
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# Logging — structured JSON to CloudWatch
# ---------------------------------------------------------------------------

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

# If running in Lambda the root handler is already attached; add one only when
# running locally so we always get output.
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)


def _log(level: str, message: str, **extra) -> None:
    """Emit a structured JSON log line."""
    record = {
        "level": level,
        "message": message,
        **extra,
    }
    getattr(logger, level.lower(), logger.info)(json.dumps(record))


# ---------------------------------------------------------------------------
# Facility configuration — mirrors facilities.py without the CLI import chain
# ---------------------------------------------------------------------------

FACILITIES: dict[str, int] = {
    "frogner": 2259,
    "ota": 1779,
    "bergentennisarena": 301,
}

DAYS_AHEAD = int(os.environ.get("SCRAPER_DAYS_AHEAD", "14"))
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "tennis-availability")
AWS_REGION = os.environ.get("AWS_REGION", "eu-north-1")

# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

_dynamodb_resource = None  # lazily initialised


def _get_dynamodb():
    """Return a boto3 DynamoDB resource, creating it once per container."""
    global _dynamodb_resource
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb_resource


def load_snapshot(table, facility_key: str, date_str: str) -> dict[str, list[str]]:
    """Load a single facility+date snapshot from DynamoDB.

    Returns an empty dict when no item exists yet.
    """
    try:
        response = table.get_item(
            Key={"facilityId": facility_key, "date": date_str}
        )
        item = response.get("Item")
        if item and "slots" in item:
            return json.loads(item["slots"])
    except ClientError as exc:
        _log("error", "DynamoDB get_item failed",
             facility=facility_key, date=date_str,
             error=str(exc))
    return {}


def save_snapshot(
    table, facility_key: str, date_str: str, slots: dict[str, list[str]]
) -> None:
    """Persist a single facility+date snapshot to DynamoDB."""
    try:
        table.put_item(
            Item={
                "facilityId": facility_key,
                "date": date_str,
                "slots": json.dumps(slots),
                "updatedAt": datetime.datetime.utcnow().isoformat(),
            }
        )
    except ClientError as exc:
        _log("error", "DynamoDB put_item failed",
             facility=facility_key, date=date_str,
             error=str(exc))


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context) -> dict:
    """AWS Lambda handler entry point.

    Args:
        event:   Lambda invocation event (unused — scraper runs on a schedule).
        context: Lambda runtime context.

    Returns:
        Dict with keys:
          - statusCode (int)
          - diff       (nested dict of new courts per facility/date)
          - summary    (dict with totals)
    """
    invocation_start = time.monotonic()

    _log("info", "Scraper Lambda invoked",
         days_ahead=DAYS_AHEAD, table=DYNAMODB_TABLE, region=AWS_REGION)

    # Lazy imports so that cold-start errors surface clearly.
    from scraper import fetch_available_slots  # noqa: PLC0415
    from diff import build_new_courts_diff     # noqa: PLC0415

    table = _get_dynamodb().Table(DYNAMODB_TABLE)

    today = datetime.date.today()
    dates = [today + datetime.timedelta(days=i) for i in range(DAYS_AHEAD)]
    date_strings = [d.strftime("%Y-%m-%d") for d in dates]

    # Full current snapshot: facility_key -> date_str -> time_slot -> [courts]
    current_snapshot: dict[str, dict[str, dict[str, list[str]]]] = {}
    # Full previous snapshot loaded from DynamoDB
    previous_snapshot: dict[str, dict[str, dict[str, list[str]]]] = {}

    total_slots_fetched = 0
    fetch_errors = 0

    for facility_key, facility_id in FACILITIES.items():
        current_snapshot[facility_key] = {}
        previous_snapshot[facility_key] = {}

        for date_str in date_strings:
            slot_start = time.monotonic()

            # --- Load previous snapshot ---
            prev_slots = load_snapshot(table, facility_key, date_str)
            previous_snapshot[facility_key][date_str] = prev_slots

            # --- Fetch current availability ---
            try:
                curr_slots = fetch_available_slots(facility_id, date_str)
            except Exception as exc:
                _log("warning", "Failed to fetch slots",
                     facility=facility_key, date=date_str, error=str(exc))
                fetch_errors += 1
                # Keep previous snapshot so we don't wipe good data.
                curr_slots = prev_slots

            current_snapshot[facility_key][date_str] = curr_slots
            slot_count = sum(len(v) for v in curr_slots.values())
            total_slots_fetched += slot_count

            duration_ms = round((time.monotonic() - slot_start) * 1000)
            _log("info", "Fetched slots",
                 facility=facility_key, date=date_str,
                 slot_count=slot_count, duration_ms=duration_ms)

            # --- Persist new snapshot ---
            save_snapshot(table, facility_key, date_str, curr_slots)

    # --- Compute diff (new courts only) ---
    diff = build_new_courts_diff(current_snapshot, previous_snapshot)

    # Count totals for the summary
    total_new_courts = sum(
        len(courts)
        for dates_map in diff.values()
        for slots in dates_map.values()
        for courts in slots.values()
    )

    total_duration_ms = round((time.monotonic() - invocation_start) * 1000)

    _log("info", "Scraper Lambda complete",
         total_slots_fetched=total_slots_fetched,
         total_new_courts=total_new_courts,
         fetch_errors=fetch_errors,
         duration_ms=total_duration_ms)

    return {
        "statusCode": 200,
        "diff": diff,
        "summary": {
            "total_slots_fetched": total_slots_fetched,
            "total_new_courts": total_new_courts,
            "fetch_errors": fetch_errors,
            "duration_ms": total_duration_ms,
            "facilities_checked": list(FACILITIES.keys()),
            "dates_checked": date_strings,
        },
    }
