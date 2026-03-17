#!/usr/bin/env bash
# Deploys the Athena DynamoDB Connector and related resources.
# Enables SQL queries against DynamoDB tables for BI tools like Steep.
#
# Usage: bash infra/athena/deploy.sh [--profile <aws-profile>]
#
# What this creates:
#   1. S3 bucket for Athena query results + connector spill
#   2. Athena DynamoDB Connector Lambda (from AWS Serverless App Repository)
#   3. Athena data catalog ("dynamodb") backed by the connector
#   4. Athena workgroup ("tennis-bot") for organized query execution

set -euo pipefail

PROFILE="${AWS_PROFILE:-tennis-bot}"
REGION="${AWS_REGION:-eu-north-1}"
ACCOUNT="605893375372"

ATHENA_BUCKET="tennis-bot-athena-${ACCOUNT}"
SPILL_PREFIX="athena-spill"
RESULTS_PREFIX="athena-results"
CONNECTOR_FN="tennis-athena-dynamodb"
CATALOG_NAME="dynamodb"
WORKGROUP_NAME="tennis-bot"
SAR_APP_ID="arn:aws:serverlessrepo:us-east-1:292517598671:applications/AthenaDynamoDBConnector"
STACK_NAME="tennis-athena-dynamodb-connector"

if [[ "$*" == *--profile* ]]; then
  PROFILE=$(echo "$*" | sed 's/.*--profile \([^ ]*\).*/\1/')
fi

echo "Deploying Athena DynamoDB Connector in ${REGION} (profile: ${PROFILE})"
echo ""

# ── Step 1: S3 bucket ────────────────────────────────────────────────────────

echo "1/4  S3 bucket for query results & spill..."
if aws s3api head-bucket --bucket "${ATHENA_BUCKET}" --profile "${PROFILE}" --region "${REGION}" 2>/dev/null; then
  echo "     [skip] s3://${ATHENA_BUCKET} already exists"
else
  aws s3api create-bucket \
    --bucket "${ATHENA_BUCKET}" \
    --create-bucket-configuration LocationConstraint="${REGION}" \
    --profile "${PROFILE}" --region "${REGION}" \
    --query 'Location' --output text
  echo "     [ok]   s3://${ATHENA_BUCKET} created"
fi

# Block public access
aws s3api put-public-access-block \
  --bucket "${ATHENA_BUCKET}" \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true \
  --profile "${PROFILE}" --region "${REGION}" 2>/dev/null
echo "     [ok]   public access blocked"

# ── Step 2: Deploy connector Lambda via SAR ──────────────────────────────────

echo ""
echo "2/4  Athena DynamoDB Connector Lambda..."

# Check if the CloudFormation stack already exists
STACK_STATUS=$(aws cloudformation describe-stacks \
  --stack-name "${STACK_NAME}" \
  --profile "${PROFILE}" --region "${REGION}" \
  --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "DOES_NOT_EXIST")

if [[ "${STACK_STATUS}" == "CREATE_COMPLETE" || "${STACK_STATUS}" == "UPDATE_COMPLETE" ]]; then
  echo "     [skip] CloudFormation stack ${STACK_NAME} already deployed (${STACK_STATUS})"
else
  echo "     Creating CloudFormation change set from SAR..."

  CHANGE_SET_ID=$(aws serverlessrepo create-cloud-formation-change-set \
    --application-id "${SAR_APP_ID}" \
    --stack-name "${STACK_NAME}" \
    --capabilities CAPABILITY_IAM CAPABILITY_RESOURCE_POLICY \
    --parameter-overrides \
      Name=AthenaCatalogName,Value="${CONNECTOR_FN}" \
      Name=SpillBucket,Value="${ATHENA_BUCKET}" \
      Name=SpillPrefix,Value="${SPILL_PREFIX}" \
      Name=DisableSpillEncryption,Value="true" \
    --profile "${PROFILE}" --region "${REGION}" \
    --query 'ChangeSetId' --output text)

  echo "     Waiting for change set to be ready..."
  # The change set ARN includes the stack ARN — extract the stack name for waiter
  aws cloudformation wait change-set-create-complete \
    --change-set-name "${CHANGE_SET_ID}" \
    --profile "${PROFILE}" --region "${REGION}" 2>/dev/null || true

  echo "     Executing change set..."
  aws cloudformation execute-change-set \
    --change-set-name "${CHANGE_SET_ID}" \
    --profile "${PROFILE}" --region "${REGION}"

  echo "     Waiting for stack to complete (this may take 2-3 minutes)..."
  aws cloudformation wait stack-create-complete \
    --stack-name "${STACK_NAME}" \
    --profile "${PROFILE}" --region "${REGION}"

  echo "     [ok]   Connector Lambda deployed"
fi

# Get the connector Lambda ARN
CONNECTOR_ARN=$(aws lambda get-function \
  --function-name "${CONNECTOR_FN}" \
  --profile "${PROFILE}" --region "${REGION}" \
  --query 'Configuration.FunctionArn' --output text 2>/dev/null || echo "NOT_FOUND")

if [[ "${CONNECTOR_ARN}" == "NOT_FOUND" ]]; then
  echo "     [error] Connector Lambda not found. Check CloudFormation stack."
  exit 1
fi
echo "     Lambda ARN: ${CONNECTOR_ARN}"

# ── Step 3: Athena data catalog ──────────────────────────────────────────────

echo ""
echo "3/4  Athena data catalog..."

CATALOG_EXISTS=$(aws athena list-data-catalogs \
  --profile "${PROFILE}" --region "${REGION}" \
  --query "DataCatalogsSummary[?CatalogName=='${CATALOG_NAME}'].CatalogName" --output text 2>/dev/null || echo "")

if [[ -n "${CATALOG_EXISTS}" ]]; then
  echo "     [skip] Catalog '${CATALOG_NAME}' already exists"
else
  aws athena create-data-catalog \
    --name "${CATALOG_NAME}" \
    --type LAMBDA \
    --parameters "function=${CONNECTOR_ARN}" \
    --profile "${PROFILE}" --region "${REGION}"
  echo "     [ok]   Catalog '${CATALOG_NAME}' created → ${CONNECTOR_ARN}"
fi

# ── Step 4: Athena workgroup ─────────────────────────────────────────────────

echo ""
echo "4/4  Athena workgroup..."

WORKGROUP_EXISTS=$(aws athena list-work-groups \
  --profile "${PROFILE}" --region "${REGION}" \
  --query "WorkGroups[?Name=='${WORKGROUP_NAME}'].Name" --output text 2>/dev/null || echo "")

if [[ -n "${WORKGROUP_EXISTS}" ]]; then
  echo "     [skip] Workgroup '${WORKGROUP_NAME}' already exists"
else
  aws athena create-work-group \
    --name "${WORKGROUP_NAME}" \
    --configuration "{\"ResultConfiguration\":{\"OutputLocation\":\"s3://${ATHENA_BUCKET}/${RESULTS_PREFIX}/\"},\"EnforceWorkGroupConfiguration\":false}" \
    --profile "${PROFILE}" --region "${REGION}"
  echo "     [ok]   Workgroup '${WORKGROUP_NAME}' created"
fi

# ── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════════════════════════════════════"
echo "  Athena DynamoDB Connector deployed successfully!"
echo ""
echo "  S3 bucket:    s3://${ATHENA_BUCKET}"
echo "  Connector:    ${CONNECTOR_FN}"
echo "  Data catalog: ${CATALOG_NAME}"
echo "  Workgroup:    ${WORKGROUP_NAME}"
echo ""
echo "  Test it in the AWS Console → Athena → Query Editor:"
echo "    • Select data source: ${CATALOG_NAME}"
echo "    • Select workgroup:   ${WORKGROUP_NAME}"
echo "    • Run: SELECT * FROM \"${CATALOG_NAME}\".\"default\".\"tennis-users\" LIMIT 10;"
echo ""
echo "  To connect Steep:"
echo "    • Data source type: Amazon Athena"
echo "    • Region:           ${REGION}"
echo "    • Workgroup:        ${WORKGROUP_NAME}"
echo "    • Data catalog:     ${CATALOG_NAME}"
echo "════════════════════════════════════════════════════════════════════════"
