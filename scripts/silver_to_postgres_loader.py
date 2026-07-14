"""
Kovalyx — Silver-to-Gold loader.

Reads Silver Parquet (MinIO) for the target date and loads each table into
its staging schema table in Supabase/postgres-gold — the bridge between
the Silver PySpark layer and dbt.

Usage:
    python silver_to_postgres_loader.py --run-id <uuid> --date <YYYY-MM-DD> --env [dev|prod]

PRE-CHECK 1 FINDING (see the session plan for the full writeup): the
staging tables in scripts/supabase_schema.sql (staging.customers/products/
orders/inventory/events) predate the Session 2 bronze-contract rewrite —
they don't just have different column names than the current Silver
output, some have NOT NULL/PRIMARY KEY constraints on columns Silver no
longer produces, and some Silver columns have no staging column at all.
supabase_schema.sql is intentionally not modified this session, so each
prepare_*_for_staging() function below documents its own reconciliation:
synthetic values where a constraint would otherwise be violated, and
column drops where there's simply nowhere to put a value.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import boto3
import hvac
import pandas as pd
import psycopg2
import pyarrow.parquet as pq
from botocore.client import Config as BotoConfig
from prometheus_client import CollectorRegistry, Counter, Gauge, push_to_gateway
from sqlalchemy import create_engine, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kovalyx.silver_to_postgres_loader")

REPO_ROOT = Path(__file__).resolve().parent.parent
SILVER_BUCKET = "silver"  # real bucket name — see docker-compose.yml minio-init


def get_secret(vault_client: hvac.Client | None, path: str, field_name: str, env_fallback: str) -> str:
    """Strict credential fetch — raises if neither Vault nor the env
    fallback has a value."""
    if vault_client is not None:
        try:
            resp = vault_client.secrets.kv.v2.read_secret_version(mount_point="kovalyx", path=path, raise_on_deleted_version=True)
            value = resp["data"]["data"].get(field_name)
            if value:
                return value
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read kovalyx/%s from Vault (%s); falling back to env var %s", path, exc, env_fallback)
    value = os.environ.get(env_fallback)
    if not value:
        raise RuntimeError(f"No credential available for {path}/{field_name} (checked Vault and env var {env_fallback})")
    return value


def get_secret_or_default(vault_client: hvac.Client | None, path: str, field_name: str, env_fallback: str, default: str) -> str:
    """Lenient fetch for non-secret config with a sensible default."""
    if vault_client is not None:
        try:
            resp = vault_client.secrets.kv.v2.read_secret_version(mount_point="kovalyx", path=path, raise_on_deleted_version=True)
            value = resp["data"]["data"].get(field_name)
            if value:
                return value
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read kovalyx/%s from Vault (%s); falling back to env var %s", path, exc, env_fallback)
    return os.environ.get(env_fallback, default)


def _load_approle_credentials(creds_path: Path, role_name: str) -> tuple[str, str] | None:
    """Reads role_id/secret_id for `role_name` out of the shared
    vault/.approle-credentials.json produced by scripts/vault_init.py."""
    if not creds_path.exists():
        return None
    try:
        data = json.loads(creds_path.read_text())
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not parse AppRole credentials file %s", creds_path, exc_info=True)
        return None
    entry = data.get(role_name)
    if not entry:
        return None
    return entry.get("role_id"), entry.get("secret_id")


def build_vault_client() -> hvac.Client | None:
    """Authenticates via the kovalyx-gold AppRole (the loader is the
    Gold-layer entry point) — role_id from env var or the mounted
    credentials file, secret_id from that same file. Returns None so
    callers fall back to plain env vars for local dev without Vault."""
    vault_addr = os.environ.get("VAULT_ADDR")
    if not vault_addr:
        logger.warning("VAULT_ADDR not set — loader will read credentials from env vars directly")
        return None

    creds_path = Path(os.environ.get("VAULT_APPROLE_CREDS_FILE", str(REPO_ROOT / "vault" / ".approle-credentials.json")))
    loaded = _load_approle_credentials(creds_path, "kovalyx-gold")
    role_id = os.environ.get("VAULT_GOLD_ROLE_ID") or (loaded[0] if loaded else None)
    secret_id = loaded[1] if loaded else None

    if not role_id or not secret_id:
        logger.warning("No AppRole role_id/secret_id available (checked VAULT_GOLD_ROLE_ID and %s) — falling back to env vars", creds_path)
        return None

    client = hvac.Client(url=vault_addr)
    try:
        client.auth.approle.login(role_id=role_id, secret_id=secret_id)
    except Exception:  # noqa: BLE001
        logger.warning("AppRole login failed for kovalyx-gold — falling back to env vars", exc_info=True)
        return None
    return client if client.is_authenticated() else None


def build_minio_client(vault_client: hvac.Client | None):
    """boto3 S3 client against MinIO using the silver secret (the loader
    reads Silver Parquet, so it uses the same read credential the GE
    runner does)."""
    endpoint = get_secret_or_default(vault_client, "minio/silver", "endpoint", "KOVALYX_MINIO_ENDPOINT", "minio:9000")
    access_key = get_secret(vault_client, "minio/silver", "access_key", "MINIO_SILVER_ACCESS_KEY")
    secret_key = get_secret(vault_client, "minio/silver", "secret_key", "MINIO_SILVER_SECRET_KEY")
    endpoint_url = endpoint if endpoint.startswith("http") else f"http://{endpoint}"
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )


def build_pg_conn_params(vault_client: hvac.Client | None) -> dict:
    """Postgres connection params for postgres-gold. Uses the admin
    credential: the pipeline_writer Postgres role has no password set yet
    (supabase_schema.sql leaves it unset by design, to be provisioned out
    of band) — switch this once that password is provisioned in Vault."""
    return {
        "host": get_secret_or_default(vault_client, "postgres/gold", "host", "GOLD_DB_HOST", "postgres-gold"),
        "port": get_secret_or_default(vault_client, "postgres/gold", "port", "GOLD_DB_PORT", "5432"),
        "dbname": get_secret_or_default(vault_client, "postgres/gold", "database", "GOLD_DB_NAME", "kovalyx_gold"),
        "user": get_secret(vault_client, "postgres/gold", "user", "GOLD_DB_USER"),
        "password": get_secret(vault_client, "postgres/gold", "password", "GOLD_DB_PASSWORD"),
    }


def build_engine(pg_conn_params: dict):
    """SQLAlchemy engine (psycopg2 dialect) for the TRUNCATE+to_sql loads."""
    url = f"postgresql+psycopg2://{pg_conn_params['user']}:{pg_conn_params['password']}@{pg_conn_params['host']}:{pg_conn_params['port']}/{pg_conn_params['dbname']}"
    return create_engine(url)


def load_silver_parquet_as_pandas(s3_client, bucket: str, prefix: str) -> pd.DataFrame:
    """Reads every Parquet part file under `prefix` in MinIO into one
    pandas DataFrame via boto3 + pyarrow (same technique as
    quality/run_checkpoints.py).

    Reconstructs Hive-style partition columns (e.g. events/.../
    event_type=order_placed/part-*.parquet) from each key's path — see
    quality/run_checkpoints.py's matching function for why: Spark's
    partitionBy() strips the partition column out of the Parquet file's
    own content and encodes it only in the directory name, so a plain
    pq.read_table() on the raw bytes silently drops it.
    """
    paginator = s3_client.get_paginator("list_objects_v2")
    frames = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".parquet"):
                continue
            body = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
            table = pq.read_table(io.BytesIO(body))
            df = table.to_pandas()
            for segment in key[len(prefix):].split("/")[:-1]:
                if "=" in segment:
                    part_col, part_value = segment.split("=", 1)
                    df[part_col] = part_value
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def prepare_events_for_staging(df: pd.DataFrame) -> pd.DataFrame:
    """staging.events has no NOT NULL constraints beyond event_id/
    event_type/event_timestamp and no column for product_name/category/
    shipping_address/card_last4/card_type/status/stock_level/
    reorder_threshold under the new Silver contract — those are simply
    left unset (all nullable, see Pre-check 1)."""
    if df.empty:
        return df
    return pd.DataFrame(
        {
            "event_id": df["event_id"],
            "event_type": df["event_type"],
            "event_timestamp": df["event_timestamp"],
            "customer_id": df["customer_id"],
            "order_id": df["order_id"],
            "product_id": df["product_id"],
            "quantity": df["quantity"],
            "order_amount": df["order_amount"],
        }
    )


def prepare_customers_for_staging(df: pd.DataFrame) -> pd.DataFrame:
    """total_orders/total_spent have no column in staging.customers at
    all (Pre-check 1) — dropped here; stg_customers.sql exposes them as
    typed NULL placeholders instead of fabricating values."""
    if df.empty:
        return df
    return pd.DataFrame(
        {
            "customer_id": df["customer_id"],
            "full_name": df["customer_name"],
            "email_hash": df["hashed_email"],
            "phone_masked": df["customer_phone"],
            "customer_tier": df["tier"],
            "registered_at": df["registration_date"],
        }
    )


def prepare_products_for_staging(df: pd.DataFrame) -> pd.DataFrame:
    """staging.products.sku is TEXT UNIQUE NOT NULL but the current
    Silver contract no longer produces a sku field (dropped in the
    Session 2 bronze rewrite) — reusing product_id as a synthetic sku so
    the insert doesn't violate the constraint. subcategory/supplier_id/
    current_stock have no column at all — dropped."""
    if df.empty:
        return df
    return pd.DataFrame(
        {
            "product_id": df["product_id"],
            "sku": df["product_id"],  # synthetic — see docstring
            "product_name": df["product_name"],
            "category": df["category"],
            "unit_price": df["unit_price"],
            "cost_price": df["cost_price"],
            "reorder_point": df["reorder_threshold"],
        }
    )


def prepare_orders_for_staging(df: pd.DataFrame) -> pd.DataFrame:
    """staging.orders.order_line_id is the PRIMARY KEY, but Silver orders
    are one row per order now (no line-item concept) — reusing order_id
    as a synthetic order_line_id, which stays unique since Silver's
    orders are already 1:1 on order_id."""
    if df.empty:
        return df
    return pd.DataFrame(
        {
            "order_id": df["order_id"],
            "order_line_id": df["order_id"],  # synthetic — see docstring
            "customer_id": df["customer_id"],
            "product_id": df["product_id"],
            "quantity": df["quantity"],
            "unit_price": df["unit_price"],
            "order_amount": df["order_amount"],
            "order_date": df["order_date"],
            "order_status": df["status"],
        }
    )


def prepare_inventory_for_staging(df: pd.DataFrame) -> pd.DataFrame:
    """warehouse_region is part of staging.inventory's composite PRIMARY
    KEY (snapshot_date, product_id, warehouse_region) but the current
    Silver contract no longer produces it — hardcoding a constant
    'UNKNOWN' value. (snapshot_date, product_id) pairs are already unique
    per Silver's one-row-per-product-per-day grain, so the composite key
    still holds with a constant third column.)"""
    if df.empty:
        return df
    return pd.DataFrame(
        {
            "snapshot_date": df["date"],
            "product_id": df["product_id"],
            "quantity_on_hand": df["stock_level"],
            "reorder_point": df["reorder_threshold"],
            "warehouse_region": "UNKNOWN",  # synthetic — see docstring
        }
    )


TABLE_CONFIG = {
    "events": {"minio_prefix": "events/date={date}/", "staging_table": "events", "prepare_fn": prepare_events_for_staging},
    "customers": {"minio_prefix": "customers/", "staging_table": "customers", "prepare_fn": prepare_customers_for_staging},
    "products": {"minio_prefix": "products/", "staging_table": "products", "prepare_fn": prepare_products_for_staging},
    "orders": {"minio_prefix": "orders/date={date}/", "staging_table": "orders", "prepare_fn": prepare_orders_for_staging},
    "inventory": {"minio_prefix": "inventory/date={date}/", "staging_table": "inventory", "prepare_fn": prepare_inventory_for_staging},
}


def load_table(engine, s3_client, bucket: str, table_key: str, config: dict, target_date: str) -> int:
    """Reads one Silver table, reshapes it for its staging table, and
    loads it inside a single TRUNCATE+INSERT transaction. Returns the
    number of rows loaded (0 if nothing was found for this date)."""
    prefix = config["minio_prefix"].format(date=target_date)
    raw_df = load_silver_parquet_as_pandas(s3_client, bucket, prefix)
    prepared = config["prepare_fn"](raw_df)
    if prepared.empty:
        logger.warning("No Silver data found for table=%s at s3://%s/%s — skipping load", table_key, bucket, prefix)
        return 0

    staging_table = config["staging_table"]
    # TRUNCATE+append chosen for idempotency on scheduled re-runs. Future
    # optimization: use PostgreSQL COPY for bulk load performance at scale.
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE staging.{staging_table} RESTART IDENTITY CASCADE"))
        prepared.to_sql(staging_table, conn, schema="staging", if_exists="append", index=False, method="multi", chunksize=1000)

    logger.info("Loaded %d row(s) into staging.%s", len(prepared), staging_table)
    return len(prepared)


def write_pipeline_audit_log(pg_conn_params: dict, run_id: str, start_time: datetime, end_time: datetime, records_processed: int, records_failed: int, status: str) -> None:
    """Writes/updates the single summary row for this run via psycopg2.
    Uses the postgres/gold admin credential — see build_pg_conn_params()
    for why."""
    conn = psycopg2.connect(**pg_conn_params)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit.kovalyx_pipeline_audit_log
                    (run_id, dag_id, task_id, triggered_by, start_time, end_time,
                     records_processed, records_failed, ge_passed, pii_events_masked, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    end_time = EXCLUDED.end_time,
                    records_processed = EXCLUDED.records_processed,
                    records_failed = EXCLUDED.records_failed,
                    status = EXCLUDED.status
                """,
                (run_id, "silver_to_postgres_loader", "loader_job", "airflow", start_time, end_time, records_processed, records_failed, None, 0, status),
            )
    finally:
        conn.close()


def push_metrics(registry: CollectorRegistry) -> None:
    """No-op unless PROMETHEUS_PUSHGATEWAY_URL is set."""
    pushgateway_url = os.environ.get("PROMETHEUS_PUSHGATEWAY_URL")
    if not pushgateway_url:
        return
    try:
        push_to_gateway(pushgateway_url, job="kovalyx_silver_to_postgres_loader", registry=registry)
    except Exception:  # noqa: BLE001
        logger.warning("Failed to push metrics to pushgateway at %s", pushgateway_url, exc_info=True)


def main() -> int:
    """Entry point: python silver_to_postgres_loader.py --run-id <uuid> --date <YYYY-MM-DD> --env [dev|prod]."""
    parser = argparse.ArgumentParser(description="Kovalyx Silver-to-Gold staging loader")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--date", default=None, help="YYYY-MM-DD, defaults to yesterday")
    parser.add_argument("--env", choices=["dev", "prod"], default="dev")
    args = parser.parse_args()

    target_date = args.date or (date.today() - timedelta(days=1)).isoformat()
    start_time = datetime.now(timezone.utc)

    registry = CollectorRegistry()
    records_written_metric = Counter("kovalyx_loader_records_written_total", "Rows loaded per staging table", ["table"], registry=registry)
    duration_metric = Gauge("kovalyx_loader_duration_seconds", "Wall-clock duration of the loader job", registry=registry)

    vault_client = build_vault_client()
    s3_client = build_minio_client(vault_client)
    pg_conn_params = build_pg_conn_params(vault_client)
    engine = build_engine(pg_conn_params)

    records_processed = 0
    records_failed = 0

    try:
        for table_key, config in TABLE_CONFIG.items():
            try:
                written = load_table(engine, s3_client, SILVER_BUCKET, table_key, config, target_date)
                records_processed += written
                records_written_metric.labels(table=table_key).inc(written)
            except Exception:  # noqa: BLE001
                logger.exception("Loading table=%s failed — continuing with remaining tables", table_key)
                records_failed += 1

        end_time = datetime.now(timezone.utc)
        duration_metric.set((end_time - start_time).total_seconds())
        write_pipeline_audit_log(pg_conn_params, args.run_id, start_time, end_time, records_processed, records_failed, status="success")
        push_metrics(registry)

        logger.info("Loader complete: run_id=%s date=%s processed=%d failed=%d", args.run_id, target_date, records_processed, records_failed)
        return 0

    except Exception:  # noqa: BLE001
        logger.exception("Unhandled failure in Silver-to-Gold loader (run_id=%s)", args.run_id)
        end_time = datetime.now(timezone.utc)
        try:
            write_pipeline_audit_log(pg_conn_params, args.run_id, start_time, end_time, records_processed, records_failed, status="failed")
        except Exception:  # noqa: BLE001
            logger.exception("Also failed to write the failure audit row")
        push_metrics(registry)
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
