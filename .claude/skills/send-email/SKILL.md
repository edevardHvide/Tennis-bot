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

Write the inner body HTML content to a temp file. Use the branded design system classes available in the email template.

**CRITICAL — Mobile email compatibility:** Always duplicate key CSS properties as inline `style` attributes on every element. Mobile email clients (Gmail app, iOS Mail dark mode, etc.) strip `<style>` blocks entirely, leaving only inline styles. Without them, text becomes invisible (e.g. white on yellow). Every example below includes the required inline styles — follow them exactly.

**Text elements:**
- `<p class="content-lead">` — Opening paragraph (use `{{NAME}}` for personalization, e.g. `Hey <strong>{{NAME}}</strong>,`)
- `<h2>` — Section headings
- `<p>`, `<ul>`, `<ol>` — Standard body text and lists

**Feature cards** (colored header + body):

IMPORTANT: Always include inline `style` attributes on feature card elements. Mobile email clients strip `<style>` blocks, causing invisible text (e.g. white on yellow). The inline styles are the only reliable way to ensure correct colors on mobile.

Color variants with their inline styles:
- **green**: `background: linear-gradient(90deg, #f0fdf4, #dcfce7);`
- **blue**: `background: linear-gradient(90deg, #eff6ff, #dbeafe);`
- **amber**: `background: linear-gradient(90deg, #fffbeb, #fef3c7);`
- **purple**: `background: linear-gradient(90deg, #faf5ff, #f3e8ff);`

```html
<div class="feature-card" style="border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; margin-bottom: 16px;">
    <div class="feature-header green" style="padding: 14px 20px; border-bottom: 1px solid #e2e8f0; background: linear-gradient(90deg, #f0fdf4, #dcfce7);">
        <span class="feature-icon" style="font-size: 22px;">&#128640;</span>
        <span class="feature-title" style="font-size: 14px; font-weight: 700; color: #0f172a;">FEATURE TITLE</span>
    </div>
    <div class="feature-body" style="padding: 14px 20px; background-color: #ffffff; font-size: 14px; color: #475569; line-height: 1.7;">
        Description text here.
    </div>
</div>
```

**Callout boxes** (always include inline styles for mobile):
```html
<div class="info-box" style="background: linear-gradient(135deg, #f0fdf4, #dcfce7); border: 1px solid #86efac; border-radius: 10px; padding: 14px 18px; margin: 24px 0; font-size: 13px; color: #166534;">
    <strong>&#128161; Note:</strong> Green info callout text.
</div>

<div class="warning-box" style="background: linear-gradient(135deg, #fefce8, #fef9c3); border: 1px solid #fde68a; border-radius: 10px; padding: 14px 18px; margin: 24px 0; font-size: 13px; color: #713f12;">
    <strong>&#9888;&#65039; Warning:</strong> Yellow warning callout text.
</div>
```

**Quote block:**
```html
<div class="quote-block" style="border-left: 3px solid #00c96b; padding: 12px 18px; margin: 24px 0; background: linear-gradient(90deg, #f0fdf4, #f8fafc); border-radius: 0 8px 8px 0;">
    <p style="font-size: 14px; color: #475569; font-style: italic; margin: 0; line-height: 1.7;">&ldquo;Quoted text here.&rdquo;</p>
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

## Gotchas

- **Use `python3` not `python` on macOS.** There is no `python` binary on this machine.
- **No venv needed for send-email.** The script runs fine with system `python3`. Don't waste time looking for `.venv/bin/activate`.
- **Pipe `echo "send"` for non-interactive use.** The script prompts `Type 'send' to confirm:` — pipe it to avoid hanging: `echo "send" | python3 scripts/send_email.py ...`
- **The venv activation path in Step 4/5 examples is Windows-style** (`Scripts/activate`). On macOS use `python3` directly instead.
