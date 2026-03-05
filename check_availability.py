#!/usr/bin/env python3
"""Tennis Court Availability Monitor for Matchi.se facilities."""

import argparse
import datetime
import os
import csv
import random
import subprocess
import time
import platform

import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich import box

from facilities import facilities
from email_notifications import (
    send_email_notification as send_email,
    send_new_courts_notification,
    send_test_email
)

# Initialize rich console
console = Console()


def send_notification(title, message, also_email: bool = False, email_body: str | None = None):
    """Send a visual alert popup (Windows/macOS). Optionally send email.

    If also_email is True and email_body is provided, the email will use email_body;
    otherwise the same message text is used.
    """
    try:
        system = platform.system()

        if system == "Windows":
            # Use Windows toast notifications
            try:
                from win10toast import ToastNotifier

                toaster = ToastNotifier()
                # duration is seconds; threaded avoids blocking
                toaster.show_toast(title, message, duration=5, threaded=True)
                return
            except Exception as e:
                print(f"Failed to send Windows toast: {e}")
                # Fall through to console output

        elif system == "Darwin":
            # Use macOS AppleScript alert (no special permissions)
            script = f"""
            display alert "{title}" message "{message}" giving up after 5
            """
            subprocess.run(["osascript", "-e", script], check=True)
            return

        # For unsupported platforms or if notification fails, just print
        print(f"[ALERT] {title}: {message}")

        # Optionally send email (best-effort)
        if also_email:
            try:
                send_email(subject=title, body=(email_body or message))
            except Exception:
                pass

    except subprocess.CalledProcessError as e:
        print(f"Failed to send alert: {e}")
    except Exception as e:
        print(f"Error sending alert: {e}")


def fetch_available_slots(facility_name, target_date):
    """Fetch available slots for a specific facility and date."""
    facility_id = facilities[facility_name.lower()]
    date_str = target_date.strftime("%Y-%m-%d")
    base_url = "https://www.matchi.se/book/schedule"
    params = {
        "wl": "",
        "facilityId": facility_id,
        "date": date_str,
        "sport": "1",
    }

    # Fetch the content from the URL
    response = requests.get(base_url, params=params)
    response.raise_for_status()  # Raise an exception for HTTP errors

    # Parse the content using BeautifulSoup
    soup = BeautifulSoup(response.text, "html.parser")

    # Search for all 'td' elements with class "slot free"
    available_slots = soup.find_all("td", class_="slot free")

    # Create a dictionary to group courts by time slots
    time_slot_dict = {}

    for slot in available_slots:
        # Split the title to extract court and time information
        parts = slot["title"].split("<br>")
        court = parts[1]
        time = parts[2]

        # Add the court to the corresponding time slot in the dictionary
        if time in time_slot_dict:
            time_slot_dict[time].append(court)
        else:
            time_slot_dict[time] = [court]

    # Return the time slot dictionary (empty if no slots available)
    return time_slot_dict


def get_date_range(days_ahead: int = 2, start_date: datetime.date | None = None):
    """Get a list of dates from start_date to start_date + days_ahead (inclusive).

    If start_date is None, uses today.
    """
    if days_ahead < 0:
        raise ValueError("days_ahead must be >= 0")

    base_date = start_date or datetime.date.today()
    return [base_date + datetime.timedelta(days=i) for i in range(days_ahead + 1)]


def parse_dates_list(dates_csv: str) -> list[datetime.date]:
    """Parse a comma-separated list of YYYY-MM-DD into sorted unique dates."""
    parsed: set[datetime.date] = set()
    for part in dates_csv.split(","):
        text = part.strip()
        if not text:
            continue
        try:
            year, month, day = map(int, text.split("-"))
            parsed.add(datetime.date(year, month, day))
        except Exception as exc:
            raise argparse.ArgumentTypeError(
                f"Invalid date '{text}'. Use YYYY-MM-DD."
            ) from exc
    if not parsed:
        raise argparse.ArgumentTypeError("No valid dates provided")
    return sorted(parsed)


def _parse_hhmm(text: str) -> datetime.time:
    """Parse time strings like '17', '17:00', '08:30' into datetime.time."""
    text = text.strip()
    if not text:
        raise argparse.ArgumentTypeError("Empty time component")
    if ":" in text:
        hour_str, minute_str = text.split(":", 1)
        hour = int(hour_str)
        minute = int(minute_str)
    else:
        hour = int(text)
        minute = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise argparse.ArgumentTypeError("Time must be between 00:00 and 23:59")
    return datetime.time(hour=hour, minute=minute)


def parse_between_time_range(arg: str) -> tuple[datetime.time, datetime.time]:
    """Parse --between ranges like '17-22' or '17:30-22:00'."""
    if not arg:
        raise argparse.ArgumentTypeError("--between requires a value like 17-22")
    raw = arg.replace(" ", "")
    if "-" not in raw:
        raise argparse.ArgumentTypeError(
            "--between must be in the form HH:MM-HH:MM or HH-HH"
        )
    start_str, end_str = raw.split("-", 1)
    start_time = _parse_hhmm(start_str)
    end_time = _parse_hhmm(end_str)
    if end_time <= start_time:
        raise argparse.ArgumentTypeError("End time must be after start time")
    return start_time, end_time


def format_date_header(date):
    """Format date for display headers."""
    if date == datetime.date.today():
        return f"Today ({date.strftime('%Y-%m-%d')})"
    elif date == datetime.date.today() + datetime.timedelta(days=1):
        return f"Tomorrow ({date.strftime('%Y-%m-%d')})"
    else:
        return f"{date.strftime('%A, %Y-%m-%d')}"


def get_court_style(court_name, is_new=False, is_removed=False):
    """Get styling for court based on type and status."""
    # Determine court type and icon
    if "grusbane" in court_name.lower():
        icon = "🟡"
    elif "hardcourt" in court_name.lower():
        icon = "🔵"
    else:
        icon = "⚪"

    # Apply status styling
    if is_new:
        return "bold bright_green", f"🆕{icon}"
    elif is_removed:
        return "strike dim white", f"❌{icon}"
    else:
        return "white", icon


def collect_all_slots(dates: list[datetime.date]):
    """Collect slots for all facilities and dates."""
    all_slots = {}

    console.print("\n🎾 Checking tennis court availability...\n", style="bold blue")

    for facility_name in facilities.keys():
        facility_display_name = facility_name.capitalize()
        all_slots[facility_name] = {}

        for date in dates:
            try:
                slots = fetch_available_slots(facility_name, date)
                all_slots[facility_name][date] = slots
                console.print(
                    f"✓ Checked {facility_display_name} for {format_date_header(date)}",
                    style="green",
                )
            except Exception as e:
                console.print(
                    "✗ Error checking "
                    f"{facility_display_name} for {format_date_header(date)}: {e}",
                    style="red",
                )
                all_slots[facility_name][date] = {}

    return all_slots


def get_slot_changes(current_slots, previous_slots, facility_name, date):
    """Get new and removed courts for a specific facility and date."""
    current = set()
    previous = set()

    current_day_slots = current_slots.get(facility_name, {}).get(date, {})
    previous_day_slots = previous_slots.get(facility_name, {}).get(date, {})

    # Flatten court lists for comparison
    for time_slot, courts in current_day_slots.items():
        for court in courts:
            current.add((time_slot, court))

    for time_slot, courts in previous_day_slots.items():
        for court in courts:
            previous.add((time_slot, court))

    new_courts = current - previous
    removed_courts = previous - current

    return new_courts, removed_courts


def _filter_slots_by_between(
    slots: dict[str, list[str]], between: tuple[datetime.time, datetime.time] | None
) -> dict[str, list[str]]:
    """Filter a single day's time_slot -> courts mapping by a time range.

    A slot is included if its start time is within [between_start, between_end).
    """
    if not between:
        return slots

    start_time, end_time = between
    filtered: dict[str, list[str]] = {}

    for time_slot_label, courts in slots.items():
        label = time_slot_label.replace(" ", "")
        # Accept formats like '17:00-18:00' or '17-18'
        if "-" in label:
            slot_start_str, _slot_end_str = label.split("-", 1)
        else:
            slot_start_str = label
        try:
            slot_start = _parse_hhmm(slot_start_str)
        except argparse.ArgumentTypeError:
            # If we can't parse, keep original behavior: include it
            filtered[time_slot_label] = courts
            continue

        if start_time <= slot_start < end_time:
            filtered[time_slot_label] = courts

    return filtered


def display_slots_table(
    all_slots,
    previous_slots=None,
    dates: list[datetime.date] | None = None,
):
    """Display slots in a beautiful colored tabular format with highlighting."""
    if previous_slots is None:
        previous_slots = {}

    if dates is None:
        dates = get_date_range(2)

    for facility_name, facility_data in all_slots.items():
        facility_display_name = facility_name.capitalize()

        # Create facility header
        console.print(
            f"\n🏟️  {facility_display_name} Tennis Courts", style="bold magenta"
        )
        console.print("=" * 60, style="magenta")

        for date in dates:
            date_header = format_date_header(date)
            slots = facility_data.get(date, {})

            # Get changes for this facility and date (only if we have previous data)
            if previous_slots:
                new_courts, removed_courts = get_slot_changes(
                    all_slots, previous_slots, facility_name, date
                )
            else:
                new_courts, removed_courts = set(), set()

            # Create table for this date
            table = Table(
                title=f"📅 {date_header}",
                box=box.ROUNDED,
                title_style="bold blue",
                show_header=True,
                header_style="bold white",
            )
            table.add_column("Time Slot", style="bold cyan", width=15)
            table.add_column("Available Courts", style="white", min_width=40)

            if not slots:
                table.add_row("", "[dim]No available slots[/dim]")
            else:
                # Add rows for each time slot
                for time_slot in sorted(slots.keys()):
                    courts = slots[time_slot]

                    # Style each court individually
                    styled_courts = []
                    for court in courts:
                        is_new = (time_slot, court) in new_courts
                        is_removed = (time_slot, court) in removed_courts

                        style, icon = get_court_style(court, is_new, is_removed)
                        styled_court = Text(f"{icon} {court}", style=style)
                        styled_courts.append(styled_court)

                    # Combine styled courts
                    if styled_courts:
                        courts_display = Text()
                        for i, styled_court in enumerate(styled_courts):
                            if i > 0:
                                courts_display.append(", ")
                            courts_display.append(styled_court)
                        table.add_row(time_slot, courts_display)

            console.print(table)
            console.print()  # Add spacing between tables


def has_changes(current_slots, previous_slots):
    """Check if there are any changes between current and previous slots."""
    # If previous_slots is empty (first run), don't consider it a change
    if not previous_slots:
        return False
    return current_slots != previous_slots


def get_changes_summary(
    current_slots,
    previous_slots,
    dates: list[datetime.date] | None = None,
):
    """Get a summary of what changed."""
    changes = []
    if dates is None:
        dates = get_date_range(2)

    # Don't generate changes if previous_slots is empty (first run)
    if not previous_slots:
        return changes

    for facility_name in facilities.keys():
        facility_display = facility_name.capitalize()
        for date in dates:
            current = current_slots.get(facility_name, {}).get(date, {})
            previous = previous_slots.get(facility_name, {}).get(date, {})

            if current != previous:
                date_str = format_date_header(date)

                # Count actual new courts
                current_courts = set()
                previous_courts = set()

                for time_slot, courts in current.items():
                    for court in courts:
                        current_courts.add((time_slot, court))

                for time_slot, courts in previous.items():
                    for court in courts:
                        previous_courts.add((time_slot, court))

                new_courts = current_courts - previous_courts
                removed_courts = previous_courts - current_courts

                if new_courts:
                    changes.append(
                        f"New courts available at {facility_display} on {date_str}"
                    )
                if removed_courts:
                    changes.append(f"Courts taken at {facility_display} on {date_str}")

    return changes


def _build_schedule_url(facility_id: int, date_obj: datetime.date) -> str:
    """Build a direct schedule link for a facility and date (tennis)."""
    date_str = date_obj.strftime("%Y-%m-%d")
    return (
        f"https://www.matchi.se/book/schedule?facilityId={facility_id}"
        f"&date={date_str}&sport=1"
    )


def _build_new_courts_email_data(
    current_slots,
    previous_slots,
    dates: list[datetime.date],
) -> dict[str, dict[datetime.date, dict[str, list[str]]]]:
    """Transform slot data into format needed for new email system.
    
    Returns:
        Dict with structure: facility_key -> date -> time_slot -> [court_names]
        Only includes NEW courts that weren't in previous_slots.
        Only includes dates from today onwards (filters out past dates).
    """
    new_courts_data = {}
    today = datetime.date.today()
    
    for facility_key in facilities.keys():
        facility_new_courts = {}
        
        for date_obj in dates:
            # Skip past dates - only include today and future dates in emails
            if date_obj < today:
                continue
                
            new_courts, _removed = get_slot_changes(
                current_slots, previous_slots, facility_key, date_obj
            )
            
            if not new_courts:
                continue
                
            # Group new courts by time slot
            time_to_courts = {}
            for time_slot, court in sorted(new_courts):
                time_to_courts.setdefault(time_slot, []).append(court)
            
            if time_to_courts:
                facility_new_courts[date_obj] = time_to_courts
        
        if facility_new_courts:
            new_courts_data[facility_key] = facility_new_courts
    
    return new_courts_data


def _build_new_slots_email_body(
    current_slots,
    previous_slots,
    dates: list[datetime.date],
) -> str:
    """Create a detailed email body listing new courts by facility/date with links.
    
    Note: This function is kept for backward compatibility but now creates
    a simple plain text version. The new HTML templates are handled by
    the enhanced email_notifications module.
    Only includes dates from today onwards (filters out past dates).
    """
    lines: list[str] = []
    lines.append("New tennis courts are available:\n")
    today = datetime.date.today()

    for facility_key in facilities.keys():
        facility_display = facility_key.capitalize()
        facility_id = facilities[facility_key]

        for date_obj in dates:
            # Skip past dates - only include today and future dates in emails
            if date_obj < today:
                continue
                
            new_courts, _removed = get_slot_changes(
                current_slots, previous_slots, facility_key, date_obj
            )
            if not new_courts:
                continue

            # Group new courts by time slot
            time_to_courts: dict[str, list[str]] = {}
            for time_slot, court in sorted(new_courts):
                time_to_courts.setdefault(time_slot, []).append(court)

            date_str = date_obj.strftime("%Y-%m-%d")
            lines.append(f"{facility_display} — {date_str}")
            for time_slot, courts in time_to_courts.items():
                courts_csv = ", ".join(courts)
                lines.append(f"  - {time_slot}: {courts_csv}")

            link = _build_schedule_url(facility_id, date_obj)
            lines.append(f"  Link: {link}\n")

    # Append a random quote if available
    quote = _get_random_quote()
    if quote:
        lines.append("\nQuote: " + quote)

    return "\n".join(lines).strip()


def _get_random_quote() -> str | None:
    """Pick a random quote from quotes.csv if present."""
    try:
        base_dir = os.path.dirname(__file__)
        path = os.path.join(base_dir, "quotes.csv")
        if not os.path.isfile(path):
            return None
        quotes: list[str] = []
        with open(path, "r", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            for row in reader:
                if not row:
                    continue
                # Support either [index, quote] or [quote]
                text = row[1].strip() if len(row) >= 2 else row[0].strip()
                if text:
                    quotes.append(text)
        if not quotes:
            return None
        return random.choice(quotes)
    except Exception:
        return None

def show_legend(
    dates: list[datetime.date],
    between: tuple[datetime.time, datetime.time] | None = None,
):
    """Display the legend for court types and status indicators."""
    console.print("\n🎾 Tennis Court Availability Monitor", style="bold blue")
    if not dates:
        date_summary = "No dates"
    elif len(dates) <= 5:
        date_summary = ", ".join(d.strftime("%Y-%m-%d") for d in dates)
    else:
        start_str = dates[0].strftime("%Y-%m-%d")
        end_str = dates[-1].strftime("%Y-%m-%d")
        date_summary = f"{start_str} … {end_str} ({len(dates)} dates)"
    console.print(
        f"Monitoring both Frogner and Voldsløkka for: {date_summary}",
        style="blue",
    )
    if between:
        start_hhmm = between[0].strftime("%H:%M")
        end_hhmm = between[1].strftime("%H:%M")
        console.print(
            f"Time filter: {start_hhmm}–{end_hhmm}",
            style="blue",
        )

    legend_table = Table(
        title="Legend",
        box=box.SIMPLE,
        show_header=False,
        title_style="bold yellow",
    )
    legend_table.add_column("Symbol", style="bold")
    legend_table.add_column("Meaning")

    legend_table.add_row("🟡 Grusbane", "[yellow]Clay courts[/yellow]")
    legend_table.add_row("🔵 Hardcourt", "[cyan]Hard courts[/cyan]")
    legend_table.add_row(
        "🆕 New", "[bold bright_green]Newly available[/bold bright_green]"
    )
    legend_table.add_row("❌ Removed", "[strike dim]No longer available[/strike dim]")
    legend_table.add_row(
        "🔔 Alerts", "[blue]Visual popups (auto-close after 5s)[/blue]"
    )

    console.print(legend_table)
    console.print("Press Ctrl+C to stop monitoring\n", style="dim")


def test_notifications():
    """Test the alert system to ensure it's working."""
    console.print("🔔 Testing alert system...\n", style="bold blue")

    console.print(
        "💡 This system uses visual popup alerts instead of notifications.",
        style="blue",
    )
    console.print(
        "Alerts appear as dialogs and automatically disappear after 5 seconds.",
        style="blue",
    )
    console.print("No special permissions required!\n", style="green")

    # Ask for confirmation before proceeding
    console.print(
        "Press Enter to continue with alert test, or Ctrl+C to exit...",
        style="dim",
    )
    try:
        input()
    except KeyboardInterrupt:
        console.print("\n❌ Test cancelled.", style="yellow")
        return

    test_messages = [
        (
            "🎾 Tennis Alert Test",
            "If you see this popup, alerts are working perfectly!",
        ),
        (
            "🏟️ System Check",
            "Tennis court monitor will show popups when courts become available.",
        ),
        ("✅ Test Complete", "Alert system is functioning correctly."),
    ]

    for i, (title, message) in enumerate(test_messages, 1):
        console.print(f"Sending test alert {i}/3...", style="dim")
        send_notification(title, message)

        if i < len(test_messages):
            console.print("Waiting 3 seconds before next test...", style="dim")
            time.sleep(3)

    console.print("\n🔔 Alert test complete!", style="bold green")
    console.print(
        "✅ If you saw 3 popup dialogs: System is working correctly!",
        style="bold green",
    )
    console.print(
        "❌ If you didn't see any popups: Check if Terminal has permission "
        "to control your computer",
        style="yellow",
    )
    console.print(
        "💡 Alerts appear as popup dialogs and disappear automatically after 5 seconds",
        style="dim blue",
    )


def test_email():
    """Send a test email using SMTP configuration from environment variables."""
    console.print("\n📧 Sending test email...", style="bold blue")
    
    # Get a random quote
    quote = _get_random_quote()
    
    try:
        # Try the new enhanced email first
        ok = send_test_email(quote)
        if ok:
            console.print("✅ Test email sent successfully.", style="bold green")
            console.print("📧 Check your inbox for a beautifully formatted HTML email!", style="green")
        else:
            console.print(
                "❌ Test email did not send. Check EMAIL_* and SMTP_* env vars.",
                style="bold red",
            )
    except Exception as exc:
        console.print(f"❌ Error sending enhanced test email: {exc}", style="bold red")
        console.print("🔄 Trying fallback email format...", style="yellow")
        
        # Fallback to simple email
        subject = "📧 Email Test: Matchi Availability Bot"
        body_lines = [
            "If you received this message, your SMTP configuration works.",
            "",
            "This is an automated test message from Matchi Availability Bot.",
        ]
        if quote:
            body_lines.extend(["", f"Quote: {quote}"])
        body = "\n".join(body_lines)
        try:
            ok = send_email(subject=subject, body=body)
            if ok:
                console.print("✅ Fallback test email sent successfully.", style="bold green")
            else:
                console.print(
                    "❌ Test email did not send. Check EMAIL_* and SMTP_* env vars.",
                    style="bold red",
                )
        except Exception as exc2:
            console.print(f"❌ Error sending fallback test email: {exc2}", style="bold red")


def run_monitor(
    dates: list[datetime.date],
    between: tuple[datetime.time, datetime.time] | None = None,
    interval_seconds: int = 300,
):
    """Run the main court availability monitoring loop."""
    # Initialize previous state
    previous_slots = {}

    show_legend(dates, between)

    while True:  # Infinite loop to keep the script running
        try:
            current_slots = collect_all_slots(dates)
            # Apply time filtering (if any)
            if between:
                for facility_name in list(current_slots.keys()):
                    for date in list(current_slots[facility_name].keys()):
                        slots = current_slots[facility_name][date]
                        current_slots[facility_name][date] = _filter_slots_by_between(
                            slots, between
                        )

            # Check for changes (only after first run)
            changes_detected = has_changes(current_slots, previous_slots)
            if changes_detected:
                changes = get_changes_summary(current_slots, previous_slots, dates)

                # Only notify for NEW courts (desktop + email)
                new_changes = [c for c in changes if "New courts available" in c]
                if new_changes:
                    summary = "; ".join(new_changes[:3])
                    if len(new_changes) > 3:
                        summary += f" and {len(new_changes) - 3} more..."

                    # Prepare data for enhanced email notification
                    new_courts_data = _build_new_courts_email_data(
                        current_slots=current_slots,
                        previous_slots=previous_slots,
                        dates=dates,
                    )
                    
                    # Get a random quote
                    quote = _get_random_quote()
                    
                    # Send desktop notification
                    send_notification(
                        title="🎾 New Tennis Courts Available!",
                        message=summary,
                        also_email=False,  # We'll handle email separately with better formatting
                    )
                    
                    # Send enhanced HTML email notification
                    try:
                        if new_courts_data:  # Only send if we have new courts
                            send_new_courts_notification(new_courts_data, quote)
                    except Exception as e:
                        # Fallback to old email system if new one fails
                        print(f"[EMAIL] Enhanced email failed, using fallback: {e}")
                        email_body = _build_new_slots_email_body(
                            current_slots=current_slots,
                            previous_slots=previous_slots,
                            dates=dates,
                        )
                        send_notification(
                            title="🎾 New Tennis Courts Available!",
                            message=summary,
                            also_email=True,
                            email_body=email_body,
                        )

                console.print("\n🔔 Changes detected!", style="bold green")
                if changes:
                    for change in changes:
                        console.print(f"   • {change}", style="green")
            elif previous_slots:  # Only show "no changes" if this isn't the first run
                console.print(
                    "\n✓ No changes detected. Courts status unchanged.",
                    style="dim green",
                )

            # Always display current state (with highlighting if there were changes)
            display_slots_table(
                current_slots,
                previous_slots if changes_detected else {},
                dates,
            )

            # Update previous state
            previous_slots = current_slots.copy()

            # Normalize interval
            if interval_seconds <= 0:
                interval_seconds = 300

            next_check_time = (
                datetime.datetime.now() + datetime.timedelta(seconds=interval_seconds)
            ).strftime("%H:%M:%S")

            if interval_seconds % 60 == 0:
                mins = interval_seconds // 60
                interval_label = f"{mins} minute{'s' if mins != 1 else ''}"
            else:
                interval_label = f"{interval_seconds} seconds"

            console.print(
                f"\n⏰ Next check in {interval_label}... (at {next_check_time})",
                style="dim blue",
            )
            time.sleep(interval_seconds)

        except KeyboardInterrupt:
            console.print(
                "\n\n👋 Monitoring stopped. Have a great game!", style="bold blue"
            )
            break
        except Exception as e:
            console.print(f"\n❌ Error occurred: {e}", style="red")
            console.print("Retrying in 1 minute...", style="yellow")
            time.sleep(60)


def main():
    """Main entry point with command-line argument parsing."""
    parser = argparse.ArgumentParser(
        description="🎾 Tennis Court Availability Monitor for Matchi.se",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                     Start monitoring (default)
  %(prog)s monitor             Start monitoring
  %(prog)s test-notifications  Test alert system
  %(prog)s --help              Show this help message

For more information, visit: https://github.com/your-username/tennis-bot
        """.strip(),
    )

    subparsers = parser.add_subparsers(
        dest="command", help="Available commands", metavar="COMMAND"
    )

    # Monitor command (default)
    monitor_parser = subparsers.add_parser(
        "monitor",
        help="Start monitoring tennis court availability (default)",
        description=(
            "Monitor tennis courts and send notifications when slots become "
            "available"
        ),
    )

    # Test notifications command
    subparsers.add_parser(
        "test-notifications",
        help="Test the alert system",
        description="Send test popup alerts to verify the system is working",
    )

    # Test email command
    subparsers.add_parser(
        "test-email",
        help="Send a test email using SMTP configuration",
        description=(
            "Uses EMAIL_ENABLED/SMTP_* env vars to send a simple test email"
        ),
    )

    # Monitoring options (apply to monitor command)
    monitor_parser.add_argument(
        "--days-ahead",
        type=int,
        default=2,
        help=(
            "Number of days ahead to include (inclusive). 0 means only today. "
            "Default: 2"
        ),
    )
    monitor_parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="Start date (defaults to today). Used with --days-ahead.",
    )
    monitor_parser.add_argument(
        "--dates",
        type=str,
        default=None,
        metavar="YYYY-MM-DD,YYYY-MM-DD",
        help=(
            "Comma-separated specific dates to monitor. Overrides "
            "--start-date/--days-ahead if provided."
        ),
    )
    monitor_parser.add_argument(
        "--between",
        type=str,
        default=None,
        metavar="START-END",
        help=(
            "Only include time slots whose start is within the interval. "
            "Formats: HH-HH or HH:MM-HH:MM (e.g., 17-22 or 17:30-22:00)."
        ),
    )
    monitor_parser.add_argument(
        "--interval-seconds",
        type=int,
        default=300,
        metavar="SECONDS",
        help=(
            "How often to re-check availability in seconds. "
            "Default: 300 (5 minutes)"
        ),
    )

    args = parser.parse_args()

    # Default to monitor if no command specified
    if args.command is None:
        args.command = "monitor"

    # Route to appropriate function
    if args.command == "monitor":
        # Build dates to monitor
        dates: list[datetime.date]
        if getattr(args, "dates", None):
            dates = parse_dates_list(args.dates)
        else:
            start_date = None
            if getattr(args, "start_date", None):
                try:
                    y, m, d = map(int, args.start_date.split("-"))
                    start_date = datetime.date(y, m, d)
                except Exception as exc:
                    raise SystemExit(
                        f"Invalid --start-date '{args.start_date}'. Use YYYY-MM-DD."
                    ) from exc
            days_ahead = getattr(args, "days_ahead", 2)
            dates = get_date_range(days_ahead=days_ahead, start_date=start_date)

        # Build optional time filter
        between = None
        if getattr(args, "between", None):
            try:
                between = parse_between_time_range(args.between)
            except argparse.ArgumentTypeError as exc:
                raise SystemExit(str(exc)) from exc

        interval_seconds = args.interval_seconds
        run_monitor(dates, between, interval_seconds)
    elif args.command == "test-notifications":
        test_notifications()
    elif args.command == "test-email":
        test_email()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
