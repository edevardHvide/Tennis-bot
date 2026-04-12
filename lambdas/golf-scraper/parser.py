"""GolfBox grid HTML parser.

Extracts available tee times from GolfBox booking grid pages.
Returns data in the same format as the matchi scraper:
    dict[time_slot, list[slot_description]]
"""

import re
from bs4 import BeautifulSoup

TEE_CAPACITY = 4


def parse_grid_html(html):
    """Parse a GolfBox grid page and extract available tee times.

    Args:
        html: Raw HTML string from a GolfBox booking grid page.

    Returns:
        Dict mapping time (HH:MM) to list of slot descriptions.
        Example: {"07:00": ["4 spots (845,-)"], "07:09": ["3 spots (845,-)"]}
    """
    soup = BeautifulSoup(html, "html.parser")
    grid_div = soup.find(id="bookingGridv3")
    if not grid_div:
        return {}

    slots = {}

    for el in grid_div.find_all(attrs={"onclick": True}):
        classes = el.get("class", [])
        if "free" not in classes and "partfree" not in classes:
            continue

        # Extract time from onclick: click_show(this,row,col,'20260411T160000',...)
        onclick = el.get("onclick", "")
        time_match = re.search(r"'(\d{8}T(\d{2})(\d{2})\d{2})'", onclick)
        if not time_match:
            continue
        hour = time_match.group(2)
        minute = time_match.group(3)
        time_key = f"{hour}:{minute}"

        # Extract price from .ymPrice div
        price_div = el.find("div", class_="ymPrice")
        price = price_div.text.strip() if price_div else ""

        # Calculate spots available
        if "free" in classes and "partfree" not in classes:
            spots_available = TEE_CAPACITY
        else:
            # Count player images in .item div
            item_div = el.find("div", class_="item")
            booked_players = 0
            if item_div:
                booked_players = len(item_div.find_all("img"))
            spots_available = max(0, TEE_CAPACITY - booked_players)

        if spots_available <= 0:
            continue

        # Build slot description string
        spot_word = "spot" if spots_available == 1 else "spots"
        description = f"{spots_available} {spot_word} ({price})" if price else f"{spots_available} {spot_word}"

        slots.setdefault(time_key, []).append(description)

    return slots
