"""PII Audit Log — masking metadata only, never original PII values."""
import pandas as pd
import streamlit as st

from db import get_db_connection

st.title("PII Audit Log")
st.caption("Metadata about PII masking events. No original values stored.")

st.info(
    "ℹ️ This log records masking metadata only. Original PII values are never "
    "stored in Kovalyx. original_length shows the character count of the masked value."
)


@st.cache_data(ttl=60)
def get_masking_summary() -> pd.DataFrame:
    """Aggregates masking event counts and recency by field."""
    conn = get_db_connection()
    return pd.read_sql(
        """
        SELECT field_name, COUNT(*) AS events, MAX(masked_at) AS last_seen,
               AVG(original_length) AS avg_original_length
        FROM audit.kovalyx_pii_audit_log
        GROUP BY field_name
        ORDER BY events DESC
        """,
        conn,
    )


@st.cache_data(ttl=60)
def get_masking_volume() -> pd.DataFrame:
    """Hourly masking event counts over the last 7 days."""
    conn = get_db_connection()
    return pd.read_sql(
        """
        SELECT DATE_TRUNC('hour', masked_at) AS hour, COUNT(*) AS events
        FROM audit.kovalyx_pii_audit_log
        WHERE masked_at > NOW() - INTERVAL '7 days'
        GROUP BY 1
        ORDER BY 1
        """,
        conn,
    )


@st.cache_data(ttl=60)
def get_recent_events(limit: int = 200) -> pd.DataFrame:
    """Returns the most recent masking events."""
    conn = get_db_connection()
    return pd.read_sql(
        """
        SELECT record_id, event_id, field_name, masking_action,
               original_length, pipeline_run_id, masked_at
        FROM audit.kovalyx_pii_audit_log
        ORDER BY masked_at DESC
        LIMIT %(limit)s
        """,
        conn,
        params={"limit": limit},
    )


summary = get_masking_summary()

st.subheader("Masking Summary by Field")
total_events = int(summary["events"].sum()) if not summary.empty else 0
st.metric("Total Masking Events", total_events)
st.dataframe(summary, use_container_width=True)

st.subheader("Masking Volume — Last 7 Days")
volume = get_masking_volume()
if volume.empty:
    st.info("No masking events in the last 7 days.")
else:
    st.line_chart(volume.set_index("hour")["events"])

st.subheader("Recent Masking Events")
st.dataframe(get_recent_events(200), use_container_width=True)
