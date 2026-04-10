---
phase: 02-integration
verified: 2026-04-10T00:00:00Z
status: human_needed
score: 8/8 must-haves verified (automated); 1 item requires human visual confirmation
re_verification: false
human_verification:
  - test: "Open http://localhost:5173, navigate to Add Preference, select Tennis sport, confirm 'Harvard Recreation' appears in the facility list. Then select Padel and confirm it does NOT appear."
    expected: "Harvard Recreation visible under Tennis, absent under Padel"
    why_human: "PREF-02 is a UI rendering check — filteredFacilities filter and FACILITIES wiring are verified in code, but correct rendering in the browser requires human eyes"
---

# Phase 2: Integration Verification Report

**Phase Goal:** Detected lesson diffs flow into the existing notification pipeline and users can subscribe via preferences and frontend
**Verified:** 2026-04-10
**Status:** human_needed — all automated checks pass; one frontend visual check outstanding
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | When a diff is detected, the existing notifications Lambda receives a payload and sends an email alert | VERIFIED | `harvard-scraper/handler.py` lines 195-205: `lambda_client.invoke(FunctionName=notifications_function, Payload=json.dumps({"diff": diff}))`. Tested by `TestColdStart::test_notification_on_second_run_new_slot` (PASS) |
| 2 | The email shows lesson location, date, time, spot count, and a direct link to the Harvard Rec registration page | VERIFIED | `email_builder.py` renders `court_name` (location), `date`, `time_slot`, `total_courts` count, and `_facility_cta("harvard")` returns `(HARVARD_REG_URL, "Register at Harvard Rec")`. Tested by `TestEmailBuilderHarvard` (3 tests, PASS) |
| 3 | The same lesson slot does not trigger a second alert within the dedup TTL window | VERIFIED | `dedup._dedup_key()` includes facilityId in SHA-256 hash. `filter_already_notified` suppresses matches with existing notificationId. Tested by `TestDedupHarvard` (2 tests, PASS) |
| 4 | "Harvard Recreation" appears as a selectable facility in the frontend PreferenceForm | PARTIAL (automated) | `types.ts` FACILITIES array contains `{ id: 'harvard', displayName: 'Harvard Recreation', sports: ['tennis'] }`. `PreferenceForm.tsx` line 39: `filteredFacilities = FACILITIES.filter((f) => f.sports.includes(sport))`. Code wiring verified; browser rendering requires human check |
| 5 | A user preference for `harvard` + `tennis` with day/time filters is matched correctly by the existing matcher.py | VERIFIED | `matcher.py` builds composite key `f"{facility_id}#{sport}"` (line 113) and looks up `diff.get(composite_key)`. Tested by `TestMatchPreferencesHarvard` (2 tests, PASS) |

**Score:** 5/5 truths verified (Truth 4 needs human confirmation for browser rendering)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `lambdas/notifications/email_builder.py` | `_facility_cta()` helper, HARVARD_REG_URL constant, per-facility CTA in HTML and plain-text | VERIFIED | `HARVARD_REG_URL` at line 14, `_facility_cta()` at line 74, called at lines 156 and 212 in both HTML and text loops |
| `frontend/src/types.ts` | harvard entry in FACILITIES array | VERIFIED | Line 77: `{ id: 'harvard', displayName: 'Harvard Recreation', sports: ['tennis'] }` |
| `tests/test_harvard_integration.py` | TestEmailBuilderHarvard, TestMatchPreferencesHarvard, TestDedupHarvard | VERIFIED | All 7 tests PASS (18/18 Harvard tests across both test files) |
| `tests/test_preferences.py` | TestCreatePreferenceHarvard with 4 tests | VERIFIED | All 4 tests PASS |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `email_builder.py` | `facilities.py get_matchi_id()` | `_facility_matchi_id()` returns `None` for harvard (no KeyError — harvard is in facilities with `matchi_id: None`) | WIRED | `_facility_cta()` line 80: `if matchi_id is None:` correctly branches to HARVARD_REG_URL |
| `frontend/src/types.ts` | `PreferenceForm.tsx` | `FACILITIES` imported and filtered by `f.sports.includes(sport)` | WIRED | `PreferenceForm.tsx` line 3 imports `FACILITIES`, line 39: `filteredFacilities = FACILITIES.filter(...)`, line 262 renders `filteredFacilities.map(...)` |
| `harvard-scraper/handler.py` | `notifications Lambda` | `lambda_client.invoke(FunctionName=notifications_function, Payload={"diff": diff})` | WIRED | Lines 198-202: async Lambda invocation with standard diff payload format matching notifications handler expectations |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| NOTF-01 | 02-01, 02-03 | Harvard scraper invokes existing notifications Lambda with standard diff payload | SATISFIED | `harvard-scraper/handler.py` lines 195-205; `test_notification_on_second_run_new_slot` PASS |
| NOTF-02 | 02-01, 02-02 | Email includes lesson location, date, time, spot count | SATISFIED | `email_builder.py` renders `court_name`, `date_str`, `time_slot`, `total_courts`; `TestEmailBuilderHarvard` 3 tests PASS |
| NOTF-03 | 02-01, 02-02 | Email includes direct link to Harvard Rec registration page | SATISFIED | `HARVARD_REG_URL = "https://membership.gocrimson.com/..."` in HTML and plain-text CTA; tests assert `"gocrimson.com" in html_body` and `"gocrimson.com" in text_body` PASS |
| NOTF-04 | 02-01 | Dedup prevents re-alerting within TTL | SATISFIED | `dedup._dedup_key()` hashes `facilityId+sport+date+time_slot+court_name`; `TestDedupHarvard` 2 tests PASS |
| PREF-01 | 02-01 | `harvard` added as facility in facilities.py | SATISFIED | `facilities.py` line 70-74: harvard entry with `matchi_id: None`, `display_name: "Harvard Recreation"`, `sports: ["tennis"]`. `VALID_FACILITY_IDS = set(facilities.keys())` auto-includes it |
| PREF-02 | 02-02, 02-03 | Frontend FACILITIES list includes Harvard Recreation | SATISFIED (code) / NEEDS HUMAN (visual) | `types.ts` line 77 has entry; `PreferenceForm.tsx` imports and filters FACILITIES; browser rendering not verified |
| PREF-03 | 02-01 | Users can create preferences for harvard+tennis | SATISFIED | `test_create_preference_harvard_tennis_accepted` PASS (201); `test_create_preference_harvard_padel_rejected` PASS (400 for unsupported sport) |
| PREF-04 | 02-01 | matcher.py correctly matches `harvard#tennis` composite key | SATISFIED | `matcher.py` line 113 builds composite key generically; `test_harvard_composite_key_match` PASS; `test_harvard_no_match_wrong_facility` PASS |

All 8 Phase 2 requirements have satisfying implementation evidence. No orphaned requirements — all 8 IDs from plans are accounted for.

### Anti-Patterns Found

None. No TODOs, FIXMEs, placeholder returns, or stub handlers found in any Phase 2 modified files.

### Notes on Pre-existing Test Failures

`tests/test_preferences.py` has 47 pre-existing failures (TestUpdatePreference, TestDeletePreference, TestSportAndCourtType, TestRouter) caused by `_valid_pref_body()` using `frogner` as facilityId — `frogner` was moved to `inactive_facilities` in a prior phase. These failures are confirmed pre-existing (43 tests in the file before Phase 2 started, same failure pattern). Phase 2 added only `TestCreatePreferenceHarvard` (4 tests, all PASS).

`tests/test_notifications.py` fails to collect on Python 3.9 due to `list[str] | None` union syntax (Python 3.10+). This is a pre-existing issue; Phase 2 correctly created the separate `test_harvard_integration.py` file to work around it.

### Human Verification Required

**1. Harvard Recreation visible in frontend PreferenceForm (PREF-02 browser rendering)**

**Test:** Start `cd /Users/edevard/Tennis-bot/frontend && npm run dev`, open http://localhost:5173, log in, click "Add preference", select sport: Tennis.

**Expected:** "Harvard Recreation" appears in the facility dropdown/list.

**Then:** Switch sport to Padel.

**Expected:** "Harvard Recreation" does NOT appear (sports: ['tennis'] filters it out).

**Why human:** UI rendering correctness requires browser — code wiring is verified (FACILITIES import, `f.sports.includes(sport)` filter, `filteredFacilities.map()`), but actual display in the React component tree needs visual confirmation.

### Gaps Summary

No gaps. All automated verifications pass. The phase goal is achieved — Harvard diffs flow into the notification pipeline (NOTF-01 through NOTF-04), and users can subscribe via the preferences API and frontend FACILITIES list (PREF-01 through PREF-04). One item (PREF-02 frontend visual) requires human eyes before the phase can be fully closed.

---

_Verified: 2026-04-10_
_Verifier: Claude (gsd-verifier)_
