"""
Email builder — construct HTML and plain-text weekly newsletter emails.

Day-first grouping: users scan "what's Monday?" not "what's at Frogner?"
"""

from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Facility configuration — imported from shared facilities module
# ---------------------------------------------------------------------------

from facilities import facilities, get_matchi_id, get_display_name, SPORT_CODES

MATCHI_GENERAL_URL = "https://www.matchi.se"
WEBAPP_URL = "https://availabilitymonitor.club"


def _booking_url(facility_id: int, date: str, sport: str = "tennis") -> str:
    """Build a Matchi booking URL for the given facility, date and sport."""
    sport_code = SPORT_CODES.get(sport, 1)
    return (
        f"https://www.matchi.se/book/schedule"
        f"?facilityId={facility_id}&date={date}&sport={sport_code}"
    )


def _parse_composite_key(facility_key: str) -> tuple[str, str]:
    """Parse a possibly-composite facility key like 'ota#padel'.

    Returns (base_key, sport).  If no '#' separator is present,
    defaults to 'tennis'.
    """
    if "#" in facility_key:
        base_key, sport = facility_key.rsplit("#", 1)
    else:
        base_key, sport = facility_key, "tennis"
    return base_key, sport


def _facility_name(facility_key: str) -> str:
    base_key, _sport = _parse_composite_key(facility_key)
    if base_key in facilities:
        return get_display_name(base_key)
    return base_key.title()


def _facility_matchi_id(facility_key: str) -> int:
    base_key, _sport = _parse_composite_key(facility_key)
    if base_key in facilities:
        return get_matchi_id(base_key)
    return 0


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
  <p>Availability Monitor Weekly Newsletter &mdash; {timestamp}</p>
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
        f"Availability Monitor: Your week ahead \u2014 "
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
        f"<h1>Your Week Ahead: {week_range}</h1>"
    )
    html_parts.append(f"<p>{total_courts} slot{'s' if total_courts != 1 else ''} matching your preferences</p>")

    for date_str in sorted(by_date.keys()):
        heading = _format_date_heading(date_str)
        html_parts.append(f"<h2>{heading}</h2>")

        facilities_map = by_date[date_str]
        for facility_key in sorted(facilities_map.keys()):
            courts = facilities_map[facility_key]
            name = _facility_name(facility_key)

            html_parts.append(f'<div class="facility">')
            html_parts.append(f"<h3>{name}</h3>")
            for court in courts:
                html_parts.append(
                    f'<div class="court">'
                    f'<span class="time">{court["time_slot"]}</span> '
                    f'&mdash; {court["court_name"]}'
                    f"</div>"
                )
            html_parts.append("</div>")

    # --- General CTA buttons ---
    html_parts.append(
        f'<div style="text-align:center; margin:24px 0 16px;">'
        f'<a class="book-link" href="{MATCHI_GENERAL_URL}" '
        f'style="display:inline-block; margin-top:8px; padding:12px 28px; '
        f'background:#2c5f2d; color:#fff; text-decoration:none; border-radius:6px; '
        f'font-size:15px; font-weight:bold;">'
        f'Take me to Matchi</a>'
        f'</div>'
    )
    html_parts.append(
        f'<div style="text-align:center; margin:8px 0 20px;">'
        f'<a href="{WEBAPP_URL}" '
        f'style="font-size:12px; color:#666; text-decoration:underline;">'
        f'Update your preferences</a>'
        f'</div>'
    )

    html_parts.append(_HTML_FOOTER.format(timestamp=timestamp))
    html_body = "\n".join(html_parts)

    # --- Plain text body ---
    text_parts: list[str] = [
        f"Your Week Ahead: {week_range}",
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
            text_parts.append(f"  {name}")
            for court in courts:
                text_parts.append(
                    f"    {court['time_slot']}  {court['court_name']}"
                )
        text_parts.append("")

    text_parts.append(f"Open Matchi: {MATCHI_GENERAL_URL}")
    text_parts.append(f"Update preferences: {WEBAPP_URL}")
    text_parts.append("")
    text_parts.append(f"-- Availability Monitor Weekly Newsletter | {timestamp}")
    text_body = "\n".join(text_parts)

    return {
        "subject": subject,
        "html_body": html_body,
        "text_body": text_body,
    }
