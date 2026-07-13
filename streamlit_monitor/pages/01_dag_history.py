"""DAG Run History — status summary and full run log for the last 100 runs."""
import pandas as pd
import plotly.express as px
import streamlit as st

from db import get_db_connection

st.title("DAG Run History")
st.caption("Last 100 pipeline runs across all tasks")


@st.cache_data(ttl=60)
def get_run_history() -> pd.DataFrame:
    """Returns the last 100 pipeline audit log rows, most recent first."""
    conn = get_db_connection()
    return pd.read_sql(
        "SELECT * FROM audit.kovalyx_pipeline_audit_log ORDER BY start_time DESC LIMIT 100",
        conn,
    )


df = get_run_history()

if df.empty:
    st.info("No pipeline runs recorded yet.")
    st.stop()

df["start_time"] = pd.to_datetime(df["start_time"])
df["end_time"] = pd.to_datetime(df["end_time"])
df["duration_seconds"] = (df["end_time"] - df["start_time"]).dt.total_seconds()
df["run_date"] = df["start_time"].dt.date

success_count = int((df["status"] == "success").sum())
failed_count = int((df["status"] == "failed").sum())
avg_duration = df["duration_seconds"].dropna().mean()

col1, col2, col3 = st.columns(3)
col1.metric("Success", success_count)
col2.metric("Failed", failed_count)
col3.metric("Avg Duration (s)", f"{avg_duration:.1f}" if pd.notna(avg_duration) else "N/A")

st.subheader("Status Over Time")
# st.bar_chart() can't color bars by category, so a Plotly Express
# histogram is used instead to stack success/failed runs per day.
fig = px.histogram(
    df,
    x="run_date",
    color="status",
    barmode="stack",
    color_discrete_map={"success": "#22c55e", "failed": "#ef4444", "running": "#eab308"},
)
st.plotly_chart(fig, use_container_width=True)

st.subheader("Full Run History")
display_cols = ["dag_id", "task_id", "status", "start_time", "duration_seconds", "records_processed", "records_failed"]
st.dataframe(
    df[display_cols],
    use_container_width=True,
    column_config={
        "status": st.column_config.TextColumn("Status"),
        "duration_seconds": st.column_config.NumberColumn("Duration (s)", format="%.1f"),
    },
)
