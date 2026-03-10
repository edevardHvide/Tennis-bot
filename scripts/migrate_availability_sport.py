"""Migrate tennis-availability table: add #tennis suffix to facilityId PK.

For multi-sport support, the availability table's partition key changes from
plain facility names (e.g. "frogner") to composite keys that include the sport
(e.g. "frogner#tennis").

This script scans every item in the table, and for each item whose facilityId
does NOT already contain a '#' separator:
  1. Creates a new item with facilityId = "{original}#tennis" (copies all attrs).
  2. Deletes the original item.

Items that already have '#' in the facilityId are skipped, making the script
safe to run multiple times (idempotent).

Usage:
    python scripts/migrate_availability_sport.py --profile tennis-bot [--dry-run]
    python scripts/migrate_availability_sport.py --profile tennis-bot --region eu-north-1
"""

import argparse
import sys

import boto3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate tennis-availability: add #tennis suffix to facilityId PK."
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
        default="tennis-availability",
        help="DynamoDB table name (default: tennis-availability).",
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
        facility_id = item["facilityId"]
        date_str = item["date"]

        # Already migrated — skip
        if "#" in facility_id:
            skipped += 1
            print(f"  SKIP  {facility_id} / {date_str}  (already has '#')")
            continue

        new_facility_id = f"{facility_id}#tennis"
        print(f"  MIGRATE  {facility_id} / {date_str}  ->  {new_facility_id} / {date_str}")

        if not args.dry_run:
            try:
                # Build new item with updated PK
                new_item = {**item, "facilityId": new_facility_id}
                table.put_item(Item=new_item)

                # Delete old item
                table.delete_item(
                    Key={"facilityId": facility_id, "date": date_str}
                )
            except Exception as exc:
                print(f"  ERROR  Failed to migrate {facility_id}/{date_str}: {exc}")
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
