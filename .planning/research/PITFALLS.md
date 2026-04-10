# Domain Pitfalls

**Domain:** Institutional portal scraping + diff-based availability monitoring for scarce booking slots
**Project:** Harvard Recreation Lesson Monitor
**Researched:** 2026-04-10

---

## Critical Pitfalls

Mistakes that cause silent failures, spurious alerts, or complete scraper death.

---

### Pitfall 1: Cold-Start Diff Explosion ("Everything Is New" on First Run)

**What goes wrong:** On the very first Lambda invocation there is no previous DynamoDB snapshot for `harvard#tennis`. The diff logic compares current availability against an empty snapshot and treats every available slot as "newly appeared" — firing alerts for every spot whether it genuinely just opened or not.

**Why it happens:** The existing `diff.py` `has_changes()` correctly guards against this for matchi.se by returning `False` when `previous` is empty. But if the Harvard scraper writes the snapshot AND computes the diff in the same invocation before a baseline exists, or if the DynamoDB read returns nothing and the code doesn't check, the guard is bypassed.

**Consequences:** Every user with Harvard preferences gets a flood of alerts the moment the Lambda first runs. This burns user trust and defeats dedup (the first run populates dedup keys, so subsequent runs won't re-notify, but the damage is already done).

**Prevention:**
- Explicitly check for an empty/missing previous snapshot before computing any diff.
- On first invocation: write the snapshot, do NOT invoke notifications Lambda, log "baseline established."
- Mirror the exact `has_changes()` early-return guard already in `diff.py`.

**Detection:** First-run alerts arriving for slots that were available before the feature launched. Log "first run — skipping notifications" to CloudWatch.

**Phase:** Scraper Lambda implementation (Phase 1/core).

---

### Pitfall 2: HTML Text Is Ground Truth, JSON Capacity Math Is Not

**What goes wrong:** `ClassSize - NumberRegistered` appears to give a simple "spots remaining" count. It does not. Innosoft Fusion can show `"1 Spot available"` in `.spots-tag p` while the JSON math computes 0 (e.g. due to waitlisted registrations occupying a slot, admin holds, or pending transactions). The inverse also occurs: math shows 1 available but the text says "No spots available."

**Why it happens:** The rendered HTML text is computed server-side by Fusion's booking logic, which accounts for holds, pending payments, and waitlist precedence that are not exposed in the raw `ClassSize`/`NumberRegistered` fields.

**Consequences:** False-positive alerts (user gets notified, clicks link, sees "No spots available") destroy trust immediately. False-negatives (spot available but no alert sent) defeat the product's entire purpose.

**Prevention:**
- Always parse availability from `.spots-tag p` text as the authoritative signal. Never derive availability from `ClassSize - NumberRegistered` arithmetic.
- The JSON fields are useful for supplementary metadata (location, time, court name) but not for the available/unavailable binary decision.
- Write a test fixture that verifies: if `.spots-tag p` says "No spots available", the scraper must return unavailable regardless of what the JSON numbers say.

**Detection:** Mismatch between "spots available" text and capacity arithmetic in any test fixture; flag in code review.

**Phase:** Scraper HTML parsing (Phase 1/core). Must be locked in before any diff or notification logic is wired up.

---

### Pitfall 3: Scraper Runs from AWS Lambda IP — Gets Rate-Limited or Blocked

**What goes wrong:** AWS Lambda runs from well-known datacenter IP ranges (eu-north-1 in this case). Institutional portals running behind CloudFront/WAF (or even just IIS-level rate limiting) frequently block or 429 datacenter IPs that make repeated identical requests. Harvard's Innosoft Fusion portal has no published SLA for automated access.

**Why it happens:** The default Python `requests` User-Agent (`python-requests/2.x.x`) is on every bot-detection blocklist. AWS datacenter egress IPs are flagged by many WAF rulesets. Sending 2+ identical GET requests per minute from the same IP/UA pair is textbook scraper pattern.

**Consequences:** Silent 403/429 responses that look like "no availability" rather than errors — the scraper happily writes an empty snapshot, diffs show all slots "removed," no alerts fire. This is a false-negative failure mode that's hard to distinguish from genuine zero availability.

**Prevention:**
- Set a browser-like `User-Agent` header (e.g. `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36`).
- Add `Accept`, `Accept-Language`, `Referer` headers that mimic a normal browser session.
- Poll conservatively: 15–30 minute intervals as stated in PROJECT.md constraints. Never poll more frequently than every 10 minutes.
- Detect non-2xx responses explicitly and raise an exception rather than treating them as "empty availability." Log status codes.
- Do NOT silently return `{}` on HTTP errors — surface them as Lambda errors so CloudWatch alarms fire.

**Detection:** Periodic 403/429 status codes in CloudWatch logs. A sudden drop from "N spots sometimes available" to "always zero" across multiple consecutive runs.

**Phase:** Scraper Lambda implementation (Phase 1/core). Add status-code assertion before any HTML parsing.

---

### Pitfall 4: Innosoft Fusion Endpoint Changes Without Notice

**What goes wrong:** The `GET /Program/GetProgramInstances?programID=...` endpoint is an internal AJAX endpoint on a commercial university recreation platform, not a public API. Innosoft pushes silent platform updates. Harvard IT can reconfigure the portal at any time. The endpoint URL, query parameter names, HTML structure of the response, JSON shape inside `#ApptInfo`, and CSS class names (`.spots-tag p`) can all change.

**Why it happens:** No SLA, no docs, no versioning. This is screen-scraping an internal endpoint. The existing matchi.se scraper has the same risk but matchi.se is a dedicated booking product; Innosoft Fusion is a campus ERP that gets enterprise updates.

**Consequences:** Scraper silently returns empty results after a platform update. Users stop receiving notifications. Could go undetected for days if no monitoring is in place.

**Prevention:**
- Assert expected structure in the parser: if `soup.find("input", {"id": "ApptInfo"})` returns `None`, raise an exception — do not return empty results.
- Assert that the parsed JSON array is non-empty at least sometimes (not every run, but a metric over time).
- Write a canary check: periodically verify the endpoint returns an HTTP 200 with the expected HTML structure; alarm on CloudWatch if it fails.
- Keep the HTML parsing logic isolated in a single `parse_harvard_availability(html)` function so structure changes are easy to fix in one place.

**Detection:** Parser returns zero instances across multiple consecutive runs for a program that normally has sessions. CloudWatch alarm on "zero instances parsed" for N consecutive invocations.

**Phase:** Scraper implementation and monitoring setup (Phase 1 + Phase 3/observability).

---

### Pitfall 5: Dedup TTL Mismatch for 1-Spot Lessons

**What goes wrong:** The existing dedup uses a 24-hour TTL keyed on `(userId, facilityId, sport, date, timeSlot, courtName)`. For matchi.se courts this is appropriate — a court available today is unlikely to be a different event tomorrow. For Harvard lessons, the same lesson slot (same date, time, location) can become available again within hours if a registered user cancels. A 24-hour TTL means the user won't be re-notified when the spot re-opens after a cancellation — exactly when notification is most valuable.

**Why it happens:** The dedup key is designed for court slots that stay available for hours. Lesson spots at ClassSize=1 turn over much faster, and re-notification on re-availability is the intended behavior.

**Consequences:** User gets notified once, fails to register, spot gets taken and then released again, user is not re-notified. They miss the cancellation window.

**Prevention:**
- Use a shorter TTL for Harvard lesson notifications — 1–2 hours rather than 24 hours.
- Or: key the dedup differently for Harvard. Include a "window open" timestamp component so that each availability window gets its own dedup key.
- Simplest approach: make TTL configurable per facility type (Harvard vs matchi.se), defaulting to 2 hours for Harvard.

**Detection:** Users report "I saw the spot was available but didn't get a second email after the first one was taken."

**Phase:** Notifications integration (Phase 2). Must be decided before wiring Harvard into the existing notifications Lambda.

---

## Moderate Pitfalls

---

### Pitfall 6: Lambda Timeout on Slow Institutional Portal

**What goes wrong:** Harvard's Innosoft Fusion portal is a campus service. Response times can spike under load (e.g., during peak registration periods, maintenance windows). A Lambda with a short timeout will time out, write nothing to DynamoDB, and produce no diff — silently missing availability windows.

**Prevention:**
- Set Lambda timeout to at least 30 seconds (not the 3-second default).
- Use `requests` timeout parameter of 20–25 seconds.
- Add retry with exponential backoff on timeout (mirror `scraper.py`'s `MAX_RETRIES = 3` pattern already in use).
- Log each attempt and its duration to CloudWatch.

**Phase:** Scraper Lambda configuration (Phase 1/core).

---

### Pitfall 7: DynamoDB Snapshot Schema Drift Between matchi.se and Harvard

**What goes wrong:** The existing `tennis-availability` table uses PK `facility#sport` and stores slot data as `dict[date, dict[time_slot, list[court_name]]]`. Harvard lessons have a different natural structure: each instance is a discrete event with a specific start/end datetime and a location, not a "time slot with N available courts."

**Prevention:**
- Do not force-fit Harvard lesson data into the matchi.se slot structure. Store lesson instances as a list of instance dicts: `[{instanceId, startDate, location, available: bool}]`.
- Use a different DynamoDB item structure under the `harvard#tennis` key rather than shoehorning into the existing court-slot shape.
- Keep the diff logic for Harvard separate from `diff.py` — Harvard availability is a per-instance boolean, not a set of (time_slot, court_name) tuples.

**Detection:** Brittle tests that break when comparing Harvard snapshots against matchi.se test fixtures.

**Phase:** Scraper data model design (Phase 1/design). Decide the snapshot shape before writing any Lambda code.

---

### Pitfall 8: programID GUID Is Not Stable Across Semesters

**What goes wrong:** The courseId `a20e7ae2-fedc-4a8e-a7c3-236695040c63` is the current semester's program GUID. When Harvard Recreation creates a new tennis lesson program for the next term, it will have a different GUID. The scraper will continue polling a stale program that has no upcoming instances — returning "nothing available" indefinitely without error.

**Prevention:**
- Log a warning when the program returns zero future instances for more than 3 consecutive runs.
- Store the programID as a Lambda environment variable (not hardcoded), so updating it for a new semester requires only a config change, not a code deployment.
- Document the semester update process in the project README.

**Detection:** Zero instances parsed over multiple runs after the semester transition date. Compare with the previous semester's end date.

**Phase:** Configuration design (Phase 1/core). Externalize programID before launch.

---

## Minor Pitfalls

---

### Pitfall 9: Email Link Points to Generic Program Page, Not Registration

**What goes wrong:** The notification email links to the program page but when the user clicks, they must still navigate to the specific instance to register. With ClassSize=1 and spots filling in seconds, adding 2–3 extra navigation clicks means the spot is gone by the time they reach the registration button.

**Prevention:**
- Construct deep links to the specific instance registration URL if Innosoft Fusion supports them.
- At minimum, link directly to the program instances page (`/Program/GetProgramInstances?programID=...` or the equivalent member-facing URL) rather than the homepage.

**Phase:** Email template implementation (Phase 2).

---

### Pitfall 10: Notification Fired for Lesson in the Past

**What goes wrong:** The scraper polls all instances returned by the endpoint, including sessions whose `StartDate` has already passed. If a past session still shows "1 Spot available" in the HTML (possible if the booking system hasn't closed it), the diff detects it as "newly available" and fires an alert for a lesson that already happened.

**Prevention:**
- Filter out any instance whose `StartDate` is before `now()` (UTC) when parsing.
- Write a test case: fixture with a past-dated instance must not appear in the diff output.

**Phase:** Scraper parsing (Phase 1/core).

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| First Lambda run / baseline | Cold-start diff explosion (Pitfall 1) | Guard on empty previous snapshot before invoking notifications |
| HTML parsing | Trusting JSON capacity math (Pitfall 2) | Use `.spots-tag p` text exclusively as availability signal |
| HTTP requests from Lambda | IP/UA-based blocking (Pitfall 3) | Browser-like headers + conservative polling + non-silent HTTP error handling |
| Platform updates | Endpoint/HTML structure change (Pitfall 4) | Assert expected structure; alarm on zero-parse runs |
| Notifications wiring | 24h dedup TTL too long for 1-spot lessons (Pitfall 5) | Shorter TTL or configurable TTL per facility type |
| Lambda config | Slow portal timeouts (Pitfall 6) | 30s Lambda timeout, 20s requests timeout, retry logic |
| Data model design | Force-fitting Harvard data into matchi slot shape (Pitfall 7) | Separate snapshot schema for Harvard instances |
| Config / semester rollover | Stale programID GUID (Pitfall 8) | Env var, not hardcoded; zero-instance alarm |
| Email template | Generic link vs deep registration link (Pitfall 9) | Link to instances page at minimum |
| Parsing | Alerting on past-dated lessons (Pitfall 10) | Filter `StartDate < now()` before diffing |

---

## Sources

- Project context: `/Users/edevard/Tennis-bot/.planning/PROJECT.md`
- Existing scraper: `lambdas/scraper/scraper.py`, `diff.py` (cold-start guard, retry pattern)
- Existing dedup: `lambdas/notifications/dedup.py` (24h TTL, SHA-256 key structure)
- ASP.NET scraping pitfalls: https://www.trickster.dev/post/scraping-legacy-asp-net-site-with-scrapy-a-real-example/ (MEDIUM confidence)
- Web scraping 2025 challenges: https://scrapingbee.com/blog/web-scraping-challenges/ (MEDIUM confidence)
- Bot detection & UA blocking: https://scrapfly.io/blog/posts/403-forbidden-web-scraping (MEDIUM confidence)
- Alert fatigue in scraper notifications: https://incident.io/blog/alert-fatigue-solutions-for-dev-ops-teams-in-2025-what-works (MEDIUM confidence)
- Innosoft Fusion release notes: https://www.fusionfamily.com/release/3-7 (no scraping-specific changes found — LOW confidence on platform stability)
- University course scraper patterns: https://github.com/hyperschedule/hyperschedule-scrapers (MEDIUM confidence — real-world institutional scraper showing enrollment tracking)

**Confidence:** HIGH on pitfalls derived from the existing codebase and HTML parsing ground truth (Pitfalls 1, 2, 5, 7, 10). MEDIUM on infrastructure/blocking pitfalls (3, 4, 6). MEDIUM on operational pitfalls (8, 9).
