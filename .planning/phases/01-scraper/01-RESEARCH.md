# Phase 1: Scraper - Research

**Researched:** 2026-04-10
**Domain:** AWS Lambda scraper for Innosoft Fusion lesson availability (Harvard Recreation)
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SCRP-01 | Lambda fetches Harvard Rec lesson data via GET /Program/GetProgramInstances endpoint | Stack section: `requests.Session` + browser headers; PITFALL-3 (IP/UA blocking) |
| SCRP-02 | Parser extracts structured slot data from #ApptInfo hidden input JSON | Architecture section: exact BS4 extraction pattern + availability logic |
| SCRP-03 | Slots stored as DynamoDB snapshots with `harvard#tennis` composite key and date sort key | Architecture section: reuses existing `tennis-availability` table, same PK/SK schema |
| SCRP-04 | Diff engine detects newly available slots (unavailable → available transitions) | diff.py reuse: `build_new_courts_diff()` works on same nested dict shape; PITFALL-2 (HTML text is ground truth) |
| SCRP-05 | First run seeds DynamoDB without triggering spurious alerts | diff.py cold-start guard: `has_changes()` returns False when previous is empty; confirmed in source |
</phase_requirements>

---

## Summary

This phase implements a new standalone AWS Lambda (`lambdas/harvard-scraper/`) that polls the Harvard Recreation Innosoft Fusion portal for tennis lesson availability, computes a diff against a DynamoDB snapshot, and invokes the existing notifications Lambda when new spots appear. The scraper is deliberately isolated from the production matchi.se scraper — it is deployed as a completely separate function with its own EventBridge schedule.

The integration point into the existing pipeline is narrow and well-defined: produce a diff payload in the format `{"diff": {"harvard#tennis": {"YYYY-MM-DD": {"HH:MM-HH:MM": ["Lesson Name"]}}}}` and invoke the notifications Lambda with it. Nothing in the notifications Lambda, dedup, matcher, or email builder needs to change — the `harvard#tennis` composite key routes through all existing logic transparently.

The two hardest problems in this phase are (1) HTML parsing ground truth — availability MUST be read from `.spots-tag p` text, NOT from `ClassSize - NumberRegistered` arithmetic — and (2) the cold-start seeding guard — the existing `diff.py` already handles this correctly and must be reused verbatim, not reimplemented.

**Primary recommendation:** Copy `diff.py` from `lambdas/scraper/` into `lambdas/harvard-scraper/`, implement a `parse_harvard_availability(html)` function that uses `.spots-tag p` as the authoritative availability signal, and feed results through the same `load_snapshot → diff → save_snapshot → invoke_notifications` loop that the matchi scraper already uses.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `requests` | >=2.33.1 | HTTP fetch of Innosoft Fusion endpoint | Already in project; supports Session for cookie handling |
| `beautifulsoup4` | >=4.14.3 | Parse server-rendered HTML, extract `#ApptInfo` value and `.spots-tag p` text | Already in project; used by existing scraper |
| `boto3` | bundled in Lambda runtime | DynamoDB read/write, Lambda.invoke for notifications | Already used everywhere |
| `json` (stdlib) | built-in | Deserialize `#ApptInfo` JSON string | No new dep needed |
| `datetime` (stdlib) | built-in | Parse ISO datetimes from `StartDate`/`EndDate` fields | `datetime.fromisoformat()` handles Innosoft format directly |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `diff.py` (copy from `lambdas/scraper/`) | internal | `build_new_courts_diff()`, `has_changes()` | Copy verbatim — do NOT import cross-Lambda at runtime |
| `facilities.py` (updated at repo root) | internal | Display name lookup, VALID_FACILITY_IDS for preferences Lambda | Add `harvard` entry; copied into package at build time |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `html.parser` (stdlib BS4 backend) | `lxml` | `lxml` is faster on large documents but adds a C binary (~2MB compressed), causes macOS → Linux build friction, not used anywhere in the project. `html.parser` is sufficient for a small AJAX partial view. |
| `datetime.fromisoformat()` | `arrow`, `python-dateutil` | `arrow` is a root-level CLI dep but is NOT included in any Lambda package to keep sizes small. `fromisoformat()` handles Innosoft's well-formed ISO datetimes natively on Python 3.11. |
| `requests.Session()` | `requests.get()` | Session preserves any ASP.NET_SessionId cookie across requests with no downside. Use Session. |

**Installation (requirements.txt for `lambdas/harvard-scraper/`):**
```
requests
beautifulsoup4
boto3
```
No new packages beyond what the existing scraper already uses.

---

## Architecture Patterns

### Recommended Project Structure

```
lambdas/
├── harvard-scraper/
│   ├── handler.py          # Lambda entry point — mirrors lambdas/scraper/handler.py structure
│   ├── scraper.py          # Harvard-specific: fetch_lesson_instances() + parse_harvard_availability()
│   ├── diff.py             # COPIED from lambdas/scraper/diff.py — do not modify
│   ├── facilities.py       # COPIED from repo root at build time (same as all other Lambdas)
│   └── requirements.txt    # requests, beautifulsoup4, boto3
```

### Pattern 1: Innosoft Fusion Fetch + Parse

**What:** Single-endpoint HTTP fetch using `requests.Session`, then BS4 extracts two things: the `#ApptInfo` JSON blob (for metadata: time, location, date) and the `.spots-tag p` text elements (for availability ground truth).

**When to use:** Every Lambda invocation.

**Availability is NOT `ClassSize - NumberRegistered`.** The `.spots-tag p` text is computed server-side and accounts for holds, pending payments, and waitlist precedence that the raw JSON fields do not reflect. Use the HTML text as the authoritative signal.

```python
# Source: .planning/research/STACK.md + .planning/research/PITFALLS.md (verified against Innosoft platform)
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

PROGRAM_URL = "https://membership.gocrimson.com/Program/GetProgramInstances"

def fetch_lesson_instances(program_id: str) -> list[dict]:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "text/html, */*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    resp = session.get(PROGRAM_URL, params={"programID": program_id}, timeout=30)
    resp.raise_for_status()  # NEVER swallow non-200 — surface as Lambda error
    return parse_harvard_availability(resp.text)


def parse_harvard_availability(html: str) -> list[dict]:
    """Parse Innosoft Fusion HTML. Returns list of available lesson slot dicts.
    
    Availability ground truth: .spots-tag p text, NOT ClassSize arithmetic.
    """
    soup = BeautifulSoup(html, "html.parser")
    
    appt_input = soup.find("input", {"id": "ApptInfo"})
    if not appt_input or not appt_input.get("value"):
        raise ValueError("ApptInfo input not found — HTML structure may have changed")
    
    appointments = json.loads(appt_input["value"])
    spot_tags = soup.find_all(class_="spots-tag")
    
    now = datetime.now(timezone.utc)
    available = []
    
    for i, appt in enumerate(appointments):
        start_dt = datetime.fromisoformat(appt["StartDate"])
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if start_dt <= now:
            continue  # filter past-dated lessons (PITFALL-10)
        
        # Ground truth: check corresponding .spots-tag p text
        is_available = False
        if i < len(spot_tags):
            p = spot_tags[i].find("p")
            if p and "spot" in p.get_text(strip=True).lower():
                text = p.get_text(strip=True).lower()
                is_available = "no spots" not in text and "spot" in text
        
        if not is_available:
            continue
        
        end_dt = datetime.fromisoformat(appt["EndDate"])
        available.append({
            "date": start_dt.strftime("%Y-%m-%d"),
            "time_slot": f"{start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')}",
            "location": appt.get("Location", ""),
        })
    
    return available
```

### Pattern 2: Snapshot → Diff → Save → Notify (reuse existing pipeline)

**What:** Exact same loop as `lambdas/scraper/handler.py`. Load previous DynamoDB snapshot, diff against current, save new snapshot, invoke notifications Lambda if diff is non-empty.

**Critical:** The diff payload key MUST be `"harvard#tennis"` — this is what `matcher.py` joins against user preferences.

```python
# Source: lambdas/scraper/handler.py (verified) + lambdas/scraper/diff.py (verified)

COMPOSITE_KEY = "harvard#tennis"

def run_scraper(program_id, table, lambda_client, notifications_function):
    lessons = fetch_lesson_instances(program_id)
    
    # Group by date: { date: { time_slot: [location] } }
    current_by_date: dict[str, dict[str, list[str]]] = {}
    for lesson in lessons:
        date = lesson["date"]
        ts = lesson["time_slot"]
        loc = lesson["location"]
        current_by_date.setdefault(date, {}).setdefault(ts, []).append(loc)
    
    # Build full snapshot structures for diff
    current_snapshot = {COMPOSITE_KEY: current_by_date}
    previous_snapshot = {COMPOSITE_KEY: {}}
    
    for date_str, slots in current_by_date.items():
        prev = load_snapshot(table, COMPOSITE_KEY, date_str)
        previous_snapshot[COMPOSITE_KEY][date_str] = prev
        save_snapshot(table, COMPOSITE_KEY, date_str, slots)
    
    # has_changes() returns False when previous is all empty — cold-start guard
    from diff import build_new_courts_diff
    diff = build_new_courts_diff(current_snapshot, previous_snapshot)
    
    if diff and notifications_function:
        lambda_client.invoke(
            FunctionName=notifications_function,
            InvocationType="Event",
            Payload=json.dumps({"diff": diff}),
        )
```

### Pattern 3: facilities.py Extension for Harvard

**What:** Add `harvard` to `facilities.py` without requiring `matchi_id`. The `get_matchi_id()` helper is only called by matchi-specific code; Harvard entry needs only `display_name` and `sports`.

```python
# Source: facilities.py (verified) + .planning/research/ARCHITECTURE.md (verified)

# In facilities.py — add to the active facilities dict:
"harvard": {
    "display_name": "Harvard Recreation",
    "sports": ["tennis"],
    # No matchi_id — Harvard uses Innosoft Fusion, not matchi.se
},
```

The `email_builder.py` already has a `KeyError` fallback that returns `facility_key.title()`. The preferences Lambda's `VALID_FACILITY_IDS = set(facilities.keys())` will accept `"harvard"` once this entry is added. The matchi scraper's `facilities.items()` loop uses `matchi_id` — the absence of that field in the harvard entry does NOT cause an error there because the matchi scraper only iterates active facilities via `get_sports()` which accesses `facilities[facility_key]["sports"]`, not `matchi_id`.

**However**, verify that `handler.py` in the matchi scraper accesses `config["matchi_id"]` directly during iteration. If it does, the harvard entry (without `matchi_id`) must NOT be present in the same `facilities` dict used by that scraper, OR a guard must be added. The current `handler.py` at line 177 does `facility_sport_pairs.append((facility_key, config["matchi_id"], sport))` — this would raise `KeyError` for harvard.

**Resolution:** Use `matchi_id: None` in the harvard entry and guard the matchi scraper's iteration: `if config.get("matchi_id") is None: continue`. Alternatively, add harvard to a separate dict (e.g., `innosoft_facilities`) in `facilities.py`. The simplest approach: use `"matchi_id": None` and add a one-line guard in the matchi scraper loop.

### Anti-Patterns to Avoid

- **Importing across Lambda packages at runtime:** Lambda packages are isolated ZIP files. `diff.py` must be physically copied into `lambdas/harvard-scraper/`, not imported from `lambdas/scraper/`.
- **Trusting ClassSize arithmetic for availability:** `ClassSize - NumberRegistered` does not account for holds, pending transactions, or waitlist precedence. Always use `.spots-tag p` text.
- **Silent swallowing of HTTP errors:** `raise_for_status()` must be called. A 403 that returns an empty page looks like "no availability" and produces a false snapshot wipe. Surface HTTP errors as Lambda errors so CloudWatch alarms fire.
- **Hardcoding programID:** The course GUID changes each semester. It must be an environment variable (`HARVARD_PROGRAM_ID`).
- **Merging Harvard logic into the matchi scraper:** The matchi scraper iterates `facilities.items()` using `matchi_id`. Harvard has no matchi_id. A Harvard scrape failure would also risk the matchi production run.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Slot diffing | Custom set-diff logic | `diff.py` copied from `lambdas/scraper/` | Already handles cold-start guard, multi-facility/date nesting, sorts results |
| Cold-start seeding | Custom "first run" flag in DynamoDB | `has_changes()` returning False when previous is empty | Already implemented and tested in `diff.py` |
| Retry with backoff | Custom sleep loop | Mirror `scraper.py` `MAX_RETRIES = 3` pattern with exponential backoff | Avoids thundering-herd on rate-limit recovery |
| Structured logging | `print()` statements | Mirror `_log()` pattern from `lambdas/scraper/handler.py` | JSON structured logs required for CloudWatch filtering |
| Lazy boto3 init | Module-level client creation | Module-level `None` + `_get_dynamodb()` / `_get_lambda_client()` pattern | Reuses warm container connections; mirrors existing handler |

**Key insight:** The existing scraper codebase already solved all of the infrastructure problems (diff, cold-start, retry, logging, DynamoDB helpers). This phase is mostly about writing the Harvard-specific HTTP fetch and HTML parse functions, then wiring them into the established pattern.

---

## Common Pitfalls

### Pitfall 1: Cold-Start Diff Explosion

**What goes wrong:** On first Lambda invocation there is no previous DynamoDB snapshot. The diff computes against an empty dict and treats every available slot as "newly appeared" — firing alerts for every existing spot.

**Why it happens:** The diff is computed correctly by `build_new_courts_diff()` — BUT `has_changes()` in `diff.py` already guards this: it returns `False` when `previous` is empty. The danger is reimplementing the diff instead of reusing `diff.py`.

**How to avoid:** Copy `diff.py` verbatim and call `build_new_courts_diff(current, previous)` — do NOT reimplement the diff. The empty-previous guard is baked in. Additionally, log "baseline established — skipping notifications" on first run.

**Warning signs:** Every user with Harvard preferences receives a flood of alerts immediately after the Lambda first runs.

### Pitfall 2: HTML Text Is Ground Truth, JSON Capacity Math Is Not

**What goes wrong:** `ClassSize - NumberRegistered` looks like "spots remaining." It is NOT. Holds, pending payments, and waitlist precedence are not reflected in those fields but ARE reflected in the server-rendered `.spots-tag p` text.

**How to avoid:** Availability decision MUST come from `.spots-tag p` text. The JSON fields (`StartDate`, `EndDate`, `Location`) are used for metadata only.

**Warning signs:** Users report clicking an alert link and seeing "No spots available" — means false positive from capacity math.

### Pitfall 3: IP/UA Blocking (Silent False Negatives)

**What goes wrong:** The default `python-requests/2.x` User-Agent and AWS datacenter IP ranges are on many bot-detection blocklists. A 403 or 429 that returns an empty page causes the scraper to write an empty snapshot and produce a diff showing "all slots removed" — no alerts fire, users think nothing is available.

**How to avoid:** Set a browser-like User-Agent. Call `raise_for_status()` before parsing — never silently return `{}` on HTTP errors. Log HTTP status codes.

**Warning signs:** CloudWatch shows 403/429 responses, or "always zero availability" across consecutive runs when lessons should be visible.

### Pitfall 4: facilities.py KeyError in Matchi Scraper

**What goes wrong:** Adding `"harvard"` to `facilities` dict without a `matchi_id` field causes `lambdas/scraper/handler.py` line 177 (`config["matchi_id"]`) to raise `KeyError` on the next matchi scraper deployment — breaking production.

**How to avoid:** Add `"matchi_id": None` to the harvard entry AND add a guard in the matchi scraper's iteration: `if config.get("matchi_id") is None: continue`. Or keep harvard in a separate `innosoft_facilities` dict.

**Warning signs:** Matchi scraper starts failing with `KeyError: 'matchi_id'` in CloudWatch after `facilities.py` is updated.

### Pitfall 5: Past-Dated Lessons Triggering Alerts

**What goes wrong:** Innosoft may return past appointments with "1 Spot available" (booking system hasn't closed them). Diff detects them as newly available and fires alerts for lessons that already happened.

**How to avoid:** Filter `StartDate <= now()` during parsing, before any slot is added to the current snapshot.

**Warning signs:** Notification emails for lesson times that have already passed.

### Pitfall 6: Stale programID After Semester Rollover

**What goes wrong:** The course GUID `a20e7ae2-fedc-4a8e-a7c3-236695040c63` is semester-specific. When Harvard Recreation creates a new program for the next term, the old GUID returns zero instances indefinitely. No alerts fire. No errors appear.

**How to avoid:** Externalize as `HARVARD_PROGRAM_ID` environment variable. Log a warning when zero instances are parsed for 3+ consecutive runs.

---

## Code Examples

### Complete Snapshot Translation

```python
# Source: .planning/research/ARCHITECTURE.md (verified against diff.py interface)

# From parsed lesson list to the dict shape that diff.py expects:
# Snapshot = dict[composite_key, dict[date_str, dict[time_slot, list[location]]]]

def build_slots_by_date(lessons: list[dict]) -> dict[str, dict[str, list[str]]]:
    """Group parsed lessons into { date: { time_slot: [location] } }."""
    by_date: dict[str, dict[str, list[str]]] = {}
    for lesson in lessons:
        date = lesson["date"]          # "2026-04-15"
        ts   = lesson["time_slot"]     # "09:00-10:00"
        loc  = lesson["location"]      # "Indoor Tennis Court 6"
        by_date.setdefault(date, {}).setdefault(ts, []).append(loc)
    return by_date
```

### DynamoDB Helpers (copy from existing handler)

```python
# Source: lambdas/scraper/handler.py (verified)
# These can be copied verbatim — the schema (facilityId PK, date SK, slots JSON) is identical.

def load_snapshot(table, facility_key: str, date_str: str) -> dict:
    response = table.get_item(Key={"facilityId": facility_key, "date": date_str})
    item = response.get("Item")
    if item and "slots" in item:
        return json.loads(item["slots"])
    return {}

def save_snapshot(table, facility_key: str, date_str: str, slots: dict) -> None:
    table.put_item(Item={
        "facilityId": facility_key,
        "date": date_str,
        "slots": json.dumps(slots),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    })
```

### Structured Logging (mirror existing format)

```python
# Source: lambdas/scraper/handler.py (verified)
# JSON structured logging matching existing scraper log format (OPS-03 — Phase 3 req, but
# the pattern should be established from the start).

def _log(level: str, message: str, **extra) -> None:
    record = {"level": level, "message": message, **extra}
    getattr(logger, level.lower(), logger.info)(json.dumps(record))
```

---

## State of the Art

| Old Approach | Current Approach | Notes |
|---|---|---|
| Headless browser (Playwright) assumed needed | Direct HTTP + BS4 confirmed sufficient | Innosoft endpoint is server-rendered AJAX partial view — no JS execution needed |
| Single monolithic scraper per project | Separate Lambda per data source | Isolation: Harvard scraper failures cannot break matchi.se production |

---

## Open Questions

1. **`.spots-tag p` index alignment with `#ApptInfo` JSON array**
   - What we know: The HTML response contains both `#ApptInfo` JSON and `.spots-tag` elements. They presumably correspond 1:1 by position.
   - What's unclear: Is the index alignment guaranteed? Does filtering (e.g., past appointments) in the JSON also remove the corresponding `.spots-tag` from the HTML, or could the indices drift?
   - Recommendation: Write a test fixture with the actual HTML response (or a synthetic one) to verify index alignment before shipping. Alternative: parse availability text from the container element that wraps both the ApptInfo entry and the spots-tag, rather than by position index.

2. **`matchi_id: None` impact on get_matchi_id() helper**
   - What we know: `get_matchi_id()` does `return facilities[facility_key]["matchi_id"]` — would return `None` for harvard rather than raising `KeyError`.
   - What's unclear: Are there any call sites that assume `matchi_id` is always an integer?
   - Recommendation: Audit call sites of `get_matchi_id()` before deploying updated `facilities.py`. Only `lambdas/scraper/scraper.py` and `lambdas/scraper/handler.py` call it — guard the matchi handler's iteration loop.

3. **`.spots-tag` availability text format variations**
   - What we know: Project research confirmed `"1 Spot available"` and `"No spots available"` as text patterns.
   - What's unclear: Are there other variants? ("2 Spots available", "Waitlist available", "Full"?)
   - Recommendation: Parse conservatively — any text containing "spot" and NOT containing "no spots" or "waitlist" signals availability. Test with a fixture captured from the live endpoint.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (via `python -m pytest`) |
| Config file | `pyproject.toml` (no pytest section — uses defaults) |
| Quick run command | `python -m pytest tests/test_harvard_scraper.py -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCRP-01 | Lambda fetches endpoint with correct URL, params, and headers | unit (mocked HTTP) | `python -m pytest tests/test_harvard_scraper.py::TestFetchLessonInstances -v` | Wave 0 |
| SCRP-01 | Non-200 response raises exception (not silent empty return) | unit (mocked HTTP) | `python -m pytest tests/test_harvard_scraper.py::TestFetchLessonInstances::test_raises_on_http_error -v` | Wave 0 |
| SCRP-02 | Parser extracts available slots from `#ApptInfo` JSON and `.spots-tag` text | unit (HTML fixture) | `python -m pytest tests/test_harvard_scraper.py::TestParseHarvardAvailability -v` | Wave 0 |
| SCRP-02 | `.spots-tag` "No spots available" overrides positive JSON capacity math | unit (HTML fixture) | `python -m pytest tests/test_harvard_scraper.py::TestParseHarvardAvailability::test_html_text_overrides_json_math -v` | Wave 0 |
| SCRP-02 | Missing `#ApptInfo` input raises ValueError (not silent empty return) | unit (HTML fixture) | `python -m pytest tests/test_harvard_scraper.py::TestParseHarvardAvailability::test_missing_apptinfo_raises -v` | Wave 0 |
| SCRP-02 | Past-dated lessons are filtered out | unit (HTML fixture) | `python -m pytest tests/test_harvard_scraper.py::TestParseHarvardAvailability::test_past_lessons_excluded -v` | Wave 0 |
| SCRP-03 | Snapshot saved to DynamoDB under `harvard#tennis` PK + date SK | unit (mocked boto3) | `python -m pytest tests/test_harvard_scraper.py::TestSnapshotStorage -v` | Wave 0 |
| SCRP-04 | Diff detects unavailable → available transition | unit (calls `build_new_courts_diff`) | Already covered by `tests/test_scraper.py::TestBuildNewCourtsDiff` (diff.py is shared) | Exists |
| SCRP-05 | First run (empty previous snapshot) does NOT invoke notifications Lambda | unit (mocked Lambda client) | `python -m pytest tests/test_harvard_scraper.py::TestColdStart::test_no_notification_on_first_run -v` | Wave 0 |
| SCRP-05 | Second run with a new slot DOES invoke notifications Lambda | unit (mocked Lambda client) | `python -m pytest tests/test_harvard_scraper.py::TestColdStart::test_notification_on_second_run_new_slot -v` | Wave 0 |

### Sampling Rate

- **Per task commit:** `python -m pytest tests/test_harvard_scraper.py -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_harvard_scraper.py` — covers SCRP-01 through SCRP-05 (new file)
- [ ] `tests/fixtures/harvard_available.html` — synthetic HTML fixture with one available lesson
- [ ] `tests/fixtures/harvard_unavailable.html` — synthetic HTML fixture with all "No spots available"
- [ ] `tests/fixtures/harvard_past_dated.html` — fixture with past-dated lesson still showing "1 Spot available"

---

## Sources

### Primary (HIGH confidence)

- Direct code review: `lambdas/scraper/handler.py` — DynamoDB helpers, snapshot loop, Lambda.invoke pattern, structured logging
- Direct code review: `lambdas/scraper/diff.py` — `build_new_courts_diff()`, `has_changes()` cold-start guard, full type signatures
- Direct code review: `lambdas/scraper/scraper.py` — retry pattern (`MAX_RETRIES=3`, exponential backoff), `raise_for_status()` usage
- Direct code review: `facilities.py` — `VALID_FACILITY_IDS` pattern, `matchi_id` access at `handler.py:177`
- `.planning/research/ARCHITECTURE.md` — integration contract, diff payload format, component boundaries (from direct codebase analysis)
- `.planning/research/STACK.md` — library versions, `X-Requested-With` header rationale, `html.parser` vs `lxml` tradeoff
- `.planning/research/PITFALLS.md` — all 10 pitfalls (HIGH confidence items derived from first-party source code)

### Secondary (MEDIUM confidence)

- `.planning/PROJECT.md` — technical discovery: endpoint URL, course GUID, `#ApptInfo` JSON field names, `.spots-tag p` text formats
- `.planning/research/STACK.md` — `X-Requested-With: XMLHttpRequest` for ASP.NET AJAX partial views (standard convention, unverified against live response)
- `.planning/research/STACK.md` — 15-minute EventBridge polling rate (balanced judgment, no official Harvard/Innosoft rate limit docs found)

### Tertiary (LOW confidence — flag for validation)

- Index alignment between `#ApptInfo` JSON array and `.spots-tag` DOM elements — assumed 1:1 positional, needs fixture verification
- `.spots-tag p` text variants beyond "1 Spot available" / "No spots available" — only two variants confirmed in project research

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all libraries already in project; no new dependencies
- Architecture: HIGH — all integration contracts verified from first-party source code
- HTML parsing ground truth rule: HIGH — documented in `.planning/research/PITFALLS.md` based on Innosoft platform behavior
- Pitfalls (cold-start, past-dates, IP blocking): HIGH — derived from existing `diff.py` and `scraper.py` source
- facilities.py `matchi_id` impact: HIGH — verified at `handler.py` line 177
- `.spots-tag` index alignment: LOW — needs fixture-based validation

**Research date:** 2026-04-10
**Valid until:** 2026-05-10 (30 days — stable platform, slow-moving stack)
