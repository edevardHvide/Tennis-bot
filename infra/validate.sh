#!/usr/bin/env bash
# Infrastructure smoke tests — assert AWS resources exist and are correctly configured.
# Usage: bash infra/validate.sh [--profile <profile>] [--region <region>]

set -euo pipefail

PROFILE="${AWS_PROFILE:-tennis-bot}"
REGION="${AWS_REGION:-eu-north-1}"

while [[ $# -gt 0 ]]; do
  case $1 in
    --profile) PROFILE="$2"; shift 2 ;;
    --region)  REGION="$2";  shift 2 ;;
    *) shift ;;
  esac
done

PASS=0
FAIL=0

check() {
  local desc=$1; shift
  if "$@" &>/dev/null; then
    echo "  [pass] $desc"
    PASS=$((PASS+1))
  else
    echo "  [FAIL] $desc"
    FAIL=$((FAIL+1))
  fi
}

echo ""
echo "Validating infrastructure (profile=$PROFILE, region=$REGION)..."
echo ""

# ── DynamoDB ─────────────────────────────────────────────────────────────────
echo "DynamoDB tables:"
for table in tennis-users tennis-preferences tennis-availability tennis-notifications; do
  check "$table exists" \
    aws dynamodb describe-table --table-name "$table" --profile "$PROFILE" --region "$REGION"
done

# ── Lambda ───────────────────────────────────────────────────────────────────
echo ""
echo "Lambda functions:"
for fn in tennis-scraper tennis-preferences tennis-notifications; do
  check "$fn exists" \
    aws lambda get-function --function-name "$fn" --profile "$PROFILE" --region "$REGION"
done

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASS passed, $FAIL failed"
echo ""
if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
