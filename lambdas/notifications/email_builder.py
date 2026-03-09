"""
Email builder — construct HTML and plain-text notification emails.

Produces SES-ready email bodies without any template engine dependency
(no Jinja2).  HTML is built with simple string formatting.
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
  h2 { color: #333; font-size: 18px; margin-top: 20px; }
  .facility { margin-bottom: 20px; padding: 16px; background: #f9f9f9; border-radius: 6px; }
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
  <p>Tennis Bot Notification &mdash; {timestamp}</p>
</div>
</div>
</body>
</html>
"""


def build_notification_email(user_id: str, matches: list[dict]) -> dict:
    """Build HTML + plain text email body for a user's matched courts.

    Args:
        user_id: the recipient's user/email ID.
        matches: list of match dicts, each with facilityId, date, courts.

    Returns:
        Dict with keys ``subject``, ``html_body``, ``text_body``.
    """
    total_courts = sum(len(m["courts"]) for m in matches)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # --- Subject ---
    subject = f"Tennis Bot: {total_courts} new court{'s' if total_courts != 1 else ''} available!"

    # --- Group by facility + date for display ---
    # { facility_key: { date: [court_dicts] } }
    grouped: dict[str, dict[str, list[dict]]] = {}
    for match in matches:
        fac = match["facilityId"]
        date = match["date"]
        grouped.setdefault(fac, {}).setdefault(date, []).extend(match["courts"])

    # --- HTML body ---
    html_parts: list[str] = [_HTML_HEADER]
    html_parts.append(f"<h1>{total_courts} New Court{'s' if total_courts != 1 else ''} Found</h1>")

    for facility_key, dates_map in sorted(grouped.items()):
        name = _facility_name(facility_key)
        matchi_id = _facility_matchi_id(facility_key)
        html_parts.append(f'<div class="facility">')
        html_parts.append(f"<h2>{name}</h2>")

        for date_str, courts in sorted(dates_map.items()):
            url = _booking_url(matchi_id, date_str)
            html_parts.append(f"<p><strong>{date_str}</strong></p>")
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
        f"{total_courts} New Court{'s' if total_courts != 1 else ''} Found",
        "=" * 40,
        "",
    ]
    for facility_key, dates_map in sorted(grouped.items()):
        name = _facility_name(facility_key)
        matchi_id = _facility_matchi_id(facility_key)
        text_parts.append(name)
        text_parts.append("-" * len(name))
        for date_str, courts in sorted(dates_map.items()):
            url = _booking_url(matchi_id, date_str)
            text_parts.append(f"  {date_str}")
            for court in courts:
                text_parts.append(
                    f"    {court['time_slot']}  {court['court_name']}"
                )
            text_parts.append(f"  Book: {url}")
        text_parts.append("")

    text_parts.append(f"-- Tennis Bot | {timestamp}")
    text_body = "\n".join(text_parts)

    return {
        "subject": subject,
        "html_body": html_body,
        "text_body": text_body,
    }
