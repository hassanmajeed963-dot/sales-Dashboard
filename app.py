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
 
st.set_page_config(page_title="BMS Dashboard", layout="wide")
 
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
    # This is a raw .xlsx file (not a native Google Sheet), so download it directly.
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
 
# ============================================================
# COLUMN AUTO-DETECTION (mutually exclusive, so e.g. "Sales Rep"
# never gets mistaken for the Revenue column just because it
# contains the substring "sales")
#
# NOTE ON "BMS": this assumes your sheet has a column identifying
# the Business Manager (e.g. "BM", "BMS", "BM Name"). If your real
# column is named something else, rename it to include "bm" or
# adjust the keyword list below.
# ============================================================
region_col = next((c for c in df.columns if c.lower().strip() == "region"), None)
 
bm_col = next(
    (c for c in df.columns if c.lower().strip() in ("bm", "bms", "bm name", "business manager")
     or "bm" in c.lower().split()),
    None,
)
# fall back to a generic "rep" column if no explicit BM column exists
if not bm_col:
    bm_col = next((c for c in df.columns if "rep" in c.lower()), None)
 
date_col = next((c for c in df.columns if c.lower().strip() == "date"), None)
 
stage_col = next(
    (c for c in df.columns if "stage" in c.lower() or "status" in c.lower()),
    None,
)
 
used_cols = {c for c in [region_col, bm_col, date_col, stage_col] if c}
 
# Expected revenue vs. actual revenue are kept distinct on purpose.
expected_revenue_col = next(
    (c for c in df.columns if c not in used_cols and "expect" in c.lower() and "rev" in c.lower()),
    None,
)
if expected_revenue_col:
    used_cols.add(expected_revenue_col)
 
revenue_col = next(
    (c for c in df.columns if c not in used_cols and ("revenue" in c.lower() or "sales" in c.lower())),
    None,
)
if revenue_col:
    used_cols.add(revenue_col)
 
units_col = next(
    (c for c in df.columns if c not in used_cols and ("unit" in c.lower() or "qty" in c.lower())),
    None,
)
 
# Parse Date column if present
if date_col:
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
 
# Force numeric columns to actually be numeric (handles stray text, blanks, commas, etc.)
for c in [revenue_col, expected_revenue_col, units_col]:
    if c:
        df[c] = pd.to_numeric(
            df[c].astype(str).str.replace(",", "", regex=False), errors="coerce"
        )
 
# Normalize the stage column so "won"/"Win"/"WIN" etc. all group together
if stage_col:
    df[stage_col] = df[stage_col].astype(str).str.strip().str.title()
 
 
# ============================================================
# SIDEBAR FILTERS — every chart/table below reacts to these
# ============================================================
st.sidebar.header("Filters")
 
filtered_df = df.copy()
 
if region_col:
    regions = st.sidebar.multiselect(
        "Region", options=sorted(df[region_col].dropna().unique()), default=None
    )
    if regions:
        filtered_df = filtered_df[filtered_df[region_col].isin(regions)]
 
if bm_col:
    bms = st.sidebar.multiselect(
        "BM", options=sorted(df[bm_col].dropna().unique()), default=None
    )
    if bms:
        filtered_df = filtered_df[filtered_df[bm_col].isin(bms)]
 
if stage_col:
    stages = st.sidebar.multiselect(
        "Sales Stage", options=sorted(df[stage_col].dropna().unique()), default=None
    )
    if stages:
        filtered_df = filtered_df[filtered_df[stage_col].isin(stages)]
 
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
# HEADER + KPIs
# ============================================================
st.title("📊 BMS Dashboard")
st.caption("Live data pulled directly from Google Drive")
 
kpi_cols = st.columns(5)
kpi_cols[0].metric("Total Rows", f"{len(filtered_df):,}")
 
if expected_revenue_col:
    total_exp = filtered_df[expected_revenue_col].sum(skipna=True)
    kpi_cols[1].metric("Total Expected Revenue", f"{total_exp:,.0f}" if pd.notna(total_exp) else "0")
 
if revenue_col:
    total_rev = filtered_df[revenue_col].sum(skipna=True)
    kpi_cols[2].metric("Total Actual Revenue", f"{total_rev:,.0f}" if pd.notna(total_rev) else "0")
 
if units_col:
    total_units = filtered_df[units_col].sum(skipna=True)
    kpi_cols[3].metric("Total Units", f"{total_units:,.0f}" if pd.notna(total_units) else "0")
 
if stage_col:
    stage_norm = filtered_df[stage_col].str.lower()
    wins = stage_norm.isin(["win", "won"]).sum()
    losses = stage_norm.isin(["loss", "lost"]).sum()
    decided = wins + losses
    win_rate = (wins / decided * 100) if decided else None
    kpi_cols[4].metric("Win Rate", f"{win_rate:.0f}%" if win_rate is not None else "n/a")
 
st.markdown("---")
 
 
# ============================================================
# BMS BY REGION — list, top to bottom, with expected revenue
# and sales stage
# ============================================================
if bm_col and region_col:
    st.subheader("BMs by Region — Expected Revenue & Stage")
 
    group_cols = [region_col, bm_col]
    agg = {}
    if expected_revenue_col:
        agg[expected_revenue_col] = "sum"
    elif revenue_col:
        agg[revenue_col] = "sum"
 
    bm_summary = filtered_df.groupby(group_cols).agg(agg).reset_index() if agg else \
        filtered_df.groupby(group_cols).size().reset_index(name="Count")
 
    # attach a stage breakdown per BM/region if a stage column exists
    if stage_col:
        stage_counts = (
            filtered_df.groupby(group_cols + [stage_col]).size()
            .unstack(fill_value=0)
            .reset_index()
        )
        bm_summary = bm_summary.merge(stage_counts, on=group_cols, how="left")
 
    sort_col = expected_revenue_col or revenue_col
    if sort_col:
        bm_summary = bm_summary.sort_values([region_col, sort_col], ascending=[True, False])
    else:
        bm_summary = bm_summary.sort_values([region_col, bm_col])
 
    st.dataframe(bm_summary, use_container_width=True, hide_index=True)
else:
    st.info("Add a BM/BMS column and a Region column to see the BM-by-region breakdown.")
 
st.markdown("---")
 
 
# ============================================================
# CHARTS — all driven by filtered_df, so they update live
# with every sidebar selection
# ============================================================
col1, col2 = st.columns(2)
 
with col1:
    if bm_col and (expected_revenue_col or revenue_col):
        rev_metric = expected_revenue_col or revenue_col
        st.subheader(f"{'Expected ' if expected_revenue_col else ''}Revenue by BM")
        by_bm = (
            filtered_df.groupby(bm_col)[rev_metric]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
        )
        st.bar_chart(by_bm, x=bm_col, y=rev_metric)
    else:
        st.info("Add a BM/BMS column and a revenue column to see revenue by BM.")
 
with col2:
    if region_col and (expected_revenue_col or revenue_col):
        rev_metric = expected_revenue_col or revenue_col
        st.subheader(f"{'Expected ' if expected_revenue_col else ''}Revenue by Region")
        by_region = (
            filtered_df.groupby(region_col)[rev_metric]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
        )
        st.bar_chart(by_region, x=region_col, y=rev_metric)
    else:
        st.info("Add a Region column to see a revenue breakdown by region.")
 
col3, col4 = st.columns(2)
 
with col3:
    if stage_col:
        st.subheader("Deals by Sales Stage")
        by_stage = filtered_df[stage_col].value_counts().reset_index()
        by_stage.columns = [stage_col, "Count"]
        st.bar_chart(by_stage, x=stage_col, y="Count")
    else:
        st.info("Add a Stage/Status column (Win / Loss / In Progress) to see this chart.")
 
with col4:
    if date_col and (expected_revenue_col or revenue_col):
        rev_metric = expected_revenue_col or revenue_col
        st.subheader("Revenue Over Time")
        trend = filtered_df.groupby(date_col)[rev_metric].sum().reset_index()
        st.line_chart(trend, x=date_col, y=rev_metric)
    else:
        st.info("Add a Date column and a revenue column to see a trend chart.")
 
if bm_col and stage_col:
    st.subheader("Sales Stage Mix by BM")
    stage_by_bm = (
        filtered_df.groupby([bm_col, stage_col]).size()
        .unstack(fill_value=0)
    )
    st.bar_chart(stage_by_bm)
 
st.markdown("---")
 
 
# ============================================================
# RAW DATA TABLE — sorted BM top to bottom by region
# ============================================================
st.subheader("Raw Data")
display_df = filtered_df.copy()
if region_col and bm_col:
    display_df = display_df.sort_values([region_col, bm_col])
st.dataframe(display_df, use_container_width=True)
 