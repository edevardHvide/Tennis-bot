
# Matchi Availability Bot

## Overview

The Matchi Availability Bot is a Python application designed to check and notify users about available slots for facilities listed on the Matchi booking website (`https://www.matchi.se/book/schedule`). It uses web scraping techniques to fetch the available time slots for a specified facility and date.

## Features

- Fetches available slots for a given facility and date from Matchi's website.
- Sends desktop notifications for available slots.
- Sends email only when new slots appear (optional via `.env`).

## Pre-requisites

- Windows 10/11 or macOS
- No global Python required if you use `uv` (recommended)

## Installation

### Clone the Repository

First, clone the repository to your local machine:

```bash
git clone <repository_url>
```

### Install with uv (recommended)

uv will install a local Python and create a virtual environment automatically.

```powershell
# 1) Install uv (once)
powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2) Clone and enter the repo
git clone <repository_url>
cd Matchi-availability-bot

# 3) One-off run (ephemeral env)
uv run --python 3.11 --with requests --with beautifulsoup4 --with arrow --with tabulate --with rich --with win10toast python check_availability.py monitor

# Or create a reusable venv
uv python install 3.11
uv venv --python 3.11 .venv
./.venv/Scripts/Activate.ps1
uv pip install -r requirements.txt
```

## Usage

### Run the monitor
```powershell
python check_availability.py monitor --between 17-22 --days-ahead 2 --interval-seconds 300
```

Examples:
```powershell
# Only today, 17:00–22:00, recheck every 2 minutes
python check_availability.py monitor --days-ahead 0 --between 17-22 --interval-seconds 120

# Specific dates
python check_availability.py monitor --dates 2025-08-20,2025-08-21
```

### Test notifications
```powershell
python check_availability.py test-notifications
```

Notes:
- On Windows, notifications use `win10toast` to show toast popups.
- On macOS, notifications use AppleScript alerts via `osascript`.
- If Focus Assist (Do Not Disturb) is on, toasts may be suppressed.

### Configure email (.env)
Create a `.env` file in the project root (or set these as environment variables):
```bash
EMAIL_ENABLED=1
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SSL=0
SMTP_USER=your@gmail.com
SMTP_PASS=your_app_password
EMAIL_FROM=your@gmail.com
EMAIL_TO=first@example.com,second@example.com
```
Notes:
- `EMAIL_ENABLED` controls whether emails send.
- Emails are sent only when new courts become available (not for removals).
- For Gmail/Yahoo, use app passwords.

### Test email
Ensure your `.env` (or environment) contains the SMTP settings (`EMAIL_ENABLED`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_SSL`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM`, `EMAIL_TO`), then run:
```powershell
python check_availability.py test-email
```

### Optional: Start automatically at login (Windows)
Use Task Scheduler → Create Task → Run only when user is logged on.

Program/script:
```
C:\Users\<you>\git\Matchi-availability-bot\.venv\Scripts\python.exe
```
Arguments:
```
check_availability.py monitor --between 17-22
```
Start in:
```
C:\Users\<you>\git\Matchi-availability-bot
```

## License

This project is licensed under the terms of the license specified in the [LICENSE](LICENSE) file.
