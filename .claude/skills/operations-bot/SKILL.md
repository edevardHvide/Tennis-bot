---
name: operations-bot
description: Check GitHub for new issues, plan fix, get Slack approval, implement, deploy, and celebrate with the requestor
user_invocable: true
---

1. Check GitHub for new issues created in the last hour using `gh issue list`.
2. For each new issue:
   a. Analyze the issue and create an implementation plan.
   b. Send the plan to Slack **#chat** channel and ask for an OK before proceeding.
   c. Wait for approval in Slack.
   d. Once approved, implement the changes.
   e. Commit and deploy the changes.
   f. Send a celebratory email to the feature requestor (the person who created the issue / submitted feedback) describing what was done, in a very celebratory tone.
