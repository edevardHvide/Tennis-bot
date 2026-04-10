import streamlit as st
import pandas as pd
import plotly.express as px
from pyathena import connect

st.set_page_config(
    page_title="Availability Monitor",
    page_icon="\U0001F3BE",
    layout="wide",
)

# ── Athena connection ────────────────────────────────────────────────────────

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


# ── Queries ──────────────────────────────────────────────────────────────────

users_df = query('SELECT * FROM "dynamodb"."default"."tennis-users"')
prefs_df = query('SELECT * FROM "dynamodb"."default"."tennis-preferences"')
feedback_df = query('SELECT * FROM "dynamodb"."default"."tennis-feedback"')

total_users = len(users_df)
total_prefs = len(prefs_df)
total_feedback = len(feedback_df)

# New preferences today
today_str = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
if "createdat" in prefs_df.columns:
    prefs_today = prefs_df[prefs_df["createdat"].astype(str).str[:10] == today_str]
    new_prefs_today = len(prefs_today)
else:
    new_prefs_today = 0

sport_counts = prefs_df.groupby("sport").size().reset_index(name="count")
facility_counts = (
    prefs_df.groupby("facilityid")
    .size()
    .reset_index(name="watchers")
    .sort_values("watchers", ascending=False)
)
user_counts = (
    prefs_df.groupby("userid")
    .size()
    .reset_index(name="preferences")
    .sort_values("preferences", ascending=False)
    .head(10)
)
facilities_watched = prefs_df["facilityid"].nunique()

# ── Custom CSS ───────────────────────────────────────────────────────────────

st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');

    .stApp { background: #08090c; }
    .block-container { padding-top: 2rem; max-width: 1200px; }

    .main-header {
        font-family: 'DM Sans', sans-serif;
        font-size: 28px;
        font-weight: 600;
        color: #e8e8ed;
        letter-spacing: -0.5px;
        margin-bottom: 0;
    }
    .sub-header {
        font-size: 13px;
        color: #52536a;
        margin-bottom: 28px;
    }

    div[data-testid="stMetric"] {
        background: #0f1117;
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 16px;
        padding: 20px;
    }
    div[data-testid="stMetric"] label { color: #8b8d98 !important; font-size: 12px !important; }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] { font-size: 36px !important; font-weight: 700 !important; }

    .chart-container {
        background: #0f1117;
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 16px;
        padding: 20px;
    }

    div[data-testid="stDataFrame"] {
        background: #0f1117;
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 16px;
        padding: 8px;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ── Layout ───────────────────────────────────────────────────────────────────

st.markdown('<div class="main-header">Availability Monitor</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Live data from DynamoDB via Athena &middot; refreshes every 5 min</div>',
    unsafe_allow_html=True,
)

# KPI row
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Users", total_users)
k2.metric("Active Preferences", total_prefs)
k3.metric("New Today", new_prefs_today)
k4.metric("Facilities Watched", facilities_watched)
k5.metric("Feature Requests", total_feedback)

st.markdown("")

# Charts row
c1, c2 = st.columns([1, 1.5])

SPORT_COLORS = {"tennis": "#34d399", "padel": "#fb923c"}

with c1:
    st.markdown("##### Preferences by Sport")
    fig = px.pie(
        sport_counts,
        values="count",
        names="sport",
        color="sport",
        color_discrete_map=SPORT_COLORS,
        hole=0.55,
    )
    fig.update_traces(
        textinfo="label+percent",
        textfont_size=14,
        textfont_color="#e8e8ed",
        marker=dict(line=dict(color="#08090c", width=2)),
        hovertemplate="<b>%{label}</b><br>%{value} preferences<br>%{percent}<extra></extra>",
    )
    fig.update_layout(
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=10, b=10, l=10, r=10),
        height=320,
        annotations=[
            dict(
                text=f"<b>{total_prefs}</b><br><span style='font-size:11px;color:#52536a'>total</span>",
                showarrow=False,
                font=dict(size=28, color="#e8e8ed"),
                x=0.5,
                y=0.5,
            )
        ],
    )
    st.plotly_chart(fig, use_container_width=True)

with c2:
    st.markdown("##### Watchers per Facility")
    st.bar_chart(
        facility_counts.set_index("facilityid"),
        color=["#60a5fa"],
        use_container_width=True,
        horizontal=True,
        height=320,
    )

st.markdown("")

# ── Facility Map ────────────────────────────────────────────────────────────

FACILITY_COORDS = {
    "ota":                {"lat": 59.9242, "lon": 10.7850, "name": "OTA"},
    "bergentennisarena":  {"lat": 60.3880, "lon": 5.3250,  "name": "Bergen Tennis Arena"},
    "furuset":            {"lat": 59.9520, "lon": 10.8650, "name": "Furuset"},
    "interpadel":         {"lat": 59.9330, "lon": 10.8350, "name": "InterPadel Oslo"},
    "nordicpadel":        {"lat": 59.9300, "lon": 10.9600, "name": "Nordic Padel"},
    "nordstrand":         {"lat": 59.8640, "lon": 10.7900, "name": "Nordstrand Tennisklubb"},
    "voldslokka":         {"lat": 59.9350, "lon": 10.7520, "name": "Voldsløkka"},
    "bergenpadelklubb":   {"lat": 60.3700, "lon": 5.3450,  "name": "Bergen Padelklubb"},
    "interpadelbergen":   {"lat": 60.3100, "lon": 5.3100,  "name": "InterPadel Bergen (Sandsli)"},
    "frogner":            {"lat": 59.9240, "lon": 10.7050, "name": "Frogner"},
    "ullern":             {"lat": 59.9300, "lon": 10.6400, "name": "Ullern Tennisklubb"},
    "heming":             {"lat": 59.9540, "lon": 10.6580, "name": "Heming Tennis og Padel"},
    "holmenkollen":       {"lat": 59.9650, "lon": 10.6600, "name": "Holmenkollen Tennisklubb"},
}

st.markdown("##### Court Locations")

# Build map data: join facility coords with watcher counts per sport
facility_sport_counts = (
    prefs_df.groupby(["facilityid", "sport"])
    .size()
    .reset_index(name="watchers")
)

map_rows = []
seen_facilities = set()
for _, row in facility_sport_counts.iterrows():
    fid = row["facilityid"]
    if fid in FACILITY_COORDS:
        seen_facilities.add(fid)
        coords = FACILITY_COORDS[fid]
        map_rows.append({
            "facility": coords["name"],
            "lat": coords["lat"],
            "lon": coords["lon"],
            "sport": row["sport"],
            "watchers": int(row["watchers"]),
        })

# Include facilities with 0 watchers
for fid, coords in FACILITY_COORDS.items():
    if fid not in seen_facilities:
        map_rows.append({
            "facility": coords["name"],
            "lat": coords["lat"],
            "lon": coords["lon"],
            "sport": "none",
            "watchers": 0,
        })

map_df = pd.DataFrame(map_rows)

MAP_COLORS = {"tennis": "#34d399", "padel": "#fb923c", "none": "#52536a"}

fig_map = px.scatter_mapbox(
    map_df,
    lat="lat",
    lon="lon",
    size=[max(w, 3) for w in map_df["watchers"]],
    size_max=30,
    color="sport",
    color_discrete_map=MAP_COLORS,
    hover_name="facility",
    hover_data={"watchers": True, "sport": True, "lat": False, "lon": False},
    zoom=5,
    center={"lat": 59.95, "lon": 10.0},
)
fig_map.update_layout(
    mapbox_style="carto-darkmatter",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(t=0, b=0, l=0, r=0),
    height=480,
    legend=dict(
        title=None,
        font=dict(color="#e8e8ed", size=12),
        bgcolor="rgba(15,17,23,0.8)",
        bordercolor="rgba(255,255,255,0.06)",
        borderwidth=1,
        orientation="h",
        yanchor="top",
        y=0.99,
        xanchor="left",
        x=0.01,
    ),
)
st.plotly_chart(fig_map, use_container_width=True)

st.markdown("")

# User table
st.markdown("##### Most Active Users")
st.dataframe(
    user_counts.rename(columns={"userid": "User", "preferences": "Preferences"}),
    use_container_width=True,
    hide_index=True,
    height=320,
)

# Footer
st.markdown(
    "<div style='text-align:center;color:#3f3f46;font-size:11px;margin-top:32px;'>"
    "Data queried live from DynamoDB via Athena"
    "</div>",
    unsafe_allow_html=True,
)
