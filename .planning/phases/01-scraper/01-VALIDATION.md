---
phase: 1
slug: scraper
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-10
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (existing) |
| **Config file** | tests/ directory (existing) |
| **Quick run command** | `python -m pytest tests/test_harvard_scraper.py -v` |
| **Full suite command** | `python -m pytest tests/test_harvard_scraper.py -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_harvard_scraper.py -v`
- **After every plan wave:** Run `python -m pytest tests/test_harvard_scraper.py -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | SCRP-01 | integration | `python -m pytest tests/test_harvard_scraper.py::test_fetch_lesson_instances -v` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | SCRP-02 | unit | `python -m pytest tests/test_harvard_scraper.py::test_parse_appt_info_json -v` | ❌ W0 | ⬜ pending |
| 01-01-03 | 01 | 1 | SCRP-03 | unit | `python -m pytest tests/test_harvard_scraper.py::test_normalize_to_diff_format -v` | ❌ W0 | ⬜ pending |
| 01-01-04 | 01 | 1 | SCRP-04 | unit | `python -m pytest tests/test_harvard_scraper.py::test_diff_detects_new_availability -v` | ❌ W0 | ⬜ pending |
| 01-01-05 | 01 | 1 | SCRP-05 | unit | `python -m pytest tests/test_harvard_scraper.py::test_cold_start_no_alerts -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_harvard_scraper.py` — test stubs for SCRP-01 through SCRP-05
- [ ] `tests/fixtures/harvard_rec_instances.html` — captured HTML fixture from live endpoint
- [ ] `tests/fixtures/harvard_rec_instances_changed.html` — modified fixture with availability change

*Test fixtures must be captured from the live GetProgramInstances endpoint to validate parser against real HTML structure.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live endpoint accessibility from local machine | SCRP-01 | Network-dependent, cannot automate in CI | Run `curl -s "https://membership.gocrimson.com/Program/GetProgramInstances?programID=a20e7ae2-fedc-4a8e-a7c3-236695040c63" | head -20` and verify HTML response |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
