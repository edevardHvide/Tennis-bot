# Tennis Bot — Claude Code Guide

## Project Overview

Serverless tennis court availability monitor. Scrapes [matchi.se](https://www.matchi.se) for open court slots, matches against user preferences, and sends HTML email alerts via AWS SES. No API from Matchi — pure HTML scraping.

**Repo:** https://github.com/edevardHvide/Tennis-bot

**To agent** If you encounter something surprising, fix a bug, or learn a new constraint, update this CLAUDE.md file with that information to improve future performance

## Architecture

Three AWS Lambda functions + React frontend:

1. **Scraper** (`lambdas/scraper/`) — EventBridge cron triggers scraping of matchi.se for 3 facilities. Diffs against DynamoDB snapshots, invokes notifications Lambda with new slots.
2. **Preferences API** (`lambdas/preferences/`) — REST CRUD for user notification preferences (facility, days, time range). Behind API Gateway.
3. **Notifications** (`lambdas/notifications/`) — Matches scraper diffs against user preferences (facility + day-of-week + time window), deduplicates, sends HTML email via SES.
4. **Frontend** (`frontend/`) — React + TypeScript + Vite + Tailwind. Users register by email and manage notification preferences.

**Local CLI** (`check_availability.py`) — Standalone polling bot with Windows toast + email alerts for manual use.

## Tech Stack

- **Backend:** Python 3.11, requests, beautifulsoup4, boto3, arrow, jinja2
- **Frontend:** React 19, TypeScript 5.9, Vite 7, Tailwind CSS 4
- **Infra:** AWS Lambda, DynamoDB (on-demand), API Gateway, EventBridge, SES, S3
- **Region:** eu-north-1

## Windows: Python Not Found

If you see `"Python was not found"` or `"File association not found for extension .py"`, the venv is not activated. Fix:

```bash
# Activate the venv first (run from repo root)
source .venv/Scripts/activate

# Then run Python commands normally
python -m pytest tests/ -v
```

If the venv doesn't exist yet:
```bash
uv venv --python 3.11 .venv
source .venv/Scripts/activate
uv pip install -r requirements.txt
```

## Key Commands

```bash
# Tests
python -m pytest tests/ -v

# Build & deploy (see Makefile)
make deploy-all          # Deploy everything
make deploy-scraper      # Package & deploy scraper Lambda
make deploy-preferences  # Package & deploy preferences Lambda
make deploy-notifications # Package & deploy notifications Lambda
make deploy-frontend     # Build & sync frontend to S3
make deploy-dynamo       # Create/verify DynamoDB tables

# Frontend dev
cd frontend && npm install && npm run dev
```

## DynamoDB Tables

| Table | PK | SK | Notes |
|-------|----|----|-------|
| tennis-users | userId | — | User registration |
| tennis-preferences | userId | preferenceId | Notification preferences |
| tennis-availability | facilityId | date | Scraper snapshots |
| tennis-notifications | notificationId | — | Dedup with 7-day TTL |

## Active Facilities

Defined in `facilities.py`: `frogner` (2259), `ota` (1779), `bergentennisarena` (301)

## Project Structure

```
lambdas/
  scraper/       handler.py, scraper.py, diff.py
  preferences/   handler.py
  notifications/  handler.py, matcher.py, dedup.py, email_builder.py
frontend/src/
  components/    Dashboard, LoginForm, PreferenceForm, PreferenceCard
  api.ts, types.ts, App.tsx
infra/
  dynamo/        tables.json, deploy.sh
  api/           openapi.yaml
tests/           test_scraper.py, test_preferences.py, test_notifications.py
email_templates/ base.html, new_courts.html, newsletter.html, etc.
```

## Environment Variables

**Scraper:** `SCRAPER_DAYS_AHEAD` (14), `DYNAMODB_TABLE`, `NOTIFICATIONS_FUNCTION`
**Preferences:** `USERS_TABLE`, `PREFS_TABLE`
**Notifications:** `NOTIFICATIONS_TABLE`, `PREFS_TABLE`, `USERS_TABLE`, `SES_FROM_EMAIL`
**Frontend:** `VITE_API_URL` (API Gateway base URL)
**Local CLI:** `EMAIL_ENABLED`, `BREVO_API_KEY`, `SMTP_*`, `EMAIL_FROM`, `EMAIL_TO`
