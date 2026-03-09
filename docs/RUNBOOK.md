# Tennis Bot -- Operations Runbook

Standard operating procedures for the Tennis Bot AWS infrastructure.

**Profile:** `tennis-bot`
**Region:** `eu-north-1`

---

## 1. Deploying a Lambda Update

### Deploy a single Lambda

```bash
# Scraper
make deploy-scraper

# Preferences
make deploy-preferences

# Notifications
make deploy-notifications
```

### Deploy everything

```bash
make deploy-all
```

### Manual packaging and deploy (without Make)

```bash
cd lambdas/scraper
pip install -r requirements.txt -t ./package
cp *.py ./package/
cd package && zip -r ../../../build/scraper.zip .
cd ../../..

aws lambda update-function-code \
  --function-name tennis-scraper \
  --zip-file fileb://build/scraper.zip \
  --profile tennis-bot --region eu-north-1
```

---

## 2. Checking Lambda Logs

CloudWatch log group names follow the pattern `/aws/lambda/<function-name>`.

### View recent logs

```bash
# Scraper logs
aws logs tail /aws/lambda/tennis-scraper \
  --profile tennis-bot --region eu-north-1 --follow

# Preferences logs
aws logs tail /aws/lambda/tennis-preferences \
  --profile tennis-bot --region eu-north-1 --follow

# Notifications logs
aws logs tail /aws/lambda/tennis-notifications \
  --profile tennis-bot --region eu-north-1 --follow
```

### Filter logs by time range

```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/tennis-scraper \
  --start-time $(date -d '1 hour ago' +%s000) \
  --profile tennis-bot --region eu-north-1
```

### Search for errors

```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/tennis-scraper \
  --filter-pattern "ERROR" \
  --profile tennis-bot --region eu-north-1
```

---

## 3. Manually Triggering the Scraper

```bash
aws lambda invoke \
  --function-name tennis-scraper \
  --profile tennis-bot --region eu-north-1 \
  --payload '{}' \
  --cli-binary-format raw-in-base64-out \
  /dev/stdout
```

The response includes a `diff` object with any newly found courts and a `summary` with totals.

---

## 4. Checking DynamoDB Data

### Scan all items in a table

```bash
# Availability snapshots
aws dynamodb scan \
  --table-name tennis-availability \
  --profile tennis-bot --region eu-north-1

# Users
aws dynamodb scan \
  --table-name tennis-users \
  --profile tennis-bot --region eu-north-1

# Preferences
aws dynamodb scan \
  --table-name tennis-preferences \
  --profile tennis-bot --region eu-north-1

# Notification history
aws dynamodb scan \
  --table-name tennis-notifications \
  --profile tennis-bot --region eu-north-1
```

### Query a specific facility and date

```bash
aws dynamodb get-item \
  --table-name tennis-availability \
  --key '{"facilityId": {"S": "frogner"}, "date": {"S": "2026-03-10"}}' \
  --profile tennis-bot --region eu-north-1
```

### Query all preferences for a user

```bash
aws dynamodb query \
  --table-name tennis-preferences \
  --key-condition-expression "userId = :uid" \
  --expression-attribute-values '{":uid": {"S": "alice@example.com"}}' \
  --profile tennis-bot --region eu-north-1
```

---

## 5. Enabling/Disabling the Scraper Schedule

### List EventBridge rules

```bash
aws events list-rules \
  --name-prefix tennis \
  --profile tennis-bot --region eu-north-1
```

### Disable the schedule (pause scraping)

```bash
aws events disable-rule \
  --name tennis-scraper-schedule \
  --profile tennis-bot --region eu-north-1
```

### Re-enable the schedule

```bash
aws events enable-rule \
  --name tennis-scraper-schedule \
  --profile tennis-bot --region eu-north-1
```

---

## 6. Adding a New Facility

To add a new tennis facility to the system, update the following files:

1. **`facilities.py`** -- Add the facility key and Matchi facility ID to the `facilities` dict. Add a display name to `facility_display_names`.

2. **`lambdas/scraper/handler.py`** -- Add the facility key and ID to the `FACILITIES` dict (line ~57).

3. **`infra/api/openapi.yaml`** -- Add the facility key to the `facilityId` enum in `CreatePreferenceRequest`.

4. **`lambdas/preferences/handler.py`** -- If facility validation is present, add the new key to the allowed list.

After updating, redeploy:

```bash
make deploy-scraper
make deploy-preferences
```

---

## 7. Troubleshooting

### Lambda timeout

**Symptom:** Lambda invocation returns a timeout error or takes longer than expected.

**Cause:** The scraper fetches pages for all facilities and all dates sequentially. With 3 facilities and 14 days, that is 42 HTTP requests.

**Fix:**
- Reduce `SCRAPER_DAYS_AHEAD` to check fewer days.
- Increase the Lambda timeout in the AWS console (default: 30s, recommended: 120s for scraper).
- The circuit breaker (3 consecutive failures per facility) automatically skips remaining dates.

### SES sandbox restrictions

**Symptom:** Emails fail with "Email address is not verified."

**Cause:** SES starts in sandbox mode, limiting sends to verified addresses only.

**Fix:**
- Verify recipient email addresses in the SES console.
- Request production access via the SES console to remove sandbox restrictions.

### CORS errors from frontend

**Symptom:** Browser console shows "Access-Control-Allow-Origin" errors.

**Cause:** API Gateway is not returning the correct CORS headers.

**Fix:**
- Ensure the API Gateway has CORS enabled on all endpoints.
- Verify that the Lambda response includes `Access-Control-Allow-Origin` headers.
- Redeploy the API stage after making changes.

### Scraper returns empty results

**Symptom:** All slots come back empty even though matchi.se shows availability.

**Cause:** Matchi may have changed their HTML structure.

**Fix:**
- Check the HTML manually: `curl "https://www.matchi.se/book/schedule?facilityId=2259&date=2026-03-10&sport=1"`
- Compare the HTML structure against `parse_slots_from_html()` in `lambdas/scraper/scraper.py`.
- Look for changes to the `<td class="slot free">` elements or the `title` attribute format.

### DynamoDB throttling

**Symptom:** Logs show "ProvisionedThroughputExceededException".

**Cause:** Should not happen with on-demand billing. If it does, there may be a burst of requests.

**Fix:**
- All tables use PAY_PER_REQUEST (on-demand) billing, which auto-scales. If errors persist, check the AWS Service Health Dashboard.

---

## 8. Destroying Resources

To tear down all AWS resources:

```bash
make destroy
```

**WARNING:** This is irreversible. It will:

- Delete all 4 DynamoDB tables and their data (tennis-users, tennis-preferences, tennis-availability, tennis-notifications)
- Delete all 3 Lambda functions (tennis-scraper, tennis-preferences, tennis-notifications)

Resources NOT deleted by `make destroy` (must be removed manually if needed):

- API Gateway (mk70fzrqy6)
- EventBridge rules
- IAM roles
- S3 frontend bucket
- CloudWatch log groups
