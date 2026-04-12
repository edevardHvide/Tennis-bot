# Feature Landscape

**Domain:** Spot-availability / lesson-drop notification system (sports)
**Researched:** 2026-04-10
**Context:** Harvard Recreation tennis lesson monitoring add-on for an existing court availability monitor

---

## Existing System — What's Already Built

Understanding what's already in production prevents recommending features that already exist.

| Feature | Status | Implementation |
|---------|--------|----------------|
| Preference creation (facility + sport + day-of-week + time range) | DONE | `lambdas/preferences/handler.py` |
| Diff-based change detection with DynamoDB snapshots | DONE | `lambdas/scraper/` |
| Per-user deduplication with 24h TTL | DONE | `lambdas/notifications/dedup.py` |
| HTML + plain-text email notifications via SES/SMTP | DONE | `lambdas/notifications/email_builder.py` |
| Date blacklist (mute specific dates) | DONE | `preferences/handler.py` `get_blacklist` / `update_blacklist` |
| Availability calendar (7-day view) in dashboard | DONE | `frontend/src/components/AvailabilityCalendar.tsx` |
| Court type filtering (padel single/double) | DONE | `matcher.py` `_court_type_matches` |
| Multiple facilities | DONE | 11 facilities in `facilities.py` |
| Weekly newsletter | DONE | `lambdas/newsletter/` |
| Feature request feedback channel | DONE | `lambdas/feedback/` |

---

## Table Stakes

Features that users of a "spot-opens-up" notification system expect as baseline. Missing any of these makes the product feel incomplete for the Harvard Rec use case.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Instant alert when lesson spot becomes available | The whole point. Seconds matter — private lessons with ClassSize=1 fill immediately. | Med | Scrape frequency is the lever. 15-min polling is the existing pattern; acceptable for lessons. |
| Direct link to the registration page in the email | Without a click-through link, users can't act on the notification. Every ticket-drop service does this. | Low | Harvard Rec URL format is known: `membership.gocrimson.com/program/...`. Include instance ID for deep link. |
| No duplicate alerts for the same lesson slot | Users tolerate one notification but unsubscribe after repeated pings for the same slot. Already solved in core via dedup.py — must extend to harvard source. | Low | Extend existing dedup key scheme with `harvard#tennis` composite. |
| Clear subject line indicating urgency | "Spot available: Harvard Tennis — Wednesday 18:00" outperforms vague subjects. | Low | Email builder already has fun subject prefixes; add lesson-specific variant. |
| Preference opt-in/out for Harvard lessons | Users should choose whether they want Harvard alerts. Forcing them into it causes unsubscribes. | Low | Add `harvard` as a facility option in preferences + facilities.py. |
| Alert only on available→unavailable→available transitions (not steady-state) | If a lesson is available every scrape cycle, users should only hear once. diff-detection handles this but must be verified for Harvard data structure. | Low | Existing diff.py logic must cover the Harvard scraper output correctly. |

---

## Differentiators

Features that raise the product above "just another cron-scraper notification." Not expected by default but meaningfully valuable for the target use case.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Lesson-specific email content (location, instructor context, class details) | Harvard lessons carry location ("Indoor Tennis Court 6") and may have instructor info. Showing "Court 6 — 60 min" in the email body is more actionable than a generic court name. | Low | Extract `Location`, `ClassSize`, `StartDate` from `#ApptInfo` JSON. Already available in the scrape data. |
| Deep link directly to the lesson registration page | Link straight to the instance registration, not just the program listing page. Saves 2-3 clicks at a time when every second counts. | Low-Med | Need to confirm Harvard Rec's instance registration URL structure. If not publicly constructable, fall back to program page. |
| "Lesson still available" freshness indicator in the email | Include the timestamp the spot was detected + the scrape interval so users know how stale the data is. ("Detected 3 minutes ago — check fast.") | Low | Scraper already records `updatedAt`. Pass through to email builder. |
| Configurable alert sensitivity (available only vs. any change) | Advanced users may want alerts when a lesson goes from 0 → 1 spot, others want any change. | High | Over-engineering risk for single-course initial scope. Defer. |
| Availability history / audit log in the dashboard | Show when slots have appeared/disappeared. Helps users tune scrape schedules and understand patterns. | High | Requires schema changes. Out of scope for this milestone. |

---

## Anti-Features

Features to explicitly NOT build. Each has a specific reason grounded in the constraints or risk profile of this project.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Automatic registration / booking | Out of scope per PROJECT.md. Also: automating bookings on a university platform risks account bans and violates ToS. | Notification-only. Let the human click. |
| Waitlist join automation | Same risk as auto-booking. Harvard Rec waitlist requires authentication. | Not applicable; detect real availability instead. |
| Real-time webhook / push notification (sub-minute) | Harvard Rec is a university service — aggressive polling risks IP blocks or rate limiting. Existing 15-30 min conservatively-paced scrape is appropriate. | Keep EventBridge cron at 15-30 min cadence. |
| Multi-program monitoring at launch | PROJECT.md explicitly scopes to one courseId. Generic multi-program support before proving the pattern adds complexity with no validated need. | Hardcode the one program; design for easy extension later via config. |
| SMS / push notifications | Adding a second delivery channel doubles infra complexity (SNS, FCM, etc.) with no clear demand signal. Email works and is already wired. | Email only. Add SMS only if users request it via feedback channel. |
| Headless browser / Playwright scraping | Already ruled out — direct HTTP API proven to work. Playwright adds 50MB Lambda layer, cold starts, and fragility. | requests + BeautifulSoup only. |
| User-managed scrape frequency settings | Letting users tune poll intervals creates coordination complexity and unfairness. One scrape serves all users who opted in. | Single shared scrape frequency; tune centrally via EventBridge cron. |
| Storing all historical lesson instances | Snapshot diff pattern only needs current + previous state. Storing all history wastes DynamoDB capacity and adds no value for notifications. | Keep existing pattern: overwrite current snapshot, compute diff, discard. |

---

## Feature Dependencies

```
Harvard scraper (new Lambda) → DynamoDB snapshot write (harvard#tennis key)
                             → Diff detection (new slots vs last snapshot)
                             → Invoke existing Notifications Lambda with diff payload

Notifications Lambda (existing) → matcher.py (already handles arbitrary composite keys)
                                → dedup.py (extend dedup key to cover harvard#tennis)
                                → email_builder.py (extend to render lesson-style content)

Preferences API (existing) → facilities.py (add harvard entry)
                           → VALID_FACILITY_IDS set (add "harvard")
                           → VALID_SPORTS set (already includes "tennis")

Frontend PreferenceForm → facility selector (add Harvard Rec option)
                       → no other changes needed — day/time preferences reuse existing fields

Deep link in email → Harvard Rec URL structure (needs verification)
                   → Falls back to program page URL if instance URL not constructable
```

---

## MVP Recommendation

The minimal set that delivers real value and validates the Harvard Rec integration:

1. **Harvard scraper Lambda** — scrapes `#ApptInfo` JSON, writes `harvard#tennis` DynamoDB snapshot, diffs, invokes notifications.
2. **Lesson-aware email content** — include Location, time, ClassSize from the scraped data. Use program page as CTA link.
3. **Opt-in via preferences** — add `harvard` to facilities.py + preferences API validation + frontend facility picker.
4. **Dedup coverage** — verify existing 24h dedup key scheme handles `harvard#tennis` correctly (it should, by design).

Defer:
- Deep-link to specific instance registration (URL structure unverified — keep as a follow-up once first scrape confirms URL patterns)
- Lesson history / availability calendar for Harvard source (requires schema design; low priority for MVP)
- Any multi-program expansion (validate single-program first)

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Table stakes | HIGH | Grounded in existing codebase reading + established patterns from restock/ticket-drop notification products |
| Differentiators | MEDIUM | Lesson-specific content and deep links depend on what the Harvard Rec API actually returns (confirmed in PROJECT.md technical discovery) |
| Anti-features | HIGH | Grounded in PROJECT.md explicit out-of-scope decisions + established risk patterns |
| Feature dependencies | HIGH | Traced through actual source files |

---

## Sources

- Existing codebase: `lambdas/notifications/dedup.py`, `matcher.py`, `email_builder.py`, `lambdas/preferences/handler.py`
- `.planning/PROJECT.md` — Harvard Rec technical discovery, explicit out-of-scope list
- [Out-of-Stock Alerts & Restock Notifications: The Complete Guide](https://pagecrawl.io/blog/out-of-stock-monitoring-alerts-guide) — dedup + alert fatigue patterns (MEDIUM confidence)
- [Alert Fatigue](https://upstat.io/blog/alert-fatigue) — frequency + dedup best practices (MEDIUM confidence)
- [Gym Class Capacity & Waitlist Management 2025](https://www.cloudgymmanager.com/gym-class-capacity-management-waitlists-class-limits-and-member-satisfaction/) — fitness lesson notification expectations (LOW confidence — gym software, not exact analog)
- [Best Ticket Alert Tools in 2026](https://www.concertsandtickets.com/blog/ticket-alert-tools-guide/) — "ticket drop" UX patterns (MEDIUM confidence — closer analog to low-inventory, fast-fill scenarios)
