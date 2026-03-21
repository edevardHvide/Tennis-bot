# Slack Integration Setup

## Overview

The Availability Monitor bot posts messages to Slack via the **Slack Web API** using a bot token. There is no MCP server or Slack SDK — just direct `curl` / HTTP calls with the bot token.

## Slack Workspace

- **Workspace:** Availability Monitor (`availabilitymonitor.slack.com`)
- **Bot name:** Availability Monitor Bot

## Bot Token

The bot uses an `xoxb-` token stored in the environment variable `SLACK_BOT_TOKEN`.

To set it up on a new machine, add to your shell profile (e.g. `~/.bashrc`, `~/.zshrc`, or Git Bash `~/.bash_profile`):

```bash
export SLACK_BOT_TOKEN="xoxb-..."
```

Get the token from the Slack App settings: https://api.slack.com/apps → **Availability Monitor Bot** → **OAuth & Permissions** → **Bot User OAuth Token**.

## Bot Scopes (Permissions)

The bot token requires these OAuth scopes:

| Scope | Purpose |
|-------|---------|
| `chat:write` | Send messages to channels |
| `chat:write.public` | Post to channels without joining |
| `chat:write.customize` | Customize bot name/icon per message |
| `channels:history` | Read message history |
| `app_mentions:read` | React to @mentions |
| `assistant:write` | Assistant thread support |
| `im:read` | Read DMs |

**Missing scope:** `channels:join` — the bot cannot self-join channels. You must manually invite it with `/invite @Availability Monitor Bot`.

## Channels

| Channel | Channel ID |
|---------|------------|
| #chat | `C0AL847SWP4` |

## Usage Examples

### Send a message

```bash
curl -s -X POST "https://slack.com/api/chat.postMessage" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-type: application/x-www-form-urlencoded" \
  --data-urlencode "channel=C0AL847SWP4" \
  --data-urlencode "text=Hello from the bot!"
```

### Read channel history

```bash
curl -s -X POST "https://slack.com/api/conversations.history" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-type: application/x-www-form-urlencoded" \
  --data-urlencode "channel=C0AL847SWP4" \
  --data-urlencode "limit=10"
```

### Send a rich message (Block Kit)

```bash
curl -s -X POST "https://slack.com/api/chat.postMessage" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-type: application/json" \
  -d '{
    "channel": "C0AL847SWP4",
    "blocks": [
      {"type": "header", "text": {"type": "plain_text", "text": "New Courts Available"}},
      {"type": "section", "text": {"type": "mrkdwn", "text": "*Frogner* has 3 new slots tomorrow"}}
    ]
  }'
```

## Notes

- The Slack MCP server (`mcp.slack.com` in `.mcp.json`) does **NOT** work with this bot token — it requires Slack's own OAuth MCP flow. Ignore that config.
- Bot token does not expire (unlike browser session `xoxc-` tokens).
- The bot must be invited to a channel before it can read history from it.
