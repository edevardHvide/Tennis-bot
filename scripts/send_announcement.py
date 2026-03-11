"""Send ad-hoc product update newsletter to all users."""

import boto3
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import dotenv_values

REGION = "eu-north-1"
PROFILE = "tennis-bot"

# Load SMTP config from .env
_env = dotenv_values(".env")
EMAIL_FROM = _env["EMAIL_FROM"]
SMTP_HOST = _env["SMTP_HOST"]
SMTP_PORT = int(_env["SMTP_PORT"])
SMTP_USER = _env["SMTP_USER"]
SMTP_PASS = _env["SMTP_PASS"]

SUBJECT = "Availability Monitor just got a MASSIVE upgrade"

HTML_BODY = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Availability Monitor — Big Update</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            font-size: 15px; line-height: 1.6; color: #1e293b;
            background-color: #07101e; width: 100% !important;
        }
        a { color: #0ea5e9; text-decoration: none; }
        .email-wrapper {
            width: 100%; background-color: #07101e; padding: 44px 0 52px;
            background-image:
                radial-gradient(ellipse 120% 75% at 50% 45%, rgba(160,50,15,0.22) 0%, transparent 60%),
                url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 800'><rect width='1200' height='800' fill='%2307101e'/><rect x='150' y='100' width='900' height='600' fill='none' stroke='white' stroke-width='2' opacity='.07'/><line x1='262' y1='100' x2='262' y2='700' stroke='white' stroke-width='1.5' opacity='.04'/><line x1='938' y1='100' x2='938' y2='700' stroke='white' stroke-width='1.5' opacity='.04'/><line x1='262' y1='238' x2='938' y2='238' stroke='white' stroke-width='1.5' opacity='.04'/><line x1='262' y1='562' x2='938' y2='562' stroke='white' stroke-width='1.5' opacity='.04'/><line x1='600' y1='238' x2='600' y2='562' stroke='white' stroke-width='1.5' opacity='.04'/><line x1='147' y1='400' x2='1053' y2='400' stroke='white' stroke-width='2.5' opacity='.09'/></svg>");
            background-size: cover; background-position: center;
        }
        .email-container {
            max-width: 600px; margin: 0 auto; background-color: #ffffff !important;
            border-radius: 16px; overflow: hidden;
            box-shadow: 0 12px 48px rgba(5,2,0,0.45), 0 3px 10px rgba(5,2,0,0.2);
            border: 1px solid rgba(210,180,160,0.2);
        }
        .header {
            background-color: #050d1f;
            background-image: linear-gradient(135deg, #050d1f 0%, #0c1e3e 55%, #0a2a1a 100%);
            padding: 40px 44px 36px;
        }
        .header-badge {
            display: inline-block;
            background: linear-gradient(135deg, #00c96b, #10b981);
            color: #ffffff; font-size: 10px; font-weight: 800;
            letter-spacing: 0.12em; text-transform: uppercase;
            padding: 5px 14px; border-radius: 100px; margin-bottom: 18px;
            box-shadow: 0 0 0 1px rgba(0,201,107,0.3), 0 4px 12px rgba(0,201,107,0.25);
        }
        .header h1 { font-size: 28px; font-weight: 800; color: #ffffff; letter-spacing: -0.03em; line-height: 1.2; margin-bottom: 8px; }
        .header .subtitle { font-size: 14px; color: #64c8a0; font-weight: 500; }
        .content { padding: 36px 44px 40px; background-color: #ffffff !important; color: #1e293b !important; }
        .content-lead { font-size: 15px; color: #475569 !important; margin-bottom: 28px; padding-bottom: 24px; border-bottom: 1px solid #f1f5f9; line-height: 1.7; }
        .content-lead strong { color: #0f172a !important; font-weight: 700; }

        .feature-card {
            border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden;
            margin-bottom: 16px; box-shadow: 0 1px 6px rgba(15,23,42,0.05);
        }
        .feature-header {
            padding: 14px 20px; border-bottom: 1px solid #e2e8f0;
            display: flex; align-items: center; gap: 10px;
        }
        .feature-header.green { background: linear-gradient(90deg, #f0fdf4, #dcfce7) !important; }
        .feature-header.blue { background: linear-gradient(90deg, #eff6ff, #dbeafe) !important; }
        .feature-header.amber { background: linear-gradient(90deg, #fffbeb, #fef3c7) !important; }
        .feature-header.purple { background: linear-gradient(90deg, #faf5ff, #f3e8ff) !important; }
        .feature-icon { font-size: 22px; }
        .feature-title { font-size: 14px; font-weight: 700; color: #0f172a !important; }
        .feature-body { padding: 14px 20px; background-color: #ffffff !important; font-size: 14px; color: #475569; line-height: 1.7; }

        .cta-section { text-align: center; margin: 32px 0 8px; }
        .cta-button {
            display: inline-block;
            background: linear-gradient(135deg, #00c96b 0%, #059652 100%) !important;
            color: #ffffff !important; text-decoration: none !important;
            font-size: 15px; font-weight: 700; letter-spacing: 0.03em;
            padding: 14px 36px; border-radius: 10px;
            box-shadow: 0 4px 14px rgba(0,150,82,0.4);
        }

        .info-box {
            background: linear-gradient(135deg, #f0fdf4, #dcfce7);
            border: 1px solid #86efac; border-radius: 10px;
            padding: 14px 18px; margin: 24px 0; font-size: 13px; color: #166534;
        }

        .quote-block {
            border-left: 3px solid #00c96b; padding: 12px 18px; margin: 24px 0;
            background: linear-gradient(90deg, #f0fdf4, #f8fafc); border-radius: 0 8px 8px 0;
        }
        .quote-block p { font-size: 14px; color: #475569; font-style: italic; margin: 0; line-height: 1.7; }

        .footer {
            background: linear-gradient(135deg, #f8fafc, #f1f5f9) !important;
            border-top: 1px solid #e2e8f0; padding: 24px 44px;
            font-size: 12px; color: #94a3b8 !important; line-height: 1.8; text-align: center;
        }
        .footer a { color: #64748b !important; }

        @media only screen and (max-width: 640px) {
            .email-wrapper { padding: 0; }
            .email-container { border-radius: 0; border-left: none; border-right: none; box-shadow: none; }
            .header { padding: 30px 24px 26px; }
            .content { padding: 28px 24px 32px; }
            .footer { padding: 20px 24px; }
        }
    </style>
</head>
<body>
<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
<tr><td class="email-wrapper">
<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" align="center" bgcolor="#ffffff" class="email-container" style="max-width:600px; background-color:#ffffff !important;">

<!-- Header -->
<tr><td class="header">
    <div class="header-badge">Product Update</div>
    <h1>We Just Levelled Up.</h1>
    <div class="subtitle">Availability Monitor &mdash; March 2026</div>
</td></tr>

<!-- Body -->
<tr><td class="content" bgcolor="#ffffff" style="background-color:#ffffff !important; padding:36px 44px 40px; color:#1e293b !important;">

<p class="content-lead">
    Hey <strong>{{NAME}}</strong>,<br><br>
    Remember when this was just a scrappy tennis bot? Those days are <em>over</em>.
    We&rsquo;ve been shipping features at an absurd pace, and today we&rsquo;re thrilled to
    announce the biggest update yet. Buckle up &mdash; this one&rsquo;s a banger.
</p>

<!-- Feature 1: Padel -->
<div class="feature-card">
    <div class="feature-header blue">
        <span class="feature-icon">&#127955;</span>
        <span class="feature-title">PADEL SUPPORT IS HERE</span>
    </div>
    <div class="feature-body">
        The #1 most requested feature is live. Set up padel alerts for OTA (Oslo Tennis Arena) right now.
        Choose between <strong>double</strong> or <strong>single</strong> courts, or just monitor all of them.
        Same instant notifications, same beautiful emails &mdash; now for the fastest-growing sport in Norway.
    </div>
</div>

<!-- Feature 2: Smart Scheduling -->
<div class="feature-card">
    <div class="feature-header green">
        <span class="feature-icon">&#128197;</span>
        <span class="feature-title">SMART DAY-OF-WEEK SCHEDULING</span>
    </div>
    <div class="feature-body">
        No more setting dates manually every week like some kind of caveman.
        Now you pick <strong>recurring days</strong> &mdash; &ldquo;Weekdays&rdquo;, &ldquo;Weekends&rdquo;,
        or any combo of Mon&ndash;Sun. Set it once, forget it forever. We&rsquo;ll keep scanning.
    </div>
</div>

<!-- Feature 3: Multi-facility -->
<div class="feature-card">
    <div class="feature-header amber">
        <span class="feature-icon">&#127963;</span>
        <span class="feature-title">MULTI-FACILITY SELECTION</span>
    </div>
    <div class="feature-body">
        Want to watch Frogner <em>and</em> OTA at the same time?
        Now you can select multiple facilities in a single form.
        One click, multiple preferences created. Efficiency has entered the chat.
    </div>
</div>

<!-- Feature 4: Rebrand -->
<div class="feature-card">
    <div class="feature-header purple">
        <span class="feature-icon">&#10024;</span>
        <span class="feature-title">FRESH NEW LOOK</span>
    </div>
    <div class="feature-body">
        We&rsquo;ve rebranded from &ldquo;Tennis Bot&rdquo; to <strong>Availability Monitor</strong> &mdash;
        because we&rsquo;re not just tennis anymore. New domain, new design,
        gorgeous clay court vibes. Same relentless scanning.
    </div>
</div>

<div class="info-box">
    <strong>&#128640; Under the hood:</strong> Rate-limited scraping to keep matchi.se happy,
    smarter notification matching per sport, independent deduplication for tennis vs padel,
    and sport-specific booking links that take you straight to the right page.
</div>

<div class="quote-block">
    <p>&ldquo;We didn&rsquo;t just add padel. We rebuilt the engine, repainted the car,
    and added a turbocharger. Same mission: never miss an open court.&rdquo;</p>
</div>

<div class="cta-section">
    <a href="https://availabilitymonitor.club" class="cta-button" style="color:#ffffff !important; text-decoration:none !important;">
        Check It Out &rarr;
    </a>
</div>

<p style="font-size: 13px; color: #94a3b8; margin-top: 24px; text-align: center;">
    Head to <a href="https://availabilitymonitor.club">availabilitymonitor.club</a> to update your preferences
    and try out padel alerts. Your existing preferences are safe &mdash; nothing was lost.
</p>

</td></tr>

<!-- Footer -->
<tr><td class="footer" bgcolor="#f1f5f9" style="background-color:#f1f5f9 !important;">
    <p>
        <strong style="color:#475569;">Availability Monitor</strong><br>
        Monitoring courts so you don&rsquo;t have to.<br>
        <a href="https://availabilitymonitor.club">availabilitymonitor.club</a>
    </p>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>
"""


def main():
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    dynamodb = session.resource("dynamodb")

    # Get all users from DynamoDB
    users_table = dynamodb.Table("tennis-users")
    response = users_table.scan()
    users = response.get("Items", [])

    print(f"Found {len(users)} users to email.")
    print(f"Sending from: {EMAIL_FROM} via {SMTP_HOST}:{SMTP_PORT}\n")

    # Connect to SMTP server once
    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
    server.starttls()
    server.login(SMTP_USER, SMTP_PASS)

    sent = 0
    for user in users:
        email = user["userId"]
        name = user.get("name", "there")
        html = HTML_BODY.replace("{{NAME}}", name)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = SUBJECT
        msg["From"] = EMAIL_FROM
        msg["To"] = email
        msg.attach(MIMEText(html, "html", "utf-8"))

        print(f"Sending to {name} <{email}>... ", end="", flush=True)
        try:
            server.sendmail(EMAIL_FROM, email, msg.as_string())
            print("OK")
            sent += 1
        except Exception as e:
            print(f"FAILED: {e}")

        time.sleep(1.1)

    server.quit()
    print(f"\nDone! Sent {sent}/{len(users)} emails.")


if __name__ == "__main__":
    main()
