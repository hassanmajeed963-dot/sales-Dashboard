
import io
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from streamlit_autorefresh import st_autorefresh
 
# ============================================================
# CONFIG — change these two values for your setup
# ============================================================
FILE_ID = "10CGmopeMHdvmGrUBQr0_MZlBLgFXSu-k"
SHEET_NAME = 0            # or a string like "Sales" if you have a named sheet
CACHE_TTL_SECONDS = 60    # how often to actually re-fetch from Drive
AUTOREFRESH_MS = 60_000   # how often the whole app reruns (should be >= cache ttl)
 
st.set_page_config(page_title="Sales Dashboard", layout="wide")
 
# Auto-rerun the app on a timer so it feels "live"
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
    # This file is a native Google Sheet (URL contains /spreadsheets/),
    # so we must EXPORT it as .xlsx rather than download it directly.
    request = service.files().export_media(
        fileId=FILE_ID,
        mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
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
 
# Try to parse a Date column if present (adjust name if yours differs)
date_col = next((c for c in df.columns if c.lower() == "date"), None)
if date_col:
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
 
 
# ============================================================
# SIDEBAR FILTERS — adjust column names to match your data
# ============================================================
st.sidebar.header("Filters")
 
filtered_df = df.copy()
 
region_col = next((c for c in df.columns if c.lower() == "region"), None)
if region_col:
    regions = st.sidebar.multiselect(
        "Region", options=sorted(df[region_col].dropna().unique()), default=None
    )
    if regions:
        filtered_df = filtered_df[filtered_df[region_col].isin(regions)]
 
rep_col = next((c for c in df.columns if "rep" in c.lower()), None)
if rep_col:
    reps = st.sidebar.multiselect(
        "Sales Rep", options=sorted(df[rep_col].dropna().unique()), default=None
    )
    if reps:
        filtered_df = filtered_df[filtered_df[rep_col].isin(reps)]
 
if date_col:
    min_d, max_d = df[date_col].min(), df[date_col].max()
    if pd.notna(min_d) and pd.notna(max_d):
        date_range = st.sidebar.date_input("Date range", value=(min_d, max_d))
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
            filtered_df = filtered_df[
                (filtered_df[date_col] >= start) & (filtered_df[date_col] <= end)
            ]
 
st.sidebar.markdown("---")
st.sidebar.caption(f"Data auto-refreshes every {AUTOREFRESH_MS // 1000}s")
if st.sidebar.button("Refresh now"):
    st.cache_data.clear()
    st.rerun()
 
 
# ============================================================
# HEADER + KPIs — adjust column names to match your data
# ============================================================
st.title("📊 Sales Dashboard")
st.caption("Live data pulled directly from Google Drive")
 
revenue_col = next((c for c in df.columns if "revenue" in c.lower() or "sales" in c.lower()), None)
units_col = next((c for c in df.columns if "unit" in c.lower() or "qty" in c.lower()), None)
 
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Total Rows", f"{len(filtered_df):,}")
if revenue_col:
    kpi2.metric("Total Revenue", f"{filtered_df[revenue_col].sum():,.0f}")
    kpi3.metric("Avg Revenue / Row", f"{filtered_df[revenue_col].mean():,.0f}")
if units_col:
    kpi4.metric("Total Units", f"{filtered_df[units_col].sum():,.0f}")
 
st.markdown("---")
 
 
# ============================================================
# CHARTS — adjust column names to match your data
# ============================================================
col1, col2 = st.columns(2)
 
with col1:
    if date_col and revenue_col:
        st.subheader("Revenue Over Time")
        trend = filtered_df.groupby(date_col)[revenue_col].sum().reset_index()
        st.line_chart(trend, x=date_col, y=revenue_col)
    else:
        st.info("Add a 'Date' and a 'Revenue' column to see a trend chart.")
 
with col2:
    if region_col and revenue_col:
        st.subheader("Revenue by Region")
        by_region = filtered_df.groupby(region_col)[revenue_col].sum().reset_index()
        st.bar_chart(by_region, x=region_col, y=revenue_col)
    else:
        st.info("Add a 'Region' column to see a breakdown chart.")
 
if rep_col and revenue_col:
    st.subheader("Revenue by Sales Rep")
    by_rep = (
        filtered_df.groupby(rep_col)[revenue_col]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    st.bar_chart(by_rep, x=rep_col, y=revenue_col)
 
st.markdown("---")
 
# ============================================================
# RAW DATA TABLE
# ============================================================
st.subheader("Raw Data")
st.dataframe(filtered_df, use_container_width=True)