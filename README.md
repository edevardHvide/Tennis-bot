# Tennis Bot -- Court Availability Alert System

An automated system that monitors [matchi.se](https://www.matchi.se) for open tennis court slots and sends email alerts when new courts become available. Built on AWS serverless infrastructure.

## Architecture

```
                         +------------------+
                         |   EventBridge    |
                         | (cron schedule)  |
                         +--------+---------+
                                  |
                                  v
                    +-------------+-------------+
                    |    Scraper Lambda          |
                    | (tennis-scraper)           |
                    +-------------+-------------+
                                  |
                      +-----------+-----------+
                      |                       |
                      v                       v
            +---------+--------+   +----------+---------+
            |   DynamoDB       |   | Notifications Lambda|
            | tennis-          |   | (tennis-            |
            | availability     |   |  notifications)     |
            +------------------+   +----------+----------+
                                              |
                                              v
                                   +----------+---------+
                                   |       SES          |
                                   | (email delivery)   |
                                   +----------+---------+
                                              |
                                              v
                                        User Email

  +----------------+       +---------------------+
  | Frontend (S3)  +------>| API Gateway          |
  | Static site    |       | (mk70fzrqy6)        |
  +----------------+       +----------+----------+
                                      |
                                      v
                           +----------+----------+
                           | Preferences Lambda   |
                           | (tennis-preferences) |
                           +----------+----------+
                                      |
                           +----------v----------+
                           |     DynamoDB        |
                           | tennis-users        |
                           | tennis-preferences  |
                           +---------------------+
```

## AWS Resources

| Resource             | Name / ID                      | Type               |
|----------------------|--------------------------------|--------------------|
| DynamoDB table       | tennis-users                   | On-demand          |
| DynamoDB table       | tennis-preferences             | On-demand          |
| DynamoDB table       | tennis-availability            | On-demand          |
| DynamoDB table       | tennis-notifications           | On-demand (TTL)    |
| Lambda function      | tennis-scraper                 | Python 3.11        |
| Lambda function      | tennis-preferences             | Python 3.11        |
| Lambda function      | tennis-notifications           | Python 3.11        |
| API Gateway          | mk70fzrqy6                     | REST API           |
| EventBridge rule     | tennis-scraper-schedule        | Cron trigger       |
| S3 bucket            | tennis-bot-frontend-*          | Static website     |
| IAM roles            | Per-Lambda execution roles     | Least privilege    |

## Prerequisites

- Python 3.11+
- Node.js 18+ (for frontend)
- AWS CLI v2, configured with a profile named `tennis-bot`
- Region: `eu-north-1`
- `make` (GNU Make)
- `zip` utility (for Lambda packaging)

## Setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/edevardHvide/Tennis-bot.git
   cd Tennis-bot
   ```

2. **Install Python dependencies**

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Linux/macOS
   # .venv\Scripts\activate    # Windows
   pip install -r requirements.txt
   ```

3. **Configure AWS credentials**

   ```bash
   aws configure --profile tennis-bot
   # Region: eu-north-1
   ```

4. **Deploy infrastructure**

   ```bash
   make deploy-all
   ```

   This provisions DynamoDB tables, packages and deploys all Lambda functions, builds the frontend, and syncs it to S3.

5. **Validate deployment**

   ```bash
   make validate
   ```

## Deployment

All deployment is managed through the Makefile. Key targets:

| Target                 | Description                              |
|------------------------|------------------------------------------|
| `make deploy-all`      | Deploy everything (infra + Lambdas + frontend) |
| `make deploy-dynamo`   | Create/verify DynamoDB tables            |
| `make deploy-scraper`  | Package and deploy scraper Lambda        |
| `make deploy-preferences` | Package and deploy preferences Lambda |
| `make deploy-notifications` | Package and deploy notifications Lambda |
| `make deploy-frontend` | Build and sync frontend to S3            |
| `make validate`        | Run infrastructure smoke tests           |
| `make destroy`         | Delete all AWS resources (destructive)   |

Override defaults with: `make deploy-all PROFILE=myprofile REGION=us-east-1`

## Frontend

The frontend is a static site served from S3.

```bash
cd frontend
npm install
npm run dev
```

For production, `make deploy-frontend` builds and syncs to S3.

## Configuration

### Scraper Lambda

| Variable            | Default              | Description                    |
|---------------------|----------------------|--------------------------------|
| `SCRAPER_DAYS_AHEAD`| `14`                 | Number of days ahead to check  |
| `DYNAMODB_TABLE`    | `tennis-availability`| DynamoDB table for snapshots   |
| `LOG_LEVEL`         | `INFO`               | Logging level                  |
| `AWS_REGION`        | `eu-north-1`         | AWS region                     |

### Preferences Lambda

| Variable            | Default              | Description                    |
|---------------------|----------------------|--------------------------------|
| `USERS_TABLE`       | `tennis-users`       | DynamoDB table for users       |
| `PREFERENCES_TABLE` | `tennis-preferences` | DynamoDB table for preferences |
| `LOG_LEVEL`         | `INFO`               | Logging level                  |

### Notifications Lambda

| Variable            | Default                  | Description                    |
|---------------------|--------------------------|--------------------------------|
| `NOTIFICATIONS_TABLE`| `tennis-notifications`  | DynamoDB dedup table           |
| `PREFERENCES_TABLE` | `tennis-preferences`     | DynamoDB preferences table     |
| `USERS_TABLE`       | `tennis-users`           | DynamoDB users table           |
| `LOG_LEVEL`         | `INFO`                   | Logging level                  |

### Local CLI (check_availability.py)

| Variable         | Description                                   |
|------------------|-----------------------------------------------|
| `EMAIL_ENABLED`  | Set to `1` to enable email alerts              |
| `BREVO_API_KEY`  | Brevo HTTP API key (preferred over SMTP)       |
| `SMTP_HOST`      | SMTP server hostname                           |
| `SMTP_PORT`      | SMTP server port                               |
| `SMTP_SSL`       | `1` for SSL, `0` for STARTTLS                  |
| `SMTP_USER`      | SMTP username                                  |
| `SMTP_PASS`      | SMTP password (use app passwords)              |
| `EMAIL_FROM`     | Sender address                                 |
| `EMAIL_TO`       | Comma-separated recipient addresses            |

## Testing

```bash
# Run all unit tests
python -m pytest tests/ -v

# Run scraper tests only
python -m pytest tests/test_scraper.py -v

# Run preferences tests only
python -m pytest tests/test_preferences.py -v

# Run notifications tests only
python -m pytest tests/test_notifications.py -v

# Run legacy slot logic tests
python -m pytest test_slot_logic.py -v

# Integration test (requires network access to matchi.se)
python -m pytest test_integration.py -v
```

## API Reference

The Preferences API is documented in an OpenAPI 3.0 specification:

- **Spec file**: [`infra/api/openapi.yaml`](infra/api/openapi.yaml)

Key endpoints:

| Method | Path                                      | Description               |
|--------|-------------------------------------------|---------------------------|
| POST   | `/users`                                  | Register a new user       |
| GET    | `/users/{userId}/preferences`             | List user preferences     |
| POST   | `/users/{userId}/preferences`             | Create a preference       |
| PUT    | `/users/{userId}/preferences/{prefId}`    | Update a preference       |
| DELETE | `/users/{userId}/preferences/{prefId}`    | Delete a preference       |

## Local CLI Usage

The original polling bot can still be run locally:

```bash
# Continuous monitor
python check_availability.py monitor --between 17-22 --interval-seconds 300

# Single check
python check_availability.py monitor --once --between 17-22

# Specific facilities
python check_availability.py monitor --facility frogner --facility ota

# Test notifications
python check_availability.py test-notifications
python check_availability.py test-email
```

## License

This project is licensed under the terms specified in the [LICENSE](LICENSE) file.
