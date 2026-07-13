"""Data Quality — Great Expectations checkpoint results."""
import json

import pandas as pd
import plotly.express as px
import streamlit as st

from db import get_db_connection

st.title("Data Quality")
st.caption("Great Expectations checkpoint results")

# audit.ge_validation_results' real columns (scripts/supabase_schema.sql)
# are id / pipeline_run_id / expectation_suite_name /
# unsuccessful_expectations / result_detail — aliased below to the clean
# names this page uses (checkpoint_name and run_time are already named
# consistently in the underlying table).
GE_RESULT_SELECT = """
    id AS result_id,
    pipeline_run_id AS run_id,
    checkpoint_name,
    expectation_suite_name AS suite_name,
    success,
    evaluated_expectations,
    successful_expectations,
    unsuccessful_expectations AS failed_expectations,
    run_time,
    result_detail AS details
"""

CHECKPOINT_NAMES = ["silver_events", "silver_customers", "silver_orders", "silver_inventory"]


@st.cache_data(ttl=60)
def get_all_results(limit: int = 500) -> pd.DataFrame:
    """Returns the most recent GE results, one row per checkpoint run."""
    conn = get_db_connection()
    return pd.read_sql(
        f"SELECT {GE_RESULT_SELECT} FROM audit.ge_validation_results ORDER BY run_time DESC LIMIT %(limit)s",
        conn,
        params={"limit": limit},
    )


@st.cache_data(ttl=60)
def get_failed_results(limit: int = 50) -> pd.DataFrame:
    """Returns the most recent failed checkpoint runs."""
    conn = get_db_connection()
    return pd.read_sql(
        f"SELECT {GE_RESULT_SELECT} FROM audit.ge_validation_results WHERE success = false ORDER BY run_time DESC LIMIT %(limit)s",
        conn,
        params={"limit": limit},
    )


all_results = get_all_results()

st.subheader("Checkpoint Status Summary")
cols = st.columns(4)
for col, checkpoint_name in zip(cols, CHECKPOINT_NAMES):
    subset = all_results[all_results["checkpoint_name"] == checkpoint_name]
    total_count = len(subset)
    pass_count = int(subset["success"].sum()) if total_count > 0 else 0
    last_success = subset.loc[subset["success"], "run_time"]
    delta = str(last_success.max()) if not last_success.empty else "never passed"
    col.metric(checkpoint_name, f"{pass_count}/{total_count} passed", delta=delta)

if all_results.empty:
    st.info("No Great Expectations results recorded yet.")
    st.stop()

st.subheader("Pass Rate Over Time")
trend = all_results.copy()
trend["pass_rate"] = trend["successful_expectations"] / trend["evaluated_expectations"].replace(0, pd.NA)
fig = px.line(trend.sort_values("run_time"), x="run_time", y="pass_rate", color="checkpoint_name")
st.plotly_chart(fig, use_container_width=True)

st.subheader("Failed Expectations")
failed = get_failed_results()
if failed.empty:
    st.success("No failed checkpoint runs in the recent history.")
else:
    for _, row in failed.iterrows():
        with st.expander(f"{row['checkpoint_name']} — {row['suite_name']} ({row['run_time']})"):
            st.write(f"Failed expectations: {row['failed_expectations']}")
            st.json(row["details"] if isinstance(row["details"], (dict, list)) else json.loads(row["details"] or "{}"))

st.subheader("Full Results")
st.dataframe(all_results.head(200), use_container_width=True)
