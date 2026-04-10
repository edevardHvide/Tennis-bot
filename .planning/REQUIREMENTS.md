# Requirements: Harvard Recreation Lesson Monitor

**Defined:** 2026-04-10
**Core Value:** Notify users the moment a Harvard Recreation tennis lesson spot opens up

## v1 Requirements

### Scraping

- [x] **SCRP-01**: Lambda fetches Harvard Rec lesson data via GET /Program/GetProgramInstances endpoint
- [x] **SCRP-02**: Parser extracts structured slot data from #ApptInfo hidden input JSON
- [x] **SCRP-03**: Slots are stored as DynamoDB snapshots with `harvard#tennis` composite key and date sort key
- [x] **SCRP-04**: Diff engine detects newly available slots (unavailable → available transitions)
- [x] **SCRP-05**: First run seeds DynamoDB without triggering spurious "everything is new" alerts

### Notifications

- [ ] **NOTF-01**: Harvard scraper invokes existing notifications Lambda with standard diff payload format
- [ ] **NOTF-02**: Email includes lesson-specific content: location, date, time, spot count
- [ ] **NOTF-03**: Email includes direct link to Harvard Rec program registration page
- [ ] **NOTF-04**: Dedup prevents re-alerting for the same lesson slot within a configurable TTL

### Preferences

- [ ] **PREF-01**: `harvard` added as a facility in facilities.py with display name "Harvard Recreation"
- [ ] **PREF-02**: Frontend FACILITIES list includes Harvard Recreation as a selectable option
- [ ] **PREF-03**: Users can create preferences for Harvard facility + tennis sport with day/time filters
- [ ] **PREF-04**: Existing matcher.py correctly matches `harvard#tennis` composite key against user preferences

### Operations

- [ ] **OPS-01**: Separate Lambda function deployed independently from matchi scraper
- [ ] **OPS-02**: EventBridge cron triggers scraper every 15 minutes
- [ ] **OPS-03**: Structured JSON logging matching existing scraper log format
- [ ] **OPS-04**: programID externalized as environment variable for semester rollover

## v2 Requirements

### Enhanced Monitoring

- **ENH-01**: CloudWatch alarm triggers when scraper returns empty data for N consecutive runs (silent failure detection)
- **ENH-02**: Freshness indicator in notification email ("spot detected 3 min ago — check fast")
- **ENH-03**: Deep link to specific instance registration page (requires URL structure research)

### Multi-Program Support

- **MULTI-01**: Support multiple courseIds / program types on the Innosoft Fusion platform
- **MULTI-02**: Availability history / audit log visible in dashboard

## Out of Scope

| Feature | Reason |
|---------|--------|
| Headless browser / Playwright | Direct HTTP API confirmed working — no need for 50MB Chromium dependency |
| Automatic registration / booking | Just notification — registration requires Harvard auth |
| Waitlist monitoring | Only spot availability; waitlist would need auth |
| Modifying existing matchi scraper | Separate Lambda — zero risk to production |
| Multiple Innosoft Fusion programs | Single courseId for now; designed to be extensible but not over-engineered |
| Instructor information parsing | Not reliably available in the endpoint data |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SCRP-01 | Phase 1 | Complete |
| SCRP-02 | Phase 1 | Complete |
| SCRP-03 | Phase 1 | Complete |
| SCRP-04 | Phase 1 | Complete |
| SCRP-05 | Phase 1 | Complete |
| NOTF-01 | Phase 2 | Pending |
| NOTF-02 | Phase 2 | Pending |
| NOTF-03 | Phase 2 | Pending |
| NOTF-04 | Phase 2 | Pending |
| PREF-01 | Phase 2 | Pending |
| PREF-02 | Phase 2 | Pending |
| PREF-03 | Phase 2 | Pending |
| PREF-04 | Phase 2 | Pending |
| OPS-01 | Phase 3 | Pending |
| OPS-02 | Phase 3 | Pending |
| OPS-03 | Phase 3 | Pending |
| OPS-04 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 17 total
- Mapped to phases: 17
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-10*
*Last updated: 2026-04-10 — traceability updated to 3-phase roadmap (NOTF+PREF → Phase 2, OPS → Phase 3)*
