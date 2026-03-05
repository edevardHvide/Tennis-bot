import os
import smtplib
import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional, Tuple

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

try:
    from jinja2 import Environment, FileSystemLoader
    JINJA2_AVAILABLE = True
except ImportError:  # pragma: no cover
    JINJA2_AVAILABLE = False


def _is_truthy(value: str | None) -> bool:
    """Check if environment variable value represents a truthy value."""
    if value is None:
        return False
    return value.strip().lower() in ("1", "true", "yes", "on")


def _load_env() -> None:
    """Load environment variables from .env if python-dotenv is available."""
    if load_dotenv is not None:
        try:
            load_dotenv()
        except Exception:
            # Best-effort; ignore issues loading .env
            pass


def _get_court_type(court_name: str) -> str:
    """Determine court type from name for styling."""
    court_lower = court_name.lower()
    if "grusbane" in court_lower or "clay" in court_lower:
        return "clay"
    elif "hardcourt" in court_lower or "hard" in court_lower:
        return "hard"
    else:
        return "standard"


def _get_template_environment() -> Optional[Environment]:
    """Get Jinja2 environment for template rendering."""
    if not JINJA2_AVAILABLE:
        return None
    
    try:
        # Get templates directory relative to this file
        current_dir = Path(__file__).parent
        templates_dir = current_dir / "email_templates"
        
        if not templates_dir.exists():
            return None
            
        return Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=True
        )
    except Exception:
        return None


def _render_template(template_name: str, **context) -> Tuple[str, str]:
    """Render HTML template and create plain text fallback.
    
    Returns:
        Tuple of (html_content, plain_text_content)
    """
    env = _get_template_environment()
    
    if not env:
        # Fallback to plain text if Jinja2 not available
        return _create_fallback_content(**context)
    
    try:
        template = env.get_template(template_name)
        
        # Add common context
        context.update({
            'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
        html_content = template.render(**context)
        
        # Create plain text version by stripping HTML-like content
        plain_text = _html_to_plain_text(html_content, **context)
        
        return html_content, plain_text
        
    except Exception as e:
        print(f"[EMAIL] Template rendering failed: {e}")
        return _create_fallback_content(**context)


def _html_to_plain_text(html_content: str, **context) -> str:
    """Convert HTML email to plain text fallback."""
    # Simple plain text conversion - in production you might use html2text
    lines = []
    
    if 'facilities' in context:
        # New courts notification
        lines.append("🎾 NEW TENNIS COURTS AVAILABLE!")
        lines.append("=" * 40)
        lines.append("")
        
        total_courts = context.get('total_new_courts', 0)
        lines.append(f"Found {total_courts} new court{'s' if total_courts != 1 else ''}")
        lines.append("")
        
        for facility in context['facilities']:
            lines.append(f"🏟️ {facility['name']}")
            lines.append("-" * len(facility['name']))
            
            for date_info in facility['dates']:
                lines.append(f"📅 {date_info['display_name']}")
                
                for time_slot in date_info['time_slots']:
                    courts = ", ".join([court['name'] for court in time_slot['courts']])
                    lines.append(f"  {time_slot['time']}: {courts}")
                
                lines.append(f"  🔗 Book: {date_info.get('web_url', date_info['booking_url'])}")
                lines.append("")
    
    elif context.get('quote'):
        # Test email
        lines.extend([
            "📧 EMAIL TEST SUCCESSFUL!",
            "=" * 25,
            "",
            "✅ Your SMTP configuration is working perfectly!",
            "",
            "The tennis court monitoring system is ready to send notifications.",
            "",
            f"Quote: {context['quote']}",
            "",
            f"Generated at: {context.get('timestamp', 'Unknown')}"
        ])
    
    return "\n".join(lines)


def _create_fallback_content(**context) -> Tuple[str, str]:
    """Create simple fallback content when templates aren't available."""
    if 'facilities' in context:
        # New courts notification
        content_lines = [
            "🎾 NEW TENNIS COURTS AVAILABLE!",
            "",
            f"Found {context.get('total_new_courts', 0)} new courts:",
            ""
        ]
        
        for facility in context['facilities']:
            content_lines.append(f"🏟️ {facility['name']}")
            for date_info in facility['dates']:
                content_lines.append(f"📅 {date_info['display_name']}")
                for time_slot in date_info['time_slots']:
                    courts = ", ".join([court['name'] for court in time_slot['courts']])
                    content_lines.append(f"  {time_slot['time']}: {courts}")
                content_lines.append(f"  🔗 {date_info.get('web_url', date_info['booking_url'])}")
                content_lines.append("")
    
    else:
        # Test email fallback
        content_lines = [
            "📧 EMAIL TEST SUCCESSFUL!",
            "",
            "Your SMTP configuration is working correctly.",
            "",
            f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ]
    
    content = "\n".join(content_lines)
    return content, content  # Same content for both HTML and plain text


def prepare_new_courts_email(
    new_courts_data: Dict[str, Any],
    quote: Optional[str] = None
) -> Tuple[str, str, str]:
    """Prepare new courts notification email.
    
    Args:
        new_courts_data: Dictionary with facility -> date -> time_slot -> courts structure
        quote: Optional quote to include
        
    Returns:
        Tuple of (subject, html_body, plain_text_body)
    """
    # Transform data for template
    facilities = []
    total_new_courts = 0
    today = datetime.date.today()
    
    for facility_key, dates_data in new_courts_data.items():
        try:
            from facilities import facility_display_names
            facility_name = facility_display_names.get(facility_key.lower(), facility_key.capitalize())
        except ImportError:
            facility_name = facility_key.capitalize()
        facility_info = {
            'name': facility_name,
            'dates': []
        }
        
        for date_obj, time_slots in dates_data.items():
            # Skip past dates - only include today and future dates in emails
            if date_obj < today:
                continue
                
            if not time_slots:
                continue
                
            date_display = _format_date_display(date_obj)

            date_info = {
                'display_name': date_display,
                'booking_url': _build_booking_url(facility_key, date_obj),
                'web_url': _build_web_booking_url(facility_key, date_obj),
                'time_slots': []
            }
            
            for time_slot, courts in time_slots.items():
                if not courts:
                    continue

                court_items = []
                for court_name in courts:
                    court_items.append({
                        'name': court_name,
                        'type': _get_court_type(court_name),
                        'is_new': True  # All courts in this context are new
                    })
                    total_new_courts += 1

                date_info['time_slots'].append({
                    'time': time_slot,
                    'url': _build_booking_url(facility_key, date_obj, time_slot),
                    'courts': court_items
                })
            
            if date_info['time_slots']:
                facility_info['dates'].append(date_info)
        
        if facility_info['dates']:
            facilities.append(facility_info)
    
    if not facilities:
        return "No new courts", "", "No new courts available."
    
    # Generate subject
    court_word = "court" if total_new_courts == 1 else "courts"
    facility_word = "facility" if len(facilities) == 1 else "facilities"
    subject = f"🎾 {total_new_courts} new tennis {court_word} available across {len(facilities)} {facility_word}"
    
    # Render template
    context = {
        'facilities': facilities,
        'total_new_courts': total_new_courts,
        'quote': quote
    }
    
    html_body, plain_text_body = _render_template('new_courts.html', **context)
    
    return subject, html_body, plain_text_body


def prepare_test_email(quote: Optional[str] = None) -> Tuple[str, str, str]:
    """Prepare test email.
    
    Returns:
        Tuple of (subject, html_body, plain_text_body)
    """
    subject = "📧 Email Test: Matchi Tennis Bot Configuration"
    
    context = {'quote': quote, 'matchi_url': 'matchi://book/schedule'}
    html_body, plain_text_body = _render_template('test_email.html', **context)
    
    return subject, html_body, plain_text_body


def _format_date_display(date_obj: datetime.date) -> str:
    """Format date for display in emails."""
    today = datetime.date.today()
    if date_obj == today:
        return f"Today ({date_obj.strftime('%Y-%m-%d')})"
    elif date_obj == today + datetime.timedelta(days=1):
        return f"Tomorrow ({date_obj.strftime('%Y-%m-%d')})"
    else:
        return f"{date_obj.strftime('%A, %Y-%m-%d')}"


def _build_booking_url(facility_key: str, date_obj: datetime.date, time_slot: Optional[str] = None) -> str:
    """Build https:// booking URL for facility, date, and optional time slot."""
    try:
        from facilities import facilities
        facility_id = facilities.get(facility_key.lower())
        if not facility_id:
            return "https://www.matchi.se/book/schedule"

        date_str = date_obj.strftime("%Y-%m-%d")
        url = f"https://www.matchi.se/book/schedule?facilityId={facility_id}&date={date_str}&sport=1"
        if time_slot:
            # Extract start time from e.g. "10:00-11:00" or "10:00"
            start_time = time_slot.split("-")[0].strip()
            url += f"&startTime={start_time}"
        return url
    except ImportError:
        return "https://www.matchi.se/book/schedule"


def _build_web_booking_url(facility_key: str, date_obj: datetime.date) -> str:
    """Build https:// web booking URL for facility and date."""
    return _build_booking_url(facility_key, date_obj)


def _send_via_brevo_api(
    subject: str,
    body: str,
    html_body: Optional[str],
    email_from: str,
    recipients: list,
    api_key: str,
) -> bool:
    """Send email via Brevo HTTP API (works when SMTP is blocked by firewall)."""
    try:
        import requests as _requests
    except ImportError:
        print("[EMAIL] requests library not available for Brevo API")
        return False

    # Parse optional display name from "Name<email>" or plain "email" format
    import re as _re
    _m = _re.match(r'^(.+?)\s*<([^>]+)>$', email_from)
    if _m:
        sender = {"name": _m.group(1).strip(), "email": _m.group(2).strip()}
    else:
        sender = {"email": email_from}

    payload = {
        "sender": sender,
        "to": [{"email": addr} for addr in recipients],
        "subject": subject,
        "textContent": body,
    }
    if html_body:
        payload["htmlContent"] = html_body

    try:
        resp = _requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        if resp.status_code in (200, 201):
            print(f"[EMAIL] Sent via Brevo API: {subject}")
            return True
        else:
            print(f"[EMAIL] Brevo API error {resp.status_code}: {resp.text}")
            return False
    except Exception as exc:
        print(f"[EMAIL] Brevo API request failed: {exc}")
        return False


def send_email_notification(
    subject: str,
    body: str,
    html_body: Optional[str] = None
) -> bool:
    """Send an email using Brevo API or SMTP from environment variables.

    Expected environment variables:
      - EMAIL_ENABLED: enable/disable sending (true/false)
      - BREVO_API_KEY: Brevo API key (preferred, works through firewalls)
      - SMTP_HOST, SMTP_PORT, SMTP_SSL (true/false)
      - SMTP_USER, SMTP_PASS
      - EMAIL_FROM, EMAIL_TO (comma-separated)

    Returns True on success, False otherwise.
    """
    _load_env()

    email_enabled = _is_truthy(os.getenv("EMAIL_ENABLED", "false"))
    if not email_enabled:
        print("[EMAIL] Email notifications disabled")
        return False

    email_from = os.getenv("EMAIL_FROM", "").strip()
    email_to = os.getenv("EMAIL_TO", "").strip()

    if not email_from or not email_to:
        print("[EMAIL] Missing EMAIL_FROM or EMAIL_TO")
        return False

    recipients = [addr.strip() for addr in email_to.split(",") if addr.strip()]
    if not recipients:
        print("[EMAIL] No valid recipients found")
        return False

    # Try Brevo HTTP API first (bypasses SMTP firewall blocks)
    brevo_api_key = os.getenv("BREVO_API_KEY", "").strip()
    if brevo_api_key:
        return _send_via_brevo_api(subject, body, html_body, email_from, recipients, brevo_api_key)

    # Fall back to SMTP
    try:
        smtp_host = os.getenv("SMTP_HOST", "").strip()
        smtp_port_text = os.getenv("SMTP_PORT", "587").strip()
        try:
            smtp_port = int(smtp_port_text)
        except ValueError:
            smtp_port = 587
        smtp_ssl = _is_truthy(os.getenv("SMTP_SSL", "false"))
        smtp_user = os.getenv("SMTP_USER", "").strip()
        smtp_pass = os.getenv("SMTP_PASS", "").strip()

        if not all([smtp_host, smtp_user, smtp_pass]):
            print("[EMAIL] Missing SMTP configuration")
            return False

        # Create multipart message
        message = MIMEMultipart("alternative")
        message["From"] = email_from
        message["To"] = ", ".join(recipients)
        message["Subject"] = subject

        text_part = MIMEText(body, "plain", "utf-8")
        message.attach(text_part)

        if html_body:
            html_part = MIMEText(html_body, "html", "utf-8")
            message.attach(html_part)

        if smtp_ssl:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()

        try:
            server.login(smtp_user, smtp_pass)
            server.send_message(message, to_addrs=recipients)
        finally:
            try:
                server.quit()
            except Exception:
                pass

        print(f"[EMAIL] Sent: {subject}")
        return True

    except Exception as exc:
        print(f"[EMAIL] Failed to send: {exc}")
        return False


def send_new_courts_notification(
    new_courts_data: Dict[str, Any],
    quote: Optional[str] = None
) -> bool:
    """Send notification about new courts using beautiful HTML template.
    
    Args:
        new_courts_data: Dictionary with new courts data
        quote: Optional quote to include
        
    Returns:
        True if email sent successfully, False otherwise
    """
    subject, html_body, plain_text_body = prepare_new_courts_email(new_courts_data, quote)
    return send_email_notification(subject, plain_text_body, html_body)


def send_test_email(quote: Optional[str] = None) -> bool:
    """Send a test email to verify SMTP configuration.
    
    Args:
        quote: Optional quote to include
        
    Returns:
        True if email sent successfully, False otherwise
    """
    subject, html_body, plain_text_body = prepare_test_email(quote)
    return send_email_notification(subject, plain_text_body, html_body)


