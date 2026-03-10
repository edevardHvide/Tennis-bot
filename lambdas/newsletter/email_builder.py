"""
Email builder — construct HTML and plain-text weekly newsletter emails.

Day-first grouping: users scan "what's Monday?" not "what's at Frogner?"
"""

from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Facility configuration — mirrors the scraper's mapping
# ---------------------------------------------------------------------------

FACILITIES: dict[str, int] = {
    "frogner": 2259,
    "ota": 1779,
    "bergentennisarena": 301,
}

FACILITY_DISPLAY_NAMES: dict[str, str] = {
    "frogner": "Frogner",
    "ota": "OTA",
    "bergentennisarena": "Bergen Tennis Arena",
}


def _booking_url(facility_id: int, date: str) -> str:
    """Build a Matchi booking URL for the given facility and date."""
    return (
        f"https://www.matchi.se/book/schedule"
        f"?facilityId={facility_id}&date={date}&sport=1"
    )


def _facility_name(facility_key: str) -> str:
    return FACILITY_DISPLAY_NAMES.get(facility_key, facility_key.title())


def _facility_matchi_id(facility_key: str) -> int:
    return FACILITIES.get(facility_key, 0)


# ---------------------------------------------------------------------------
# HTML email builder
# ---------------------------------------------------------------------------

_HTML_HEADER = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
  .container { max-width: 600px; margin: 0 auto; background: #fff; border-radius: 8px; padding: 24px; }
  h1 { color: #2c5f2d; font-size: 22px; }
  h2 { color: #333; font-size: 18px; margin-top: 20px; border-bottom: 1px solid #eee; padding-bottom: 4px; }
  h3 { color: #555; font-size: 15px; margin: 12px 0 4px; }
  .facility { margin-bottom: 12px; padding: 12px; background: #f9f9f9; border-radius: 6px; }
  .court { padding: 4px 0; }
  .time { font-weight: bold; color: #2c5f2d; }
  .book-link { display: inline-block; margin-top: 8px; padding: 8px 16px;
               background: #2c5f2d; color: #fff; text-decoration: none; border-radius: 4px; }
  .footer { margin-top: 24px; font-size: 12px; color: #999; }
</style>
</head>
<body>
<div class="container">
"""

_HTML_FOOTER = """\
<div class="footer">
  <p>Tennis Bot Weekly Newsletter &mdash; {timestamp}</p>
</div>
</div>
</body>
</html>
"""

_DAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
]


def _format_date_heading(date_str: str) -> str:
    """Convert 'YYYY-MM-DD' to 'Monday, 16 Mar'."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    day_name = _DAY_NAMES[dt.weekday()]
    return f"{day_name}, {dt.strftime('%d %b')}"


def build_newsletter_email(
    user_id: str,
    matches: list[dict],
    week_start: str,
    week_end: str,
) -> dict:
    """Build HTML + plain text weekly newsletter email.

    Args:
        user_id: the recipient's user/email ID.
        matches: list of match dicts from matcher, each with
                 facilityId, date, courts.
        week_start: YYYY-MM-DD of Monday.
        week_end: YYYY-MM-DD of Sunday.

    Returns:
        Dict with keys ``subject``, ``html_body``, ``text_body``.
    """
    total_courts = sum(len(m["courts"]) for m in matches)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Format week range for subject/header
    ws = datetime.strptime(week_start, "%Y-%m-%d")
    we = datetime.strptime(week_end, "%Y-%m-%d")
    week_range = f"{ws.strftime('Mon %d %b')} \u2013 {we.strftime('Sun %d %b')}"

    subject = (
        f"Tennis Bot: Your week ahead \u2014 "
        f"{total_courts} court slot{'s' if total_courts != 1 else ''} available "
        f"({ws.strftime('%d %b')} \u2013 {we.strftime('%d %b')})"
    )

    # --- Group by date -> facility (day-first) ---
    # { date_str: { facility_key: [court_dicts] } }
    by_date: dict[str, dict[str, list[dict]]] = {}
    for match in matches:
        date = match["date"]
        fac = match["facilityId"]
        by_date.setdefault(date, {}).setdefault(fac, []).extend(match["courts"])

    # --- HTML body ---
    html_parts: list[str] = [_HTML_HEADER]
    html_parts.append(
        f"<h1>Your Tennis Week: {week_range}</h1>"
    )
    html_parts.append(f"<p>{total_courts} slot{'s' if total_courts != 1 else ''} matching your preferences</p>")

    for date_str in sorted(by_date.keys()):
        heading = _format_date_heading(date_str)
        html_parts.append(f"<h2>{heading}</h2>")

        facilities_map = by_date[date_str]
        for facility_key in sorted(facilities_map.keys()):
            courts = facilities_map[facility_key]
            name = _facility_name(facility_key)
            matchi_id = _facility_matchi_id(facility_key)
            url = _booking_url(matchi_id, date_str)

            html_parts.append(f'<div class="facility">')
            html_parts.append(f"<h3>{name}</h3>")
            for court in courts:
                html_parts.append(
                    f'<div class="court">'
                    f'<span class="time">{court["time_slot"]}</span> '
                    f'&mdash; {court["court_name"]}'
                    f"</div>"
                )
            html_parts.append(
                f'<a class="book-link" href="{url}">Book at {name}</a>'
            )
            html_parts.append("</div>")

    html_parts.append(_HTML_FOOTER.format(timestamp=timestamp))
    html_body = "\n".join(html_parts)

    # --- Plain text body ---
    text_parts: list[str] = [
        f"Your Tennis Week: {week_range}",
        f"{total_courts} slot{'s' if total_courts != 1 else ''} matching your preferences",
        "=" * 50,
        "",
    ]
    for date_str in sorted(by_date.keys()):
        heading = _format_date_heading(date_str)
        text_parts.append(heading)
        text_parts.append("-" * len(heading))

        facilities_map = by_date[date_str]
        for facility_key in sorted(facilities_map.keys()):
            courts = facilities_map[facility_key]
            name = _facility_name(facility_key)
            matchi_id = _facility_matchi_id(facility_key)
            url = _booking_url(matchi_id, date_str)
            text_parts.append(f"  {name}")
            for court in courts:
                text_parts.append(
                    f"    {court['time_slot']}  {court['court_name']}"
                )
            text_parts.append(f"    Book: {url}")
        text_parts.append("")

    text_parts.append(f"-- Tennis Bot Weekly Newsletter | {timestamp}")
    text_body = "\n".join(text_parts)

    return {
        "subject": subject,
        "html_body": html_body,
        "text_body": text_body,
    }
