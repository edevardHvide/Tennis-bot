#!/usr/bin/env bash
# Creates DynamoDB tables for festival ticket monitoring (beta).
# Totally isolated from the tennis tables.
# Usage: bash infra/dynamo/deploy-festival.sh [--profile <aws-profile>]

set -euo pipefail

PROFILE="${AWS_PROFILE:-tennis-bot}"
REGION="${AWS_REGION:-eu-north-1}"

if [[ "$*" == *--profile* ]]; then
  PROFILE=$(echo "$*" | sed 's/.*--profile \([^ ]*\).*/\1/')
fi

create_table() {
  local name=$1
  shift
  if aws dynamodb describe-table --table-name "$name" --profile "$PROFILE" --region "$REGION" &>/dev/null; then
    echo "  [skip] $name already exists"
  else
    aws dynamodb create-table --table-name "$name" --billing-mode PAY_PER_REQUEST \
      --profile "$PROFILE" --region "$REGION" "$@" --query 'TableDescription.TableStatus' --output text
    aws dynamodb wait table-exists --table-name "$name" --profile "$PROFILE" --region "$REGION"
    echo "  [ok]   $name created"
  fi
}

echo "Provisioning festival DynamoDB tables in $REGION..."

# Last known ticket availability per festival
create_table festival-availability \
  --attribute-definitions AttributeName=festivalId,AttributeType=S \
  --key-schema AttributeName=festivalId,KeyType=HASH

# User subscriptions: which users monitor which festivals
create_table festival-subscriptions \
  --attribute-definitions AttributeName=userId,AttributeType=S AttributeName=festivalId,AttributeType=S \
  --key-schema AttributeName=userId,KeyType=HASH AttributeName=festivalId,KeyType=RANGE

echo "Done."
