# Phase 2: Integration - Research

**Researched:** 2026-04-10
**Domain:** Notification pipeline integration, preferences API, frontend facility list, email builder
**Confidence:** HIGH

## Summary

Phase 2 wires the Harvard scraper (already invoking the notifications Lambda) into the full end-to-end pipeline so users can subscribe and receive emails. The research involved reading every source file in the integration path: `facilities.py`, `lambdas/notifications/` (handler, matcher, dedup, email_builder), `lambdas/preferences/handler.py`, `frontend/src/types.ts`, and the Phase 1 verification report.

The good news: the pipeline is almost entirely compatible already. The `harvard` entry exists in `facilities.py` with `matchi_id=None`, `VALID_FACILITY_IDS` is auto-derived from `facilities.keys()`, `matcher.py` constructs composite keys dynamically, and `dedup.py` hashes sport into the key. Only three files need targeted changes: `email_builder.py` (Harvard-specific CTA), `frontend/src/types.ts` (add harvard to FACILITIES array), and `dedup.py` / `NOTIFICATION_TTL_SECONDS` (TTL discussion below).

**Primary recommendation:** Make four small, targeted changes — email_builder Harvard CTA, frontend FACILITIES entry, dedup TTL configuration, and a Harvard-specific link in email — then add tests. No structural refactoring needed.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| NOTF-01 | Harvard scraper invokes existing notifications Lambda with standard diff payload format | Already wired in Phase 1 — handler.py line 198 invokes NOTIFICATIONS_FUNCTION with `{"diff": diff}`. No change needed. |
| NOTF-02 | Email includes lesson-specific content: location, date, time, spot count | email_builder.py renders `court["court_name"]` and `court["time_slot"]` inline. Harvard's `court_name` = location string (e.g. "Indoor Tennis Court 6"). These fields pass through unchanged. Subject line says "courts" — consider "lessons" variant but not required. |
| NOTF-03 | Email includes direct link to Harvard Rec program registration page | email_builder.py currently has a hardcoded "Take me to Matchi" button pointing to `MATCHI_GENERAL_URL`. This button must be made facility-aware: when `facility_key == "harvard"`, emit a "Register at Harvard Rec" button pointing to `https://membership.gocrimson.com/Program/GetProgramInstances?programID=...` (or the program page root). |
| NOTF-04 | Dedup prevents re-alerting for the same lesson slot within a configurable TTL | dedup.py uses SHA-256 of (userId, facilityId, sport, date, time_slot, court_name). Harvard lessons have distinct `time_slot` and `court_name` (location) so the hash will be unique per slot. 24h TTL is a concern for single-spot lessons — see Pitfalls section. |
| PREF-01 | `harvard` added as a facility in facilities.py | ALREADY DONE in Phase 1. `facilities.py` line 70-75: `"harvard": {"matchi_id": None, "display_name": "Harvard Recreation", "sports": ["tennis"]}`. No change required. |
| PREF-02 | Frontend FACILITIES list includes Harvard Recreation | `frontend/src/types.ts` line 67-77: FACILITIES array does NOT include `harvard`. Must add `{ id: 'harvard', displayName: 'Harvard Recreation', sports: ['tennis'] }`. |
| PREF-03 | Users can create preferences for Harvard facility + tennis sport | Preferences Lambda validation: `VALID_FACILITY_IDS = set(facilities.keys())` (line 41) — auto-includes `harvard` already. Sport `"tennis"` is in `VALID_SPORTS`. `get_sports("harvard")` returns `["tennis"]`. No backend change needed. |
| PREF-04 | Existing matcher.py correctly matches `harvard#tennis` composite key against user preferences | `matcher.py` line 110: `composite_key = f"{facility_id}#{sport}"`. If user has `facilityId="harvard"` and `sport="tennis"`, this yields `"harvard#tennis"` which matches the scraper's diff key. Works without modification. |
</phase_requirements>

## Standard Stack

### Core — No New Dependencies

All integration work uses the existing stack. No new packages required.

| Component | File | Version/Status | Purpose |
|-----------|------|----------------|---------|
| email_builder | `lambdas/notifications/email_builder.py` | Existing | HTML + plain-text email construction |
| matcher | `lambdas/notifications/matcher.py` | Existing | Composite key matching; works for harvard#tennis already |
| dedup | `lambdas/notifications/dedup.py` | Existing | SHA-256 hash dedup with 24h TTL |
| preferences handler | `lambdas/preferences/handler.py` | Existing | VALID_FACILITY_IDS auto-derived; no change needed |
| facilities | `facilities.py` | Existing | `harvard` entry already present |
| frontend types | `frontend/src/types.ts` | Existing | FACILITIES array needs one entry added |

## Architecture Patterns

### How the Notification Pipeline Consumes Harvard Diffs

The Harvard scraper already emits:

```python
# lambdas/harvard-scraper/handler.py line 161-162
current_snapshot: dict = {COMPOSITE_KEY: current_by_date}
# COMPOSITE_KEY = "harvard#tennis"
```

The diff sent to notifications Lambda has shape:
```python
{
  "harvard#tennis": {
    "2026-04-15": {
      "10:00-11:00": ["Indoor Tennis Court 6"],
      "14:00-15:00": ["Indoor Tennis Court 3"]
    }
  }
}
```

The notifications Lambda `handler.py` receives this as `event["diff"]` and passes it straight to `matcher.match_preferences()`.

### How Matcher Handles Harvard (No Change Needed)

`matcher.py` constructs: `composite_key = f"{facility_id}#{sport}"`. A preference with `facilityId="harvard"`, `sport="tennis"` produces `"harvard#tennis"` — exact match. Day-of-week, time window, and court_type filtering all work on the standard fields. Court type filtering for Harvard will always pass through since `courtType` is `None` for tennis preferences and `_court_type_matches` returns `True` when `court_type` is None.

### How Dedup Handles Harvard (Works; TTL Worth Considering)

`dedup.py` hashes: `f"{user_id}|{facility_id}|{sport}|{date}|{time_slot}|{court_name}"`. For Harvard: `facility_id="harvard"`, `sport="tennis"`, `court_name="Indoor Tennis Court 6"`. This is a unique, stable key — dedup works correctly.

The 24h TTL (`NOTIFICATION_TTL_SECONDS = 86400`) is defined as a module-level constant. It is NOT an environment variable. If a lesson slot is released, grabbed, then released again within 24 hours, the user will not get a second alert. For typical Harvard lesson cycles this is acceptable (spots are held for hours/days not minutes), but it is a known limitation.

### Email Builder — The Only Required Code Change

`email_builder.py` line 139 retrieves `matchi_id` but does NOT use it for the CTA button (lines 158-166 always link to `MATCHI_GENERAL_URL = "https://www.matchi.se"`).

For Harvard, "Take me to Matchi" is wrong. The fix is to make the per-facility section emit a conditional CTA:

```python
# Pattern to implement in email_builder.py
HARVARD_REG_URL = "https://membership.gocrimson.com/Program/GetProgramInstances?programID=a20e7ae2-fedc-4a8e-a7c3-236695040c63"
MATCHI_GENERAL_URL = "https://www.matchi.se"

# In the per-facility loop (currently lines 137-155):
is_harvard = (facility_key == "harvard")
cta_url = HARVARD_REG_URL if is_harvard else MATCHI_GENERAL_URL
cta_label = "Register at Harvard Rec" if is_harvard else "Book on Matchi"
```

The general "Take me to Matchi" button at the bottom (lines 158-166) should also become conditional — either omit it entirely for all-Harvard emails or replace it with a Harvard link.

The cleanest approach: move the CTA inside the per-facility loop so each facility block has its own button. This handles mixed-facility emails (unlikely but possible) correctly.

### Frontend FACILITIES — One Line Addition

`frontend/src/types.ts` line 77 is where the last FACILITIES entry sits. Add after it:

```typescript
{ id: 'harvard', displayName: 'Harvard Recreation', sports: ['tennis'] },
```

The `PreferenceForm.tsx` filters by `f.sports.includes(sport)` so when a user selects "tennis", Harvard Recreation will appear. When they select "padel", it won't appear (correct, since Harvard only has tennis).

The `getFacilityDisplayName()` helper on line 134 does a lookup against FACILITIES — it will correctly return "Harvard Recreation" once the entry is added.

### Anti-Patterns to Avoid

- **Hard-coding harvard-specific logic in matcher.py or dedup.py**: These are generic and already work. Do not add any `if facility_key == "harvard"` branches there.
- **Adding a separate notification Lambda for Harvard**: The whole point of Phase 2 is to reuse the existing pipeline.
- **Making TTL an environment variable now**: It would require a Lambda redeploy and is out of scope. Document the 24h limitation clearly.
- **Changing the matchi scraper or its handler**: Completely separate Lambda. Leave it alone.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Composite key matching | Custom facility resolver | Existing `matcher.py` composite key pattern | Already works for any `facilityId#sport` pair |
| Dedup | Custom timestamp-based logic | Existing `dedup.py` SHA-256 + DynamoDB TTL | Hash covers all identity fields including sport |
| Preference validation | Custom harvard facility check | Existing `VALID_FACILITY_IDS = set(facilities.keys())` | Auto-includes harvard already |
| Email HTML | Jinja2 template engine | Existing inline string-building in email_builder.py | No new deps; consistent with existing code |

**Key insight:** The pipeline was designed to be facility-agnostic through composite keys. Harvard slots through as a normal `facilityId#sport` pair.

## Common Pitfalls

### Pitfall 1: email_builder.py fetches matchi_id but doesn't use it for per-facility CTAs
**What goes wrong:** `matchi_id = _facility_matchi_id(facility_key)` is called on line 139, but `matchi_id` is never referenced again in the body (the CTA links to the generic `MATCHI_GENERAL_URL`). For Harvard, `get_matchi_id("harvard")` returns `None` — if anyone ever tries to build a per-facility Matchi URL, they'll get a TypeError trying to format `None` into a URL. The dead variable also confuses readers.
**How to avoid:** Remove the dead variable assignment OR repurpose it: make the per-facility CTA conditional on whether `matchi_id` is None. If `matchi_id is None`, the facility is non-Matchi; emit the Harvard Rec link. This is the cleanest generalization.
**Warning signs:** `matchi_id` assigned but not used anywhere in the function body after assignment.

### Pitfall 2: Frontend FACILITIES missing harvard causes silent preference creation failure
**What goes wrong:** If `harvard` is missing from `frontend/src/types.ts` FACILITIES, users simply can't select it in the UI. The backend will still accept it (VALID_FACILITY_IDS is backend-authoritative), but there's no UI path to create the preference. This is easy to miss in testing since the backend still works.
**How to avoid:** Add the frontend entry and verify it appears in the PreferenceForm facility grid when tennis is selected.
**Warning signs:** Harvard not appearing as a selectable facility in the UI when tennis sport is chosen.

### Pitfall 3: 24h dedup TTL may suppress re-alerting for re-opened slots
**What goes wrong:** If a 1-spot Harvard lesson opens, is booked within minutes, then the booking is cancelled (spot re-opens) within 24 hours, the user will NOT get a second alert. The dedup record from the first alert is still live.
**Why it happens:** `NOTIFICATION_TTL_SECONDS = 86400` is a hard constant. The hash includes `court_name` and `time_slot` which don't change between open/close/reopen cycles for the same lesson.
**How to avoid:** For Phase 2 this is acceptable — document it. If it becomes a real problem, a future phase can reduce TTL or make it configurable per-facility via environment variable.
**Warning signs:** User reports "I got an alert, spot was gone, I checked back 2 hours later and a spot opened again but no alert came."

### Pitfall 4: Email subject says "courts" not "lessons" for Harvard
**What goes wrong:** The subject line reads "1 new court available!" — Harvard users are booking lesson spots, not courts. The distinction may confuse users.
**Why it happens:** `email_builder.py` uses the word "court" uniformly for all facilities.
**How to avoid:** For Phase 2, this is cosmetic and acceptable — the content of the email clearly shows location and time. A future enhancement could vary the vocabulary.

### Pitfall 5: courtType validation blocks tennis preferences with "courtType" set
**What goes wrong:** `preferences/handler.py` line 169: `if sport != "padel": errors.append("courtType is only valid when sport is 'padel'")`. This is correct behavior — if a frontend bug ever sends `courtType` for a tennis preference, it'll be rejected. No risk for Harvard specifically.
**How to avoid:** Frontend form already only shows courtType UI for padel. No action needed.

## Code Examples

### How to Add a Conditional CTA to email_builder.py

```python
# Source: existing email_builder.py pattern extended for non-Matchi facilities

HARVARD_REG_URL = (
    "https://membership.gocrimson.com/Program/GetProgramInstances"
    "?programID=a20e7ae2-fedc-4a8e-a7c3-236695040c63"
)
MATCHI_GENERAL_URL = "https://www.matchi.se"


def _facility_cta(facility_key: str) -> tuple[str, str]:
    """Return (url, label) for the CTA button for a given facility."""
    matchi_id = _facility_matchi_id(facility_key)
    if matchi_id is None:
        # Non-Matchi facility (e.g. harvard) — link to their platform
        return HARVARD_REG_URL, "Register at Harvard Rec"
    return MATCHI_GENERAL_URL, "Book on Matchi"
```

This generalizes correctly: any future non-Matchi facility with `matchi_id=None` gets the Harvard link (which isn't ideal long-term, but for Phase 2 with only one non-Matchi facility it's fine).

A cleaner v2 approach would add a `booking_url` key to the facilities dict, but that's out of scope.

### How to Add harvard to Frontend FACILITIES

```typescript
// frontend/src/types.ts — add after the existing last entry
export const FACILITIES: Facility[] = [
  { id: 'ota', displayName: 'OTA (Oslo Tennis Arena)', sports: ['tennis', 'padel'] },
  // ... existing entries ...
  { id: 'bergenpadelklubb', displayName: 'Bergen Padelklubb', sports: ['padel'] },
  { id: 'interpadelbergen', displayName: 'InterPadel Bergen (Sandsli)', sports: ['padel'] },
  { id: 'harvard', displayName: 'Harvard Recreation', sports: ['tennis'] },  // add this line
];
```

### What a Harvard Notification Match Dict Looks Like

```python
# Output of matcher.match_preferences() for a harvard preference
{
    "userId": "alice@example.com",
    "preferenceId": "uuid-xxx",
    "facilityId": "harvard",
    "sport": "tennis",
    "date": "2026-04-15",
    "courts": [
        {"time_slot": "10:00-11:00", "court_name": "Indoor Tennis Court 6"},
    ],
}
```

Note: `court_name` holds the `location` field from the Harvard scraper (e.g. "Indoor Tennis Court 6"). This renders as the location in the email, which is meaningful — users know which court they'd be on.

## State of the Art

| Area | Current State | What's Needed for Harvard | Impact |
|------|--------------|--------------------------|--------|
| `facilities.py` | `harvard` entry with `matchi_id=None` | DONE (Phase 1) | No change needed |
| `lambdas/scraper/handler.py` | Guard skips None matchi_id | DONE (Phase 1) | No change needed |
| `lambdas/harvard-scraper/handler.py` | Invokes NOTIFICATIONS_FUNCTION | DONE (Phase 1) | No change needed |
| `lambdas/notifications/matcher.py` | Generic composite key matching | Works for harvard#tennis | No change needed |
| `lambdas/notifications/dedup.py` | SHA-256 hash includes sport | Works for harvard | No change needed — but 24h TTL is a known limitation |
| `lambdas/notifications/email_builder.py` | Dead `matchi_id` variable; CTA hardcoded to Matchi | Needs Harvard-aware CTA | Requires targeted change |
| `lambdas/preferences/handler.py` | `VALID_FACILITY_IDS = set(facilities.keys())` | Auto-includes harvard | No change needed |
| `frontend/src/types.ts` | FACILITIES array missing `harvard` | Needs one entry added | Requires targeted change |

## Open Questions

1. **HARVARD_REG_URL constant: where should it live?**
   - What we know: The program ID `a20e7ae2-fedc-4a8e-a7c3-236695040c63` is already the env var `HARVARD_PROGRAM_ID` in the scraper Lambda, but the notifications Lambda has no Harvard-specific env var.
   - What's unclear: Should the Harvard booking URL be hardcoded in `email_builder.py`, or should it come from a `booking_url` field in `facilities.py`?
   - Recommendation: For Phase 2, hardcode in `email_builder.py` as a module constant. Adding `booking_url` to `facilities.py` is cleaner long-term but is a larger change touching all facilities — defer.

2. **Should the email subject vary for Harvard ("lesson" vs "court")?**
   - What we know: The subject reads "1 new court available!" regardless of facility.
   - What's unclear: Whether this matters to users receiving Harvard alerts.
   - Recommendation: Leave as-is for Phase 2. The email body content clearly shows it's a lesson slot.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (existing, no new setup needed) |
| Config file | none — invoked directly |
| Quick run command | `python -m pytest tests/test_notifications.py tests/test_preferences.py -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| NOTF-01 | Harvard scraper invokes notifications Lambda | unit (handler test) | `python -m pytest tests/test_harvard_scraper.py::TestHarvardHandler::test_notification_on_second_run_new_slot -x` | ✅ (Phase 1) |
| NOTF-02 | Email renders location + time for Harvard matches | unit (email_builder) | `python -m pytest tests/test_notifications.py -k "harvard" -x` | ❌ Wave 0 |
| NOTF-03 | Email CTA links to Harvard Rec, not Matchi | unit (email_builder) | `python -m pytest tests/test_notifications.py -k "harvard_cta" -x` | ❌ Wave 0 |
| NOTF-04 | Dedup prevents re-alert for same harvard slot | unit (dedup) | `python -m pytest tests/test_notifications.py -k "harvard_dedup" -x` | ❌ Wave 0 |
| PREF-01 | `harvard` in VALID_FACILITY_IDS | unit (preferences) | `python -m pytest tests/test_preferences.py -k "harvard" -x` | ❌ Wave 0 |
| PREF-02 | Frontend FACILITIES includes harvard | manual visual | n/a — frontend visual check | n/a |
| PREF-03 | Preferences API accepts harvard+tennis | unit (preferences) | `python -m pytest tests/test_preferences.py -k "harvard" -x` | ❌ Wave 0 |
| PREF-04 | matcher matches harvard#tennis composite key | unit (matcher) | `python -m pytest tests/test_notifications.py -k "harvard_match" -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `python -m pytest tests/test_notifications.py tests/test_preferences.py -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] Tests for `email_builder` harvard CTA behavior — add to `tests/test_notifications.py` in `TestEmailBuilder` class
- [ ] Tests for matcher handling `harvard#tennis` composite key — add to `tests/test_notifications.py` in `TestMatchPreferences` class
- [ ] Tests for dedup with harvard facilityId — add to `tests/test_notifications.py` in `TestDedup` class
- [ ] Tests for preferences API accepting/rejecting `facilityId="harvard"` — add to `tests/test_preferences.py`

No new test files needed — all tests extend existing test modules using existing fixtures.

## Sources

### Primary (HIGH confidence)

- Direct code reading: `lambdas/notifications/email_builder.py` — full function analysis
- Direct code reading: `lambdas/notifications/matcher.py` — composite key logic confirmed
- Direct code reading: `lambdas/notifications/dedup.py` — TTL constant and hash inputs confirmed
- Direct code reading: `lambdas/preferences/handler.py` — `VALID_FACILITY_IDS = set(facilities.keys())` line 41 confirmed
- Direct code reading: `facilities.py` — `harvard` entry confirmed present with `matchi_id=None`
- Direct code reading: `frontend/src/types.ts` — FACILITIES array confirmed missing `harvard`
- Direct code reading: `.planning/phases/01-scraper/01-VERIFICATION.md` — Phase 1 artifacts confirmed

### Secondary (MEDIUM confidence)

- None needed — all findings from direct code inspection

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all files read directly; no inference
- Architecture: HIGH — integration path traced end-to-end through actual code
- Pitfalls: HIGH — identified from direct code reading (dead variable, missing frontend entry, TTL constant)

**Research date:** 2026-04-10
**Valid until:** 2026-05-10 (stable codebase; no moving targets)
