# Roadmap: Harvard Recreation Lesson Monitor

## Overview

Build a separate scraper Lambda that polls the Harvard Rec Innosoft Fusion endpoint, diffs availability against DynamoDB snapshots, and feeds new lesson spots into the existing notification pipeline. Then wire Harvard into the preferences system and frontend so users can subscribe, and deploy to production with proper scheduling and ops config.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Scraper** - Fetch, parse, diff, and snapshot Harvard Rec lesson availability in DynamoDB
- [ ] **Phase 2: Integration** - Wire scraper output into notifications pipeline and preferences/frontend
- [ ] **Phase 3: Deploy** - Deploy Lambda with cron schedule, structured logging, and externalized config

## Phase Details

### Phase 1: Scraper
**Goal**: Harvard Rec lesson availability is scraped, parsed, snapshotted, and diffed — new spots are detected reliably
**Depends on**: Nothing (first phase)
**Requirements**: SCRP-01, SCRP-02, SCRP-03, SCRP-04, SCRP-05
**Success Criteria** (what must be TRUE):
  1. Lambda successfully fetches the GetProgramInstances endpoint and returns structured slot data
  2. Slots are stored in DynamoDB under the `harvard#tennis` composite key with date sort keys
  3. A second run after nothing changes produces zero diffs
  4. When a slot transitions from unavailable to available, the diff engine surfaces it
  5. The very first run seeds DynamoDB silently without producing any alerts
**Plans**: 3 plans

Plans:
- [ ] 01-01-PLAN.md — Test scaffolding: HTML fixtures + test stubs (Wave 1)
- [ ] 01-02-PLAN.md — facilities.py harvard entry + matchi scraper guard (Wave 1)
- [ ] 01-03-PLAN.md — lambdas/harvard-scraper/ implementation + tests passing (Wave 2)

### Phase 2: Integration
**Goal**: Detected lesson diffs flow into the existing notification pipeline and users can subscribe via preferences and frontend
**Depends on**: Phase 1
**Requirements**: NOTF-01, NOTF-02, NOTF-03, NOTF-04, PREF-01, PREF-02, PREF-03, PREF-04
**Success Criteria** (what must be TRUE):
  1. When a diff is detected, the existing notifications Lambda receives a payload and sends an email alert
  2. The email shows lesson location, date, time, spot count, and a direct link to the Harvard Rec registration page
  3. The same lesson slot does not trigger a second alert within the dedup TTL window
  4. "Harvard Recreation" appears as a selectable facility in the frontend PreferenceForm
  5. A user preference for `harvard` + `tennis` with day/time filters is matched correctly by the existing matcher.py
**Plans**: 3 plans

Plans:
- [ ] 02-01-PLAN.md — TDD RED: Harvard email/matcher/dedup/preferences tests (Wave 1)
- [ ] 02-02-PLAN.md — Implement email_builder Harvard CTA + frontend FACILITIES entry (Wave 2)
- [ ] 02-03-PLAN.md — Full test suite verification + frontend visual checkpoint (Wave 3)

### Phase 3: Deploy
**Goal**: The Harvard scraper Lambda runs in production on a schedule with proper logging and externalized configuration
**Depends on**: Phase 2
**Requirements**: OPS-01, OPS-02, OPS-03, OPS-04
**Success Criteria** (what must be TRUE):
  1. A dedicated Harvard scraper Lambda is deployed independently from the matchi scraper — both coexist in production
  2. EventBridge triggers the Harvard scraper every 15 minutes automatically
  3. Lambda logs emit structured JSON matching the existing scraper log format (visible in CloudWatch)
  4. The programID can be changed via environment variable without a code deploy
**Plans**: 2 plans

Plans:
- [ ] 03-01-PLAN.md — Makefile targets + create Lambda function + fix scraper.py structured logging (Wave 1)
- [ ] 03-02-PLAN.md — EventBridge cron rule + Lambda permission + live smoke test (Wave 2)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Scraper | 2/3 | In Progress|  |
| 2. Integration | 2/3 | In Progress|  |
| 3. Deploy | 1/2 | In Progress|  |
