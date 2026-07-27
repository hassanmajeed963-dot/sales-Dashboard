
import streamlit as st
import pandas as pd
import os
from insights import generate_insights

# ------------------------------------------------------------------
# CONFIG: path to your Excel file
# ------------------------------------------------------------------
# The Excel file must be uploaded into the same GitHub repo/folder
# as this app.py file, since Streamlit Cloud has no "Desktop" access.
FILE_PATH = os.path.join(
    os.path.dirname(__file__),
    "cloud_company_sales_data.xlsx"
)

st.set_page_config(page_title="Sales Dashboard", layout="wide")


# ------------------------------------------------------------------
# LOAD DATA
# ------------------------------------------------------------------
@st.cache_data(ttl=300)  # cache for 5 minutes, then reload from disk
def load_data(path):
    return pd.read_excel(path)


st.title("📊 Cloud Company Sales Dashboard")

if st.button("🔄 Refresh Data"):
    st.cache_data.clear()

if not os.path.exists(FILE_PATH):
    st.error(f"File not found at: {FILE_PATH}\n\n"
             f"Make sure 'cloud_company_sales_data.xlsx' is inside the "
             f"'SKY 47' folder on your Desktop.")
    st.stop()

df = load_data(FILE_PATH)

st.caption(f"Last refreshed: {pd.Timestamp.now():%Y-%m-%d %H:%M:%S}  |  "
           f"Rows loaded: {len(df)}")

# ------------------------------------------------------------------
# AUTOMATIC INSIGHTS
# ------------------------------------------------------------------
st.subheader("🔎 Automatic Insights")
for insight in generate_insights(df):
    st.write("•", insight)

# ------------------------------------------------------------------
# SHOW RAW DATA (optional, collapsible)
# ------------------------------------------------------------------
with st.expander("View raw data"):
    st.dataframe(df, use_container_width=True)

# ------------------------------------------------------------------
# KPI METRICS
# ------------------------------------------------------------------
st.subheader("Key Metrics")

numeric_cols = df.select_dtypes(include="number").columns.tolist()

col1, col2, col3 = st.columns(3)

if numeric_cols:
    main_col = numeric_cols[0]  # first numeric column, e.g. Revenue/Sales
    col1.metric(f"Total {main_col}", f"{df[main_col].sum():,.0f}")
    col2.metric(f"Average {main_col}", f"{df[main_col].mean():,.2f}")
    col3.metric("Total Records", f"{len(df):,}")
else:
    st.warning("No numeric columns detected in the file.")

# ------------------------------------------------------------------
# CHARTS
# ------------------------------------------------------------------
st.subheader("Charts")

text_cols = df.select_dtypes(include="object").columns.tolist()

if text_cols and numeric_cols:
    group_col = st.selectbox("Group by (category column):", text_cols)
    value_col = st.selectbox("Value column (numeric):", numeric_cols)

    chart_data = df.groupby(group_col)[value_col].sum().sort_values(ascending=False)
    st.bar_chart(chart_data)
else:
    st.info("Not enough categorical/numeric columns to build a chart automatically.")

# ------------------------------------------------------------------
# TREND OVER TIME (if a date column exists)
# ------------------------------------------------------------------
date_cols = [c for c in df.columns if "date" in c.lower()]

if date_cols and numeric_cols:
    st.subheader("Trend Over Time")
    date_col = st.selectbox("Date column:", date_cols)
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    trend = df.groupby(df[date_col].dt.to_period("M"))[numeric_cols[0]].sum()
    trend.index = trend.index.astype(str)
    st.line_chart(trend)
 