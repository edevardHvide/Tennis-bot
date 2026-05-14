"""
AWS Lambda handler — Weather Fetcher.

Fetches yr.no (MET Norway) Locationforecast for each weather region defined in
``facilities.WEATHER_REGIONS`` and writes hourly forecast buckets to the
``tennis-weather`` DynamoDB table.

Schedule: every 6 hours via EventBridge. yr.no's Expires header is typically
~30 min for short-range, longer for far-range; refreshing 4×/day per region
(3 regions = 12 requests/day) is well within MET fair-use.

Environment variables:
  AWS_REGION       (default eu-north-1)
  WEATHER_TABLE    (default tennis-weather)
  EMAIL_FROM       (used in yr.no User-Agent for contact)
  HORIZON_DAYS     (default 11)
  LOG_LEVEL        (default INFO)

Each bucket item:
  region    (PK)   region key, e.g. "oslo"
  hourIso   (SK)   "YYYY-MM-DDTHH:00" Europe/Oslo local
  temp      (N)    air temperature in Celsius
  symbol    (S)    yr.no symbol_code (e.g. "clearsky_day")
  ttl       (N)    unix epoch; item expires ~14 days after the forecast hour
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3

from facilities import WEATHER_REGIONS
from weather import (
    build_user_agent,
    expand_to_hourly_buckets,
    fetch_forecast,
)

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
if not logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_h)


def _log(level: str, message: str, **extra) -> None:
    record = {"level": level, "message": message, **extra}
    getattr(logger, level.lower(), logger.info)(json.dumps(record))


AWS_REGION = os.environ.get("AWS_REGION", "eu-north-1")
WEATHER_TABLE = os.environ.get("WEATHER_TABLE", "tennis-weather")
HORIZON_DAYS = int(os.environ.get("HORIZON_DAYS", "11"))

_dynamodb_resource = None


def _get_dynamodb():
    global _dynamodb_resource
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb_resource


def _ttl_epoch(hour_iso: str) -> int:
    """Return a unix-epoch TTL ~14 days after the bucket's hour."""
    dt = datetime.strptime(hour_iso, "%Y-%m-%dT%H:%M")
    # Treat as Oslo-local; offset doesn't matter for TTL (DynamoDB compares seconds).
    return int(dt.replace(tzinfo=timezone.utc).timestamp()) + 14 * 86400


def _write_region(region: str, buckets: list[dict], table) -> int:
    """Batch-write hourly buckets for a region. Returns count written."""
    written = 0
    with table.batch_writer(overwrite_by_pkeys=["region", "hourIso"]) as batch:
        for b in buckets:
            batch.put_item(
                Item={
                    "region": region,
                    "hourIso": b["hour_iso"],
                    "temp": Decimal(str(b["temp"])),
                    "symbol": b["symbol"],
                    "ttl": _ttl_epoch(b["hour_iso"]),
                }
            )
            written += 1
    return written


def lambda_handler(event: dict, context) -> dict:
    started = time.monotonic()
    user_agent = build_user_agent()
    _log("info", "Weather Lambda invoked",
         table=WEATHER_TABLE, regions=list(WEATHER_REGIONS.keys()),
         user_agent=user_agent)

    table = _get_dynamodb().Table(WEATHER_TABLE)
    summary: dict[str, int] = {}
    errors: list[str] = []

    for region, (lat, lon) in WEATHER_REGIONS.items():
        try:
            timeseries = fetch_forecast(lat, lon, user_agent=user_agent)
            buckets = expand_to_hourly_buckets(timeseries, horizon_days=HORIZON_DAYS)
            count = _write_region(region, buckets, table)
            summary[region] = count
            _log("info", "Region refreshed", region=region, buckets=count)
        except Exception as exc:
            errors.append(f"{region}: {exc}")
            _log("error", "Region refresh failed", region=region, error=str(exc))

    duration_ms = round((time.monotonic() - started) * 1000)
    _log("info", "Weather Lambda complete",
         summary=summary, errors=errors, duration_ms=duration_ms)

    return {
        "statusCode": 200 if not errors else 207,
        "summary": summary,
        "errors": errors,
        "duration_ms": duration_ms,
    }
