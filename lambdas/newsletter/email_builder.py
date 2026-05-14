"""
Email builder — construct HTML and plain-text weekly newsletter emails.

Day-first grouping: users scan "what's Monday?" not "what's at Frogner?"
"""

from datetime import datetime, timezone
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Facility configuration — imported from shared facilities module
# ---------------------------------------------------------------------------

from facilities import facilities, get_matchi_id, get_display_name, SPORT_CODES

WeatherLookup = Callable[[str, str, str], Optional[dict]]


def _format_weather(weather: dict | None) -> str:
    """Render a compact ' EMOJI Nm°C' suffix, or '' on miss."""
    if not weather:
        return ""
    emoji = weather.get("emoji") or ""
    temp = weather.get("temp")
    if temp is None:
        return f" {emoji}".rstrip() if emoji else ""
    return f" {emoji} {round(temp)}°C".rstrip()

MATCHI_GENERAL_URL = "https://www.matchi.se"
WEBAPP_URL = "https://availabilitymonitor.club"

SPORT_GROUP_RACKET = "racket"
SPORT_GROUP_GOLF = "golf"


def sport_group_for(sport: str) -> str:
    """Map a sport to its email taxonomy group (racket vs golf)."""
    return SPORT_GROUP_GOLF if sport == "golf" else SPORT_GROUP_RACKET


def _newsletter_config(sport_group: str) -> dict:
    """Return copy + accent palette for a sport-group newsletter."""
    if sport_group == SPORT_GROUP_GOLF:
        return {
            "slot_word_singular": "tee time",
            "slot_word_plural": "tee times",
            "title_prefix": "Your Golf Week Ahead",
            "cta_label": "Browse upcoming tee times",
            "cta_url": "https://availabilitymonitor.club",
            "accent": "#1f4a20",
            "icon": "&#9971;",
        }
    return {
        "slot_word_singular": "court slot",
        "slot_word_plural": "court slots",
        "title_prefix": "Your Week Ahead",
        "cta_label": "Take me to Matchi",
        "cta_url": MATCHI_GENERAL_URL,
        "accent": "#2c5f2d",
        "icon": "&#127934;",
    }


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
    weather_lookup: WeatherLookup | None = None,
    sport_group: str | None = None,
) -> dict:
    """Build HTML + plain text weekly newsletter email.

    Args:
        user_id: the recipient's user/email ID.
        matches: list of match dicts from matcher. All matches MUST belong
            to the same sport-group (racket or golf); callers partition first.
        week_start: YYYY-MM-DD of Monday.
        week_end: YYYY-MM-DD of Sunday.
        weather_lookup: optional ``(facility_key, date, time_slot) -> dict|None``
            used to enrich each slot with icon + temp. Decorative.
        sport_group: ``"racket"`` or ``"golf"``. If omitted, inferred from
            the first match. Drives copy + accent.

    Returns:
        Dict with keys ``subject``, ``html_body``, ``text_body``.
    """
    if sport_group is None:
        first_sport = matches[0].get("sport", "tennis") if matches else "tennis"
        sport_group = sport_group_for(first_sport)
    cfg = _newsletter_config(sport_group)

    total_slots = sum(len(m["courts"]) for m in matches)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Format week range for subject/header
    ws = datetime.strptime(week_start, "%Y-%m-%d")
    we = datetime.strptime(week_end, "%Y-%m-%d")
    week_range = f"{ws.strftime('Mon %d %b')} \u2013 {we.strftime('Sun %d %b')}"

    slot_word = cfg["slot_word_singular"] if total_slots == 1 else cfg["slot_word_plural"]
    subject = (
        f"Availability Monitor: {cfg['title_prefix']} \u2014 "
        f"{total_slots} {slot_word} available "
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
    accent = cfg["accent"]
    html_parts: list[str] = [_HTML_HEADER]
    html_parts.append(
        f'<h1>{cfg["icon"]} {cfg["title_prefix"]}: {week_range}</h1>'
    )
    html_parts.append(
        f"<p>{total_slots} {slot_word} matching your preferences</p>"
    )

    for date_str in sorted(by_date.keys()):
        heading = _format_date_heading(date_str)
        html_parts.append(f"<h2>{heading}</h2>")

        facilities_map = by_date[date_str]
        for facility_key in sorted(facilities_map.keys()):
            courts = facilities_map[facility_key]
            name = _facility_name(facility_key)

            base_key, _sport = _parse_composite_key(facility_key)
            html_parts.append(f'<div class="facility">')
            html_parts.append(f"<h3>{name}</h3>")
            for court in courts:
                weather = (
                    weather_lookup(base_key, date_str, court["time_slot"])
                    if weather_lookup else None
                )
                weather_html = _format_weather(weather)
                html_parts.append(
                    f'<div class="court">'
                    f'<span class="time" style="color:{accent};">{court["time_slot"]}</span>'
                    f'<span style="color:#475569; font-size:13px;">{weather_html}</span>'
                    f' &mdash; {court["court_name"]}'
                    f"</div>"
                )
            html_parts.append("</div>")

    # --- General CTA button (sport-group-specific) ---
    html_parts.append(
        f'<div style="text-align:center; margin:24px 0 16px;">'
        f'<a class="book-link" href="{cfg["cta_url"]}" '
        f'style="display:inline-block; margin-top:8px; padding:12px 28px; '
        f'background:{accent}; color:#fff; text-decoration:none; border-radius:6px; '
        f'font-size:15px; font-weight:bold;">'
        f'{cfg["cta_label"]}</a>'
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
        f"{cfg['title_prefix']}: {week_range}",
        f"{total_slots} {slot_word} matching your preferences",
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
            base_key, _sport = _parse_composite_key(facility_key)
            text_parts.append(f"  {name}")
            for court in courts:
                weather = (
                    weather_lookup(base_key, date_str, court["time_slot"])
                    if weather_lookup else None
                )
                weather_text = _format_weather(weather)
                text_parts.append(
                    f"    {court['time_slot']}{weather_text}  {court['court_name']}"
                )
        text_parts.append("")

    text_parts.append(f"{cfg['cta_label']}: {cfg['cta_url']}")
    text_parts.append(f"Update preferences: {WEBAPP_URL}")
    text_parts.append("")
    text_parts.append(f"-- Availability Monitor Weekly Newsletter | {timestamp}")
    text_body = "\n".join(text_parts)

    return {
        "subject": subject,
        "html_body": html_body,
        "text_body": text_body,
    }
