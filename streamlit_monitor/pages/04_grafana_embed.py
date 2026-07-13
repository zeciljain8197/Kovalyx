"""Grafana Dashboards — live observability dashboards embedded via iframe."""
import streamlit as st
import streamlit.components.v1 as components

from db import get_grafana_base_url

st.title("Grafana Dashboards")
st.caption("Live observability dashboards (embedded from Grafana)")

# Matches the dashboard uids set in monitoring/grafana/dashboards/*.json.
DASHBOARDS = {
    "Pipeline Health": "kovalyx-pipeline-health",
    "Data Quality": "kovalyx-data-quality",
    "Security": "kovalyx-security",
    "Business Metrics": "kovalyx-business-metrics",
}

base_url = get_grafana_base_url()

label = st.selectbox("Select dashboard", list(DASHBOARDS.keys()))
dashboard_uid = DASHBOARDS[label]
url = f"{base_url}/d/{dashboard_uid}?orgId=1&kiosk=tv&refresh=30s"

components.iframe(url, height=800, scrolling=True)

st.caption(
    "If the dashboard doesn't load, ensure Grafana's `allow_embedding = true` is set "
    "in grafana.ini and you are accessing this monitor from the same network."
)
st.markdown(f"Direct link: [{url}]({url})")
