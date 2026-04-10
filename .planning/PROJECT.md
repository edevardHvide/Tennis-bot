# Harvard Recreation Lesson Monitor

## What This Is

An add-on feature for the Availability Monitor that detects when tennis lessons become available on Harvard Recreation's Innosoft Fusion platform (membership.gocrimson.com). Users can opt into notifications through the existing preferences system, and get alerted when lesson spots open up — just like the existing matchi.se court availability alerts.

## Core Value

Notify users the moment a Harvard Recreation tennis lesson spot becomes available, so they can register before it fills up.

## Requirements

### Validated

- ✓ Existing preferences system supports facility/sport/day/time filtering — existing
- ✓ Existing notification pipeline handles email alerts with dedup — existing
- ✓ Existing scraper architecture uses EventBridge cron + DynamoDB snapshots + diff detection — existing
- ✓ Frontend supports facility selection, sport, and preference management — existing

### Active

- [ ] Scrape Harvard Rec lesson availability via direct HTTP (no headless browser needed)
- [ ] Detect when lessons go from unavailable → available (diff-based)
- [ ] Integrate as a preference option alongside existing matchi.se facilities
- [ ] Send email notifications when spots open up
- [ ] Store availability snapshots in DynamoDB for diff comparison
- [ ] Separate Lambda to avoid breaking production scraper

### Out of Scope

- Multiple Innosoft Fusion programs — scoped to single courseId for now
- Automatic registration/booking — just notification
- Headless browser / Playwright — direct HTTP API works
- Waitlist monitoring — just spot availability
- Harvard authentication integration — read-only public data

## Context

### Technical Discovery (2026-04-10)

The Innosoft Fusion platform at membership.gocrimson.com is NOT a true client-side SPA as originally assumed in issue #107. It uses a **server-side rendered AJAX endpoint**:

```
GET /Program/GetProgramInstances?programID=a20e7ae2-fedc-4a8e-a7c3-236695040c63
```

This returns full HTML containing:
1. **Structured JSON** in a hidden `#ApptInfo` input — dates, times, locations, capacity (`ClassSize`), registrations (`NumberRegistered`), waitlist count
2. **Human-readable text** — `"1 Spot available"` or `"No spots available"` in `.spots-tag p` elements

No authentication needed for reading availability. Plain `requests` + `BeautifulSoup` works — same stack as existing matchi.se scraper.

### Key Details

- **URL:** `https://membership.gocrimson.com/Program/GetProgramInstances?programID=a20e7ae2-fedc-4a8e-a7c3-236695040c63`
- **Platform:** Innosoft Fusion (ASP.NET backend)
- **Course ID:** `a20e7ae2-fedc-4a8e-a7c3-236695040c63`
- **GitHub Issue:** #107
- **Contacts:** Cameron LeBlanc (cleblanc@fas.harvard.edu), Miles Keesy (mkeesy@fas.harvard.edu)

### Availability Data Structure (from #ApptInfo JSON)

Each appointment object contains:
- `StartDate`, `EndDate` — ISO datetime
- `Location` — e.g., "Indoor Tennis Court 6"
- `ClassSize` — max capacity (typically 1 for private lessons)
- `NumberRegistered` — current registrations
- `NumberOnWaitlist` — waitlist count
- Instance IDs for registration links

### Integration Points

- **Preferences API** — add "harvard" as a facility option
- **Notifications Lambda** — reuse matcher + email pipeline
- **Frontend** — add Harvard Rec as a facility in PreferenceForm
- **DynamoDB** — new availability records with `harvard#tennis` composite key
- **facilities.py** — add Harvard config (but this is a different scraping pattern)

## Constraints

- **Separation:** Must be a separate Lambda — do not modify the production matchi.se scraper
- **Same stack:** Use requests + BeautifulSoup (no new heavy deps like Playwright)
- **Respect rate limits:** Harvard portal is a university service; poll conservatively (every 15-30 min)
- **Single program:** Only the one courseId for now; make it easy to add more later but don't over-engineer

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Direct HTTP instead of Playwright | Research proved the API returns server-rendered HTML; no JS execution needed | ✓ Good — eliminates 50MB Chromium dependency |
| Separate Lambda | User decision — protect production matchi scraper from changes | — Pending |
| Single courseId scope | Start small, prove the pattern, expand later | — Pending |
| Reuse existing notification pipeline | Don't reinvent email/dedup; just feed diffs into existing notifications Lambda | — Pending |

---
*Last updated: 2026-04-10 after initialization*
