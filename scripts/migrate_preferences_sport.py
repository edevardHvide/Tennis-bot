"""Migrate tennis-preferences table: add sport attribute to existing items.

For multi-sport support, every preference item needs a 'sport' attribute.
Existing items were created before sports were introduced and default to tennis.

This script scans every item in the table, and for each item that is missing
the 'sport' attribute, updates it to set sport = "tennis".

Items that already have a 'sport' attribute are skipped, making the script
safe to run multiple times (idempotent).

Usage:
    python scripts/migrate_preferences_sport.py --profile tennis-bot [--dry-run]
    python scripts/migrate_preferences_sport.py --profile tennis-bot --region eu-north-1
"""

import argparse
import sys

import boto3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate tennis-preferences: add sport attribute to existing items."
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

        # Already has sport attribute — skip
        if "sport" in item:
            skipped += 1
            print(f"  SKIP  user={user_id}  pref={preference_id}  (already has 'sport': {item['sport']!r})")
            continue

        print(f"  MIGRATE  user={user_id}  pref={preference_id}  -> sport='tennis'")

        if not args.dry_run:
            try:
                table.update_item(
                    Key={"userId": user_id, "preferenceId": preference_id},
                    UpdateExpression="SET sport = :s",
                    ExpressionAttributeValues={":s": "tennis"},
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
