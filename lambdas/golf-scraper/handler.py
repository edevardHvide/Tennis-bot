"""AWS Lambda handler for GolfBox availability scraping.

Triggered by EventBridge every 20 minutes. Logs into GolfBox (with session
caching), fetches booking grids, diffs against DynamoDB, and invokes the
shared notifications Lambda with any new availability.
"""

import datetime
import json
import logging
import os
import re
import time

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
GOLFBOX_USERNAME = os.environ.get("GOLFBOX_USERNAME", "")
GOLFBOX_PASSWORD = os.environ.get("GOLFBOX_PASSWORD", "")
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "tennis-availability")
SESSION_TABLE = os.environ.get("SESSION_TABLE", "golf-sessions")
NOTIFICATIONS_FUNCTION = os.environ.get("NOTIFICATIONS_FUNCTION", "")
DAYS_AHEAD = int(os.environ.get("SCRAPER_DAYS_AHEAD", "14"))
AWS_REGION = os.environ.get("AWS_REGION", "eu-north-1")

# Lazy-loaded AWS clients
_dynamodb = None
_lambda_client = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb


def _get_lambda_client():
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client("lambda", region_name=AWS_REGION)
    return _lambda_client


def _get_cached_session():
    """Load cached GolfBox session from DynamoDB. Returns cookies dict or None."""
    table = _get_dynamodb().Table(SESSION_TABLE)
    try:
        resp = table.get_item(Key={"sessionId": "golfbox-default"})
    except ClientError:
        return None

    item = resp.get("Item")
    if not item:
        return None

    expires_at = int(item.get("expiresAt", 0))
    if expires_at <= int(time.time()):
        return None

    cookies_str = item.get("cookies", "{}")
    return json.loads(cookies_str)


def _cache_session(cookies):
    """Cache GolfBox session cookies in DynamoDB with 2-hour TTL."""
    table = _get_dynamodb().Table(SESSION_TABLE)
    expires_at = int(time.time()) + 7200  # 2 hours
    table.put_item(Item={
        "sessionId": "golfbox-default",
        "cookies": json.dumps(cookies),
        "expiresAt": expires_at,
    })


def _load_previous_snapshot(table, composite_key, date_strings):
    """Load previous availability snapshot from DynamoDB."""
    snapshot = {}
    for date_str in date_strings:
        try:
            resp = table.get_item(Key={"facilityId": composite_key, "date": date_str})
            item = resp.get("Item")
            if item and "slots" in item:
                snapshot[date_str] = json.loads(item["slots"]) if isinstance(item["slots"], str) else item["slots"]
        except ClientError as e:
            logger.warning("Failed to load snapshot for %s/%s: %s", composite_key, date_str, e)
    return snapshot


def _save_snapshot(table, composite_key, date_str, slots):
    """Save current availability snapshot to DynamoDB."""
    table.put_item(Item={
        "facilityId": composite_key,
        "date": date_str,
        "slots": slots,
        "updatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })


def _extract_spots(description):
    """Extract spot count from a slot description like '3 spots (845,-)'.

    Returns 0 when no spot count can be parsed.
    """
    match = re.search(r"(\d+)\s*spot", description, re.IGNORECASE)
    return int(match.group(1)) if match else 0


def _compute_new_slots(prev_slots, current_slots):
    """Return only slot entries whose spot count INCREASED vs. previous snapshot.

    Golf tee times encode availability as e.g. "3 spots (price)". If a tee
    previously had 4 spots and now has 3, the user already saw the 4-spot
    notification; a degrade to 3 is not newly actionable. We only emit a
    description when its spot count exceeds the max spot count previously
    recorded for that time_key (0 if the tee was not seen before).

    Descriptions without parseable spot counts fall back to raw set-diff
    so non-golf callers / unknown formats still work.
    """
    new_slots = {}
    for time_key, descriptions in current_slots.items():
        prev_descriptions = prev_slots.get(time_key, [])
        prev_max_spots = max(
            (_extract_spots(d) for d in prev_descriptions),
            default=0,
        )
        new_descriptions = []
        for d in descriptions:
            cur_spots = _extract_spots(d)
            if cur_spots > 0:
                if cur_spots > prev_max_spots:
                    new_descriptions.append(d)
            else:
                # No parseable spot count — fall back to raw set-diff
                if d not in prev_descriptions:
                    new_descriptions.append(d)
        if new_descriptions:
            new_slots[time_key] = new_descriptions
    return new_slots


def _invoke_notifications(diff):
    """Invoke the notifications Lambda with the diff payload."""
    if not NOTIFICATIONS_FUNCTION:
        logger.warning("NOTIFICATIONS_FUNCTION not set, skipping notification")
        return

    _get_lambda_client().invoke(
        FunctionName=NOTIFICATIONS_FUNCTION,
        InvocationType="Event",  # async
        Payload=json.dumps({"diff": diff}),
    )
    logger.info("Invoked notifications Lambda with %d facility keys", len(diff))


def _fetch_slots_via_scrape(client, golfbox_config, date_str, _cache_session_cb):
    """Log into GolfBox, fetch HTML grid, parse."""
    from parser import parse_grid_html

    resource_guid = golfbox_config["resource_guid"]
    club_guid = golfbox_config["club_guid"]

    html = client.fetch_grid(resource_guid, club_guid, date_str)
    if html is None and not client._logged_in:
        logger.info("Re-logging in after session expiry")
        if not client.login():
            return None
        _cache_session_cb(client.cookies_dict)
        html = client.fetch_grid(resource_guid, club_guid, date_str)
    if html is None:
        return None
    return parse_grid_html(html)


def lambda_handler(event, context):
    """AWS Lambda entry point."""
    start_time = time.monotonic()
    logger.info("Golf scraper invoked, days_ahead=%d", DAYS_AHEAD)

    from facilities import get_facilities_for_sport, get_golfbox_config
    from scraper import GolfBoxClient

    scrape_client = GolfBoxClient(GOLFBOX_USERNAME, GOLFBOX_PASSWORD)
    cached_cookies = _get_cached_session()
    if cached_cookies:
        scrape_client.restore_cookies(cached_cookies)
        logger.info("Restored cached GolfBox session")
    else:
        if not scrape_client.login():
            return {"statusCode": 500, "body": "GolfBox login failed"}
        _cache_session(scrape_client.cookies_dict)

    today = datetime.date.today()
    dates = [today + datetime.timedelta(days=i) for i in range(DAYS_AHEAD)]
    date_strings = [d.strftime("%Y-%m-%d") for d in dates]

    availability_table = _get_dynamodb().Table(DYNAMODB_TABLE)
    golf_facilities = get_facilities_for_sport("golf")

    full_diff = {}
    total_slots = 0
    fetch_errors = 0

    for facility_key, config in golf_facilities.items():
        golfbox_config = get_golfbox_config(facility_key)
        if not golfbox_config:
            continue

        composite_key = f"{facility_key}#golf"
        previous = _load_previous_snapshot(
            availability_table, composite_key, date_strings,
        )
        facility_diff = {}

        for date_str in date_strings:
            current_slots = _fetch_slots_via_scrape(
                scrape_client, golfbox_config, date_str, _cache_session,
            )
            if current_slots is None:
                fetch_errors += 1
                continue

            total_slots += len(current_slots)
            _save_snapshot(availability_table, composite_key, date_str, current_slots)

            prev_slots = previous.get(date_str, {})
            new_slots = _compute_new_slots(prev_slots, current_slots)
            if new_slots:
                facility_diff[date_str] = new_slots

        if facility_diff:
            full_diff[composite_key] = facility_diff

    if full_diff:
        _invoke_notifications(full_diff)

    elapsed = time.monotonic() - start_time
    logger.info(
        "Golf scraper complete: slots=%d, errors=%d, diff_keys=%d, elapsed=%.1fs",
        total_slots, fetch_errors, len(full_diff), elapsed,
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "totalSlots": total_slots,
            "fetchErrors": fetch_errors,
            "diffFacilities": len(full_diff),
            "elapsed": round(elapsed, 1),
        }),
    }
