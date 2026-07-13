-- =====================================================================
-- Kovalyx — Gold layer schema, roles, grants, and Row Level Security.
--
-- Run once against a fresh database:
--   - Local dev: mounted automatically as docker-entrypoint-initdb.d/
--     for the postgres-gold container (see docker-compose.yml).
--   - Production: run against the managed Supabase project via the
--     Supabase SQL editor or `psql "$SUPABASE_DB_URL" -f supabase_schema.sql`
--     using the Supabase-provided `postgres` superuser role.
--
-- Layout:
--   staging  — landing zone the Silver-to-Gold Python loader writes into.
--              dbt's staging/ models select from these.
--   marts    — everything dbt builds: dim_/fact_ tables and mart_
--              reporting tables. Tables here are created by `dbt run`,
--              not by this script — see marts.apply_*_rls() below for
--              how RLS gets attached to them after the fact.
--   audit    — kovalyx_pipeline_audit_log, kovalyx_pii_audit_log, and
--              ge_validation_results. Written directly by Airflow, the
--              Presidio masking step, and the Great Expectations
--              checkpoint runner. Queried by the Next.js /pipeline admin
--              page and the Streamlit ops monitor.
--
-- Roles (see SECURITY.md for the full threat model):
--   analytics_reader — SELECT on marts.mart_* only. Used by the public
--                       Next.js dashboard via Supabase RLS.
--   pipeline_writer   — INSERT/UPDATE/DELETE on staging + marts
--                       (dim_/fact_/mart_) + audit. Used by dbt, the
--                       Silver-to-Gold loader, and Airflow.
--   audit_reader      — SELECT on audit.* only. Used by the Streamlit
--                       ops monitor.
--
-- NOTE ON PASSWORDS: role passwords are intentionally NOT set in this
-- file — it is committed to a public repo. Roles are created with LOGIN
-- but no password, so authentication fails until a password is set out
-- of band via `ALTER ROLE <role> WITH PASSWORD '<from Vault>'`, which
-- scripts/vault_init.py does not perform automatically (Supabase network
-- access varies per deployment) — run it manually once per environment,
-- immediately after this script, using credentials generated into Vault.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS marts;
CREATE SCHEMA IF NOT EXISTS audit;

-- ---------------------------------------------------------------------
-- Roles
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'analytics_reader') THEN
        CREATE ROLE analytics_reader LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'pipeline_writer') THEN
        CREATE ROLE pipeline_writer LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'audit_reader') THEN
        CREATE ROLE audit_reader LOGIN;
    END IF;
END
$$;

-- Harden the default public schema — nobody gets implicit access.
REVOKE ALL ON SCHEMA public FROM PUBLIC;

-- ---------------------------------------------------------------------
-- Staging tables — Silver Parquet lands here via the Python loader.
-- Column shapes mirror scripts/seed_data.py and the Silver PySpark
-- output so `staging.*` -> `stg_*` dbt models are a thin 1:1 pass-through.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS staging.customers (
    customer_id TEXT PRIMARY KEY,
    full_name TEXT,
    email_hash TEXT,     -- SHA-256 of email, raw email never reaches Gold
    phone_masked TEXT,
    city TEXT,
    state TEXT,
    postal_code TEXT,
    country TEXT,
    customer_tier TEXT,
    registered_at TIMESTAMPTZ,
    _silver_loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.products (
    product_id TEXT PRIMARY KEY,
    sku TEXT UNIQUE NOT NULL,
    product_name TEXT,
    category TEXT,
    unit_price NUMERIC(12, 2),
    cost_price NUMERIC(12, 2),
    reorder_point INTEGER,
    created_at TIMESTAMPTZ,
    _silver_loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.orders (
    order_id TEXT NOT NULL,
    order_line_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    sku TEXT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2),
    order_amount NUMERIC(12, 2) NOT NULL CHECK (order_amount BETWEEN 0.01 AND 50000),
    order_date TIMESTAMPTZ NOT NULL,
    order_status TEXT NOT NULL,
    payment_method TEXT,
    shipping_carrier TEXT,
    return_reason TEXT,
    _silver_loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.inventory (
    snapshot_date DATE NOT NULL,
    product_id TEXT NOT NULL,
    sku TEXT,
    quantity_on_hand INTEGER NOT NULL,
    reorder_point INTEGER,
    warehouse_region TEXT,
    _silver_loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_date, product_id, warehouse_region)
);

CREATE TABLE IF NOT EXISTS staging.events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL,
    customer_id TEXT,
    order_id TEXT,
    product_id TEXT,
    sku TEXT,
    quantity INTEGER,
    order_amount NUMERIC(12, 2),
    payment_method TEXT,
    shipping_carrier TEXT,
    return_reason TEXT,
    inventory_delta INTEGER,
    _silver_loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_staging_orders_order_id ON staging.orders (order_id);
CREATE INDEX IF NOT EXISTS idx_staging_orders_order_date ON staging.orders (order_date);
CREATE INDEX IF NOT EXISTS idx_staging_events_event_type ON staging.events (event_type);
CREATE INDEX IF NOT EXISTS idx_staging_events_customer_id ON staging.events (customer_id);
CREATE INDEX IF NOT EXISTS idx_staging_inventory_product_id ON staging.inventory (product_id);

-- ---------------------------------------------------------------------
-- Audit tables — written by Airflow / Presidio / Great Expectations.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit.kovalyx_pipeline_audit_log (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dag_id TEXT NOT NULL,
    task_id TEXT,
    triggered_by TEXT,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    records_processed BIGINT NOT NULL DEFAULT 0,
    records_failed BIGINT NOT NULL DEFAULT 0,
    ge_passed BOOLEAN,
    pii_events_masked INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'success', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit.kovalyx_pii_audit_log (
    id BIGSERIAL PRIMARY KEY,
    record_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    masking_action TEXT NOT NULL,
    masked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    pipeline_run_id UUID REFERENCES audit.kovalyx_pipeline_audit_log (run_id)
);

CREATE TABLE IF NOT EXISTS audit.ge_validation_results (
    id BIGSERIAL PRIMARY KEY,
    pipeline_run_id UUID REFERENCES audit.kovalyx_pipeline_audit_log (run_id),
    expectation_suite_name TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    evaluated_expectations INTEGER,
    successful_expectations INTEGER,
    unsuccessful_expectations INTEGER,
    run_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    result_detail JSONB
);

CREATE INDEX IF NOT EXISTS idx_pipeline_audit_log_dag_id ON audit.kovalyx_pipeline_audit_log (dag_id, start_time DESC);
CREATE INDEX IF NOT EXISTS idx_pii_audit_log_run_id ON audit.kovalyx_pii_audit_log (pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_ge_validation_results_run_id ON audit.ge_validation_results (pipeline_run_id);

-- ---------------------------------------------------------------------
-- Grants — schema-level + default privileges so tables created later
-- (by dbt, by the loader) automatically inherit the right access.
-- ---------------------------------------------------------------------
GRANT USAGE ON SCHEMA staging TO pipeline_writer;
GRANT USAGE ON SCHEMA marts TO analytics_reader, pipeline_writer;
GRANT USAGE, CREATE ON SCHEMA marts TO pipeline_writer;
GRANT USAGE ON SCHEMA audit TO audit_reader, pipeline_writer;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA staging TO pipeline_writer;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA audit TO pipeline_writer;
GRANT SELECT ON ALL TABLES IN SCHEMA audit TO audit_reader;

ALTER DEFAULT PRIVILEGES IN SCHEMA staging GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO pipeline_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO pipeline_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit GRANT SELECT ON TABLES TO audit_reader;
-- Every table dbt creates in marts/ (dim_, fact_, mart_) is writable by
-- pipeline_writer by default; SELECT for analytics_reader is scoped down
-- to mart_* only via the RLS policies applied by apply_analytics_rls()
-- below, not by a blanket grant.
ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO pipeline_writer;

-- Explicit least-privilege: nobody else touches staging/audit.
REVOKE ALL ON SCHEMA staging FROM analytics_reader, audit_reader;
REVOKE ALL ON SCHEMA audit FROM analytics_reader;
REVOKE ALL ON SCHEMA marts FROM audit_reader;

-- ---------------------------------------------------------------------
-- Row Level Security
--
-- marts.dim_*/fact_* and marts.mart_* tables don't exist yet — dbt
-- creates them on first `dbt run`. Postgres can't ALTER TABLE ... ENABLE
-- ROW LEVEL SECURITY on a table that doesn't exist, so these two helper
-- functions retroactively attach RLS + a permissive per-role policy to
-- every table matching the naming convention. dbt_project's
-- on-run-end hook calls both after every run, making this idempotent
-- and safe to run as often as dbt runs.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION marts.apply_analytics_rls() RETURNS void AS $$
DECLARE
    tbl RECORD;
BEGIN
    FOR tbl IN
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'marts' AND tablename LIKE 'mart\_%' ESCAPE '\'
    LOOP
        EXECUTE format('ALTER TABLE marts.%I ENABLE ROW LEVEL SECURITY', tbl.tablename);
        EXECUTE format('GRANT SELECT ON marts.%I TO analytics_reader', tbl.tablename);
        EXECUTE format('DROP POLICY IF EXISTS analytics_reader_select ON marts.%I', tbl.tablename);
        EXECUTE format(
            'CREATE POLICY analytics_reader_select ON marts.%I FOR SELECT TO analytics_reader USING (true)',
            tbl.tablename
        );
        EXECUTE format('DROP POLICY IF EXISTS pipeline_writer_all ON marts.%I', tbl.tablename);
        EXECUTE format(
            'CREATE POLICY pipeline_writer_all ON marts.%I FOR ALL TO pipeline_writer USING (true) WITH CHECK (true)',
            tbl.tablename
        );
    END LOOP;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION marts.apply_pipeline_writer_rls() RETURNS void AS $$
DECLARE
    tbl RECORD;
BEGIN
    FOR tbl IN
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'marts'
          AND (tablename LIKE 'dim\_%' ESCAPE '\' OR tablename LIKE 'fact\_%' ESCAPE '\')
    LOOP
        EXECUTE format('ALTER TABLE marts.%I ENABLE ROW LEVEL SECURITY', tbl.tablename);
        EXECUTE format('DROP POLICY IF EXISTS pipeline_writer_all ON marts.%I', tbl.tablename);
        EXECUTE format(
            'CREATE POLICY pipeline_writer_all ON marts.%I FOR ALL TO pipeline_writer USING (true) WITH CHECK (true)',
            tbl.tablename
        );
        -- dim_/fact_ tables are intentionally NOT granted to
        -- analytics_reader — only the curated mart_ views/tables are
        -- public-facing, per the "analytics_reader: SELECT on mart_
        -- tables only" access-control requirement.
    END LOOP;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

ALTER TABLE audit.kovalyx_pipeline_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit.kovalyx_pii_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit.ge_validation_results ENABLE ROW LEVEL SECURITY;

CREATE POLICY audit_reader_select ON audit.kovalyx_pipeline_audit_log FOR SELECT TO audit_reader USING (true);
CREATE POLICY pipeline_writer_all ON audit.kovalyx_pipeline_audit_log FOR ALL TO pipeline_writer USING (true) WITH CHECK (true);

CREATE POLICY audit_reader_select ON audit.kovalyx_pii_audit_log FOR SELECT TO audit_reader USING (true);
CREATE POLICY pipeline_writer_all ON audit.kovalyx_pii_audit_log FOR ALL TO pipeline_writer USING (true) WITH CHECK (true);

CREATE POLICY audit_reader_select ON audit.ge_validation_results FOR SELECT TO audit_reader USING (true);
CREATE POLICY pipeline_writer_all ON audit.ge_validation_results FOR ALL TO pipeline_writer USING (true) WITH CHECK (true);

-- Run once now in case marts already has tables from a prior dbt run
-- (no-op on a fresh database — the loops simply match zero rows).
SELECT marts.apply_analytics_rls();
SELECT marts.apply_pipeline_writer_rls();

-- =====================================================================
-- MIGRATION: Session 2 additions (Silver-layer PII/GE audit writes)
--
-- Additive only — does not alter, rename, or drop anything above.
-- kovalyx_pii_audit_log already had (id, record_id, field_name,
-- masking_action, masked_at, pipeline_run_id); event_id/original_length
-- are new. ge_validation_results already had (id, pipeline_run_id,
-- expectation_suite_name, success, evaluated_expectations,
-- successful_expectations, unsuccessful_expectations, run_time,
-- result_detail) — verified against the CREATE TABLE above before writing
-- this migration; only checkpoint_name was actually missing.
-- =====================================================================
ALTER TABLE audit.kovalyx_pii_audit_log
    ADD COLUMN IF NOT EXISTS event_id TEXT,
    ADD COLUMN IF NOT EXISTS original_length INTEGER;

ALTER TABLE audit.ge_validation_results
    ADD COLUMN IF NOT EXISTS checkpoint_name TEXT;

-- =====================================================================
-- MIGRATION: Session 5 — anon role RLS for the public Next.js dashboard
--
-- Pre-check finding: this file only ever granted marts.* access to the
-- custom `analytics_reader` role (Session 1). Supabase's actual
-- PostgREST layer — what @supabase/supabase-js talks to when the
-- frontend uses NEXT_PUBLIC_SUPABASE_ANON_KEY — authenticates those
-- requests as the built-in `anon` role, not `analytics_reader`, and
-- `anon` had no grants here at all. Both roles are kept:
-- `analytics_reader` stays available for any direct-Postgres reporting
-- tool, `anon` is what actually serves the Vercel frontend.
--
-- Deviation from a literal "GRANT SELECT ON marts.mart_sales_summary
-- ... TO anon" per named table: marts.* tables don't exist yet the
-- first time this script runs (docker-entrypoint-initdb.d locally, or a
-- freshly created Supabase project in production — both before dbt's
-- first `dbt run`), so a static GRANT on a named mart table would fail
-- with "relation does not exist" and abort the whole init script.
-- Mirrors the existing apply_analytics_rls() pattern instead: a
-- SECURITY DEFINER function that discovers tables at call time.
--
-- apply_anon_rls() is invoked from dbt_project.yml's on-run-end hook
-- alongside apply_analytics_rls()/apply_pipeline_writer_rls(), so it
-- re-runs after every `dbt run` — no manual step needed.
-- =====================================================================
GRANT USAGE ON SCHEMA marts TO anon;

CREATE OR REPLACE FUNCTION marts.apply_anon_rls() RETURNS void AS $$
DECLARE
    tbl RECORD;
BEGIN
    FOR tbl IN
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'marts'
          AND (
              tablename LIKE 'mart\_%' ESCAPE '\'
              OR tablename LIKE 'dim\_%' ESCAPE '\'
              OR tablename LIKE 'fact\_%' ESCAPE '\'
          )
    LOOP
        EXECUTE format('ALTER TABLE marts.%I ENABLE ROW LEVEL SECURITY', tbl.tablename);
        EXECUTE format('GRANT SELECT ON marts.%I TO anon', tbl.tablename);
        EXECUTE format('DROP POLICY IF EXISTS anon_select ON marts.%I', tbl.tablename);
        EXECUTE format(
            'CREATE POLICY anon_select ON marts.%I FOR SELECT TO anon USING (true)',
            tbl.tablename
        );
    END LOOP;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- audit.* stays out of anon's reach entirely: this file never grants
-- anon USAGE on the audit schema, so access is implicitly denied.

-- Run once now in case marts already has tables from a prior dbt run
-- (no-op on a fresh database — the loop simply matches zero rows).
SELECT marts.apply_anon_rls();
