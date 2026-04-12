---
phase: 01-scraper
verified: 2026-04-10T00:00:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Phase 1: Scraper Verification Report

**Phase Goal:** Harvard Rec lesson availability is scraped, parsed, snapshotted, and diffed — new spots are detected reliably
**Verified:** 2026-04-10
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Lambda successfully fetches the GetProgramInstances endpoint and returns structured slot data | VERIFIED | `fetch_lesson_instances()` in `scraper.py` calls `GET https://membership.gocrimson.com/Program/GetProgramInstances` with `programID` param and browser-like headers. `TestFetchLessonInstances` tests pass (3/3). |
| 2 | Slots are stored in DynamoDB under the `harvard#tennis` composite key with date sort keys | VERIFIED | `handler.py` line 67: `COMPOSITE_KEY = "harvard#tennis"`. `save_snapshot()` calls `table.put_item` with `facilityId=COMPOSITE_KEY` and `date=date_str`. `TestSnapshotStorage` tests pass (2/2). |
| 3 | A second run after nothing changes produces zero diffs | VERIFIED | `build_new_courts_diff` returns only new courts via set subtraction. If current == previous no new courts exist. `diff.py` is byte-for-byte identical to `lambdas/scraper/diff.py` (verified). |
| 4 | When a slot transitions from unavailable to available, the diff engine surfaces it | VERIFIED | `build_new_courts_diff` computes `current_set - previous_set` per date. `test_notification_on_second_run_new_slot` confirms invocation with `harvard#tennis` in payload when a new slot appears. |
| 5 | The very first run seeds DynamoDB silently without producing any alerts | VERIFIED | `run_scraper()` tracks `any_previous_record_existed` via `_snapshot_record_exists()`. Notifications Lambda only invoked when `diff and any_previous_record_existed`. `test_no_notification_on_first_run` passes. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `lambdas/harvard-scraper/scraper.py` | `fetch_lesson_instances`, `parse_harvard_availability` | VERIFIED | Both functions present and substantive. Reads `.spots-tag p` text as availability ground truth (not ClassSize arithmetic). Filters past-dated lessons. Raises ValueError on missing ApptInfo. |
| `lambdas/harvard-scraper/handler.py` | `lambda_handler`, `load_snapshot`, `save_snapshot`, `run_scraper` | VERIFIED | All four functions present. Contains cold-start guard (`any_previous_record_existed`). Imports `fetch_lesson_instances` and `build_new_courts_diff` at top level. `COMPOSITE_KEY = "harvard#tennis"`. |
| `lambdas/harvard-scraper/diff.py` | `build_new_courts_diff`, `has_changes`, `get_slot_changes` | VERIFIED | Byte-for-byte identical to `lambdas/scraper/diff.py` (confirmed). All three functions present. |
| `lambdas/harvard-scraper/requirements.txt` | Contains `requests`, `beautifulsoup4`, `boto3` | VERIFIED | All three deps present. |
| `tests/test_harvard_scraper.py` | 11 passing tests covering SCRP-01 through SCRP-05 | VERIFIED | All 11 tests pass (0 skipped, 0 failed). pytest exits 0 in 3.16s. |
| `tests/fixtures/harvard_available.html` | ApptInfo JSON + `.spots-tag p "1 Spot available"` | VERIFIED | BeautifulSoup parse confirms: ApptInfo input found, JSON is a non-empty list, `.spots-tag` element present. |
| `tests/fixtures/harvard_unavailable.html` | ApptInfo JSON + `.spots-tag p "No spots available"` | VERIFIED | Same checks pass. |
| `tests/fixtures/harvard_past_dated.html` | ApptInfo JSON with StartDate in the past | VERIFIED | Same checks pass. |
| `facilities.py` | `harvard` entry with `matchi_id=None`, `display_name="Harvard Recreation"`, `sports=["tennis"]` | VERIFIED | All assertions confirmed: `get_matchi_id("harvard")` returns `None`, `get_display_name("harvard")` returns `"Harvard Recreation"`, existing entries untouched. |
| `lambdas/scraper/handler.py` | Guard skipping `harvard` during matchi iteration | VERIFIED | Line 176: `if config.get("matchi_id") is None: continue  # Skip non-matchi facilities`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `handler.py` | `scraper.py` | `from scraper import fetch_lesson_instances` | WIRED | Top-level import at line 35. Used in `run_scraper()` at line 155. |
| `handler.py` | `diff.py` | `from diff import build_new_courts_diff` | WIRED | Top-level import at line 36. Used in `run_scraper()` at line 185. |
| `handler.py` | DynamoDB `tennis-availability` | `table.put_item / table.get_item` with `facilityId='harvard#tennis'` | WIRED | `COMPOSITE_KEY = "harvard#tennis"` used in both `load_snapshot` and `save_snapshot` calls throughout `run_scraper()`. |
| `handler.py` | Notifications Lambda | `lambda_client.invoke(FunctionName=NOTIFICATIONS_FUNCTION, ...)` | WIRED | Line 198: `lambda_client.invoke(FunctionName=notifications_function, ...)`. Only called when `diff and any_previous_record_existed`. |
| `lambdas/scraper/handler.py` | `facilities.py` | `for facility_key, config in facilities.items()` with `config.get("matchi_id") is None` guard | WIRED | Line 176 guard skips harvard. Confirmed via grep. |
| `tests/test_harvard_scraper.py` | `lambdas/harvard-scraper/scraper.py` | `sys.path.insert` via `HARVARD_SCRAPER_DIR` | WIRED | Lines 13-18: path insertion guard. All import statements in test methods succeed (tests pass). |

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SCRP-01 | 01-01, 01-03 | Lambda fetches Harvard Rec lesson data via GET /Program/GetProgramInstances | SATISFIED | `fetch_lesson_instances()` calls the endpoint with `programID` param and browser headers. 3 passing fetch tests. |
| SCRP-02 | 01-01, 01-03 | Parser extracts structured slot data from #ApptInfo hidden input JSON | SATISFIED | `parse_harvard_availability()` uses `soup.find("input", {"id": "ApptInfo"})`. Extracts `date`, `time_slot`, `location` from JSON. 4 passing parse tests including `.spots-tag` override and past-date filtering. |
| SCRP-03 | 01-01, 01-02, 01-03 | Slots stored as DynamoDB snapshots with `harvard#tennis` composite key and date sort key | SATISFIED | `COMPOSITE_KEY = "harvard#tennis"` in handler. `save_snapshot` uses `facilityId=facility_key, date=date_str`. `test_save_snapshot_uses_harvard_composite_key` passes. |
| SCRP-04 | 01-01, 01-03 | Diff engine detects newly available slots (unavailable → available transitions) | SATISFIED | `build_new_courts_diff` computes `current_set - previous_set`. `test_notification_on_second_run_new_slot` confirms diff surfaces when slot appears. |
| SCRP-05 | 01-01, 01-03 | First run seeds DynamoDB without triggering spurious alerts | SATISFIED | `_snapshot_record_exists()` distinguishes cold start from warm runs. `any_previous_record_existed` gate before Lambda invocation. `test_no_notification_on_first_run` passes. |

No orphaned requirements — all 5 Phase 1 requirements are claimed and satisfied. Requirements NOTF-*, PREF-*, and OPS-* are correctly deferred to Phases 2 and 3.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `handler.py` | 105 | `return {}` | Info | False positive — this is the legitimate empty-dict fallback in `load_snapshot()` when DynamoDB has no record. Not a stub. |
| `tests/test_harvard_scraper.py` | 200 | `return {}` | Info | False positive — mock return value simulating a DynamoDB miss in a test. Not a stub. |
| `tests/test_harvard_scraper.py` | 3 | Stale docstring comment "All tests skipped until implementation exists" | Info | Harmless stale comment — tests all pass now. No behavioral impact. |

No blockers or warnings found.

### Human Verification Required

None — all success criteria are programmatically verifiable via the test suite, which passes fully.

### Gaps Summary

No gaps. All 5 observable truths verified, all artifacts exist and are substantive, all key links are wired, all 5 requirements satisfied by passing tests.

---

_Verified: 2026-04-10_
_Verifier: Claude (gsd-verifier)_
