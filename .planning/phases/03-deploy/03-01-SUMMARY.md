---
phase: 03-deploy
plan: "01"
subsystem: harvard-scraper
tags: [lambda, makefile, logging, ops]
dependency_graph:
  requires: []
  provides: [harvard-scraper-lambda-infra, structured-logging-scraper]
  affects: [lambdas/harvard-scraper/scraper.py, Makefile]
tech_stack:
  added: []
  patterns: [structured-json-logging, makefile-deploy-targets]
key_files:
  created:
    - scripts/create_harvard_scraper_lambda.sh
  modified:
    - Makefile
    - lambdas/harvard-scraper/scraper.py
key_decisions:
  - "Deploy script created instead of running aws lambda create-function directly — AWS credentials not configured in this session"
  - "Local _log helper defined in scraper.py (not imported from handler) to avoid circular imports"
  - "package-harvard-scraper uses cp *.py (not cp -r .) — no shared facilities.py dependency for harvard-scraper"
metrics:
  duration_seconds: 97
  completed_date: "2026-04-10"
  tasks_completed: 2
  files_modified: 3
---

# Phase 03 Plan 01: Harvard Scraper Deploy Infrastructure Summary

Makefile packaging/deploy targets for harvard-scraper Lambda, structured JSON logging in scraper.py, and a one-time Lambda creation script — enabling independent deployment of harvard-scraper from the matchi scraper.

## What Was Built

### Task 1: Makefile targets + structured logging in scraper.py

**Makefile changes:**
- Added `HARVARD_SCRAPER_FN = harvard-scraper` variable (line 6)
- Added `package-harvard-scraper` target that installs deps, copies all `.py` files, and zips to `build/harvard-scraper.zip`
- Added `deploy-harvard-scraper: package-harvard-scraper` target that runs `aws lambda update-function-code`
- Added both targets to `.PHONY`

**scraper.py changes:**
- Added local `_log(level, message, **extra)` helper after the logger setup — identical pattern to `handler.py`, outputs structured JSON via `json.dumps`
- Replaced `logger.warning(...)` in the retry loop with `_log("warning", "Fetch attempt failed", attempt=..., total=..., error=..., retry_in_seconds=...)`
- Replaced `logger.error(...)` on final failure with `_log("error", "All fetch attempts failed", total=..., error=...)`
- No new imports needed (`json` was already imported at line 10)

### Task 2: Lambda creation script

Created `scripts/create_harvard_scraper_lambda.sh` — a one-time provisioning script that:
- Packages the Lambda using `uv pip install` (consistent with CLAUDE.md requirements)
- Detects whether the function already exists (idempotent — uses `update-function-code` if it does, `create-function` if not)
- Sets all three required env vars: `HARVARD_PROGRAM_ID`, `DYNAMODB_TABLE`, `NOTIFICATIONS_FUNCTION`
- Creates with `python3.11` runtime, `tennis-scraper-role`, 900s timeout, 256MB memory

Note: The actual `aws lambda create-function` was not run in this session (AWS credentials not configured). The user can run this with:
```bash
bash scripts/create_harvard_scraper_lambda.sh
```
Subsequent code updates use: `make deploy-harvard-scraper`

## Env Vars Configured (in deploy script)

| Variable | Value |
|----------|-------|
| HARVARD_PROGRAM_ID | a20e7ae2-fedc-4a8e-a7c3-236695040c63 |
| DYNAMODB_TABLE | tennis-availability |
| NOTIFICATIONS_FUNCTION | tennis-notifications |

## Verification

- `grep -n "harvard-scraper" Makefile` — shows HARVARD_SCRAPER_FN, package target, deploy target, .PHONY
- `grep -n "def _log" lambdas/harvard-scraper/scraper.py` — shows line 21 local helper
- `grep -n "logger\.warning\|logger\.error" lambdas/harvard-scraper/scraper.py` — returns empty (no bare calls)
- 34 tests pass: `pytest tests/test_harvard_integration.py tests/test_scraper.py -v`

## Deviations from Plan

### Deviation 1: Deploy script instead of live AWS deployment

**Found during:** Task 2
**Issue:** The plan called for running `aws lambda create-function` directly. The important_context in the execution prompt explicitly stated: "Do NOT actually deploy to AWS — create a deploy script instead."
**Fix:** Created `scripts/create_harvard_scraper_lambda.sh` as a self-contained, idempotent provisioning script the user can run when AWS credentials are available.
**Files modified:** `scripts/create_harvard_scraper_lambda.sh` (created)
**Type:** Expected deviation per execution instructions

## Self-Check: PASSED

- `fed9d88` — feat(03-deploy-01): add Makefile harvard-scraper targets and structured logging
- `68f3880` — feat(03-deploy-01): add one-time Lambda creation script for harvard-scraper
- `Makefile` modified: confirmed via git log
- `lambdas/harvard-scraper/scraper.py` modified: confirmed via git log
- `scripts/create_harvard_scraper_lambda.sh` created: confirmed exists
