#!/usr/bin/env bash
# Re-creates all DynamoDB tables from scratch.
# Safe to run if tables already exist (skips with a warning).
# Usage: bash infra/dynamo/deploy.sh [--profile <aws-profile>]

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

echo "Provisioning DynamoDB tables in $REGION..."

create_table tennis-users \
  --attribute-definitions AttributeName=userId,AttributeType=S \
  --key-schema AttributeName=userId,KeyType=HASH

create_table tennis-preferences \
  --attribute-definitions AttributeName=userId,AttributeType=S AttributeName=preferenceId,AttributeType=S \
  --key-schema AttributeName=userId,KeyType=HASH AttributeName=preferenceId,KeyType=RANGE

create_table tennis-availability \
  --attribute-definitions AttributeName=facilityId,AttributeType=S AttributeName=date,AttributeType=S \
  --key-schema AttributeName=facilityId,KeyType=HASH AttributeName=date,KeyType=RANGE

create_table tennis-notifications \
  --attribute-definitions AttributeName=notificationId,AttributeType=S \
  --key-schema AttributeName=notificationId,KeyType=HASH

create_table tennis-feedback \
  --attribute-definitions AttributeName=feedbackId,AttributeType=S \
  --key-schema AttributeName=feedbackId,KeyType=HASH

# Enable TTL on notifications (idempotent)
aws dynamodb update-time-to-live \
  --table-name tennis-notifications \
  --time-to-live-specification Enabled=true,AttributeName=ttl \
  --profile "$PROFILE" --region "$REGION" &>/dev/null
echo "  [ok]   TTL enabled on tennis-notifications"

echo "Done."
