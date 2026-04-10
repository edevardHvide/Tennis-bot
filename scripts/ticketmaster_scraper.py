#!/usr/bin/env python3
"""
Event ticket availability scraper.

Supports:
  - ticketmaster.no  — selects 1 Ordinær ticket, clicks "Finn billetter", reads result
  - universe.com     — clicks "HENT BILLETTER", reads ticket modal inside iframe

Usage:
    python3 scripts/ticketmaster_scraper.py [--url URL] [--headed]
    python3 scripts/ticketmaster_scraper.py --url https://www.universe.com/events/trevarefest-2026-tickets-YBG2MZ
"""

import argparse
import os
import re
import sys
from datetime import datetime
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, Page, Frame


SCREENSHOT_DIR = "scripts/screenshots"
DEFAULTS = {
    "vinjerock": "https://www.ticketmaster.no/event/vinjerock-2026-billetter/1742328414",
    "trevarefest": "https://www.universe.com/events/trevarefest-2026-tickets-YBG2MZ?ref=ticketmaster",
}


def screenshot(page: Page, label: str, ts: str) -> str:
    path = f"{SCREENSHOT_DIR}/evt_{ts}_{label}.png"
    page.screenshot(path=path, full_page=True)
    print(f"  [{label}] {path}")
    return path


def dismiss_cookies(page: Page):
    for sel in ["#onetrust-accept-btn-handler", "button:has-text('Godta alle cookier')",
                "button:has-text('Godta alle')", "button:has-text('Accept All')",
                "button:has-text('Tillat alle')"]:
        try:
            btn = page.locator(sel)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click(timeout=2000)
                page.wait_for_timeout(800)
                return
        except Exception:
            pass


def detect_platform(url: str) -> str:
    host = urlparse(url).hostname or ""
    if "ticketmaster" in host:
        return "ticketmaster"
    if "universe" in host:
        return "universe"
    return "unknown"


# ─── Ticketmaster.no ───────────────────────────────────────────────

def scrape_ticketmaster(page: Page, ts: str) -> dict:
    """Select 1 Ordinær → Finn billetter → read result."""
    result = {"raw_signals": [], "screenshots": []}

    # Extract event metadata from page title
    title = page.title() or ""
    result["event_name"] = title.split("|")[0].split("–")[0].strip() or None
    result["venue"] = None
    venue = page.locator("header a, nav a").filter(has_text=re.compile(r"[A-ZÆØÅ]{2,}"))
    if venue.count() > 0:
        result["venue"] = venue.first.text_content().strip()

    result["screenshots"].append(screenshot(page, "1_loaded", ts))

    # Step 1: Click + on Ordinær row
    print("  Selecting 1 Ordinær ticket...")
    row = page.locator("li:has(span:has-text('Ordinær'))")
    if row.count() > 0:
        btns = row.first.locator("button")
        if btns.count() >= 2:
            btns.last.click()  # + is the last button in the stepper
            page.wait_for_timeout(500)
            result["raw_signals"].append("Selected 1 Ordinær ticket")
        else:
            result["raw_signals"].append("ERROR: No +/- buttons in Ordinær row")
            return result
    else:
        # Fallback: click any PlusButton
        plus = page.locator("button[class*='PlusButton']")
        if plus.count() > 0:
            plus.first.click()
            page.wait_for_timeout(500)
            result["raw_signals"].append("Selected ticket via PlusButton fallback")
        else:
            result["raw_signals"].append("ERROR: Could not find Ordinær row")
            return result

    # Grab price
    price = page.locator("text=/\\d[\\d\\s]*,\\d{2}\\s*kr/").first
    if price.count() > 0:
        result["price_info"] = price.text_content().strip()

    result["screenshots"].append(screenshot(page, "2_selected", ts))

    # Step 2: Click Finn billetter
    print("  Clicking 'Finn billetter'...")
    finn = page.locator("button:has-text('Finn billetter')").first
    if finn.count() == 0:
        result["raw_signals"].append("ERROR: 'Finn billetter' not found")
        return result

    finn.click()
    page.wait_for_timeout(3000)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass

    result["screenshots"].append(screenshot(page, "3_result", ts))

    # Step 3: Read the result
    body = (page.locator("body").text_content() or "").lower()

    sold_out_phrases = ["ikke nok billetter", "ingen billetter tilgjengelig", "utsolgt", "sold out"]
    available_elements = [
        "button:has-text('Legg i handlekurv')",
        "button:has-text('Gå til betaling')",
        "button:has-text('Add to cart')",
    ]

    for phrase in sold_out_phrases:
        if phrase in body:
            result["raw_signals"].append(f"SOLD OUT: '{phrase}'")

    sok_igjen = page.locator("button:has-text('Søk igjen')")
    if sok_igjen.count() > 0:
        result["raw_signals"].append("'Søk igjen' button present")

    for sel in available_elements:
        if page.locator(sel).count() > 0:
            result["raw_signals"].append(f"AVAILABLE: found {sel}")

    # Determine result
    has_sold = any(s.startswith("SOLD OUT") for s in result["raw_signals"])
    has_avail = any(s.startswith("AVAILABLE") for s in result["raw_signals"])

    if has_sold:
        result["ticket_available"] = False
        result["ticket_status_text"] = "Sold out"
    elif has_avail:
        result["ticket_available"] = True
        result["ticket_status_text"] = "Tickets available"
    else:
        result["ticket_available"] = None
        result["ticket_status_text"] = "Unknown — check screenshots"

    return result


# ─── Universe.com ──────────────────────────────────────────────────

def scrape_universe(page: Page, ts: str) -> dict:
    """Click HENT BILLETTER → read ticket modal in iframe."""
    result = {"raw_signals": [], "screenshots": []}

    # Event metadata from page
    title = page.title() or ""
    result["event_name"] = title.replace(" - Universe", "").strip() or None
    result["venue"] = None

    # Price from main page
    price = page.locator("text=/\\d[\\d\\s]*,\\d{2}\\s*kr/").first
    if price.count() > 0:
        result["price_info"] = price.text_content().strip()

    result["screenshots"].append(screenshot(page, "1_loaded", ts))

    # Click HENT BILLETTER
    print("  Clicking 'HENT BILLETTER'...")
    btn = page.locator("button:has-text('HENT BILLETTER'), button:has-text('GET TICKETS')")
    if btn.count() == 0:
        result["raw_signals"].append("ERROR: 'HENT BILLETTER' button not found")
        result["ticket_status_text"] = "Error — no ticket button"
        return result

    btn.first.click()
    page.wait_for_timeout(3000)

    result["screenshots"].append(screenshot(page, "2_modal", ts))

    # Find the universe widget iframe
    widget_frame = None
    for frame in page.frames:
        if "widgets.universe.com" in frame.url:
            widget_frame = frame
            break

    if not widget_frame:
        result["raw_signals"].append("ERROR: Universe widget iframe not found")
        result["ticket_status_text"] = "Error — no widget iframe"
        return result

    result["raw_signals"].append(f"Widget iframe: {widget_frame.url[:80]}...")

    # Read ticket types from the iframe
    read_universe_iframe(widget_frame, result)

    return result


def read_universe_iframe(frame: Frame, result: dict):
    """Extract ticket availability from the Universe widget iframe."""

    # Check each ticket type
    ticket_rows = frame.locator("text=Festival Pass, text=Billett, text=Ticket, text=Pass")
    for i in range(ticket_rows.count()):
        text = ticket_rows.nth(i).text_content().strip()
        if len(text) > 5:
            result["raw_signals"].append(f"Ticket type: {text[:80]}")

    # Key signals
    utsolgt = frame.locator("text=Utsolgt")
    if utsolgt.count() > 0:
        result["raw_signals"].append(f"SOLD OUT: 'Utsolgt' ({utsolgt.count()} matches)")

    sold_out = frame.locator("text=Sold out, text=Sold Out, text=SOLD OUT")
    if sold_out.count() > 0:
        result["raw_signals"].append(f"SOLD OUT: 'Sold out' ({sold_out.count()} matches)")

    # Percentage sold warning
    pct = frame.locator("text=/\\d+%.*solgt/")
    if pct.count() > 0:
        result["raw_signals"].append(f"Warning: '{pct.first.text_content().strip()}'")

    # Available signals: a non-sold-out ticket with a working quantity selector
    # Note: input fields in the access-key area are NOT ticket quantity selectors
    qty = frame.locator("[class*='stepper'] input, [class*='Stepper'] input, [class*='quantity'] input")
    if qty.count() > 0:
        result["raw_signals"].append(f"Quantity stepper found ({qty.count()})")

    cart_btn = frame.locator("button:has-text('Fortsett'), button:has-text('Continue')")
    if cart_btn.count() > 0:
        enabled = not cart_btn.first.is_disabled()
        result["raw_signals"].append(f"'Fortsett' button (enabled={enabled})")
        # Fortsett alone doesn't mean available — it can be present even when all tickets are sold out

    # Check for access key / waitlist
    waitlist = frame.locator("text=Venteliste, text=Waitlist, text=waitlist")
    if waitlist.count() > 0:
        result["raw_signals"].append("Waitlist option found")

    access_key = frame.locator("text=/Access key|rabattkode|access code/i")
    if access_key.count() > 0:
        result["raw_signals"].append("Access key / discount code field present")

    # Determine result — "Utsolgt" on ticket rows is the primary signal
    has_sold = any(s.startswith("SOLD OUT") for s in result["raw_signals"])
    has_avail = any(s.startswith("AVAILABLE") for s in result["raw_signals"])

    if has_sold:
        result["ticket_available"] = False
        result["ticket_status_text"] = "Sold out"
    elif has_avail:
        result["ticket_available"] = True
        result["ticket_status_text"] = "Tickets available"
    else:
        result["ticket_available"] = None
        result["ticket_status_text"] = "Unknown — check screenshots"


# ─── Main ──────────────────────────────────────────────────────────

def scrape(url: str, headed: bool = False) -> dict:
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    platform = detect_platform(url)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        page = browser.new_context(
            viewport={"width": 1280, "height": 900}, locale="nb-NO",
        ).new_page()

        print(f"Loading {url}")
        page.goto(url, wait_until="networkidle", timeout=30000)
        dismiss_cookies(page)

        if platform == "ticketmaster":
            result = scrape_ticketmaster(page, ts)
        elif platform == "universe":
            result = scrape_universe(page, ts)
        else:
            result = {
                "raw_signals": [f"Unknown platform: {platform}"],
                "ticket_available": None,
                "ticket_status_text": f"Unsupported platform: {platform}",
                "screenshots": [],
            }

        browser.close()

    result.setdefault("url", url)
    result.setdefault("platform", platform)
    result.setdefault("scraped_at", datetime.now().isoformat())
    result.setdefault("event_name", None)
    result.setdefault("venue", None)
    result.setdefault("price_info", None)
    result.setdefault("ticket_available", None)
    result.setdefault("ticket_status_text", "Unknown")
    return result


def print_result(r: dict):
    print(f"\n{'='*60}")
    print(f"  {r['event_name'] or 'Unknown Event'}")
    print(f"{'='*60}")
    print(f"  Platform:  {r.get('platform', '?')}")
    print(f"  Venue:     {r['venue'] or 'N/A'}")
    print(f"  Price:     {r['price_info'] or 'N/A'}")
    print(f"  Status:    {r['ticket_status_text']}")
    print(f"  Available: {r['ticket_available']}")
    print(f"\n  Signals:")
    for s in r["raw_signals"]:
        print(f"    - {s}")
    print(f"\n  Screenshots:")
    for s in r.get("screenshots", []):
        print(f"    - {s}")
    print(f"\n  Scraped: {r['scraped_at']}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Scrape event ticket availability")
    parser.add_argument("--url", nargs="*", help="Event URL(s). Omit to check all defaults.")
    parser.add_argument("--headed", action="store_true", help="Show browser window")
    args = parser.parse_args()

    urls = args.url if args.url else list(DEFAULTS.values())

    results = []
    for url in urls:
        print(f"\n{'─'*60}")
        result = scrape(url, headed=args.headed)
        print_result(result)
        results.append(result)

    # Summary
    if len(results) > 1:
        print(f"\n{'━'*60}")
        print("SUMMARY")
        print(f"{'━'*60}")
        for r in results:
            icon = {True: "✓", False: "✗", None: "?"}[r["ticket_available"]]
            print(f"  [{icon}] {r['event_name'] or r['url'][:50]} — {r['ticket_status_text']}")
        print(f"{'━'*60}")

    # Exit: 0 if any available, 1 if all sold out, 2 if unknown
    if any(r["ticket_available"] is True for r in results):
        sys.exit(0)
    elif all(r["ticket_available"] is False for r in results):
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
