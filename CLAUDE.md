# Tennis Bot — Claude Code Guide

## Project Overview

A Python polling bot that monitors [matchi.se](https://www.matchi.se) for open tennis court slots, then fires desktop popups and HTML email alerts when new courts appear. It scrapes the Matchi booking schedule page (no API), compares slot state between polls, and notifies only on new courts (not removals).

## Key Files

| File | Role |
|------|------|
| `check_availability.py` | Entry point, CLI, monitoring loop, slot diffing, notification orchestration |
| `facilities.py` | Facility name → Matchi facility ID mappings (active + inactive) |
| `email_notifications.py` | Email sending via Brevo API or SMTP; Jinja2 HTML template rendering |
| `email_templates/new_courts.html` | Jinja2 template for new-court alerts |
| `email_templates/test_email.html` | Jinja2 template for test emails |
| `email_templates/base.html` | Shared HTML base template |
| `quotes.csv` | Random quotes appended to email notifications |
| `requirements.txt` | Canonical dependency list (use this for installs) |
| `pyproject.toml` | Poetry metadata (package-mode = false) |
| `.env` | Local secrets — never commit (gitignored) |

## Architecture

```
check_availability.py
  run_monitor()                  # main loop
    collect_all_slots()          # scrapes matchi.se for all facilities/dates
    _filter_slots_by_between()   # optional time-window filter
    has_changes() / get_slot_changes()  # diff against previous state
    _build_new_courts_email_data()      # transform diff for email template
    send_new_courts_notification()      # email_notifications.py
    send_notification()                 # desktop popup (win10toast / osascript)
```

Slot data structure throughout: `dict[facility_key, dict[date, dict[time_slot_label, list[court_name]]]]`

## Setup

```bash
# Recommended: uv
uv python install 3.11
uv venv --python 3.11 .venv
./.venv/Scripts/Activate.ps1      # Windows PowerShell
uv pip install -r requirements.txt

# Or plain pip
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Python 3.11+ required (uses `X | Y` union type hints throughout).

## Running

```bash
# Continuous monitor — evening slots, all facilities
python check_availability.py monitor --between 17-22 --interval-seconds 300

# Single check and exit (good for Task Scheduler / cron)
python check_availability.py monitor --once --between 17-22

# Specific facilities
python check_availability.py monitor --facility frogner --facility ota

# Specific dates
python check_availability.py monitor --dates 2025-08-20,2025-08-21

# Suppress output when nothing changes
python check_availability.py monitor --quiet

# Test desktop popups
python check_availability.py test-notifications

# Test email
python check_availability.py test-email
```

## Environment Variables (.env)

```bash
EMAIL_ENABLED=1                    # set to 0 to silence all emails

# Option A: Brevo HTTP API (preferred — bypasses SMTP firewall blocks)
BREVO_API_KEY=your_brevo_api_key

# Option B: SMTP fallback (used only if BREVO_API_KEY is absent)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SSL=0
SMTP_USER=your@gmail.com
SMTP_PASS=your_app_password        # use an app password for Gmail/Yahoo

EMAIL_FROM=Your Name <your@gmail.com>
EMAIL_TO=first@example.com,second@example.com
```

Brevo API is tried first; SMTP is the fallback. Email is sent only when NEW courts appear (not for removals).

## Common Tasks

### Add or disable a facility
Edit `facilities.py`:
- Move entry between `facilities` (active) and `inactive_facilities` (disabled)
- Add the matching display name to `facility_display_names`
- The `facilities` dict maps lowercase key → Matchi integer facility ID

### Modify email templates
Templates live in `email_templates/` and are rendered with Jinja2. Context variables passed to `new_courts.html`:
- `facilities` — list of facility dicts with `name`, `dates` (each with `display_name`, `booking_url`, `web_url`, `time_slots`)
- `total_new_courts` — int
- `quote` — optional string
- `timestamp` — render time string

If Jinja2 is unavailable or rendering fails, `email_notifications.py` falls back to plain text automatically.

### Add a new random quote
Append a row to `quotes.csv`. Format: `index,quote text` or just `quote text`.

## Testing

```bash
# Unit tests for slot logic (date ranges, time filtering, diffing)
python -m pytest test_slot_logic.py -v

# Integration test (hits live matchi.se — requires network)
python -m pytest test_integration.py -v
```

`test_slot_logic.py` covers: `get_date_range`, `parse_dates_list`, `parse_between_time_range`, `_filter_slots_by_between`, `has_changes`, `get_slot_changes`.

## Scraping Notes

- Target URL: `https://www.matchi.se/book/schedule?facilityId=<id>&date=<YYYY-MM-DD>&sport=1`
- Available slots are `<td class="slot free">` elements; `title` attribute contains `<br>`-separated parts: `[0]` unused, `[1]` court name, `[2]` time slot label
- No auth required; no rate limiting observed, but 5-minute poll intervals are standard
- If the site changes its HTML structure, `fetch_available_slots()` in `check_availability.py:77` is the only scraping code to update

## Desktop Notifications

- **Windows**: `win10toast` — shows a 5-second toast; falls back to `print` if the library fails
- **macOS**: `osascript` AppleScript alert — no special permissions needed
- Desktop alerts fire for both new courts and changes; email fires only for new courts

## Conventions

- Facility keys are always lowercase strings (e.g., `"frogner"`, `"ota"`)
- Dates are `datetime.date` objects throughout; never strings in internal data structures
- Time slot labels come directly from Matchi HTML (e.g., `"17:00-18:00"`) — do not normalise them
- `--between` filters are applied after fetching, not in the scraper
- Error backoff in `run_monitor`: doubles each failure up to 10-minute cap
