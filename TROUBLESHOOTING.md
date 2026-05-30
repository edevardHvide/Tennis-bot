# Email Outage Troubleshooting — 2026-03-11

## Symptom
No notification emails being received by users.

## Root Cause
**The scraper Lambda was timing out before it could compute diffs or invoke the notifications Lambda.**

The chain of failures:

1. **Scraper timeout (120s)** — The scraper needs to make ~196 HTTP requests (14 facility+sport pairs x 14 days). With a 0.5s throttle delay + request time, this takes 5-15 minutes. The Lambda timeout was only 120 seconds.

2. **429 rate limiting from matchi.se** — Matchi.se aggressively rate-limits requests. Each 429 triggers exponential backoff retries (4s, 8s), burning through the time budget even faster.

3. **Concurrent invocations compounding the problem** — EventBridge cron fired every 5 minutes, but each run took longer than 5 minutes. Multiple simultaneous scrapers all hit matchi.se, making rate limiting exponentially worse.

4. **No partial results** — When the scraper timed out, it was killed before reaching the diff computation (line 234) or the notifications Lambda invoke (line 251). Zero emails sent.

### Why it looked like emails worked
The notifications Lambda itself was fine. On the rare occasions the scraper completed (light rate-limiting periods), it successfully matched preferences, sent SMTP emails via Gmail, and logged "Emails sent: 1". The email pipeline (SMTP, matching, dedup) had no issues.

## Evidence from CloudWatch Logs

| Log | Finding |
|-----|---------|
| `tennis-scraper` REPORT | `Duration: 120000.00 ms, Status: timeout` — repeated across all runs |
| `tennis-scraper` WARNING | Constant `429 Client Error: Too Many Requests` from matchi.se |
| `tennis-notifications` | "Emails sent: 1" on 2 runs at 08:23 and 08:33 — scraper occasionally completed |
| `tennis-notifications` ERROR | None — email sending itself was healthy |
| SES statistics | Deliveries confirmed, 0 bounces/rejects |

## Fixes Applied

### 1. Increased Lambda timeout: 120s -> 900s (max)
```
aws lambda update-function-configuration --function-name tennis-scraper --timeout 900
```

### 2. Increased request throttle delay: 0.5s -> 1.0s
File: `lambdas/scraper/handler.py` line 68
```python
REQUEST_DELAY = 1.0  # was 0.5
```
Reduces 429 rate-limit hits from matchi.se.

### 3. Reduced EventBridge cron frequency: 5min -> 20min
```
aws events put-rule --name tennis-scraper-schedule --schedule-expression "rate(20 minutes)"
```
Prevents overlapping invocations that compound rate limiting.

### 4. Added time-budget guard to scraper
File: `lambdas/scraper/handler.py`

The scraper now checks `context.get_remaining_time_in_millis()` before each fetch. If less than 30 seconds remain, it stops fetching and proceeds to compute the diff with partial results. This ensures notifications are sent for whatever facilities were scraped, rather than losing everything to a timeout.

### 5. Deployed updated scraper code
Packaged and deployed via `aws lambda update-function-code`.

## Current State (updated 2026-03-11)
- EventBridge rule `tennis-scraper-schedule` is **ENABLED** at `rate(10 minutes)`
- Lambda timeout: **900s**
- Lambda code: **updated** with time-budget guard and 1.0s delay
- Reserved concurrency: not set (account limit prevents it)
- 10-minute interval chosen to avoid overlapping runs (full scrape takes 7-10 min)

## TODO
- [x] Re-enable EventBridge rule
- [ ] Verify a clean run completes and triggers notification emails
- [ ] Monitor for a few cycles to confirm stability
- [x] ~~Consider setting reserved concurrency to 1~~ — not possible (account `UnreservedConcurrentExecution` minimum of 10)

---

# Golf MCP auth-failure storm — 2026-05-21

> **CLOSED 2026-05-30 — MCP path deleted.** GolfBox ordered Vardenlab's MCP
> shut down (2026-05-26); every `tools/call` now returns a disablement string.
> All MCP code was removed (`mcp_client.py`, `mcp_to_slots.py`,
> `scripts/golfbox_mcp_*.py`, `tests/test_golf_mcp.py`, the `GOLF_DATA_SOURCE`
> switch + run-lock + circuit-breaker in `handler.py`, `mcp_slug` in
> `facilities.py`). golf-scraper now scrapes GolfBox directly as its only path.
> The "STILL OPEN" items below are obsolete — kept for incident history only.

## Symptom
First live `golf-scraper` run with `GOLF_DATA_SOURCE=mcp` produced
`slots=0, errors=56, auth_failures=56`. CloudWatch showed one successful
refresh, then a flood of `400 invalid_grant` interleaved with
`429 too_many_requests` from `mcp.vardenlab.com`'s token endpoint.

## Root cause (two compounding issues)
1. **No circuit breaker.** The scraper iterates `facilities × DAYS_AHEAD`
   (4 × 14 = 56). A broken OAuth chain fails identically for every
   combination, so the handler retried all 56 — each a token refresh —
   and Vardenlab rate-limited us (429). One bad token became 56 hammering
   attempts.
2. **Vardenlab rotates AND invalidates refresh tokens on every use.** The
   first refresh succeeded and rotated the token, but `initialize` returned
   no `Mcp-Session-Id` and the subsequent `tools/call` returned 401. The
   client misread that 401 as an auth failure and refreshed again, burning
   the just-rotated token → `invalid_grant` cascade.

## Fixes applied
- **Circuit breaker** (`handler.py`): abort the whole run once
  `auth_failures >= MCP_AUTH_FAILURE_LIMIT` (default 3). One bad token now
  costs a few log lines, not 56. Covered by `TestMcpAuthCircuitBreaker`.
- **Immediate mitigation**: set `GOLF_DATA_SOURCE=scrape` and temporarily
  disabled `golf-scraper-schedule` to stop hammering the token endpoint.

## Current state (2026-05-21, end of session)
- `GOLF_DATA_SOURCE=scrape` — Lambda runs the legacy GolfBox scrape path
  (guest-view prices, the original issue, but functional). Verified manually:
  3024 slots, 0 errors, 44s.
- Circuit-breaker code **deployed**.
- `golf-scraper-schedule` **re-enabled** at `rate(20 minutes)` — golf
  notifications are flowing again on the scrape fallback.
- Secret `golfbox-mcp-tokens` exists but its refresh token was burned by the
  storm (do not assume valid).

## Root cause CONFIRMED — 2026-05-22 (supersedes the aud/IP hypothesis)

The earlier guess (access-token `aud` mismatch / Vardenlab IP-binding) is
**wrong**. CloudWatch for the 2026-05-21 05:56 run proves the MCP path works
fine from Lambda:

- `70039ca4` (invocation A): refresh OK 05:56:57 → `initialize` OK 05:56:59
  (`session_id=None`) → **collected 874 slots across 3 facilities** before any
  failure. 874 successful `tools/call`s from an AWS IP ⇒ token, audience, AND
  IP are all fine. `session_id=None` is also fine — Vardenlab's golfbox MCP is
  stateless.
- `52a1ee1d` (invocation B): started 05:57:55 — **60s after A, concurrently**.
  Refresh OK 05:57:58.
- A's first failure is at 05:57:59 — **1 second after B's refresh**. From then
  A logs `400 invalid_grant` on every re-refresh; B gets `slots=0, errors=56`.

**Actual root cause: a concurrency race on the rotating refresh token.**
Vardenlab rotates the refresh token on every use and applies refresh-token
**reuse detection** (using a rotated-away token revokes the whole token
family, incl. access tokens). Two overlapping invocations share one stored RT:
B rotated RT1→RT2; when A then re-refreshed with its stale in-memory RT1,
Vardenlab revoked the entire family → both invocations' tokens died → the
per-call "401 → re-refresh" retry amplified it into the 429 storm.

Why two concurrent invocations at all: the schedule is `rate(20 minutes)` and a
run takes ~100s, so scheduled runs never overlap. The 05-21 overlap was manual
test invokes (05:56:55 and 05:57:55). In normal scheduled operation MCP would
not have raced — but nothing *prevents* concurrency (manual invoke during a
scheduled run, or any future faster schedule).

## STILL OPEN — do before flipping back to mcp source
- [ ] **Set reserved concurrency = 1 on `golf-scraper`** — the real fix.
      Serializes access to the rotating RT so invocations can't poison each
      other. One-line infra change, no code change. The circuit breaker stays
      as a secondary guardrail.
- [ ] Re-provision the secret (run `scripts/golfbox_mcp_oauth_setup.py`) — the
      RT family was revoked, so the stored token is dead and must be replaced.
      Interactive (browser PKCE), run from a workstation.
- [ ] Flip `GOLF_DATA_SOURCE=mcp` and monitor one run for
      `auth_failures=0, source=mcp` before trusting it.
- Optional hardening: cache the access token (valid ~1h) in the secret so
  warm+cold invocations reuse it and only refresh ~once/hour, cutting RT
  rotations from ~72/day to ~24/day (each rotation is a fragility point).
