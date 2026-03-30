---
name: operations-bot
description: Check GitHub for new issues, plan fix, get Telegram approval from owner, implement, deploy, and celebrate with the requestor
user_invocable: true
---

1. **Scraper health check** — Verify the scraper has run successfully recently:
   a. Query the `tennis-availability` DynamoDB table (region `eu-north-1`) for a recent item to check its `updatedAt` timestamp:
      ```
      aws dynamodb scan --table-name tennis-availability --region eu-north-1 --max-items 1 --projection-expression "updatedAt" --profile tennis-bot
      ```
   b. If the most recent `updatedAt` is older than 2 hours, the scraper is unhealthy. Create a GitHub issue:
      ```
      gh issue create --title "Bug: Scraper has not run successfully" --body "The scraper's last successful run was at <updatedAt timestamp>. It should run every hour. Please investigate CloudWatch logs for the scraper Lambda." --label bug
      ```
   c. Before creating the issue, check that there isn't already an open issue with the same title to avoid duplicates:
      ```
      gh issue list --search "Bug: Scraper has not run successfully" --state open
      ```
   d. If the scraper is healthy, log it and move on.

2. Check GitHub for new issues created in the last hour using `gh issue list`.
3. For each new issue:
   a. Analyze the issue and create an implementation plan.
   b. Send the plan to the owner via Telegram (chat_id: `8777542698`) using the `mcp__plugin_telegram_telegram__reply` tool and ask for an OK before proceeding.
   c. Wait for the owner's approval in Telegram. The owner will reply in Telegram — look for their response in the conversation.
   d. Once approved, implement the changes.
   e. Commit and deploy the changes.
   f. Send a celebratory email to the feature requestor (the person who created the issue / submitted feedback) describing what was done, in a very celebratory tone.

## Gotchas — Deployment

- **Makefile `pip install` fails silently on macOS.** The Makefile uses `|| true` after `pip install -r requirements.txt -t ./package`, so missing deps won't error. After packaging, always verify that key libraries (requests, bs4, etc.) exist in the `package/` dir before zipping.
- **Don't include boto3 in Lambda packages.** Lambda runtime already has boto3. Including it bloats the zip from ~1MB to 2GB+ and wastes deploy time.
- **Verify Lambda works after deploy.** After deploying, check CloudWatch logs for the next invocation (or invoke manually with `aws lambda invoke`). A successful `update-function-code` does NOT mean the code runs — missing deps will crash at import time.
- **macOS Python ≠ Lambda Python.** Local Python is 3.9 (macOS system), Lambda runs 3.11. Native `.so` files compiled locally (e.g. `cpython-39-darwin.so`) won't work on Lambda's Linux. Pure-Python deps are fine; native extensions need Lambda-compatible builds.
- **Old zip files may not be overwritten.** On macOS, `zip -qr` may append to existing archives rather than replace them. Always `rm` the old zip before creating a new one.
- **`aws lambda invoke` can timeout from CLI side.** The scraper Lambda takes 7-10 min. The default CLI read timeout is 60s. The Lambda still runs — check CloudWatch logs rather than assuming failure.

## Gotchas — Email

- **Use `python3` not `python` on macOS.** There is no `python` binary; use `python3` directly. No venv is needed for the send-email script.
- **Pipe `echo "send"` to auto-confirm.** The send script prompts for confirmation. Pipe `echo "send"` to skip interactive input in non-TTY contexts.

## Gotchas — GitHub CLI

- **`gh issue list` has no `--sort` flag.** Use `-L` (limit) and `--json` fields, then sort in post-processing if needed.
