# Availability Monitor — Claude Code Guide

## Project Overview

Serverless **multi-sport** court availability monitor. Scrapes [matchi.se](https://www.matchi.se) for open tennis and padel court slots, matches against user preferences, and sends HTML email alerts via AWS SES. No API from Matchi — pure HTML scraping.

**Supported sports:** Tennis (`sport=1`) and Padel (`sport=5`) on matchi.se.

**Repo:** https://github.com/edevardHvide/Tennis-bot

**To agent** If you encounter something surprising, fix a bug, or learn a new constraint, update this CLAUDE.md file with that information to improve future performance

## Architecture

Five AWS Lambda functions + React frontend:

1. **Scraper** (`lambdas/scraper/`) — EventBridge cron triggers scraping of matchi.se for all facility+sport pairs. Diffs against DynamoDB snapshots, invokes notifications Lambda with new slots. Uses composite keys `facility#sport` (e.g. `"ota#padel"`).
2. **Preferences API** (`lambdas/preferences/`) — REST CRUD for user notification preferences (facility, sport, court type, dates, time range). Behind API Gateway.
3. **Notifications** (`lambdas/notifications/`) — Matches scraper diffs against user preferences (facility + sport + day-of-week + time window + court type), deduplicates, sends HTML email via SES.
4. **Newsletter** (`lambdas/newsletter/`) — Weekly summary email of upcoming availability. Uses shared `matcher.py` from notifications.
5. **Feedback** (`lambdas/feedback/`) — Receives user feature requests via `POST /feedback`, saves to DynamoDB, and creates GitHub issues with `feature-request` label. Rate-limited to 1 request per user per 5 minutes.
6. **Frontend** (`frontend/`) — React + TypeScript + Vite + Tailwind. Users register by email, select sport (tennis/padel), manage notification preferences, and submit feature requests.

**Local CLI** (`check_availability.py`) — Standalone polling bot with Windows toast + email alerts. Supports `--sport` and `--court-type` flags.

## Facilities Configuration

All facility config is centralized in `facilities.py` and copied into each Lambda package at build time via `Makefile`. Never duplicate facility data in Lambda handlers.

```python
SPORT_CODES = {"tennis": 1, "padel": 5}

facilities = {
    "frogner": {"matchi_id": 2259, "display_name": "Frogner", "sports": ["tennis"]},
    "ota": {"matchi_id": 1779, "display_name": "OTA", "sports": ["tennis", "padel"]},
    "bergentennisarena": {"matchi_id": 301, "display_name": "Bergen Tennis Arena", "sports": ["tennis"]},
    "voldslokka": {"matchi_id": 642, "display_name": "Voldsløkka", "sports": ["tennis"]},
    "furuset": {"matchi_id": 542, "display_name": "Furuset", "sports": ["tennis", "padel"]},
    "interpadel": {"matchi_id": 872, "display_name": "InterPadel Oslo", "sports": ["padel"]},
    "nordicpadel": {"matchi_id": 811, "display_name": "Nordic Padel", "sports": ["padel"]},
    "ullern": {"matchi_id": 219, "display_name": "Ullern Tennisklubb", "sports": ["tennis"]},
    "nordstrand": {"matchi_id": 178, "display_name": "Nordstrand Tennisklubb", "sports": ["tennis"]},
    "heming": {"matchi_id": 2144, "display_name": "Heming Tennis og Padel", "sports": ["tennis", "padel"]},
    "holmenkollen": {"matchi_id": 452, "display_name": "Holmenkollen Tennisklubb", "sports": ["tennis"]},
}
```

Helpers: `get_matchi_id()`, `get_display_name()`, `get_sports()`, `get_facilities_for_sport()`.

## Tech Stack

- **Backend:** Python 3.11, requests, beautifulsoup4, boto3, arrow, jinja2
- **Frontend:** React 19, TypeScript 5.9, Vite 7, Tailwind CSS 4
- **Infra:** AWS Lambda, DynamoDB (on-demand), API Gateway, EventBridge, SES, S3
- **Email:** Gmail SMTP (edetennisapp@gmail.com) — if `SMTP_HOST` is set, SMTP is used; otherwise falls back to SES
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

## IMPORTANT: Do NOT use `encodeURIComponent` on API path params

This API Gateway (HTTP API) does **NOT** decode `%40` back to `@` in path parameters. If you `encodeURIComponent` the userId (email), the Lambda receives the literal `%40` and returns 404. **Always pass email userIds raw** in URL paths — axios/browsers handle `@` in paths fine.

```typescript
// WRONG — API Gateway passes %40 literally, Lambda can't find user
`/users/${encodeURIComponent(userId)}/preferences`

// CORRECT — @ passes through fine
`/users/${userId}/preferences`
```

## IMPORTANT: Use `uv pip` for installing packages

**NEVER use `pip install` directly** — it will silently fail or not be found on this Windows setup. **ALWAYS use `uv pip install`** instead. This applies everywhere: installing deps, packaging Lambdas, etc.

```bash
# WRONG — will fail silently
pip install -r requirements.txt -t ./package

# CORRECT — always use uv pip
uv pip install -r requirements.txt --target ./package
```

## IMPORTANT: `make` is not available on Windows

This repo runs on Windows (Git Bash). `make` is NOT installed. When deploying, use manual bash commands instead of `make` targets. See the Makefile for reference on what each target does, then replicate with bash.

## IMPORTANT: `zip` is not available — use PowerShell instead

Git Bash on this machine does **not** have `zip`. Use PowerShell's `Compress-Archive` to create zip files:

```bash
# WRONG — zip is not installed
cd package && zip -r ../function.zip .

# CORRECT — use PowerShell Compress-Archive
powershell -Command "Compress-Archive -Path 'package/*' -DestinationPath 'function.zip' -Force"

# To add more files to an existing zip (e.g. handler.py on top of dependencies):
powershell -Command "Compress-Archive -Path 'handler.py' -DestinationPath 'function.zip' -Update"
```

When packaging Lambdas, the typical pattern is:
```bash
# 1. Install deps into package dir
uv pip install -r requirements.txt --target ./package

# 2. Zip the package dir
powershell -Command "Compress-Archive -Path 'package/*' -DestinationPath 'build/function.zip' -Force"

# 3. Add handler + shared files
powershell -Command "Compress-Archive -Path 'handler.py','facilities.py' -DestinationPath 'build/function.zip' -Update"
```

## Testing Policy — Scoped Tests Only

Only run tests relevant to the code that was actually changed. Do **not** run the full test suite by default.

- **Frontend-only changes** (`frontend/`): Run frontend tests/lint only — skip Python tests.
- **Backend-only changes** (`lambdas/`, `facilities.py`, `tests/`): Run `python -m pytest tests/ -v` — skip frontend.
- **Both touched**: Run both.

Before running tests, check which files were modified and only run the relevant test commands.

## Key Commands

```bash
# Tests (run only what's relevant — see Testing Policy above)
python -m pytest tests/ -v

# Build & deploy (see Makefile)
make deploy-all          # Deploy everything
make deploy-scraper      # Package & deploy scraper Lambda
make deploy-preferences  # Package & deploy preferences Lambda
make deploy-notifications # Package & deploy notifications Lambda
make deploy-newsletter   # Package & deploy newsletter Lambda
make deploy-feedback     # Package & deploy feedback Lambda
make deploy-frontend     # Build & sync frontend to S3
make deploy-dynamo       # Create/verify DynamoDB tables

# Frontend dev
cd frontend && npm install && npm run dev

# DynamoDB migrations (one-time, for existing data)
python scripts/migrate_availability_sport.py --profile tennis-bot [--dry-run]
python scripts/migrate_preferences_sport.py --profile tennis-bot [--dry-run]
```

## DynamoDB Tables

| Table | PK | SK | Notes |
|-------|----|----|-------|
| tennis-users | userId | — | User registration |
| tennis-preferences | userId | preferenceId | Has `sport` (tennis/padel), `dates` (list of day names like `["monday", "wednesday"]`), and optional `courtType` (double/single) |
| tennis-availability | facilityId | date | Scraper snapshots. PK uses composite key: `facility#sport` (e.g. `"ota#padel"`) |
| tennis-notifications | notificationId | — | Dedup with 24h TTL. Hash includes sport for independent dedup |
| tennis-feedback | feedbackId | — | User feature requests. Backup for GitHub issues |

## Multi-Sport Key Conventions

- **DynamoDB availability PK:** `"frogner#tennis"`, `"ota#padel"` — encodes sport into facilityId
- **Diff keys:** Same composite format, flows through scraper → notifications pipeline
- **Preferences:** Have `sport` field (default `"tennis"`), `dates` field (list of lowercase day-of-week names, e.g. `["monday", "friday"]`), and optional `courtType` field
- **Court type filtering (padel):** `"single"` matches courts with "single" in name; `"double"` matches courts WITHOUT "single" in name
- **Booking URLs:** Use `sport=1` for tennis, `sport=5` for padel

## Project Structure

```
facilities.py          Shared facility config (copied into Lambda packages)
lambdas/
  scraper/             handler.py, scraper.py, diff.py
  preferences/         handler.py
  notifications/       handler.py, matcher.py, dedup.py, email_builder.py
  newsletter/          handler.py, email_builder.py
  feedback/            handler.py
frontend/src/
  components/          Dashboard, LoginForm, PreferenceForm, PreferenceCard, FeatureRequestModal
  api.ts, types.ts, App.tsx
scripts/               DynamoDB migration scripts
infra/
  dynamo/              tables.json, deploy.sh
  api/                 openapi.yaml
tests/                 test_scraper.py, test_preferences.py, test_notifications.py, test_newsletter.py, test_e2e_pipeline.py, test_feedback.py
tests/fixtures/        HTML fixtures for e2e tests (matchi_frogner_*.html, matchi_ota_padel_*.html)
email_templates/       base.html, new_courts.html, newsletter.html, etc.
```

## Environment Variables

**Scraper:** `SCRAPER_DAYS_AHEAD` (14), `DYNAMODB_TABLE`, `NOTIFICATIONS_FUNCTION`
**Preferences:** `USERS_TABLE`, `PREFS_TABLE`
**Notifications:** `NOTIFICATIONS_TABLE`, `PREFS_TABLE`, `USERS_TABLE`, `SES_FROM_EMAIL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM`
**Newsletter:** `AVAILABILITY_TABLE`, `PREFS_TABLE`, `USERS_TABLE`, `SES_FROM_EMAIL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM`, `NEWSLETTER_TEST_RECIPIENT`
**Feedback:** `USERS_TABLE`, `FEEDBACK_TABLE`, `GITHUB_TOKEN`, `GITHUB_REPO`
**Frontend:** `VITE_API_URL` (API Gateway base URL)
**Local CLI:** `EMAIL_ENABLED`, `BREVO_API_KEY`, `SMTP_*`, `EMAIL_FROM`, `EMAIL_TO`


## Workflow Orchestration

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: update tasks/lessons.md with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes -- don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests -- then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

1. **Plan First**: Write plan to tasks/todo.md with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to tasks/todo.md
6. **Capture Lessons**: Update tasks/lessons.md after corrections

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Only touch what's necessary. No side effects with new bugs.

## Other

When troubleshooting, append findings to troubleshooting to [text](TROUBLESHOOTING.md), this is a log for earlier troubleshooting that should be checked before doing new troibleshooting.