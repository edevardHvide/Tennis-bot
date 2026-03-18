---
name: dashboard
description: Create or update the live Streamlit analytics dashboard deployed on Render
user_invocable: true
---

# Dashboard Skill

Create new dashboards or update the existing Streamlit analytics dashboard that is deployed on Render with live DynamoDB data via Athena.

## Context

- **Dashboard app:** `dashboard/app.py` (Streamlit + pyathena)
- **Dependencies:** `dashboard/requirements.txt`
- **Render service:** `tennis-dashboard` (ID: `srv-d6sgq4c50q8c73fj8n90`)
- **Live URL:** https://tennis-dashboard-l4xo.onrender.com
- **Auto-deploys** on every push to `main`
- **Data source:** DynamoDB tables queried via Athena federated connector

## Available DynamoDB Tables (via Athena)

All tables are accessed as `"dynamodb"."default"."<table-name>"`:

| Table | Key Fields | Description |
|-------|-----------|-------------|
| `tennis-users` | userId, createdAt, name | Registered subscribers |
| `tennis-preferences` | userId, preferenceId, facilityid, sport, courtType, dates, timefrom, timeto | Per-user alert preferences |
| `tennis-availability` | facilityId (composite: `facility#sport`), date, slots | Scraped court availability snapshots |
| `tennis-notifications` | notificationId, sentat, ttl | Sent notification log (24h TTL) |
| `tennis-feedback` | feedbackId, userId, message, createdAt | User feature requests |

## Workflow

### Step 1: Understand the Request

Ask the user what they want. This could be:
- **New dashboard:** "I want a dashboard showing X, Y, Z"
- **Update existing:** "Add a chart showing feedback over time" or "Change the color scheme"
- **Replace:** "Rebuild the dashboard to focus on availability data"

If the user's request is vague, ask clarifying questions:
- What metrics/data do they want to see?
- Any specific chart types? (bar, line, donut, table, KPIs)
- Any filtering or interactivity needed?

### Step 2: Query Live Data (if needed)

Use the Athena MCP tool to understand the data shape before building visualizations:

```
mcp__athena__run_query(database="default", query='SELECT * FROM "dynamodb"."default"."tennis-users" LIMIT 5')
```

This helps you:
- Discover available columns and their types
- Understand data volumes and distributions
- Validate that your planned queries will work

### Step 3: Read the Current Dashboard

Always read `dashboard/app.py` first to understand the current state. Do NOT start from scratch unless the user explicitly asks for a full rebuild.

### Step 4: Edit or Rewrite the Dashboard

Apply changes to `dashboard/app.py`. Follow these conventions:

**Athena connection (never change this block):**
```python
REGION = "eu-north-1"
CATALOG = "dynamodb"
DATABASE = "default"
WORKGROUP = "primary"
S3_OUTPUT = "s3://tennis-bot-athena-605893375372/athena-results/"

@st.cache_resource
def get_connection():
    return connect(
        region_name=REGION,
        s3_staging_dir=S3_OUTPUT,
        work_group=WORKGROUP,
        catalog_name=CATALOG,
        schema_name=DATABASE,
    )

@st.cache_data(ttl=300)
def query(sql: str) -> pd.DataFrame:
    conn = get_connection()
    return pd.read_sql(sql, conn)
```

**Query pattern — always use full qualified table names:**
```python
df = query('SELECT col1, col2 FROM "dynamodb"."default"."tennis-users"')
```

**Design conventions:**
- Dark theme: background `#08090c`, surface `#0f1117`, borders `rgba(255,255,255,0.06)`
- Accent colors: green `#34d399`, blue `#60a5fa`, orange `#fb923c`, purple `#a78bfa`
- Font: DM Sans (imported via Google Fonts in CSS)
- Use `st.metric()` for KPI cards
- Use `st.bar_chart()`, `st.line_chart()`, `st.area_chart()` for charts
- Use `st.dataframe()` for tables
- Use `st.columns()` for layout
- Use `st.tabs()` for multi-page views
- Add custom CSS via `st.markdown()` with `unsafe_allow_html=True`

**If adding new pip dependencies**, update `dashboard/requirements.txt` too.

### Step 5: Test Locally (Optional)

If the user wants to preview before deploying:
```bash
source .venv/Scripts/activate && cd dashboard && streamlit run app.py
```

### Step 6: Deploy

Commit and push to trigger auto-deploy on Render:

```bash
git add dashboard/app.py dashboard/requirements.txt
git commit -m "Update dashboard: <brief description>"
git push
```

Then check deploy status using Render MCP:
```
mcp__render__get_deploy(serviceId="srv-d6sgq4c50q8c73fj8n90", deployId="<from latest>")
```

Or list recent deploys:
```
mcp__render__list_deploys(serviceId="srv-d6sgq4c50q8c73fj8n90")
```

### Step 7: Notify Slack

After deploying, send a message to #chat (channel ID: `C0AL847SWP4`) summarizing the update. Use a curl call with the Slack bot token:

```bash
curl -s -X POST "https://slack.com/api/chat.postMessage" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-type: application/x-www-form-urlencoded" \
  --data-urlencode "channel=C0AL847SWP4" \
  --data-urlencode "text=:chart_with_upwards_trend: *Dashboard updated*
<brief summary of what changed>
:link: <https://tennis-dashboard-l4xo.onrender.com|View live dashboard>
_Deploying now — live in ~2 min_"
```

Keep the message short. Use Slack mrkdwn formatting (bold with `*`, links with `<url|text>`).

### Step 8: Report to User

Tell the user:
- What was changed
- That the deploy is in progress and Slack was notified
- The live URL: https://tennis-dashboard-l4xo.onrender.com
- That it takes ~2-3 minutes for the deploy to complete

## Important Notes

- **Cache TTL:** Data is cached for 5 minutes (`ttl=300`). Users see fresh data after 5 min.
- **Athena query cost:** Each query scans DynamoDB. Keep queries efficient (use LIMIT, avoid SELECT *  on large tables in production).
- **Render free tier:** The service spins down after 15 min of inactivity. First visit after idle takes ~30s to cold start.
- **Environment variables** (already set on Render): `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`
- **Never hardcode AWS credentials** in the app code — they're injected via Render env vars.
