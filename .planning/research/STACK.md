# Technology Stack: Harvard Recreation Scraper Add-On

**Project:** Harvard Rec Lesson Monitor (Innosoft Fusion)
**Researched:** 2026-04-10
**Scope:** Stack decisions for the new `lambdas/harvard-scraper/` Lambda only. The existing matchi.se stack is unchanged.

---

## Recommended Stack

### HTTP Client

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `requests` (stdlib `urllib` alternative) | >=2.33.1 (current: 2.33.1, released 2026-03-30) | Fetch `GetProgramInstances` endpoint | Already in project. No new dependency. Supports `Session` for cookie persistence and `X-Requested-With` headers. |

**Do NOT add:** `httpx`, `aiohttp`. The Lambda is synchronous and polling a single endpoint. Adding an async HTTP client for one URL introduces unnecessary complexity with zero latency benefit.

### HTML + JSON Parser

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `beautifulsoup4` | >=4.14.3 (current: 4.14.3, released 2025-11-30) | Parse server-rendered HTML response, extract `#ApptInfo` input value | Already in project. The response is a partial HTML view, not a full page — BS4 + `html.parser` handles it cleanly. |
| `json` (stdlib) | built-in | Deserialize the JSON string from `#ApptInfo` `value` attribute | No extra dep. The embedded JSON is in a standard `<input id="ApptInfo" value='[...]'>` — `soup.find('input', {'id': 'ApptInfo'})['value']` then `json.loads()`. |

**Parser choice — use `html.parser`, not `lxml`:**
The existing matchi.se scraper uses `html.parser` and the Innosoft response is a small partial view (not a full document). `lxml` is faster for large documents but adds a C binary to the Lambda package (~2MB compressed), complicates cross-platform builds (macOS dev → Linux Lambda), and the existing code does not use it. Consistency and zero new deps outweigh the marginal parse-time difference on a small payload.

**Do NOT add:** `lxml`, `html5lib`, `selectolax`. Overkill for a small AJAX partial view response. The `#ApptInfo` field lookup is a single `soup.find()` call.

### AWS Infrastructure

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| AWS Lambda (Python 3.11) | — | Run the scraper on a schedule | Matches existing Lambda runtime. Separate function per PROJECT.md constraint. |
| EventBridge Scheduler | — | Trigger every 15–30 minutes | Same pattern as matchi.se scraper. Conservative polling appropriate for a university service. |
| DynamoDB (on-demand) | — | Store snapshots under `harvard#tennis` composite key | Reuses `tennis-availability` table and existing schema. No new table needed. |
| boto3 | >=1.34 (bundled in Lambda runtime) | DynamoDB read/write, invoke Notifications Lambda | Already used everywhere. |

**EventBridge rate:** Use `rate(15 minutes)`. Faster than the matchi.se scraper (which runs every few minutes on a cron) but aggressive enough to catch spot openings promptly. The Harvard portal is a low-traffic university service — polling faster risks IP blocks with no user-facing benefit.

### Shared Modules (reused as-is)

| Module | Location | Usage |
|--------|----------|-------|
| `diff.py` | `lambdas/scraper/diff.py` | Copy (don't import cross-Lambda) into `lambdas/harvard-scraper/`. `build_new_courts_diff()` works on any dict with the same nested shape. |
| `facilities.py` | repo root | Add `"harvard"` entry. Copy into Lambda package at build time as with other Lambdas. |

**Do NOT import from `lambdas/scraper/` at runtime.** Lambda packages are independent ZIP artifacts. Copy `diff.py` into the Harvard scraper package the same way `facilities.py` is copied.

---

## Data Extraction Pattern

The Innosoft Fusion endpoint returns server-rendered HTML with a single embedded JSON blob. The canonical extraction pattern:

```python
import json
import requests
from bs4 import BeautifulSoup

def fetch_lesson_instances(program_id: str) -> list[dict]:
    url = "https://membership.gocrimson.com/Program/GetProgramInstances"
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; AvailabilityMonitor/1.0)",
        "X-Requested-With": "XMLHttpRequest",   # identifies as AJAX to ASP.NET
        "Accept": "text/html, */*",
    })
    resp = session.get(url, params={"programID": program_id}, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    appt_input = soup.find("input", {"id": "ApptInfo"})
    if not appt_input or not appt_input.get("value"):
        return []

    return json.loads(appt_input["value"])
```

**Why `X-Requested-With: XMLHttpRequest`:** The endpoint is an ASP.NET partial view intended to be called by its own frontend JavaScript. Sending this header mimics the legitimate browser call and avoids the server returning an unexpected redirect or full-page response. Confidence: MEDIUM — based on standard ASP.NET AJAX partial view conventions; verify against actual response if the server returns a full page instead of the partial.

**Why `requests.Session()`:** Preserves any `ASP.NET_SessionId` cookie across retries without extra bookkeeping. The Harvard endpoint is read-only and does not require login, but ASP.NET may issue a session cookie on the first request that subsequent requests should echo back. Using a `Session` costs nothing and avoids a class of "second request gets redirected to login" failures that appear with stateless `requests.get()`.

---

## Availability Normalization

Innosoft Fusion does not return time-slot strings in `"HH:MM-HH:MM"` format. You must derive them from the JSON fields. The normalized format must match what `matcher.py` expects:

```python
# Input from #ApptInfo JSON
{
    "StartDate": "2026-04-15T09:00:00",
    "EndDate":   "2026-04-15T10:00:00",
    "Location":  "Indoor Tennis Court 6",
    "ClassSize": 1,
    "NumberRegistered": 0,
}

# Required output (matches existing diff/matcher interface)
time_slot = "09:00-10:00"   # derived from StartDate/EndDate
court_name = "Indoor Tennis Court 6"   # from Location
date_str = "2026-04-15"     # from StartDate
```

Use `datetime.fromisoformat()` (stdlib, Python 3.11) — no `arrow` or `python-dateutil` needed. The ISO datetime strings from Innosoft are well-formed.

**Do NOT add:** `arrow`, `python-dateutil`, `pendulum`. The date parsing here is a single `datetime.fromisoformat()` call. `arrow` is a CLI dependency (it's in the root `requirements.txt`) but was not included in Lambda packages to keep them small.

---

## What NOT to Add

| Rejected library | Reason |
|-----------------|--------|
| `playwright` / `selenium` / `pyppeteer` | PROJECT.md explicitly ruled out. The endpoint returns HTML without JS execution. Would add 50MB+ to Lambda. |
| `scrapy` | Full crawler framework for a single endpoint. Massive overkill. |
| `lxml` | C binary, cross-platform build friction, not used elsewhere, marginal benefit on small payloads. |
| `httpx` | Async HTTP client for a synchronous Lambda polling one URL. Adds complexity with no benefit. |
| `pydantic` | Adds 10MB+ to Lambda package. Dict validation is adequate for this scope. |

---

## Lambda Package Requirements

```
# lambdas/harvard-scraper/requirements.txt
requests
beautifulsoup4
boto3
```

No new packages. All three are already used in the existing scraper. Lambda package size stays small.

---

## Confidence Assessment

| Decision | Confidence | Basis |
|----------|------------|-------|
| `requests` + `beautifulsoup4` sufficient | HIGH | Verified: the endpoint returns static server-rendered HTML (per PROJECT.md technical discovery). No JS execution path. Both libraries already in project. |
| `html.parser` over `lxml` | HIGH | Official BS4 docs confirm `html.parser` is stdlib (no C ext), already used in `lambdas/scraper/scraper.py`. Performance tradeoff is documented. |
| `X-Requested-With` header needed | MEDIUM | Standard ASP.NET AJAX partial view convention. Should be verified by inspecting a live response without the header — the endpoint may work fine without it. |
| `requests.Session()` for cookie handling | MEDIUM | Defensive best practice for ASP.NET endpoints. Harvard portal is public/read-only so session cookie requirement is unconfirmed — but Session has no downside. |
| EventBridge 15-minute rate | MEDIUM | Balanced between responsiveness and respectful polling. No official Harvard/Innosoft rate limit documentation found. Start conservative; reduce to 5 minutes if no blocks observed. |
| `datetime.fromisoformat()` for Innosoft dates | HIGH | Python 3.11 stdlib. ISO datetime format confirmed in PROJECT.md JSON structure. |

---

## Sources

- BeautifulSoup 4.14.3 docs: https://www.crummy.com/software/BeautifulSoup/bs4/doc/
- requests 2.33.1 release: https://requests.readthedocs.io/
- requests PyPI (version history): https://pypi.org/project/requests/
- ASP.NET AJAX partial view scraping patterns: https://toddhayton.com/2015/05/04/scraping-aspnet-pages-with-ajax-pagination/
- BS4 parser performance comparison: https://dev.to/dmitriiweb/beautifulsoup-vs-lxml-a-practical-performance-comparison-1l0a
- Innosoft Fusion platform: http://www.innosoftfusion.com/
