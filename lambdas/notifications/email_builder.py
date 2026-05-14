"""
Email builder — construct HTML and plain-text notification emails.

Produces SES-ready email bodies without any template engine dependency
(no Jinja2).  HTML is built with simple string formatting.
"""

import random
from datetime import datetime, timezone
from typing import Callable, Optional

from facilities import facilities, get_matchi_id, get_display_name, get_golfbox_config, get_oslobooking_config, SPORT_CODES

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


def _format_date_heading(date_str: str) -> str:
    """Convert 'YYYY-MM-DD' to 'Friday, 15 May'. Fail-safe: returns input on parse error."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return date_str
    return f"{dt.strftime('%A')}, {dt.strftime('%d %b')}"

MATCHI_GENERAL_URL = "https://www.matchi.se"
HARVARD_REG_URL = (
    "https://membership.gocrimson.com/Program/GetProgramInstances"
    "?programID=a20e7ae2-fedc-4a8e-a7c3-236695040c63"
)
WEBAPP_URL = "https://availabilitymonitor.club"


# ---------------------------------------------------------------------------
# Sport-group taxonomy
# ---------------------------------------------------------------------------
# Tennis and padel share matchi.se, racket vocabulary ("court"), and look the
# same in an inbox. Golf uses GolfBox, "tee time" vocabulary, and a fairway
# vibe. Emails are split per sport-group so a golfer's inbox never gets
# racket copy and vice versa.

SPORT_GROUP_RACKET = "racket"
SPORT_GROUP_GOLF = "golf"


def sport_group_for(sport: str) -> str:
    """Map a sport to its email taxonomy group."""
    return SPORT_GROUP_GOLF if sport == "golf" else SPORT_GROUP_RACKET


# ---------------------------------------------------------------------------
# Fun quotes & subject lines, keyed by sport-group.
# ---------------------------------------------------------------------------

_QUOTES_RACKET = [
    "The ball is round, the court is open — go get it!",
    "You miss 100% of the shots you don't book.",
    "Tennis is the sport in which you talk to yourself, the ball, the racket, and the net.",
    "Champions keep playing until they get it right. — Billie Jean King",
    "The most important point in tennis is always the next one.",
    "In tennis, it is not the opponent you fear, it is the failure itself. — Andre Agassi",
    "Life is like tennis — the player who serves well seldom loses.",
    "Good things come to those who book early.",
    "New balls, please!",
    "Padel is not just a sport, it's an addiction with glass walls.",
    "The only bad workout is the one that never happened — book a court!",
    "Every champion was once a contender who refused to give up. — Rocky Balboa",
]

_QUOTES_GOLF = [
    "Golf is deceptively simple and endlessly complicated. — Arnold Palmer",
    "The most important shot in golf is the next one. — Ben Hogan",
    "A bad day on the course beats a good day anywhere else.",
    "Drive for show, putt for dough.",
    "Swing hard in case you hit it. — Dan Marino",
    "Golf is a good walk spoiled — until you book the right tee time.",
    "The harder I practice, the luckier I get. — Gary Player",
    "Tee it high and let it fly.",
    "Eighteen holes of match play will teach you more about your foe than 18 years of dealing with him across a desk. — Grantland Rice",
]

_SUBJECT_PREFIXES_RACKET = [
    "Game, Set, Match!",
    "New courts on the radar!",
    "Court alert!",
    "Heads up!",
    "Fresh courts just dropped!",
    "Racket ready?",
    "Time to play!",
]

_SUBJECT_PREFIXES_GOLF = [
    "Fairway alert!",
    "Tee time drop!",
    "Fore!",
    "On the tee...",
    "Fresh tee times!",
    "Greens are calling!",
    "Heads up, golfer!",
]


def _config_for_group(sport_group: str) -> dict:
    """Return copy + accent palette for the sport group."""
    if sport_group == SPORT_GROUP_GOLF:
        return {
            "slot_word_singular": "tee time",
            "slot_word_plural": "tee times",
            "headline_singular": "1 New Tee Time Found",
            "headline_plural_template": "{n} New Tee Times Found",
            "subject_prefixes": _SUBJECT_PREFIXES_GOLF,
            "quotes": _QUOTES_GOLF,
            "accent": "#1f4a20",         # deep fairway green
            "accent_soft": "#f0fdf4",
            "icon": "&#9971;",           # ⛳
        }
    return {
        "slot_word_singular": "court",
        "slot_word_plural": "courts",
        "headline_singular": "1 New Court Found",
        "headline_plural_template": "{n} New Courts Found",
        "subject_prefixes": _SUBJECT_PREFIXES_RACKET,
        "quotes": _QUOTES_RACKET,
        "accent": "#2c5f2d",
        "accent_soft": "#f0f9f0",
        "icon": "&#127934;",            # 🎾
    }


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


def _facility_cta(facility_key: str, sport: str = "tennis", date: str = "") -> tuple:
    """Return (url, label) for the CTA button for a given facility.

    Facilities with matchi_id=None are non-Matchi platforms (e.g. Harvard Rec, GolfBox).
    """
    golfbox_config = get_golfbox_config(facility_key)
    if golfbox_config and sport == "golf":
        club_guid = golfbox_config["club_guid"]
        resource_guid = golfbox_config["resource_guid"]
        url = (
            f"https://www.golfbox.no/portal/public/greenfee/greenfee.asp"
            f"?ClubGUID={club_guid}&ResourceGUID={resource_guid}"
        )
        if date:
            url += f"&Date={date}"
        return url, "Book on GolfBox"
    oslobooking_config = get_oslobooking_config(facility_key)
    if oslobooking_config:
        return oslobooking_config["booking_url"], "Book on Oslo kommune"
    matchi_id = _facility_matchi_id(facility_key)
    if matchi_id is None:
        return HARVARD_REG_URL, "Register at Harvard Rec"
    return MATCHI_GENERAL_URL, "Book on Matchi"


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


def build_notification_email(
    user_id: str,
    matches: list[dict],
    weather_lookup: WeatherLookup | None = None,
    sport_group: str | None = None,
) -> dict:
    """Build HTML + plain text email body for a user's matched slots.

    Args:
        user_id: the recipient's user/email ID.
        matches: list of match dicts, each with facilityId, sport, date, courts.
            All matches MUST belong to the same sport group (racket or golf);
            callers are expected to partition before invoking.
        weather_lookup: optional ``(facility_key, date, time_slot) -> dict|None``
            callable used to enrich each slot with an icon + temperature.
        sport_group: ``"racket"`` or ``"golf"``. If omitted, inferred from the
            first match's sport. Controls copy, vocabulary, and accent colour.

    Returns:
        Dict with keys ``subject``, ``html_body``, ``text_body``.
    """
    if sport_group is None:
        first_sport = matches[0].get("sport", "tennis") if matches else "tennis"
        sport_group = sport_group_for(first_sport)
    cfg = _config_for_group(sport_group)

    total_slots = sum(len(m["courts"]) for m in matches)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # --- Subject (sport-group-themed) ---
    prefix = random.choice(cfg["subject_prefixes"])
    slot_word = cfg["slot_word_singular"] if total_slots == 1 else cfg["slot_word_plural"]
    subject = f"Availability Monitor: {prefix} {total_slots} new {slot_word} available!"

    # --- Group by facility + sport + date for display ---
    grouped: dict[tuple[str, str], dict[str, list[dict]]] = {}
    for match in matches:
        fac = match["facilityId"]
        sport = match.get("sport", "tennis")
        date = match["date"]
        group_key = (fac, sport)
        grouped.setdefault(group_key, {}).setdefault(date, []).extend(match["courts"])

    accent = cfg["accent"]

    # --- HTML body ---
    html_parts: list[str] = [_HTML_HEADER]
    headline = (
        cfg["headline_singular"] if total_slots == 1
        else cfg["headline_plural_template"].format(n=total_slots)
    )
    html_parts.append(
        f'<h1>{cfg["icon"]} {headline}</h1>'
    )

    for (facility_key, sport), dates_map in sorted(grouped.items()):
        name = _facility_name(facility_key)
        # For racket emails, only show "Padel" label (tennis is the default in this email).
        # For golf emails, no extra sport label — every facility is golf.
        sport_label = sport.title() if sport_group == "racket" and sport != "tennis" else ""
        heading = f"{name} — {sport_label}" if sport_label else name
        first_date = sorted(dates_map.keys())[0] if dates_map else ""
        cta_url, cta_label = _facility_cta(facility_key, sport=sport, date=first_date)
        html_parts.append(f'<div class="facility">')
        html_parts.append(f"<h2>{heading}</h2>")

        for date_str, courts in sorted(dates_map.items()):
            html_parts.append(f"<p><strong>{_format_date_heading(date_str)}</strong></p>")
            for court in courts:
                weather = (
                    weather_lookup(facility_key, date_str, court["time_slot"])
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

        html_parts.append(
            f'<div style="text-align:center; margin:12px 0 4px;">'
            f'<a class="book-link" href="{cta_url}" '
            f'style="display:inline-block; margin-top:8px; padding:10px 24px; '
            f'background:{accent}; color:#fff; text-decoration:none; border-radius:6px; '
            f'font-size:14px; font-weight:bold;">'
            f'{cta_label}</a>'
            f'</div>'
        )
        html_parts.append("</div>")

    # --- Preferences link ---
    html_parts.append(
        f'<div style="text-align:center; margin:8px 0 20px;">'
        f'<a href="{WEBAPP_URL}" '
        f'style="font-size:12px; color:#666; text-decoration:underline;">'
        f'Update your preferences</a>'
        f'</div>'
    )

    # --- Fun quote ---
    quote = random.choice(cfg["quotes"])
    html_parts.append(
        f'<div style="border-left:3px solid {accent}; padding:10px 16px; margin:20px 0;'
        f' background:{cfg["accent_soft"]}; border-radius:0 6px 6px 0; font-style:italic;'
        f' color:#475569; font-size:14px;">'
        f"{quote}</div>"
    )

    html_parts.append(_HTML_FOOTER.format(timestamp=timestamp))
    html_body = "\n".join(html_parts)

    # --- Plain text body ---
    text_parts: list[str] = [
        headline,
        "=" * 40,
        "",
    ]
    for (facility_key, sport), dates_map in sorted(grouped.items()):
        name = _facility_name(facility_key)
        sport_label = sport.title() if sport_group == "racket" and sport != "tennis" else ""
        heading = f"{name} — {sport_label}" if sport_label else name
        first_date = sorted(dates_map.keys())[0] if dates_map else ""
        cta_url, cta_label = _facility_cta(facility_key, sport=sport, date=first_date)
        text_parts.append(heading)
        text_parts.append("-" * len(heading))
        for date_str, courts in sorted(dates_map.items()):
            text_parts.append(f"  {_format_date_heading(date_str)}")
            for court in courts:
                weather = (
                    weather_lookup(facility_key, date_str, court["time_slot"])
                    if weather_lookup else None
                )
                weather_text = _format_weather(weather)
                text_parts.append(
                    f"    {court['time_slot']}{weather_text}  {court['court_name']}"
                )
        text_parts.append(f"  {cta_label}: {cta_url}")
        text_parts.append("")
    text_parts.append(f"Update preferences: {WEBAPP_URL}")
    text_parts.append("")
    text_parts.append(f'"{quote}"')
    text_parts.append("")
    text_parts.append(f"-- Availability Monitor | {timestamp}")
    text_body = "\n".join(text_parts)

    return {
        "subject": subject,
        "html_body": html_body,
        "text_body": text_body,
    }
