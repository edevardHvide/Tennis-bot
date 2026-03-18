---
name: send-email
description: Compose and send branded ad-hoc emails to Availability Monitor users
user_invocable: true
---

# Send Email Skill

Send branded ad-hoc emails to specific users or all users of Availability Monitor.

## Workflow

### Step 1: Gather Information

Ask the user for:
- **Recipients:** specific email(s), or "all" users
- **Subject line**
- **What the email should say** (content/purpose — you will compose the HTML)

### Step 2: Compose the HTML Body

Write the inner body HTML content to a temp file. Use the branded design system classes available in the email template:

**Text elements:**
- `<p class="content-lead">` — Opening paragraph (use `{{NAME}}` for personalization, e.g. `Hey <strong>{{NAME}}</strong>,`)
- `<h2>` — Section headings
- `<p>`, `<ul>`, `<ol>` — Standard body text and lists

**Feature cards** (colored header + body):
```html
<div class="feature-card">
    <div class="feature-header green">  <!-- variants: green, blue, amber, purple -->
        <span class="feature-icon">&#128640;</span>
        <span class="feature-title">FEATURE TITLE</span>
    </div>
    <div class="feature-body">
        Description text here.
    </div>
</div>
```

**Callout boxes:**
```html
<div class="info-box">
    <strong>&#128161; Note:</strong> Green info callout text.
</div>

<div class="warning-box">
    <strong>&#9888;&#65039; Warning:</strong> Yellow warning callout text.
</div>
```

**Quote block:**
```html
<div class="quote-block">
    <p>&ldquo;Quoted text here.&rdquo;</p>
</div>
```

**CTA button:**
```html
<div class="cta-section">
    <a href="https://availabilitymonitor.club" class="cta-button" style="color:#ffffff !important; text-decoration:none !important;">
        Button Text &rarr;
    </a>
</div>
```

**Stats table:**
```html
<table class="stats-table">
    <tr><td>Label</td><td>Value</td></tr>
    <tr><td>Another label</td><td>Another value</td></tr>
</table>
```

**Section heading (small caps divider):**
```html
<div class="section-heading">SECTION NAME</div>
```

### Step 3: Write to Temp File

Save the composed HTML body to a temporary file:

```bash
# Write the body HTML to a temp file (use Write tool)
# Path: scripts/email_body_tmp.html
```

### Step 4: Dry Run First (MANDATORY)

Always do a dry run first to verify recipients:

```bash
source .venv/Scripts/activate && python scripts/send_email.py \
  --subject "Subject here" \
  --body-file scripts/email_body_tmp.html \
  --to user@example.com \
  --dry-run
```

Or for all users:
```bash
source .venv/Scripts/activate && python scripts/send_email.py \
  --subject "Subject here" \
  --body-file scripts/email_body_tmp.html \
  --all \
  --dry-run
```

Show the user the recipient count and ask for confirmation to proceed.

### Step 5: Send After Explicit Confirmation

Only after the user explicitly confirms, run without `--dry-run`:

```bash
source .venv/Scripts/activate && python scripts/send_email.py \
  --subject "Subject here" \
  --body-file scripts/email_body_tmp.html \
  --to user@example.com
```

The script will prompt for a second confirmation (`Type 'send' to confirm`).

### Step 6: Clean Up and Report

- Delete the temp body file (`scripts/email_body_tmp.html`)
- Report success/failure counts to the user

## CLI Options Reference

```
--subject        Required. Email subject line.
--body-file      Required. Path to HTML file with inner body content.
--to EMAIL ...   Send to specific email(s). Mutually exclusive with --all.
--all            Send to all DynamoDB users. Mutually exclusive with --to.
--badge-text     Badge in header (default: "Announcement"). E.g. "Product Update", "Maintenance".
--header-title   Main heading (default: same as subject).
--header-subtitle Subtitle (default: "Availability Monitor").
--dry-run        Preview recipients, don't send.
```

## Important Notes

- The `{{NAME}}` placeholder is replaced per-recipient with their name from DynamoDB (falls back to "there")
- The body file should contain ONLY the inner content HTML — not `<html>`, `<head>`, or the full template
- Rate limited to 1.1s between sends to respect SMTP limits
- SMTP config is loaded from `.env` file in the repo root
