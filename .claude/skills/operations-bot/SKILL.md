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
