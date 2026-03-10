PROFILE   ?= tennis-bot
REGION    ?= eu-north-1
ACCOUNT   ?= 605893375372

SCRAPER_FN    = tennis-scraper
PREFERENCES_FN = tennis-preferences
NOTIFICATIONS_FN = tennis-notifications
NEWSLETTER_FN  = tennis-newsletter

S3_FRONTEND_BUCKET = tennis-bot-frontend-$(ACCOUNT)

.PHONY: help install deploy-all deploy-scraper deploy-preferences deploy-notifications \
        deploy-newsletter deploy-frontend package-scraper package-preferences \
        package-notifications package-newsletter deploy-dynamo validate destroy

# ── Help ─────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "Tennis Bot — available targets:"
	@echo ""
	@echo "  install                Install Python dependencies"
	@echo "  deploy-all             Deploy everything (infra + lambdas + frontend)"
	@echo "  deploy-dynamo          Create/verify DynamoDB tables"
	@echo "  deploy-scraper         Package and deploy scraper Lambda"
	@echo "  deploy-preferences     Package and deploy preferences Lambda"
	@echo "  deploy-notifications   Package and deploy notifications Lambda"
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

# ── Lambda packaging ──────────────────────────────────────────────────────────

package-scraper:
	@echo ">> Packaging scraper Lambda..."
	@mkdir -p build
	@cd lambdas/scraper && pip install -r requirements.txt -t ./package --quiet 2>/dev/null || true
	@cd lambdas/scraper && cp -r . ./package/ 2>/dev/null || true
	@cd lambdas/scraper/package && zip -qr ../../../build/scraper.zip .
	@echo "   build/scraper.zip ready"

package-preferences:
	@echo ">> Packaging preferences Lambda..."
	@mkdir -p build
	@cd lambdas/preferences && pip install -r requirements.txt -t ./package --quiet 2>/dev/null || true
	@cd lambdas/preferences && cp -r . ./package/ 2>/dev/null || true
	@cd lambdas/preferences/package && zip -qr ../../../build/preferences.zip .
	@echo "   build/preferences.zip ready"

package-notifications:
	@echo ">> Packaging notifications Lambda..."
	@mkdir -p build
	@cd lambdas/notifications && pip install -r requirements.txt -t ./package --quiet 2>/dev/null || true
	@cd lambdas/notifications && cp -r . ./package/ 2>/dev/null || true
	@cd lambdas/notifications/package && zip -qr ../../../build/notifications.zip .
	@echo "   build/notifications.zip ready"

package-newsletter:
	@echo ">> Packaging newsletter Lambda..."
	@mkdir -p build
	@cd lambdas/newsletter && pip install -r requirements.txt -t ./package --quiet 2>/dev/null || true
	@cd lambdas/newsletter && cp -r . ./package/ 2>/dev/null || true
	@cp lambdas/notifications/matcher.py lambdas/newsletter/package/
	@cd lambdas/newsletter/package && zip -qr ../../../build/newsletter.zip .
	@echo "   build/newsletter.zip ready"

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

# ── Frontend ──────────────────────────────────────────────────────────────────

deploy-frontend:
	@echo ">> Building frontend..."
	@cd frontend && npm run build
	@echo ">> Syncing to S3..."
	@aws s3 sync frontend/dist s3://$(S3_FRONTEND_BUCKET) \
		--delete \
		--profile $(PROFILE) --region $(REGION)
	@echo "   Done: http://$(S3_FRONTEND_BUCKET).s3-website.$(REGION).amazonaws.com"

# ── Deploy all ────────────────────────────────────────────────────────────────

deploy-all: deploy-dynamo deploy-scraper deploy-preferences deploy-notifications deploy-newsletter deploy-frontend
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
	@for table in tennis-users tennis-preferences tennis-availability tennis-notifications; do \
		aws dynamodb delete-table --table-name $$table \
			--profile $(PROFILE) --region $(REGION) 2>/dev/null && echo "  deleted $$table" || echo "  skipped $$table (not found)"; \
	done
	@echo ">> Deleting Lambda functions..."
	@for fn in $(SCRAPER_FN) $(PREFERENCES_FN) $(NOTIFICATIONS_FN); do \
		aws lambda delete-function --function-name $$fn \
			--profile $(PROFILE) --region $(REGION) 2>/dev/null && echo "  deleted $$fn" || echo "  skipped $$fn (not found)"; \
	done
	@echo "Done."
