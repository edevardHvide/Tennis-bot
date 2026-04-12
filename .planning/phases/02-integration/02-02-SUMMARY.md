---
phase: 02-integration
plan: "02"
subsystem: notifications/email_builder + frontend/types
tags: [harvard, email-cta, facilities, green-phase, tdd]
dependency_graph:
  requires: [02-01]
  provides: [NOTF-02, NOTF-03, PREF-02]
  affects: [lambdas/notifications, frontend/src]
tech_stack:
  added: []
  patterns: [per-facility CTA routing via matchi_id sentinel, tuple return helper]
key_files:
  created: []
  modified:
    - lambdas/notifications/email_builder.py
    - frontend/src/types.ts
decisions:
  - "tuple return type used instead of dataclass for _facility_cta() to keep change minimal"
  - "matchi_id is None sentinel reliably distinguishes Harvard from Matchi facilities"
  - "Per-facility CTA placed inside facility loop div so each facility section has its own button"
metrics:
  duration: "~5 min"
  completed_date: "2026-04-10"
  tasks_completed: 2
  files_modified: 2
---

# Phase 02 Plan 02: Harvard Email CTA and Frontend Facility Summary

One-liner: Harvard email CTA routes to gocrimson.com registration page instead of matchi.se, turning 3 RED tests GREEN with two targeted file edits.

## What Was Built

### Task 1: _facility_cta() helper in email_builder.py (GREEN phase)

Added `HARVARD_REG_URL` constant and `_facility_cta(facility_key)` helper that returns `(url, label)` based on the `matchi_id` sentinel. For facilities where `matchi_id is None` (Harvard), returns the gocrimson.com URL and "Register at Harvard Rec". For all Matchi facilities, returns `MATCHI_GENERAL_URL` and "Book on Matchi".

Moved the CTA button inside the per-facility HTML loop so each facility section renders its own contextually correct button. Removed the single post-loop "Take me to Matchi" block. Updated the plain-text loop similarly — each facility now appends `"  {cta_label}: {cta_url}"` instead of a global "Open Matchi" line.

### Task 2: Harvard in frontend FACILITIES array (types.ts)

Added `{ id: 'harvard', displayName: 'Harvard Recreation', sports: ['tennis'] }` as the final entry in the `FACILITIES` constant in `frontend/src/types.ts`. TypeScript compiles without errors.

## Test Results

All 7 Harvard integration tests pass:
- `TestEmailBuilderHarvard` (3 tests) — RED → GREEN
- `TestMatchPreferencesHarvard` (2 tests) — already GREEN, remain GREEN
- `TestDedupHarvard` (2 tests) — already GREEN, remain GREEN

Pre-existing `test_preferences.py` failures (14 tests) confirmed pre-existing via git stash — not caused by this plan.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check

- [x] `lambdas/notifications/email_builder.py` modified and committed (f971294)
- [x] `frontend/src/types.ts` modified and committed (3eb3ea9)
- [x] `HARVARD_REG_URL` constant present in email_builder.py
- [x] `_facility_cta()` helper defined and called in both HTML and plain-text loops
- [x] `matchi_id is None` check present
- [x] Harvard entry present in FACILITIES array
- [x] All 3 TestEmailBuilderHarvard tests PASS
- [x] TypeScript compiles without errors

## Self-Check: PASSED
