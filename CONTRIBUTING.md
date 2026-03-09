# Contributing

## Branching

- `main` — production-ready code only
- Feature branches: `feature/<issue-number>-short-description`
- Bug fixes: `fix/<issue-number>-short-description`

## Workflow

1. Pick an issue from the [project board](https://github.com/edevardHvide/Tennis-bot/issues)
2. Create a branch: `git checkout -b feature/42-add-scraper-retries`
3. Make your changes and write/update tests
4. Open a PR referencing the issue: `Closes #42`
5. PR must pass all CI checks before merge

## Environment Setup

See the README for full setup instructions. Minimum requirements:
- Python 3.11+
- AWS CLI configured with `tennis-bot` profile
- `.env` file with required secrets (see `.env.example`)

## Commit Style

Short imperative subject line, e.g.:
- `Add retry logic to scraper`
- `Fix CORS headers on preferences API`
- `Update DynamoDB TTL to 14 days`
