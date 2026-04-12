# Architecture Patterns

**Domain:** Multi-source court/lesson availability monitoring
**Researched:** 2026-04-10

## Context

This documents how a new Harvard Recreation scraper Lambda should integrate with the existing scraper → diff → notify pipeline. The analysis is based on direct code review of the production system.

---

## Existing Pipeline (Verified from source)

### Data Flow

```
EventBridge cron
    |
    v
matchi-scraper Lambda (lambdas/scraper/)
    |
    |-- fetch_available_slots(facility_id, date, sport)  [scraper.py]
    |-- load_snapshot(table, composite_key, date)         [DynamoDB read]
    |-- build_new_courts_diff(current, previous)          [diff.py]
    |-- save_snapshot(table, composite_key, date)         [DynamoDB write]
    |
    v
diff payload: { "diff": { "facility#sport": { "YYYY-MM-DD": { "HH:MM-HH:MM": ["Court Name"] } } } }
    |
    v  (async Lambda.invoke InvocationType="Event")
notifications Lambda (lambdas/notifications/)
    |
    |-- scan all preferences from tennis-preferences
    |-- match_preferences(diff, prefs, blacklisted_dates)  [matcher.py]
    |-- filter_already_notified(matches, notif_table)      [dedup.py]
    |-- build_notification_email(user_id, matches)         [email_builder.py]
    |-- send via SMTP or SES
    |-- record_notifications(matches, notif_table)         [dedup.py]
```

### Key Contract: The Diff Payload

The notifications Lambda accepts one thing from its caller:

```python
event = {
    "diff": {
        "<facilityId>#<sport>": {          # e.g. "harvard#tennis"
            "YYYY-MM-DD": {
                "HH:MM-HH:MM": ["Court/Lesson Name"],
            }
        }
    }
}
```

This is the **only contract** between scraper and notifications. Any Lambda that produces this structure and invokes notifications Lambda with it will work transparently — the notifications Lambda has no knowledge of the scraper source.

### Matching Contract: Preferences

`matcher.py` constructs composite keys from preferences:

```python
composite_key = f"{facility_id}#{sport}"   # e.g. "harvard#tennis"
facility_diff = diff.get(composite_key)
```

So the matcher already handles arbitrary facility IDs — it does not reference `facilities.py` for validation, only for display names (with a `KeyError` fallback to `facility_key.title()`). Harvard preferences with `facilityId="harvard"` and `sport="tennis"` will resolve to `"harvard#tennis"` and match against diff keys correctly.

### Validation Constraint: Preferences Lambda

`VALID_FACILITY_IDS = set(facilities.keys())` is enforced at preference creation time in `lambdas/preferences/handler.py`. Harvard must be added to `facilities.py` for the Preferences API to accept `facilityId="harvard"`. However since Harvard uses a completely different scraping mechanism (Innosoft Fusion, not matchi.se), it cannot simply be added to the matchi `facilities` dict — the facilities module would need an extension pattern.

---

## Recommended Architecture for Harvard Scraper

### Component Diagram

```
EventBridge cron (separate schedule, every 15-30 min)
    |
    v
harvard-scraper Lambda  [lambdas/harvard_scraper/]
    |
    |-- GET https://membership.gocrimson.com/Program/GetProgramInstances?programID=...
    |-- parse #ApptInfo JSON from HTML  (BeautifulSoup)
    |-- build slots dict: { "HH:MM-HH:MM": ["Indoor Tennis Court N"] }
    |-- load_snapshot(dynamodb, "harvard#tennis", date)
    |-- diff: new_slots - previous_slots
    |-- save_snapshot(dynamodb, "harvard#tennis", date)
    |
    v
same diff payload format
    |
    v  (async Lambda.invoke — same mechanism as matchi scraper)
notifications Lambda  [UNCHANGED]
    |
    v
tennis-preferences  [harvard preferences matched via "harvard#tennis" key]
    |
    v
email to user
```

### Component Boundaries

| Component | Responsibility | Communicates With | Changes Needed |
|-----------|---------------|-------------------|----------------|
| `harvard-scraper Lambda` | Fetch Innosoft Fusion HTML, parse lesson slots, diff against DynamoDB, invoke notifications | DynamoDB (tennis-availability), notifications Lambda | New — created from scratch |
| `notifications Lambda` | Match diff against preferences, dedup, send email | DynamoDB (tennis-preferences, tennis-notifications, tennis-users) | None — zero changes required |
| `preferences Lambda` | CRUD for user preferences | DynamoDB (tennis-preferences, tennis-users, tennis-availability) | Add "harvard" to VALID_FACILITY_IDS |
| `facilities.py` | Shared facility config | Copied into Lambda packages at build time | Add harvard entry (no matchi_id needed; use 0 or omit) |
| `email_builder.py` | HTML email construction | `facilities.py` for display names | None — already has KeyError fallback |
| `frontend PreferenceForm` | Facility selection UI | Preferences API | Add Harvard Rec as a selectable facility |
| `DynamoDB tennis-availability` | Availability snapshots | Both matchi scraper and harvard scraper | No schema change — composite key "harvard#tennis" fits existing PK pattern |

### Why Zero Notifications Lambda Changes Are Required

1. The diff payload format is generic: `facilityKey#sport -> date -> timeslot -> [names]`. Harvard data fits without modification.
2. `matcher.py` does not validate facility IDs against `facilities.py` — it just does dict lookups.
3. `email_builder.py` has an explicit `KeyError` fallback: `return facility_key.title()` — so "harvard" displays as "Harvard" with no code change needed there either.
4. `dedup.py` hashes on `(userId, facilityId, sport, date, timeSlot, courtName)` — Harvard entries deduplicate independently.

### Lesson Slot Schema Translation

The Innosoft Fusion `#ApptInfo` JSON needs to be translated into the diff format. The scraper's internal representation should be:

```python
# Input from Innosoft Fusion
appointment = {
    "StartDate": "2026-04-15T09:00:00",
    "EndDate":   "2026-04-15T10:00:00",
    "Location":  "Indoor Tennis Court 6",
    "ClassSize": 1,
    "NumberRegistered": 0,
}

# Translated snapshot (what gets stored in DynamoDB and diffed)
slots = {
    "09:00-10:00": ["Indoor Tennis Court 6"]
}
```

Availability condition: `NumberRegistered < ClassSize` (and `NumberOnWaitlist == 0` if waitlist filtering is desired — out of scope for now per PROJECT.md).

The date dimension: since lessons have fixed dates (not a rolling 14-day window), the Harvard scraper iterates over the actual appointment dates returned by the API rather than generating a date range.

---

## Data Flow: Harvard-Specific Details

```
Innosoft Fusion HTML
    |
    v
BeautifulSoup → soup.find("input", {"id": "ApptInfo"})["value"]
    |
    v
json.loads(appt_info_value)  → list of appointment dicts
    |
    v
Filter: NumberRegistered < ClassSize  (available spots exist)
    |
    v
Group by date, build slots dict per date
    |
    v
DynamoDB load previous snapshot for "harvard#tennis" / each date
    |
    v
Diff (new slots only — same build_new_courts_diff logic)
    |
    v
DynamoDB save new snapshot
    |
    v
If diff non-empty: invoke notifications Lambda {"diff": {"harvard#tennis": {...}}}
```

The harvard scraper can import and reuse `diff.py` from the matchi scraper — but because Lambda packages are isolated zip files built per-function, `diff.py` should be copied into the harvard scraper package (same pattern as `facilities.py` is copied via Makefile).

---

## Build Order

Dependencies between components determine the correct build sequence:

1. **`facilities.py` update** — Add `harvard` entry. This file is copied into Lambda packages at build time and is a prerequisite for both the scraper and preferences Lambda packages.

2. **`harvard-scraper Lambda`** — Core new component. Depends on: updated `facilities.py`, DynamoDB table already existing (it does), `NOTIFICATIONS_FUNCTION` env var pointing to existing notifications Lambda.

3. **`preferences Lambda` redeploy** — Rebuild package with updated `facilities.py` so `VALID_FACILITY_IDS` includes "harvard". Without this step, users get 400 errors trying to save Harvard preferences.

4. **EventBridge rule** — New cron trigger for the harvard-scraper Lambda. Independent of code changes.

5. **Frontend update** — Add Harvard Rec to the facility selector in `PreferenceForm`. Depends on preferences Lambda accepting "harvard" (step 3).

**Notifications Lambda: NOT in build order** — no changes needed.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Merging Harvard Logic Into the Matchi Scraper
**What goes wrong:** The matchi scraper iterates over `facilities.py` using `matchi_id` for URL construction. Adding Harvard there requires either special-casing the matchi URL builder or adding a fake matchi_id. This creates conditional branching in production code that handles a different HTTP protocol (Innosoft vs matchi.se).
**Consequence:** Any Harvard scrape error could circuit-break matchi scraping for the entire run. Deployment of Harvard requires redeploying the production scraper.
**Instead:** Separate Lambda, separate EventBridge rule. Harvard failures are fully isolated.

### Anti-Pattern 2: Modifying the Notifications Lambda Interface
**What goes wrong:** Adding a `source` field to the diff payload, or separate Harvard-specific routing inside notifications Lambda.
**Consequence:** Breaks existing scraper → notifications contract, requires coordination across multiple deployments.
**Instead:** The existing `facilityId#sport` composite key is the namespace. "harvard#tennis" is already a distinct key that routes correctly through all existing logic.

### Anti-Pattern 3: Creating a Separate Notifications Path for Harvard
**What goes wrong:** Building a harvard-specific email sender to avoid touching the notifications Lambda.
**Consequence:** Duplicates dedup logic, email templates, SMTP/SES configuration. Users with both matchi and Harvard preferences get emails from two different code paths with inconsistent formatting.
**Instead:** The existing notifications Lambda already handles arbitrary facilityIds. Feed the same pipeline.

### Anti-Pattern 4: Adding `matchi_id` as a Required Field in `facilities.py`
**What goes wrong:** Harvard has no matchi_id. If the facilities dict requires `matchi_id`, adding Harvard either breaks helper functions or requires a sentinel value.
**Prevention:** Make `matchi_id` optional in the Harvard entry (or use `None`). The `get_matchi_id()` helper is only called by matchi-specific code. The email builder's `_facility_matchi_id()` already returns `0` on `KeyError`.

---

## Scalability Considerations

| Concern | Current (matchi) | Harvard Addition |
|---------|-----------------|------------------|
| Poll frequency | EventBridge every N minutes, 14 days × N facilities | Separate schedule, 15-30 min recommended per PROJECT.md |
| DynamoDB throughput | On-demand, no contention | Same table, different PK prefix — no contention |
| Notifications Lambda concurrency | One invocation per scraper run | Second independent invocation path, still async |
| Lessons vs courts | Courts: many per date | Lessons: few per date (typically 1 per `ClassSize=1` slot) — simpler diff, smaller payloads |

---

## Sources

- Direct code review: `lambdas/scraper/handler.py`, `diff.py`
- Direct code review: `lambdas/notifications/handler.py`, `matcher.py`, `dedup.py`, `email_builder.py`
- Direct code review: `lambdas/preferences/handler.py`
- Direct code review: `facilities.py`
- Project context: `.planning/PROJECT.md` (technical discovery 2026-04-10)
- Confidence: HIGH — all findings from first-party source code, no external references needed for integration design
