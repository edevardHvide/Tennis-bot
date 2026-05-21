PROFILE   ?= tennis-bot
REGION    ?= eu-north-1
ACCOUNT   ?= 605893375372

SCRAPER_FN    = tennis-scraper
HARVARD_SCRAPER_FN = harvard-scraper
PREFERENCES_FN = tennis-preferences
NOTIFICATIONS_FN = tennis-notifications
NEWSLETTER_FN  = tennis-newsletter
FEEDBACK_FN    = tennis-feedback
WEATHER_FN     = tennis-weather
FESTIVAL_PREFS_FN = festival-preferences
GOLF_SCRAPER_FN   = golf-scraper

S3_FRONTEND_BUCKET = tennis-bot-frontend

.PHONY: help install deploy-all deploy-scraper deploy-preferences deploy-notifications \
        deploy-newsletter deploy-feedback deploy-weather deploy-harvard-scraper deploy-frontend \
        package-scraper package-preferences package-notifications package-newsletter \
        package-feedback package-weather package-harvard-scraper deploy-dynamo \
        deploy-festival-dynamo package-festival-preferences deploy-festival-preferences \
        package-golf-scraper deploy-golf-scraper \
        validate destroy

# ── Help ─────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "Availability Monitor — available targets:"
	@echo ""
	@echo "  install                Install Python dependencies"
	@echo "  deploy-all             Deploy everything (infra + lambdas + frontend)"
	@echo "  deploy-dynamo          Create/verify DynamoDB tables"
	@echo "  deploy-athena          Deploy Athena DynamoDB connector (for Steep BI)"
	@echo "  deploy-scraper         Package and deploy scraper Lambda"
	@echo "  deploy-preferences     Package and deploy preferences Lambda"
	@echo "  deploy-notifications   Package and deploy notifications Lambda"
	@echo "  deploy-feedback        Package and deploy feedback Lambda"
	@echo "  deploy-weather         Package and deploy weather Lambda"
	@echo "  deploy-frontend        Build and sync frontend to S3"
	@echo "  validate               Run infrastructure smoke tests"
	@echo "  destroy                Delete all AWS resources (DESTRUCTIVE)"
	@echo ""
	@echo "  PROFILE=$(PROFILE)  REGION=$(REGION)"
	@echo ""

# ── Install ───────────────────────────────────────────────────────────────────

install:
	pip install -r requirements.txt

# ── DynamoDB ──────────────────────────────────────────────────────────────────

deploy-dynamo:
	@echo ">> Provisioning DynamoDB tables..."
	@bash infra/dynamo/deploy.sh --profile $(PROFILE)

# ── Athena (BI / Steep) ───────────────────────────────────────────────────────

deploy-athena:
	@echo ">> Deploying Athena DynamoDB Connector..."
	@bash infra/athena/deploy.sh --profile $(PROFILE)

# ── Lambda packaging ──────────────────────────────────────────────────────────

package-scraper:
	@echo ">> Packaging scraper Lambda..."
	@mkdir -p build
	@rm -rf lambdas/scraper/package
	@uv pip install -r lambdas/scraper/requirements.txt --target lambdas/scraper/package --quiet
	@cp lambdas/scraper/*.py lambdas/scraper/package/
	@cp facilities.py lambdas/scraper/package/
	@cd lambdas/scraper/package && zip -qr ../../../build/scraper.zip .
	@echo "   build/scraper.zip ready"

package-preferences:
	@echo ">> Packaging preferences Lambda..."
	@mkdir -p build
	@rm -rf lambdas/preferences/package
	@uv pip install -r lambdas/preferences/requirements.txt --target lambdas/preferences/package --quiet
	@cp lambdas/preferences/*.py lambdas/preferences/package/
	@cp facilities.py lambdas/preferences/package/
	@cd lambdas/preferences/package && zip -qr ../../../build/preferences.zip .
	@echo "   build/preferences.zip ready"

package-notifications:
	@echo ">> Packaging notifications Lambda..."
	@mkdir -p build
	@rm -rf lambdas/notifications/package
	@uv pip install -r lambdas/notifications/requirements.txt --target lambdas/notifications/package --quiet
	@cp lambdas/notifications/*.py lambdas/notifications/package/
	@cp facilities.py lambdas/notifications/package/
	@cp weather.py lambdas/notifications/package/
	@cd lambdas/notifications/package && zip -qr ../../../build/notifications.zip .
	@echo "   build/notifications.zip ready"

package-newsletter:
	@echo ">> Packaging newsletter Lambda..."
	@mkdir -p build
	@rm -rf lambdas/newsletter/package
	@uv pip install -r lambdas/newsletter/requirements.txt --target lambdas/newsletter/package --quiet
	@cp lambdas/newsletter/*.py lambdas/newsletter/package/
	@cp facilities.py lambdas/newsletter/package/
	@cp weather.py lambdas/newsletter/package/
	@cp lambdas/notifications/matcher.py lambdas/newsletter/package/
	@cd lambdas/newsletter/package && zip -qr ../../../build/newsletter.zip .
	@echo "   build/newsletter.zip ready"

package-weather:
	@echo ">> Packaging weather Lambda..."
	@mkdir -p build
	@rm -rf lambdas/weather/package
	@uv pip install -r lambdas/weather/requirements.txt --target lambdas/weather/package --quiet
	@cp lambdas/weather/*.py lambdas/weather/package/
	@cp facilities.py lambdas/weather/package/
	@cp weather.py lambdas/weather/package/
	@cd lambdas/weather/package && zip -qr ../../../build/weather.zip .
	@echo "   build/weather.zip ready"

package-feedback:
	@echo ">> Packaging feedback Lambda..."
	@mkdir -p build
	@rm -rf lambdas/feedback/package
	@uv pip install -r lambdas/feedback/requirements.txt --target lambdas/feedback/package --quiet
	@cp lambdas/feedback/*.py lambdas/feedback/package/
	@cd lambdas/feedback/package && zip -qr ../../../build/feedback.zip .
	@echo "   build/feedback.zip ready"

package-harvard-scraper:
	@echo ">> Packaging harvard-scraper Lambda..."
	@mkdir -p build
	@rm -rf lambdas/harvard-scraper/package
	@uv pip install -r lambdas/harvard-scraper/requirements.txt --target lambdas/harvard-scraper/package --quiet
	@cp lambdas/harvard-scraper/*.py lambdas/harvard-scraper/package/
	@cp facilities.py lambdas/harvard-scraper/package/
	@cd lambdas/harvard-scraper/package && zip -qr ../../../build/harvard-scraper.zip .
	@echo "   build/harvard-scraper.zip ready"

# ── Lambda deploy ─────────────────────────────────────────────────────────────

deploy-scraper: package-scraper
	@echo ">> Deploying scraper Lambda..."
	@aws lambda update-function-code \
		--function-name $(SCRAPER_FN) \
		--zip-file fileb://build/scraper.zip \
		--profile $(PROFILE) --region $(REGION) \
		--query 'LastUpdateStatus' --output text

deploy-preferences: package-preferences
	@echo ">> Deploying preferences Lambda..."
	@aws lambda update-function-code \
		--function-name $(PREFERENCES_FN) \
		--zip-file fileb://build/preferences.zip \
		--profile $(PROFILE) --region $(REGION) \
		--query 'LastUpdateStatus' --output text

deploy-notifications: package-notifications
	@echo ">> Deploying notifications Lambda..."
	@aws lambda update-function-code \
		--function-name $(NOTIFICATIONS_FN) \
		--zip-file fileb://build/notifications.zip \
		--profile $(PROFILE) --region $(REGION) \
		--query 'LastUpdateStatus' --output text

deploy-newsletter: package-newsletter
	@echo ">> Deploying newsletter Lambda..."
	@aws lambda update-function-code \
		--function-name $(NEWSLETTER_FN) \
		--zip-file fileb://build/newsletter.zip \
		--profile $(PROFILE) --region $(REGION) \
		--query 'LastUpdateStatus' --output text

deploy-feedback: package-feedback
	@echo ">> Deploying feedback Lambda..."
	@aws lambda update-function-code \
		--function-name $(FEEDBACK_FN) \
		--zip-file fileb://build/feedback.zip \
		--profile $(PROFILE) --region $(REGION) \
		--query 'LastUpdateStatus' --output text

deploy-weather: package-weather
	@echo ">> Deploying weather Lambda..."
	@aws lambda update-function-code \
		--function-name $(WEATHER_FN) \
		--zip-file fileb://build/weather.zip \
		--profile $(PROFILE) --region $(REGION) \
		--query 'LastUpdateStatus' --output text

deploy-harvard-scraper: package-harvard-scraper
	@echo ">> Deploying harvard-scraper Lambda..."
	@aws lambda update-function-code \
		--function-name $(HARVARD_SCRAPER_FN) \
		--zip-file fileb://build/harvard-scraper.zip \
		--profile $(PROFILE) --region $(REGION) \
		--query 'LastUpdateStatus' --output text

# ── Golf ──────────────────────────────────────────────────────────────────────

package-golf-scraper:
	@echo ">> Packaging golf-scraper Lambda..."
	@mkdir -p build
	@rm -f build/golf-scraper.zip
	@rm -rf lambdas/golf-scraper/package
	@uv pip install -r lambdas/golf-scraper/requirements.txt \
		--target lambdas/golf-scraper/package \
		--python-platform x86_64-manylinux2014 \
		--python-version 3.11 \
		--only-binary=:all: \
		--quiet
	@cp lambdas/golf-scraper/*.py lambdas/golf-scraper/package/
	@cp facilities.py lambdas/golf-scraper/package/
	@cd lambdas/golf-scraper/package && zip -qr ../../../build/golf-scraper.zip .
	@echo "   build/golf-scraper.zip ready"

deploy-golf-scraper: package-golf-scraper
	@echo ">> Deploying golf-scraper Lambda..."
	@aws lambda update-function-code \
		--function-name $(GOLF_SCRAPER_FN) \
		--zip-file fileb://$(PWD)/build/golf-scraper.zip \
		--profile $(PROFILE) --region $(REGION) \
		--query 'LastUpdateStatus' --output text

# ── Festival (beta) ──────────────────────────────────────────────────────────

deploy-festival-dynamo:
	@echo ">> Provisioning festival DynamoDB tables..."
	@bash infra/dynamo/deploy-festival.sh --profile $(PROFILE)

package-festival-preferences:
	@echo ">> Packaging festival-preferences Lambda..."
	@mkdir -p build
	@rm -rf lambdas/festival-preferences/package
	@uv pip install -r lambdas/festival-preferences/requirements.txt --target lambdas/festival-preferences/package --quiet
	@cp lambdas/festival-preferences/*.py lambdas/festival-preferences/package/
	@cp festivals.py lambdas/festival-preferences/package/
	@cd lambdas/festival-preferences/package && zip -qr ../../../build/festival-preferences.zip .
	@echo "   build/festival-preferences.zip ready"

deploy-festival-preferences: package-festival-preferences
	@echo ">> Deploying festival-preferences Lambda..."
	@aws lambda update-function-code \
		--function-name $(FESTIVAL_PREFS_FN) \
		--zip-file fileb://build/festival-preferences.zip \
		--profile $(PROFILE) --region $(REGION) \
		--query 'LastUpdateStatus' --output text

# ── Frontend ──────────────────────────────────────────────────────────────────

CLOUDFRONT_DIST_ID = E2OWR5DUA704T3

deploy-frontend:
	@echo ">> Building frontend..."
	@cd frontend && npm run build
	@echo ">> Syncing to S3..."
	@aws s3 sync frontend/dist s3://$(S3_FRONTEND_BUCKET) \
		--delete \
		--profile $(PROFILE) --region $(REGION)
	@echo ">> Invalidating CloudFront cache..."
	@aws cloudfront create-invalidation \
		--distribution-id $(CLOUDFRONT_DIST_ID) \
		--paths "/*" \
		--profile $(PROFILE) \
		--query 'Invalidation.Status' --output text
	@echo "   Done: https://availabilitymonitor.club"

# ── Deploy all ────────────────────────────────────────────────────────────────

deploy-all: deploy-dynamo deploy-scraper deploy-preferences deploy-notifications deploy-newsletter deploy-feedback deploy-weather deploy-frontend
	@echo ""
	@echo "All components deployed."

# ── Validate ─────────────────────────────────────────────────────────────────

validate:
	@echo ">> Running infrastructure validation..."
	@bash infra/validate.sh --profile $(PROFILE) --region $(REGION)

# ── Destroy ───────────────────────────────────────────────────────────────────

destroy:
	@echo "WARNING: This will delete all AWS resources for this project."
	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ]
	@echo ">> Deleting DynamoDB tables..."
	@for table in tennis-users tennis-preferences tennis-availability tennis-notifications tennis-feedback; do \
		aws dynamodb delete-table --table-name $$table \
			--profile $(PROFILE) --region $(REGION) 2>/dev/null && echo "  deleted $$table" || echo "  skipped $$table (not found)"; \
	done
	@echo ">> Deleting Lambda functions..."
	@for fn in $(SCRAPER_FN) $(PREFERENCES_FN) $(NOTIFICATIONS_FN) $(FEEDBACK_FN); do \
		aws lambda delete-function --function-name $$fn \
			--profile $(PROFILE) --region $(REGION) 2>/dev/null && echo "  deleted $$fn" || echo "  skipped $$fn (not found)"; \
	done
	@echo "Done."
