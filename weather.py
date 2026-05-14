"""
Weather module — yr.no (MET Norway) Locationforecast client + DynamoDB cache.

Used by:
  - lambdas/weather/   to fetch forecasts and write hourly buckets
  - lambdas/notifications/ and lambdas/newsletter/ to look up weather per slot

Design notes:
  - MET requires a contact-identifying User-Agent. We derive it from EMAIL_FROM.
  - Forecast hours are stored in Europe/Oslo local naive ISO form, matching slot keys.
  - yr.no's compact timeseries drops from hourly to 6h-resolution after ~48h.
    To keep slot coverage useful, each entry's forecast is propagated forward
    to fill hourly buckets until the next entry.
  - Symbol codes map to a small emoji set (advisor symbol list at
    https://api.met.no/weatherapi/weathericon/2.0/documentation).

Reader contract: ``weather_lookup(facility_key, date, hour) -> dict | None``
where date is "YYYY-MM-DD" and hour is "HH:MM" (Oslo local).
Returns ``{"temp": float, "symbol": str, "emoji": str}`` or None on any miss.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

YR_ENDPOINT = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
OSLO_TZ = ZoneInfo("Europe/Oslo")

# Symbol-base → emoji. Strip _day / _night / _polartwilight suffix before lookup.
# See https://api.met.no/weatherapi/weathericon/2.0/documentation
_SYMBOL_EMOJI: dict[str, str] = {
    "clearsky": "☀️",
    "fair": "🌤️",
    "partlycloudy": "⛅",
    "cloudy": "☁️",
    "fog": "🌫️",
    "lightrain": "🌦️",
    "rain": "🌧️",
    "heavyrain": "🌧️",
    "lightrainshowers": "🌦️",
    "rainshowers": "🌦️",
    "heavyrainshowers": "🌧️",
    "lightsleet": "🌨️",
    "sleet": "🌨️",
    "heavysleet": "🌨️",
    "lightsnow": "🌨️",
    "snow": "❄️",
    "heavysnow": "❄️",
    "lightsnowshowers": "🌨️",
    "snowshowers": "🌨️",
    "heavysnowshowers": "❄️",
    "thunder": "⛈️",
    "rainandthunder": "⛈️",
    "heavyrainandthunder": "⛈️",
    "sleetandthunder": "⛈️",
    "snowandthunder": "⛈️",
}
_DEFAULT_EMOJI = "🌡️"


def symbol_to_emoji(symbol_code: str | None) -> str:
    """Map a yr.no symbol_code to an emoji. Fallback if unknown."""
    if not symbol_code:
        return _DEFAULT_EMOJI
    base = symbol_code
    for suffix in ("_day", "_night", "_polartwilight"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return _SYMBOL_EMOJI.get(base, _DEFAULT_EMOJI)


def build_user_agent(contact: str | None = None) -> str:
    """Build MET-compliant User-Agent. MET will reject requests without one."""
    contact = contact or os.environ.get("EMAIL_FROM") or "edevard.hvide@gmail.com"
    return f"AvailabilityMonitor/1.0 {contact}"


def fetch_forecast(lat: float, lon: float, user_agent: str | None = None) -> list[dict]:
    """Fetch yr.no compact forecast for a (lat, lon). Returns raw timeseries entries.

    Each entry has keys ``time`` (ISO UTC) and ``data``. Caller is responsible
    for converting to hourly buckets via ``expand_to_hourly_buckets``.
    """
    ua = user_agent or build_user_agent()
    url = f"{YR_ENDPOINT}?lat={lat:.4f}&lon={lon:.4f}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": ua,
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        payload = json.loads(raw)
    return payload.get("properties", {}).get("timeseries", [])


def _entry_symbol(entry: dict) -> str | None:
    """Pick the best symbol_code from a timeseries entry (1h > 6h > 12h)."""
    data = entry.get("data", {})
    for key in ("next_1_hours", "next_6_hours", "next_12_hours"):
        block = data.get(key)
        if block:
            sym = block.get("summary", {}).get("symbol_code")
            if sym:
                return sym
    return None


def _entry_temp(entry: dict) -> float | None:
    """Instant air temperature in Celsius, or None."""
    details = entry.get("data", {}).get("instant", {}).get("details", {})
    temp = details.get("air_temperature")
    return float(temp) if temp is not None else None


def expand_to_hourly_buckets(
    timeseries: Iterable[dict],
    horizon_days: int = 11,
) -> list[dict]:
    """Convert raw yr.no timeseries to hourly buckets in Europe/Oslo time.

    yr.no entries are hourly for ~48h, then 6-hourly, then 12-hourly. We
    propagate each entry's forecast forward to fill every hour until the
    next entry, so callers get coverage at hourly granularity.

    Returns a list of dicts with keys:
      - hour_iso: "YYYY-MM-DDTHH:00" (Oslo local naive)
      - temp:    float
      - symbol:  str
    """
    entries = sorted(
        (e for e in timeseries if "time" in e),
        key=lambda e: e["time"],
    )
    if not entries:
        return []

    now_utc = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    cutoff_utc = now_utc + timedelta(days=horizon_days)
    buckets: list[dict] = []

    for idx, entry in enumerate(entries):
        try:
            start = datetime.fromisoformat(entry["time"].replace("Z", "+00:00"))
        except ValueError:
            continue
        if start > cutoff_utc:
            break
        symbol = _entry_symbol(entry)
        temp = _entry_temp(entry)
        if symbol is None or temp is None:
            continue

        # Propagate forward until the next entry's time (exclusive) or cutoff.
        if idx + 1 < len(entries):
            try:
                end = datetime.fromisoformat(entries[idx + 1]["time"].replace("Z", "+00:00"))
            except ValueError:
                end = start + timedelta(hours=1)
        else:
            end = start + timedelta(hours=1)
        end = min(end, cutoff_utc)

        cur = start.replace(minute=0, second=0, microsecond=0)
        while cur < end:
            oslo = cur.astimezone(OSLO_TZ)
            buckets.append({
                "hour_iso": oslo.strftime("%Y-%m-%dT%H:00"),
                "temp": round(temp, 1),
                "symbol": symbol,
            })
            cur += timedelta(hours=1)

    return buckets


# ---------------------------------------------------------------------------
# DynamoDB read side — used by notifications + newsletter email builders.
# ---------------------------------------------------------------------------


def _slot_hour_iso(date: str, time_slot: str) -> str | None:
    """Compose a weather lookup key from a slot's date + start time.

    Accepts time_slot like "17:00" or "17:00-18:00". Returns "YYYY-MM-DDTHH:00".
    """
    if not date or not time_slot:
        return None
    start = time_slot.split("-")[0].strip()
    if len(start) < 4:
        return None
    hh = start.split(":")[0].zfill(2)
    return f"{date}T{hh}:00"


def make_weather_lookup(
    table,
    region_resolver: Callable[[str], str | None],
) -> Callable[[str, str, str], dict | None]:
    """Build a memoised weather_lookup(facility_key, date, time_slot) callable.

    Args:
        table: a boto3 DynamoDB Table for the tennis-weather table.
        region_resolver: facility_key -> region_key (e.g., facilities.get_weather_region).

    Returns a callable that returns ``{"temp": float, "symbol": str, "emoji": str}``
    or None on any miss / error. Errors are logged but never raised — weather is
    decorative.
    """
    cache: dict[tuple[str, str], dict | None] = {}

    def lookup(facility_key: str, date: str, time_slot: str) -> dict | None:
        try:
            region = region_resolver(facility_key)
            if not region:
                return None
            hour_iso = _slot_hour_iso(date, time_slot)
            if not hour_iso:
                return None
            cache_key = (region, hour_iso)
            if cache_key in cache:
                return cache[cache_key]
            resp = table.get_item(Key={"region": region, "hourIso": hour_iso})
            item = resp.get("Item")
            if not item:
                cache[cache_key] = None
                return None
            symbol = item.get("symbol")
            temp = item.get("temp")
            result = {
                "temp": float(temp) if temp is not None else None,
                "symbol": symbol,
                "emoji": symbol_to_emoji(symbol),
            }
            cache[cache_key] = result
            return result
        except Exception as exc:
            logger.warning("weather_lookup failed: %s", exc)
            return None

    return lookup
