"""
AWS Lambda handler — Court Availability Scraper.

Responsibilities:
1. Fetch availability for all active facilities and sports for the next 14 days.
2. For each facility+sport+date, load the previous snapshot from DynamoDB.
3. Diff against the new snapshot to find only newly available courts.
4. Write the new snapshot back to DynamoDB.
5. Return the diff result as JSON.

DynamoDB table: tennis-availability
  PK (partition key): facilityId  (string, e.g. "frogner#tennis", "ota#padel")
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
from facilities import facilities, get_sports

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
# Configuration
# ---------------------------------------------------------------------------

DAYS_AHEAD = int(os.environ.get("SCRAPER_DAYS_AHEAD", "14"))
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "tennis-availability")
AWS_REGION = os.environ.get("AWS_REGION", "eu-north-1")
NOTIFICATIONS_FUNCTION = os.environ.get("NOTIFICATIONS_FUNCTION", "")

# Circuit breaker: skip remaining dates for a facility after this many
# consecutive fetch failures.
CIRCUIT_BREAKER_THRESHOLD = 3

# Throttle: seconds to sleep between HTTP requests to avoid 429s from matchi.se.
REQUEST_DELAY = 0.5

# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

_dynamodb_resource = None  # lazily initialised
_lambda_client = None


def _get_dynamodb():
    """Return a boto3 DynamoDB resource, creating it once per container."""
    global _dynamodb_resource
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb_resource


def _get_lambda_client():
    """Return a boto3 Lambda client, creating it once per container."""
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client("lambda", region_name=AWS_REGION)
    return _lambda_client


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
                "updatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
    from oslobooking_scraper import (  # noqa: PLC0415
        fetch_available_slots as fetch_oslobooking_slots,
    )
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
    facilities_skipped = []

    # Build list of (facility_key, sport) pairs to scrape
    facility_sport_pairs = []
    for facility_key, config in facilities.items():
        if config.get("matchi_id") is None:
            continue  # Skip non-matchi facilities (e.g. harvard uses Innosoft Fusion)
        for sport in get_sports(facility_key):
            facility_sport_pairs.append((facility_key, config["matchi_id"], sport))

    for facility_key, facility_id, sport in facility_sport_pairs:
        composite_key = f"{facility_key}#{sport}"
        current_snapshot[composite_key] = {}
        previous_snapshot[composite_key] = {}

        consecutive_failures = 0

        for date_str in date_strings:
            # --- Circuit breaker: skip remaining dates if too many failures ---
            if consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                _log("warning", "Circuit breaker tripped — skipping remaining dates",
                     facility=composite_key,
                     consecutive_failures=consecutive_failures,
                     skipped_date=date_str)
                if composite_key not in facilities_skipped:
                    facilities_skipped.append(composite_key)
                # Load previous snapshot to preserve existing data
                prev_slots = load_snapshot(table, composite_key, date_str)
                previous_snapshot[composite_key][date_str] = prev_slots
                current_snapshot[composite_key][date_str] = prev_slots
                continue

            slot_start = time.monotonic()

            # --- Load previous snapshot ---
            prev_slots = load_snapshot(table, composite_key, date_str)
            previous_snapshot[composite_key][date_str] = prev_slots

            # --- Fetch current availability ---
            try:
                curr_slots = fetch_available_slots(facility_id, date_str, sport=sport)
                consecutive_failures = 0  # reset on success
            except Exception as exc:
                _log("warning", "Failed to fetch slots",
                     facility=composite_key, date=date_str, error=str(exc))
                fetch_errors += 1
                consecutive_failures += 1
                # Keep previous snapshot so we don't wipe good data.
                curr_slots = prev_slots

            current_snapshot[composite_key][date_str] = curr_slots
            slot_count = sum(len(v) for v in curr_slots.values())
            total_slots_fetched += slot_count

            duration_ms = round((time.monotonic() - slot_start) * 1000)
            _log("info", "Fetched slots",
                 facility=composite_key, date=date_str,
                 slot_count=slot_count, duration_ms=duration_ms)

            # --- Persist new snapshot ---
            save_snapshot(table, composite_key, date_str, curr_slots)

            # Throttle to avoid 429 Too Many Requests from matchi.se
            time.sleep(REQUEST_DELAY)

    # ------------------------------------------------------------------
    # Oslo kommune booking platform (booking.oslo.kommune.no)
    # ------------------------------------------------------------------
    # Same snapshot/diff/persist shape as Matchi — only the fetch call
    # differs. Capped per-facility by ``oslobooking.days_ahead`` since the
    # kommune refuses bookings beyond 7 days out.
    for facility_key, config in facilities.items():
        osloc = config.get("oslobooking")
        if not osloc:
            continue

        asset_id = osloc["bookable_asset_id"]
        court_name = osloc.get("court_name", "Padelbane")
        facility_days_ahead = min(osloc.get("days_ahead", DAYS_AHEAD), DAYS_AHEAD)
        facility_dates = date_strings[:facility_days_ahead]

        for sport in config["sports"]:
            composite_key = f"{facility_key}#{sport}"
            current_snapshot[composite_key] = {}
            previous_snapshot[composite_key] = {}

            consecutive_failures = 0

            for date_str in facility_dates:
                if consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                    _log("warning",
                         "Circuit breaker tripped — skipping remaining dates",
                         facility=composite_key,
                         consecutive_failures=consecutive_failures,
                         skipped_date=date_str)
                    if composite_key not in facilities_skipped:
                        facilities_skipped.append(composite_key)
                    prev_slots = load_snapshot(table, composite_key, date_str)
                    previous_snapshot[composite_key][date_str] = prev_slots
                    current_snapshot[composite_key][date_str] = prev_slots
                    continue

                slot_start = time.monotonic()

                prev_slots = load_snapshot(table, composite_key, date_str)
                previous_snapshot[composite_key][date_str] = prev_slots

                try:
                    curr_slots = fetch_oslobooking_slots(
                        asset_id, date_str, court_name=court_name
                    )
                    consecutive_failures = 0
                except Exception as exc:
                    _log("warning", "Failed to fetch oslobooking slots",
                         facility=composite_key, date=date_str, error=str(exc))
                    fetch_errors += 1
                    consecutive_failures += 1
                    curr_slots = prev_slots

                current_snapshot[composite_key][date_str] = curr_slots
                slot_count = sum(len(v) for v in curr_slots.values())
                total_slots_fetched += slot_count

                duration_ms = round((time.monotonic() - slot_start) * 1000)
                _log("info", "Fetched oslobooking slots",
                     facility=composite_key, date=date_str,
                     slot_count=slot_count, duration_ms=duration_ms)

                save_snapshot(table, composite_key, date_str, curr_slots)

                time.sleep(REQUEST_DELAY)

    # --- Compute diff (new courts only) ---
    diff = build_new_courts_diff(current_snapshot, previous_snapshot)

    # Count totals for the summary
    total_new_courts = sum(
        len(courts)
        for dates_map in diff.values()
        for slots in dates_map.values()
        for courts in slots.values()
    )

    # --- Invoke notifications Lambda with the diff ---
    notifications_sent = False
    if diff and NOTIFICATIONS_FUNCTION:
        try:
            _log("info", "Invoking notifications Lambda",
                 function=NOTIFICATIONS_FUNCTION, new_courts=total_new_courts)
            _get_lambda_client().invoke(
                FunctionName=NOTIFICATIONS_FUNCTION,
                InvocationType="Event",  # async — don't wait for response
                Payload=json.dumps({"diff": diff}),
            )
            notifications_sent = True
        except ClientError as exc:
            _log("error", "Failed to invoke notifications Lambda",
                 function=NOTIFICATIONS_FUNCTION, error=str(exc))
    elif not diff:
        _log("info", "No new courts — skipping notification invocation")
    elif not NOTIFICATIONS_FUNCTION:
        _log("warning", "NOTIFICATIONS_FUNCTION not configured — skipping notification invocation")

    total_duration_ms = round((time.monotonic() - invocation_start) * 1000)

    _log("info", "Scraper Lambda complete",
         total_slots_fetched=total_slots_fetched,
         total_new_courts=total_new_courts,
         fetch_errors=fetch_errors,
         facilities_skipped=facilities_skipped,
         notifications_sent=notifications_sent,
         duration_ms=total_duration_ms)

    return {
        "statusCode": 200,
        "diff": diff,
        "summary": {
            "total_slots_fetched": total_slots_fetched,
            "total_new_courts": total_new_courts,
            "fetch_errors": fetch_errors,
            "facilities_skipped": facilities_skipped,
            "notifications_invoked": notifications_sent,
            "duration_ms": total_duration_ms,
            "facilities_checked": [f"{k}#{s}" for k, _, s in facility_sport_pairs],
            "dates_checked": date_strings,
        },
    }
