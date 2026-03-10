"""Migrate tennis-preferences table: convert specific dates to day-of-week names.

Preferences previously stored specific dates like ["2026-03-10", "2026-03-11"].
The new system uses day-of-week names like ["monday", "tuesday"].

This script scans every item in the table, and for each item whose dates list
contains date strings (YYYY-MM-DD format), converts them to day-of-week names
and deduplicates.

Items whose dates already contain day names are skipped, making the script
safe to run multiple times (idempotent).

Usage:
    python scripts/migrate_preferences_days.py --profile tennis-bot [--dry-run]
    python scripts/migrate_preferences_days.py --profile tennis-bot --region eu-north-1
"""

import argparse
import sys
from datetime import datetime

import boto3

VALID_DAY_NAMES = {
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate tennis-preferences: convert specific dates to day-of-week names."
    )
    parser.add_argument(
        "--profile",
        required=True,
        help="AWS CLI profile name to use for credentials.",
    )
    parser.add_argument(
        "--region",
        default="eu-north-1",
        help="AWS region (default: eu-north-1).",
    )
    parser.add_argument(
        "--table",
        default="tennis-preferences",
        help="DynamoDB table name (default: tennis-preferences).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would happen without writing to DynamoDB.",
    )
    return parser.parse_args()


def scan_all_items(table) -> list[dict]:
    """Scan the entire table, handling pagination."""
    items: list[dict] = []
    scan_kwargs: dict = {}

    while True:
        response = table.scan(**scan_kwargs)
        items.extend(response.get("Items", []))

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key

    return items


def _is_date_string(s: str) -> bool:
    """Check if a string looks like a YYYY-MM-DD date."""
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _date_to_day_name(date_str: str) -> str:
    """Convert a YYYY-MM-DD date string to a lowercase day name."""
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%A").lower()


def migrate(args: argparse.Namespace) -> None:
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    dynamodb = session.resource("dynamodb")
    table = dynamodb.Table(args.table)

    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"[{mode}] Scanning table '{args.table}' in {args.region} ...")

    items = scan_all_items(table)
    print(f"  Found {len(items)} total item(s).\n")

    migrated = 0
    skipped = 0
    errors = 0

    for item in items:
        user_id = item["userId"]
        preference_id = item["preferenceId"]
        dates = item.get("dates", [])

        # Check if dates already contain day names (already migrated)
        if dates and all(d.lower() in VALID_DAY_NAMES for d in dates):
            skipped += 1
            print(f"  SKIP  user={user_id}  pref={preference_id}  (already has day names: {dates})")
            continue

        # Check if dates contain specific date strings
        date_strings = [d for d in dates if _is_date_string(d)]
        if not date_strings:
            skipped += 1
            print(f"  SKIP  user={user_id}  pref={preference_id}  (no dates or unrecognized format: {dates})")
            continue

        # Convert to day names and deduplicate
        day_names = sorted(set(_date_to_day_name(d) for d in date_strings))

        print(f"  MIGRATE  user={user_id}  pref={preference_id}")
        print(f"           dates: {dates}")
        print(f"           ->  days: {day_names}")

        if not args.dry_run:
            try:
                table.update_item(
                    Key={"userId": user_id, "preferenceId": preference_id},
                    UpdateExpression="SET dates = :d",
                    ExpressionAttributeValues={":d": day_names},
                )
            except Exception as exc:
                print(f"  ERROR  Failed to update {user_id}/{preference_id}: {exc}")
                errors += 1
                continue

        migrated += 1

    # Summary
    print()
    print("=" * 50)
    print(f"  Mode:     {mode}")
    print(f"  Total:    {len(items)}")
    print(f"  Migrated: {migrated}")
    print(f"  Skipped:  {skipped}")
    if errors:
        print(f"  Errors:   {errors}")
    print("=" * 50)

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    args = parse_args()
    migrate(args)
