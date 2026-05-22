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
- **Immediate mitigation**: disabled `golf-scraper-schedule` EventBridge rule
  and set `GOLF_DATA_SOURCE=scrape` to stop hammering the endpoint while the
  remaining root cause (the `tools/call` 401 / session handling) is debugged.

## STILL OPEN — do before re-enabling mcp source
- [ ] Diagnose why `tools/call` returns 401 from the Lambda when the PoC on a
      laptop (same code, same `session_id=None`) works. Prime suspects:
      access-token `aud`/resource-audience mismatch, or Vardenlab binding the
      token to the issuing IP. Decode the access-token JWT `aud` claim from a
      fresh OAuth flow (don't burn a refresh just to test).
- [ ] Re-provision the secret (current token likely burned by the storm).
- [ ] Re-enable `golf-scraper-schedule` and flip `GOLF_DATA_SOURCE=mcp` only
      after the 401 is understood and the breaker is deployed.
- NOTE: we are likely still inside a Vardenlab rate-limit window — avoid
  hitting the token endpoint until it clears.
