"""
Email builder — construct HTML and plain-text notification emails.

Produces SES-ready email bodies without any template engine dependency
(no Jinja2).  HTML is built with simple string formatting.
"""

from datetime import datetime, timezone

from facilities import facilities, get_matchi_id, get_display_name, SPORT_CODES


def _booking_url(facility_id: int, date: str, sport: str = "tennis") -> str:
    """Build a Matchi booking URL for the given facility, date, and sport."""
    sport_code = SPORT_CODES.get(sport, 1)
    return (
        f"https://www.matchi.se/book/schedule"
        f"?facilityId={facility_id}&date={date}&sport={sport_code}"
    )


def _facility_name(facility_key: str) -> str:
    try:
        return get_display_name(facility_key)
    except KeyError:
        return facility_key.title()


def _facility_matchi_id(facility_key: str) -> int:
    try:
        return get_matchi_id(facility_key)
    except KeyError:
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
  <p>Availability Monitor Notification &mdash; {timestamp}</p>
</div>
</div>
</body>
</html>
"""


def build_notification_email(user_id: str, matches: list[dict]) -> dict:
    """Build HTML + plain text email body for a user's matched courts.

    Args:
        user_id: the recipient's user/email ID.
        matches: list of match dicts, each with facilityId, sport, date, courts.

    Returns:
        Dict with keys ``subject``, ``html_body``, ``text_body``.
    """
    total_courts = sum(len(m["courts"]) for m in matches)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # --- Subject ---
    subject = f"Availability Monitor: {total_courts} new court{'s' if total_courts != 1 else ''} available!"

    # --- Group by facility + sport + date for display ---
    # { (facility_key, sport): { date: [court_dicts] } }
    grouped: dict[tuple[str, str], dict[str, list[dict]]] = {}
    for match in matches:
        fac = match["facilityId"]
        sport = match.get("sport", "tennis")
        date = match["date"]
        group_key = (fac, sport)
        grouped.setdefault(group_key, {}).setdefault(date, []).extend(match["courts"])

    # --- HTML body ---
    html_parts: list[str] = [_HTML_HEADER]
    html_parts.append(f"<h1>{total_courts} New Court{'s' if total_courts != 1 else ''} Found</h1>")

    for (facility_key, sport), dates_map in sorted(grouped.items()):
        name = _facility_name(facility_key)
        matchi_id = _facility_matchi_id(facility_key)
        sport_label = sport.title() if sport != "tennis" else ""
        heading = f"{name} — {sport_label}" if sport_label else name
        html_parts.append(f'<div class="facility">')
        html_parts.append(f"<h2>{heading}</h2>")

        for date_str, courts in sorted(dates_map.items()):
            url = _booking_url(matchi_id, date_str, sport)
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
    for (facility_key, sport), dates_map in sorted(grouped.items()):
        name = _facility_name(facility_key)
        matchi_id = _facility_matchi_id(facility_key)
        sport_label = sport.title() if sport != "tennis" else ""
        heading = f"{name} — {sport_label}" if sport_label else name
        text_parts.append(heading)
        text_parts.append("-" * len(heading))
        for date_str, courts in sorted(dates_map.items()):
            url = _booking_url(matchi_id, date_str, sport)
            text_parts.append(f"  {date_str}")
            for court in courts:
                text_parts.append(
                    f"    {court['time_slot']}  {court['court_name']}"
                )
            text_parts.append(f"  Book: {url}")
        text_parts.append("")

    text_parts.append(f"-- Availability Monitor | {timestamp}")
    text_body = "\n".join(text_parts)

    return {
        "subject": subject,
        "html_body": html_body,
        "text_body": text_body,
    }
