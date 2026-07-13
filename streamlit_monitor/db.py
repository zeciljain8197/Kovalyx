"""Shared DB connection helper for streamlit_monitor's app.py and pages/.

Not one of the named deliverables, but factored out rather than
duplicated across app.py + 4 page scripts — Streamlit's multipage app
model runs each pages/*.py as an independent script, so without a shared
module this credential-loading logic (and its st.secrets/env-var
fallback) would need to be copy-pasted five times.
"""
import os

import psycopg2
import streamlit as st


@st.cache_resource
def get_db_connection():
    """Opens a read-only, autocommit psycopg2 connection to postgres-gold.

    Tries st.secrets["supabase"] first (Streamlit Community Cloud secrets
    management). Falls back to the environment variables actually injected
    by docker-compose.yml's streamlit-monitor service for local dev —
    GOLD_DB_HOST/PORT/NAME + AUDIT_READER_DB_USER/PASSWORD. Vault is
    intentionally never used here — Streamlit Community Cloud can't reach it.
    """
    host = port = database = user = password = None

    try:
        cfg = st.secrets["supabase"]
        host = cfg["host"]
        port = cfg["port"]
        database = cfg["database"]
        user = cfg["user"]
        password = cfg["password"]
    except Exception:
        host = os.environ.get("GOLD_DB_HOST")
        port = os.environ.get("GOLD_DB_PORT", "5432")
        database = os.environ.get("GOLD_DB_NAME")
        user = os.environ.get("AUDIT_READER_DB_USER")
        password = os.environ.get("AUDIT_READER_DB_PASSWORD")

    if not all([host, database, user, password]):
        st.error(
            "Database credentials are not configured. Set st.secrets['supabase'] "
            "(Streamlit Cloud) or GOLD_DB_HOST/GOLD_DB_PORT/GOLD_DB_NAME/"
            "AUDIT_READER_DB_USER/AUDIT_READER_DB_PASSWORD (local docker compose)."
        )
        st.stop()

    conn = psycopg2.connect(host=host, port=port, dbname=database, user=user, password=password)
    conn.set_session(readonly=True, autocommit=True)
    return conn


def get_grafana_base_url() -> str:
    """Resolves the Grafana base URL for iframe embeds.

    st.secrets["app"]["grafana_base_url"] first, then the GRAFANA_EMBED_URL
    env var docker-compose.yml's streamlit-monitor service actually sets
    (not GRAFANA_BASE_URL, which a generic spec might assume), defaulting
    to the dev-mode Nginx path.
    """
    try:
        return st.secrets["app"]["grafana_base_url"]
    except Exception:
        return os.environ.get("GRAFANA_EMBED_URL", "http://localhost:8090/grafana")
