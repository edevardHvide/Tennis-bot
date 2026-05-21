"""Map Vardenlab MCP search_tee_times response → parser-format dict.

The rest of the pipeline (handler._compute_new_slots, downstream notifications,
newsletter) expects slot data as:
    {"HH:MM": ["N spot[s] (price,-)", ...], ...}

The MCP returns a list of slot dicts with:
    start: ISO timestamp
    status: free|partial|full|expired|too_far_ahead|tournament|closed|blocked|unknown
    capacity: int or null
    booked: int or null
    raw_label: messy concatenation that contains the price near the end

This module converts the MCP shape to the dict format, filtering to only
actionable slots (free + partial with >=1 free spot) and skipping every
blocked variant (tournament, closed, blocked, expired, too_far_ahead, full).
"""

import logging
import re

logger = logging.getLogger(__name__)

TEE_CAPACITY = 4
ACTIONABLE_STATUSES = {"free", "partial"}
# Price extraction is messy because MCP concatenates time ("07:00"),
# handicap decimals ("hcp:21,7"), and the price into one unseparated
# tail. See _extract_price for the case logic.
HANDICAP_MERGED_PRICE = re.compile(r",\d(\d{3,4})$")
TRAILING_DIGITS = re.compile(r"(\d+)$")


def _extract_time_key(start_iso):
    """'2026-05-25T07:09:00' -> '07:09'. Returns None if unparseable."""
    if not start_iso or "T" not in start_iso:
        return None
    try:
        hhmm = start_iso.split("T", 1)[1][:5]
    except (IndexError, AttributeError):
        return None
    if len(hhmm) != 5 or hhmm[2] != ":":
        return None
    return hhmm


def _extract_price(raw_label):
    """Extract the price from the END of raw_label as 'NNN,-' string.

    Cases (after stripping the optional ',-' suffix):
      A. Trailing run is preceded by 'NN,N' (handicap decimal) — capture
         the 3-4 digits after that single handicap digit as the price.
      B. Trailing digit run length tells us how to split:
           3 → bare 3-digit price ("845")
           4 → bare 4-digit price ("1095") if leading digit is 1-9
           5 → HH:MM(NN) merged with 3-digit price → take last 3
           6 → HH:MM(NN) merged with 4-digit price → take last 4
              (only if that last-4 starts 1-9; else give up)
    Returns None on any other shape (truncated labels, garbage).
    """
    if not raw_label:
        return None
    s = raw_label.rstrip()
    if s.endswith(",-"):
        s = s[:-2].rstrip(",")

    match = HANDICAP_MERGED_PRICE.search(s)
    if match:
        return f"{match.group(1)},-"

    match = TRAILING_DIGITS.search(s)
    if not match:
        return None
    digits = match.group(1)
    n = len(digits)

    if n == 3:
        return f"{digits},-"
    if n == 4 and digits[0] != "0":
        return f"{digits},-"
    if n == 5:
        return f"{digits[-3:]},-"
    if n == 6:
        last4 = digits[-4:]
        if last4[0] != "0":
            return f"{last4},-"
    return None


def _spots_available(slot):
    """How many seats are still bookable on this tee."""
    status = slot.get("status")
    if status == "free":
        return TEE_CAPACITY
    if status != "partial":
        return 0
    capacity = slot.get("capacity") or TEE_CAPACITY
    booked = slot.get("booked")
    if booked is None:
        # MCP reports partial but didn't fill booked — fall back to
        # counting parsed player entries. We deliberately do NOT trust the
        # raw_label name count here (the MCP truncates raw_label at ~120 chars).
        booked = len(slot.get("players") or []) or 1
    return max(0, capacity - booked)


def mcp_slots_to_dict(mcp_slots):
    """Convert MCP slot list to {time_key: [description, ...]}.

    Drops slots whose status is anything other than free/partial, and drops
    partial slots with 0 spots left (i.e. genuinely full despite the
    "partial" label — rare but possible).
    """
    result = {}
    skipped_status = 0

    for slot in mcp_slots:
        status = slot.get("status")
        if status not in ACTIONABLE_STATUSES:
            skipped_status += 1
            continue

        time_key = _extract_time_key(slot.get("start"))
        if not time_key:
            continue

        spots = _spots_available(slot)
        if spots <= 0:
            continue

        # NOTE(price-truncation): crowded "partial" tees concatenate every
        # player name into raw_label, which the MCP caps at ~120 chars — the
        # trailing price often gets cut off, so those slots render as
        # "N spots" with no price. Spot count is still correct (from
        # capacity/booked), so matching is unaffected; only the cosmetic price
        # is missing. Verified against live data 2026-05-21 (Onsøy).
        price = _extract_price(slot.get("raw_label"))
        spot_word = "spot" if spots == 1 else "spots"
        description = (
            f"{spots} {spot_word} ({price})" if price else f"{spots} {spot_word}"
        )
        result.setdefault(time_key, []).append(description)

    if skipped_status:
        logger.debug(
            "mcp_slots_to_dict: skipped %d non-actionable slots, kept %d times",
            skipped_status, len(result),
        )
    return result
