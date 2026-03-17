"""Reusable CLI for sending ad-hoc branded emails to users."""

import argparse
import smtplib
import sys
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import boto3
from dotenv import dotenv_values

REGION = "eu-north-1"
PROFILE = "tennis-bot"

# %%PLACEHOLDER%% markers used in template to avoid conflicts with CSS braces
TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="color-scheme" content="light">
    <meta name="supported-color-schemes" content="light">
    <title>%%SUBJECT%%</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            font-size: 15px; line-height: 1.6; color: #1e293b;
            background-color: #07101e; width: 100% !important;
            -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%;
        }
        table { border-collapse: collapse; }
        a { color: #0ea5e9; text-decoration: none; }
        a:hover { text-decoration: underline; }

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

        /* Header */
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

        /* Content */
        .content { padding: 36px 44px 40px; background-color: #ffffff !important; color: #1e293b !important; }
        .content p { margin-bottom: 16px; }
        .content h2 { font-size: 18px; font-weight: 700; color: #0f172a; margin-bottom: 12px; margin-top: 24px; }
        .content ul, .content ol { margin: 12px 0 16px 24px; color: #475569; }
        .content li { margin-bottom: 6px; }
        .content-lead { font-size: 15px; color: #475569 !important; margin-bottom: 28px; padding-bottom: 24px; border-bottom: 1px solid #f1f5f9; line-height: 1.7; }
        .content-lead strong { color: #0f172a !important; font-weight: 700; }

        /* Feature cards */
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

        /* CTA */
        .cta-section { text-align: center; margin: 32px 0 8px; }
        .cta-button {
            display: inline-block;
            background: linear-gradient(135deg, #00c96b 0%, #059652 100%) !important;
            color: #ffffff !important; text-decoration: none !important;
            font-size: 15px; font-weight: 700; letter-spacing: 0.03em;
            padding: 14px 36px; border-radius: 10px;
            box-shadow: 0 4px 14px rgba(0,150,82,0.4);
        }

        /* Info / warning boxes */
        .info-box {
            background: linear-gradient(135deg, #f0fdf4, #dcfce7);
            border: 1px solid #86efac; border-radius: 10px;
            padding: 14px 18px; margin: 24px 0; font-size: 13px; color: #166534;
        }
        .warning-box {
            background: linear-gradient(135deg, #fefce8, #fef9c3);
            border: 1px solid #fde68a; border-radius: 10px;
            padding: 14px 18px; margin: 24px 0; font-size: 13px; color: #713f12;
        }

        /* Quote */
        .quote-block {
            border-left: 3px solid #00c96b; padding: 12px 18px; margin: 24px 0;
            background: linear-gradient(90deg, #f0fdf4, #f8fafc); border-radius: 0 8px 8px 0;
        }
        .quote-block p { font-size: 14px; color: #475569; font-style: italic; margin: 0; line-height: 1.7; }

        /* Stats table */
        .stats-table {
            width: 100%; border: 1px solid #e2e8f0; border-radius: 10px;
            overflow: hidden; margin-bottom: 24px;
            box-shadow: 0 1px 4px rgba(15,23,42,0.04);
        }
        .stats-table td {
            padding: 13px 18px; font-size: 14px;
            border-bottom: 1px solid #f1f5f9; color: #334155;
        }
        .stats-table tr:nth-child(even) td { background-color: #fafbfc; }
        .stats-table td:first-child { color: #64748b; width: 55%; }
        .stats-table td:last-child { font-weight: 700; color: #0f172a; text-align: right; }
        .stats-table tr:last-child td { border-bottom: none; }

        /* Section heading */
        .section-heading {
            font-size: 11px; font-weight: 800; letter-spacing: 0.1em;
            text-transform: uppercase; color: #94a3b8;
            margin-bottom: 14px; margin-top: 28px;
        }

        /* Footer */
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
    <div class="header-badge">%%BADGE_TEXT%%</div>
    <h1>%%HEADER_TITLE%%</h1>
    <div class="subtitle">%%HEADER_SUBTITLE%%</div>
</td></tr>

<!-- Body -->
<tr><td class="content" bgcolor="#ffffff" style="background-color:#ffffff !important; padding:36px 44px 40px; color:#1e293b !important;">
%%BODY%%
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


def get_all_users(session):
    """Scan tennis-users DynamoDB table for all users."""
    dynamodb = session.resource("dynamodb")
    table = dynamodb.Table("tennis-users")
    response = table.scan()
    return response.get("Items", [])


def lookup_users(session, emails):
    """Look up specific users from DynamoDB to get their names."""
    dynamodb = session.resource("dynamodb")
    table = dynamodb.Table("tennis-users")
    users = []
    for email in emails:
        try:
            response = table.get_item(Key={"userId": email})
            if "Item" in response:
                users.append(response["Item"])
            else:
                # User not in DB — send anyway with fallback name
                users.append({"userId": email, "name": "there"})
        except Exception:
            users.append({"userId": email, "name": "there"})
    return users


def build_html(body_content, subject, badge_text, header_title, header_subtitle):
    """Insert body content into the branded template shell."""
    html = TEMPLATE
    html = html.replace("%%SUBJECT%%", subject)
    html = html.replace("%%BADGE_TEXT%%", badge_text)
    html = html.replace("%%HEADER_TITLE%%", header_title)
    html = html.replace("%%HEADER_SUBTITLE%%", header_subtitle)
    html = html.replace("%%BODY%%", body_content)
    return html


def send_emails(users, subject, html_template, env_config, dry_run=False):
    """Send personalized email to each user."""
    email_from = env_config["EMAIL_FROM"]
    smtp_host = env_config["SMTP_HOST"]
    smtp_port = int(env_config["SMTP_PORT"])
    smtp_user = env_config["SMTP_USER"]
    smtp_pass = env_config["SMTP_PASS"]

    total = len(users)

    if dry_run:
        print(f"\n--- DRY RUN ---")
        print(f"Subject: {subject}")
        print(f"From: {email_from} via {smtp_host}:{smtp_port}")
        print(f"Recipients ({total}):")
        for user in users:
            name = user.get("name", "there")
            print(f"  - {name} <{user['userId']}>")
        print(f"\nNo emails sent (dry run).")
        return

    # Interactive confirmation
    print(f"\nAbout to send '{subject}' to {total} recipient(s).")
    print(f"From: {email_from} via {smtp_host}:{smtp_port}")
    confirm = input("Type 'send' to confirm: ").strip().lower()
    if confirm != "send":
        print("Aborted.")
        sys.exit(0)

    server = smtplib.SMTP(smtp_host, smtp_port)
    server.starttls()
    server.login(smtp_user, smtp_pass)

    sent = 0
    failed = 0
    for i, user in enumerate(users, 1):
        email = user["userId"]
        name = user.get("name", "there")
        html = html_template.replace("{{NAME}}", name)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = email_from
        msg["To"] = email
        msg.attach(MIMEText(html, "html", "utf-8"))

        print(f"[{i}/{total}] Sending to {name} <{email}>... ", end="", flush=True)
        try:
            server.sendmail(email_from, email, msg.as_string())
            print("OK")
            sent += 1
        except Exception as e:
            print(f"FAILED: {e}")
            failed += 1

        if i < total:
            time.sleep(1.1)

    server.quit()
    print(f"\nDone! Sent: {sent}, Failed: {failed}, Total: {total}")


def main():
    parser = argparse.ArgumentParser(
        description="Send branded ad-hoc emails to Availability Monitor users."
    )
    parser.add_argument("--subject", required=True, help="Email subject line")
    parser.add_argument(
        "--body-file", required=True,
        help="Path to HTML file with inner body content (not full template)"
    )

    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--to", nargs="+", metavar="EMAIL",
        help="Send to specific email address(es)"
    )
    target.add_argument(
        "--all", action="store_true", dest="send_all",
        help="Send to all users in DynamoDB"
    )

    parser.add_argument(
        "--badge-text", default="Announcement",
        help="Badge text in header (default: Announcement)"
    )
    parser.add_argument(
        "--header-title",
        help="Main heading (default: same as subject)"
    )
    parser.add_argument(
        "--header-subtitle", default="Availability Monitor",
        help="Subtitle under heading (default: Availability Monitor)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview recipients without sending"
    )

    args = parser.parse_args()

    # Load SMTP config
    env = dotenv_values(".env")
    for key in ("EMAIL_FROM", "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS"):
        if key not in env:
            print(f"Error: {key} not found in .env file")
            sys.exit(1)

    # Read body content
    try:
        with open(args.body_file, "r", encoding="utf-8") as f:
            body_content = f.read()
    except FileNotFoundError:
        print(f"Error: Body file not found: {args.body_file}")
        sys.exit(1)

    header_title = args.header_title or args.subject

    # Build full HTML
    html = build_html(
        body_content, args.subject, args.badge_text,
        header_title, args.header_subtitle
    )

    # Get recipients
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    if args.send_all:
        users = get_all_users(session)
    else:
        users = lookup_users(session, args.to)

    if not users:
        print("No recipients found.")
        sys.exit(1)

    send_emails(users, args.subject, html, env, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
