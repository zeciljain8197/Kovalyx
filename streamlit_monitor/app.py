"""Kovalyx Pipeline Monitor — internal ops dashboard entry point.

Reads the audit schema (audit_reader role) to show pipeline run health,
data quality, and PII masking activity. Business KPIs live on the public
Next.js dashboard instead — this app is for operators, not customers.
"""
from datetime import date

import pandas as pd
import streamlit as st

from db import get_db_connection

st.set_page_config(
    page_title="Kovalyx Pipeline Monitor",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(ttl=60)
def get_last_run() -> pd.DataFrame:
    """Returns the single most recent row from the pipeline audit log."""
    conn = get_db_connection()
    return pd.read_sql(
        "SELECT * FROM audit.kovalyx_pipeline_audit_log ORDER BY start_time DESC LIMIT 1",
        conn,
    )


@st.cache_data(ttl=60)
def get_today_totals() -> pd.DataFrame:
    """Sums records processed and PII events masked for today's runs."""
    conn = get_db_connection()
    return pd.read_sql(
        """
        SELECT
            COALESCE(SUM(records_processed), 0) AS records_processed_today,
            COALESCE(SUM(pii_events_masked), 0) AS pii_events_masked_today
        FROM audit.kovalyx_pipeline_audit_log
        WHERE start_time::date = %(today)s
        """,
        conn,
        params={"today": date.today()},
    )


@st.cache_data(ttl=60)
def get_recent_runs(limit: int = 10) -> pd.DataFrame:
    """Returns the most recent N pipeline audit log rows."""
    conn = get_db_connection()
    return pd.read_sql(
        "SELECT * FROM audit.kovalyx_pipeline_audit_log ORDER BY start_time DESC LIMIT %(limit)s",
        conn,
        params={"limit": limit},
    )


st.title("Kovalyx Pipeline Monitor")
st.caption("Internal ops view — for business KPIs see [kovalyx.vercel.app](https://kovalyx.vercel.app)")

last_run_df = get_last_run()
today_df = get_today_totals()

col1, col2, col3 = st.columns(3)
with col1:
    status = last_run_df.iloc[0]["status"] if not last_run_df.empty else "unknown"
    st.metric("Last Pipeline Run Status", status)
with col2:
    processed_today = int(today_df.iloc[0]["records_processed_today"]) if not today_df.empty else 0
    st.metric("Records Processed Today", processed_today)
with col3:
    pii_today = int(today_df.iloc[0]["pii_events_masked_today"]) if not today_df.empty else 0
    st.metric("PII Events Masked Today", pii_today)

st.subheader("Recent Pipeline Runs")
st.dataframe(get_recent_runs(10), use_container_width=True)

st.caption("Data refreshes when you reload this page or navigate between tabs.")
