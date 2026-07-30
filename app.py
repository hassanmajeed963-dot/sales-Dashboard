import io
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from streamlit_autorefresh import st_autorefresh
 
# ============================================================
# CONFIG
# ============================================================
FILE_ID = "10CGmopeMHdvmGrUBQr0_MZlBLgFXSu-k"   # <-- update if your live file has a different ID
SHEET_NAME = 0
CACHE_TTL_SECONDS = 60
AUTOREFRESH_MS = 60_000
 
# Exact column names taken from your sheet (random_sales_data.xlsx):
# 'S.No.', 'Client Name', 'OTC (USD)', 'MRC (USD)', 'EAR (USD)',
# 'Probability', 'Win/Loss/Status', 'BMs', 'Region'
COL_SNO = "S.No."
COL_CLIENT = "Client Name"
COL_OTC = "OTC (USD)"
COL_MRC = "MRC (USD)"
COL_EAR = "EAR (USD)"          # <- expected revenue
COL_PROB = "Probability"
COL_STAGE = "Win/Loss/Status"  # <- Won / In-Progress / Loss
COL_BM = "BMs"
COL_REGION = "Region"
 
st.set_page_config(page_title="BMS Dashboard", layout="wide")
st_autorefresh(interval=AUTOREFRESH_MS, key="datarefresh")
 
 
# ============================================================
# DRIVE CONNECTION
# ============================================================
@st.cache_resource
def get_drive_service():
    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scopes
    )
    return build("drive", "v3", credentials=creds)
 
 
@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_data():
    service = get_drive_service()
    request = service.files().get_media(fileId=FILE_ID)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    df = pd.read_excel(fh, sheet_name=SHEET_NAME)
    df.columns = [str(c).strip() for c in df.columns]
    return df
 
 
# ============================================================
# LOAD DATA
# ============================================================
try:
    df = load_data()
except Exception as e:
    st.error(f"Could not load data from Google Drive: {e}")
    st.stop()
 
if df.empty:
    st.warning("The file was read but contains no rows.")
    st.stop()
 
missing = [c for c in [COL_OTC, COL_MRC, COL_EAR, COL_PROB, COL_STAGE, COL_BM, COL_REGION] if c not in df.columns]
if missing:
    st.error(f"These expected columns are missing from the sheet: {missing}. "
             f"Columns found: {list(df.columns)}")
    st.stop()
 
# --- clean numeric columns ---
for c in [COL_OTC, COL_MRC, COL_EAR, COL_PROB]:
    df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "", regex=False), errors="coerce")
 
# --- normalize text columns (fixes things like "muhammad Umair" vs "Muhammad Umair") ---
df[COL_BM] = df[COL_BM].astype(str).str.strip().str.title()
df[COL_REGION] = df[COL_REGION].astype(str).str.strip().str.title()
df[COL_STAGE] = df[COL_STAGE].astype(str).str.strip().str.title()
 
 
# ============================================================
# SIDEBAR FILTERS — every table/chart below reacts to these
# ============================================================
st.sidebar.header("Filters")
filtered_df = df.copy()
 
regions = st.sidebar.multiselect("Region", options=sorted(df[COL_REGION].dropna().unique()))
if regions:
    filtered_df = filtered_df[filtered_df[COL_REGION].isin(regions)]
 
bms = st.sidebar.multiselect("BM", options=sorted(df[COL_BM].dropna().unique()))
if bms:
    filtered_df = filtered_df[filtered_df[COL_BM].isin(bms)]
 
stages = st.sidebar.multiselect("Stage", options=sorted(df[COL_STAGE].dropna().unique()))
if stages:
    filtered_df = filtered_df[filtered_df[COL_STAGE].isin(stages)]
 
st.sidebar.markdown("---")
st.sidebar.caption(f"Data auto-refreshes every {AUTOREFRESH_MS // 1000}s")
if st.sidebar.button("Refresh now"):
    st.cache_data.clear()
    st.rerun()
 
 
# ============================================================
# HEADER + KPIs
# ============================================================
st.title("📊 BMS Dashboard")
st.caption("Live data pulled directly from Google Drive")
 
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Rows", f"{len(filtered_df):,}")
k2.metric("Total EAR (USD)", f"{filtered_df[COL_EAR].sum(skipna=True):,.0f}")
k3.metric("Total OTC (USD)", f"{filtered_df[COL_OTC].sum(skipna=True):,.0f}")
k4.metric("Avg Probability", f"{filtered_df[COL_PROB].mean(skipna=True) * 100:,.0f}%")
 
stage_norm = filtered_df[COL_STAGE].str.lower()
wins = stage_norm.eq("won").sum()
losses = stage_norm.eq("loss").sum()
decided = wins + losses
k5.metric("Win Rate", f"{(wins / decided * 100):.0f}%" if decided else "n/a")
 
st.markdown("---")
 
 
# ============================================================
# FULL DATA — every column, with the row count
# ============================================================
st.subheader(f"All Data ({len(filtered_df):,} rows)")
st.dataframe(filtered_df, use_container_width=True)
 
st.markdown("---")
 
 
# ============================================================
# BM RANKING (overall) — who is #1, #2, #3... by EAR (USD)
# ============================================================
st.subheader("BM Ranking (Overall)")
 
bm_rank = (
    filtered_df.groupby(COL_BM)
    .agg(
        **{
            "Total EAR (USD)": (COL_EAR, "sum"),
            "Total OTC (USD)": (COL_OTC, "sum"),
            "Avg Probability": (COL_PROB, "mean"),
            "Deals": (COL_BM, "count"),
        }
    )
    .reset_index()
    .sort_values("Total EAR (USD)", ascending=False)
    .reset_index(drop=True)
)
bm_rank.insert(0, "Rank", bm_rank.index + 1)
bm_rank["Avg Probability"] = (bm_rank["Avg Probability"] * 100).round(0).astype(str) + "%"
 
st.dataframe(bm_rank, use_container_width=True, hide_index=True)
 
st.markdown("---")
 
 
# ============================================================
# BM RANKING BY REGION — who is on top in each region
# ============================================================
st.subheader("BM Ranking by Region")
 
bm_region_rank = (
    filtered_df.groupby([COL_REGION, COL_BM])
    .agg(
        **{
            "Total EAR (USD)": (COL_EAR, "sum"),
            "Total OTC (USD)": (COL_OTC, "sum"),
            "Avg Probability": (COL_PROB, "mean"),
            "Deals": (COL_BM, "count"),
        }
    )
    .reset_index()
    .sort_values([COL_REGION, "Total EAR (USD)"], ascending=[True, False])
)
bm_region_rank["Rank in Region"] = (
    bm_region_rank.groupby(COL_REGION)["Total EAR (USD)"]
    .rank(method="first", ascending=False)
    .astype(int)
)
bm_region_rank["Avg Probability"] = (bm_region_rank["Avg Probability"] * 100).round(0).astype(str) + "%"
# reorder columns nicely
bm_region_rank = bm_region_rank[
    [COL_REGION, "Rank in Region", COL_BM, "Total EAR (USD)", "Total OTC (USD)", "Avg Probability", "Deals"]
]
 
st.dataframe(bm_region_rank, use_container_width=True, hide_index=True)
 
# quick callout: top BM per region
top_per_region = bm_region_rank[bm_region_rank["Rank in Region"] == 1]
if not top_per_region.empty:
    st.caption("🏆 Top BM per region: " + " | ".join(
        f"{row[COL_REGION]} → {row[COL_BM]}" for _, row in top_per_region.iterrows()
    ))
 
st.markdown("---")
 
 
# ============================================================
# CHARTS — all driven by filtered_df, update with filters
# ============================================================
col1, col2 = st.columns(2)
 
with col1:
    st.subheader("EAR (USD) by BM")
    by_bm = filtered_df.groupby(COL_BM)[COL_EAR].sum().sort_values(ascending=False).reset_index()
    st.bar_chart(by_bm, x=COL_BM, y=COL_EAR)
 
with col2:
    st.subheader("EAR (USD) by Region")
    by_region = filtered_df.groupby(COL_REGION)[COL_EAR].sum().sort_values(ascending=False).reset_index()
    st.bar_chart(by_region, x=COL_REGION, y=COL_EAR)
 
col3, col4 = st.columns(2)
 
with col3:
    st.subheader("Deals by Stage")
    by_stage = filtered_df[COL_STAGE].value_counts().reset_index()
    by_stage.columns = [COL_STAGE, "Count"]
    st.bar_chart(by_stage, x=COL_STAGE, y="Count")
 
with col4:
    st.subheader("OTC (USD) by BM")
    by_bm_otc = filtered_df.groupby(COL_BM)[COL_OTC].sum().sort_values(ascending=False).reset_index()
    st.bar_chart(by_bm_otc, x=COL_BM, y=COL_OTC)
 
st.subheader("EAR (USD) by BM, split by Region")
ear_bm_region = filtered_df.pivot_table(
    index=COL_BM, columns=COL_REGION, values=COL_EAR, aggfunc="sum", fill_value=0
)
st.bar_chart(ear_bm_region)
 
st.subheader("Average Probability by BM")
prob_by_bm = filtered_df.groupby(COL_BM)[COL_PROB].mean().sort_values(ascending=False).reset_index()
st.bar_chart(prob_by_bm, x=COL_BM, y=COL_PROB)
 