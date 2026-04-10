---
phase: 01-scraper
plan: 02
subsystem: infra
tags: [facilities, scraper, lambda, python]

# Dependency graph
requires: []
provides:
  - "Harvard facility entry in facilities.py with matchi_id=None"
  - "Matchi scraper handler guards against None matchi_id facilities"
affects: [01-scraper-03, preferences-lambda]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Non-matchi facilities use matchi_id=None sentinel in facilities dict"
    - "Scraper skips facilities with config.get('matchi_id') is None before building pairs"

key-files:
  created: []
  modified:
    - facilities.py
    - lambdas/scraper/handler.py

key-decisions:
  - "Harvard added to active facilities dict (not inactive) so preferences Lambda VALID_FACILITY_IDS includes it"
  - "matchi_id=None sentinel chosen over separate dict to keep all facility config co-located"
  - "Guard uses config.get('matchi_id') is None (not 'not config[...]') to be safe if matchi_id=0 ever occurs"

patterns-established:
  - "Pattern: Non-matchi facilities live in active facilities dict with matchi_id=None; scraper guards skip them"

requirements-completed: [SCRP-03]

# Metrics
duration: 5min
completed: 2026-04-10
---

# Phase 01 Plan 02: Facilities Harvard Extension Summary

**Harvard Recreation added to facilities.py with matchi_id=None sentinel and matchi scraper loop guarded to skip non-matchi facilities**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-10T08:44:00Z
- **Completed:** 2026-04-10T08:49:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Added `harvard` key to active `facilities` dict in facilities.py with `matchi_id=None`, `display_name='Harvard Recreation'`, `sports=['tennis']`
- Added `config.get("matchi_id") is None` guard to matchi scraper handler so it skips Harvard (and any future non-matchi facility) without error
- All 9 existing matchi facility entries unchanged; all 27 scraper tests pass with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add harvard entry to facilities.py** - `2e1ff8d` (feat)
2. **Task 2: Guard matchi scraper handler against None matchi_id** - `bc130f8` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified
- `facilities.py` - Added harvard entry with matchi_id=None as last active facility
- `lambdas/scraper/handler.py` - Added None matchi_id guard in facility_sport_pairs loop

## Decisions Made
- Harvard placed in active facilities dict (not `inactive_facilities`) so that `VALID_FACILITY_IDS = set(facilities.keys())` in the preferences Lambda automatically includes `"harvard"` without additional changes.
- The `config.get("matchi_id") is None` pattern (using `.get()` + `is None`) is more robust than `not config["matchi_id"]` because it would not accidentally skip a hypothetical `matchi_id=0`.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

Pre-existing test_preferences.py failures (Python 3.9 incompatibility with `str | None` union syntax in `lambdas/preferences/handler.py`) were confirmed to be pre-existing and unrelated to this plan's changes. All 27 scraper tests pass.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `facilities['harvard']` exists and is importable; preferences Lambda VALID_FACILITY_IDS will include "harvard" at next deploy
- Matchi scraper production safety confirmed — Harvard entry will not cause KeyError or invalid matchi requests
- Ready for Plan 03: Harvard scraper Lambda implementation

---
*Phase: 01-scraper*
*Completed: 2026-04-10*
