#!/usr/bin/env bash
# create_harvard_scraper_lambda.sh
#
# One-time script to create the harvard-scraper Lambda function in AWS.
# Run this ONCE to provision the function. Subsequent code updates use:
#   make deploy-harvard-scraper
#
# Prerequisites:
#   - AWS CLI configured with tennis-bot profile
#   - uv installed (for packaging)
#   - Run from the repo root: bash scripts/create_harvard_scraper_lambda.sh

set -euo pipefail

PROFILE="${PROFILE:-tennis-bot}"
REGION="${REGION:-eu-north-1}"
FUNCTION_NAME="harvard-scraper"
ROLE_ARN="arn:aws:iam::605893375372:role/tennis-scraper-role"
HARVARD_PROGRAM_ID="a20e7ae2-fedc-4a8e-a7c3-236695040c63"
DYNAMODB_TABLE="tennis-availability"
NOTIFICATIONS_FUNCTION="tennis-notifications"

echo ">> Building deployment package..."
mkdir -p build lambdas/harvard-scraper/package
uv pip install -r lambdas/harvard-scraper/requirements.txt --target lambdas/harvard-scraper/package --quiet
cp lambdas/harvard-scraper/*.py lambdas/harvard-scraper/package/
cp facilities.py lambdas/harvard-scraper/package/
cd lambdas/harvard-scraper/package && zip -qr ../../../build/harvard-scraper.zip . && cd -
echo "   build/harvard-scraper.zip ready"

echo ">> Checking if Lambda already exists..."
if aws lambda get-function --function-name "$FUNCTION_NAME" --profile "$PROFILE" --region "$REGION" > /dev/null 2>&1; then
    echo "   Lambda '$FUNCTION_NAME' already exists — updating code and config instead."

    aws lambda update-function-code \
        --function-name "$FUNCTION_NAME" \
        --zip-file fileb://build/harvard-scraper.zip \
        --profile "$PROFILE" --region "$REGION" \
        --query 'LastUpdateStatus' --output text

    aws lambda update-function-configuration \
        --function-name "$FUNCTION_NAME" \
        --runtime python3.11 \
        --handler handler.lambda_handler \
        --timeout 900 \
        --memory-size 256 \
        --environment "Variables={HARVARD_PROGRAM_ID=${HARVARD_PROGRAM_ID},DYNAMODB_TABLE=${DYNAMODB_TABLE},NOTIFICATIONS_FUNCTION=${NOTIFICATIONS_FUNCTION}}" \
        --profile "$PROFILE" --region "$REGION" \
        --query 'LastUpdateStatus' --output text
else
    echo ">> Creating Lambda function '$FUNCTION_NAME'..."
    aws lambda create-function \
        --function-name "$FUNCTION_NAME" \
        --runtime python3.11 \
        --role "$ROLE_ARN" \
        --handler handler.lambda_handler \
        --zip-file fileb://build/harvard-scraper.zip \
        --timeout 900 \
        --memory-size 256 \
        --environment "Variables={HARVARD_PROGRAM_ID=${HARVARD_PROGRAM_ID},DYNAMODB_TABLE=${DYNAMODB_TABLE},NOTIFICATIONS_FUNCTION=${NOTIFICATIONS_FUNCTION}}" \
        --profile "$PROFILE" --region "$REGION" \
        --query 'FunctionArn' --output text
fi

echo ""
echo ">> Verifying function state..."
aws lambda get-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --profile "$PROFILE" --region "$REGION" \
    --query '{State:State, Runtime:Runtime, Handler:Handler, Timeout:Timeout}' \
    --output json

echo ""
echo ">> Setting up EventBridge schedule (every 15 minutes)..."
LAMBDA_ARN=$(aws lambda get-function --function-name "$FUNCTION_NAME" --profile "$PROFILE" --region "$REGION" --query 'Configuration.FunctionArn' --output text)

# Create or update the EventBridge rule
aws events put-rule \
    --name harvard-scraper-schedule \
    --schedule-expression "rate(15 minutes)" \
    --state ENABLED \
    --description "Trigger harvard-scraper Lambda every 15 minutes" \
    --profile "$PROFILE" --region "$REGION" \
    --query 'RuleArn' --output text

# Add the Lambda as a target
aws events put-targets \
    --rule harvard-scraper-schedule \
    --targets "Id=harvard-scraper-target,Arn=${LAMBDA_ARN}" \
    --profile "$PROFILE" --region "$REGION"

# Grant EventBridge permission to invoke the Lambda
aws lambda add-permission \
    --function-name "$FUNCTION_NAME" \
    --statement-id harvard-scraper-eventbridge \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn "arn:aws:events:${REGION}:605893375372:rule/harvard-scraper-schedule" \
    --profile "$PROFILE" --region "$REGION" 2>/dev/null || echo "   Permission already exists (OK)"

echo ""
echo ">> Verifying EventBridge rule..."
aws events describe-rule \
    --name harvard-scraper-schedule \
    --profile "$PROFILE" --region "$REGION" \
    --query '{State:State, Schedule:ScheduleExpression}' \
    --output json

echo ""
echo "Done. harvard-scraper Lambda is live in $REGION with 15-minute schedule."
echo "To update code in the future: make deploy-harvard-scraper"
