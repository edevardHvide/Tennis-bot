---
name: operations-bot
description: Check GitHub for new issues, plan fix, get Telegram approval from owner, implement, deploy, and celebrate with the requestor
user_invocable: true
---

1. Check GitHub for new issues created in the last hour using `gh issue list`.
2. For each new issue:
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
