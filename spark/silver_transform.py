"""
Kovalyx — Silver layer PySpark job.

Reads Bronze (raw NDJSON streaming events + batch CSVs) from MinIO,
cleanses/conforms/dedupes, masks PII via spark/pii_masking.py, validates
against the bronze contract, and writes Parquet to the MinIO Silver zone.
Every run writes one audit row to postgres-gold's
audit.kovalyx_pipeline_audit_log and flushes PresidioMasker's PII audit
trail to audit.kovalyx_pii_audit_log.

Usage:
    spark-submit silver_transform.py --run-id <uuid> --date <YYYY-MM-DD> --env [dev|prod]

Bucket names: MinIO buckets are literally named "bronze"/"silver"/"gold"
(see docker-compose.yml's minio-init service — the "kovalyx" prefix seen
in some documentation is the `mc` CLI alias name, not a bucket prefix).
This module treats docker-compose.yml as the single source of truth for
those names rather than any spec text that suggests otherwise.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import hvac
import psycopg2
from prometheus_client import CollectorRegistry, Counter, Gauge, push_to_gateway
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DateType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)
from pyspark.sql.utils import AnalysisException
from pyspark.sql.window import Window

from pii_masking import PresidioMasker

logging.basicConfig(
    level=logging.WARN,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kovalyx.silver_transform")
logger.setLevel(logging.INFO)

REPO_ROOT = Path(__file__).resolve().parent.parent

# Real bucket names created by minio-init in docker-compose.yml.
BRONZE_BUCKET = "bronze"
SILVER_BUCKET = "silver"

# ---------------------------------------------------------------------
# Explicit Bronze/Silver schemas.
#
# Streaming events arrive as genuine JSON (numbers aren't quoted), so
# numeric fields use their real numeric types here — only event_timestamp
# needs an explicit string->timestamp cast downstream. Batch CSVs are all
# StringType by design: CSV is inherently text, and reading everything as
# a string then casting explicitly in the transform step (rather than
# letting Spark's CSV reader silently null malformed numeric values) makes
# bad source data fail loudly instead of disappearing.
# ---------------------------------------------------------------------
STREAMING_EVENT_SCHEMA = StructType(
    [
        StructField("event_id", StringType(), True),
        StructField("event_type", StringType(), True),
        StructField("event_timestamp", StringType(), True),
        StructField("order_id", StringType(), True),
        StructField("customer_id", StringType(), True),
        StructField("customer_name", StringType(), True),
        StructField("customer_email", StringType(), True),
        StructField("customer_phone", StringType(), True),
        StructField("product_id", StringType(), True),
        StructField("product_name", StringType(), True),
        StructField("category", StringType(), True),
        StructField("quantity", IntegerType(), True),
        StructField("unit_price", DoubleType(), True),
        StructField("order_amount", DoubleType(), True),
        StructField("shipping_address", StringType(), True),
        StructField("card_last4", StringType(), True),
        StructField("card_type", StringType(), True),
        StructField("status", StringType(), True),
        StructField("stock_level", IntegerType(), True),
        StructField("reorder_threshold", IntegerType(), True),
    ]
)

CUSTOMERS_SCHEMA = StructType(
    [
        StructField("customer_id", StringType(), True),
        StructField("customer_name", StringType(), True),
        StructField("customer_email", StringType(), True),
        StructField("customer_phone", StringType(), True),
        StructField("shipping_address", StringType(), True),
        StructField("registration_date", StringType(), True),
        StructField("tier", StringType(), True),
        StructField("total_orders", StringType(), True),
        StructField("total_spent", StringType(), True),
    ]
)

PRODUCTS_SCHEMA = StructType(
    [
        StructField("product_id", StringType(), True),
        StructField("product_name", StringType(), True),
        StructField("category", StringType(), True),
        StructField("subcategory", StringType(), True),
        StructField("unit_price", StringType(), True),
        StructField("cost_price", StringType(), True),
        StructField("supplier_id", StringType(), True),
        StructField("reorder_threshold", StringType(), True),
        StructField("current_stock", StringType(), True),
    ]
)

ORDERS_SCHEMA = StructType(
    [
        StructField("order_id", StringType(), True),
        StructField("customer_id", StringType(), True),
        StructField("product_id", StringType(), True),
        StructField("quantity", StringType(), True),
        StructField("unit_price", StringType(), True),
        StructField("order_amount", StringType(), True),
        StructField("order_date", StringType(), True),
        StructField("status", StringType(), True),
        StructField("shipping_address", StringType(), True),
        StructField("card_last4", StringType(), True),
        StructField("card_type", StringType(), True),
    ]
)

INVENTORY_SCHEMA = StructType(
    [
        StructField("inventory_id", StringType(), True),
        StructField("product_id", StringType(), True),
        StructField("date", StringType(), True),
        StructField("stock_level", StringType(), True),
        StructField("reorder_threshold", StringType(), True),
        StructField("units_sold", StringType(), True),
        StructField("units_received", StringType(), True),
    ]
)


def get_secret(vault_client: hvac.Client | None, path: str, field_name: str, env_fallback: str) -> str:
    """Strict credential fetch — raises if neither Vault nor the env
    fallback has a value. Use for true secrets (passwords, access keys)."""
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
    """Lenient fetch for non-secret config (hostnames, ports) that has a
    sensible default and shouldn't ever raise."""
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
    """Authenticates to Vault via the kovalyx-silver AppRole (role_id from
    env var or the mounted credentials file, secret_id from that same
    file), or returns None so callers fall back to plain env vars for
    local dev without Vault running."""
    vault_addr = os.environ.get("VAULT_ADDR")
    if not vault_addr:
        logger.warning("VAULT_ADDR not set — Silver job will read credentials from env vars directly")
        return None

    creds_path = Path(os.environ.get("VAULT_APPROLE_CREDS_FILE", str(REPO_ROOT / "vault" / ".approle-credentials.json")))
    loaded = _load_approle_credentials(creds_path, "kovalyx-silver")
    role_id = os.environ.get("VAULT_SILVER_ROLE_ID") or (loaded[0] if loaded else None)
    secret_id = loaded[1] if loaded else None

    if not role_id or not secret_id:
        logger.warning(
            "No AppRole role_id/secret_id available (checked VAULT_SILVER_ROLE_ID and %s) — falling back to env vars",
            creds_path,
        )
        return None

    client = hvac.Client(url=vault_addr)
    try:
        client.auth.approle.login(role_id=role_id, secret_id=secret_id)
    except Exception:  # noqa: BLE001
        logger.warning("AppRole login failed for kovalyx-silver — falling back to env vars", exc_info=True)
        return None
    return client if client.is_authenticated() else None


def build_spark_session(minio_endpoint: str, minio_access_key: str, minio_secret_key: str) -> SparkSession:
    """Builds the SparkSession with S3A configured for MinIO. Dynamic
    allocation is disabled for predictable, reproducible executor counts
    on every run."""
    endpoint_url = minio_endpoint if minio_endpoint.startswith("http") else f"http://{minio_endpoint}"
    spark = (
        SparkSession.builder.appName("kovalyx-silver-transform")
        .config("spark.hadoop.fs.s3a.endpoint", endpoint_url)
        .config("spark.hadoop.fs.s3a.access.key", minio_access_key)
        .config("spark.hadoop.fs.s3a.secret.key", minio_secret_key)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .config("spark.dynamicAllocation.enabled", "false")
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


def read_streaming_events(spark: SparkSession, target_date: str) -> DataFrame:
    """Reads every NDJSON object written by ingestion/kafka_consumer.py
    for `target_date` across all event_type partitions in one glob read."""
    path = f"s3a://{BRONZE_BUCKET}/event_type=*/date={target_date}/*.json"
    try:
        return spark.read.schema(STREAMING_EVENT_SCHEMA).json(path)
    except AnalysisException:
        logger.warning("No streaming event files found at %s", path)
        return spark.createDataFrame([], STREAMING_EVENT_SCHEMA)


def read_batch_csv(spark: SparkSession, entity: str, schema: StructType) -> DataFrame:
    """Reads scripts/seed_data.py's batch/<entity>/<entity>.csv upload."""
    path = f"s3a://{BRONZE_BUCKET}/batch/{entity}/{entity}.csv"
    try:
        return spark.read.schema(schema).option("header", True).csv(path)
    except AnalysisException:
        logger.warning("No batch file found at %s", path)
        return spark.createDataFrame([], schema)


def transform_streaming_events(events_df: DataFrame, target_date: str, masker: PresidioMasker) -> tuple[DataFrame, int, int]:
    """Casts/dedupes/filters the streaming events DataFrame and applies
    PII masking. Returns (masked_df, rows_written, rows_dropped).

    Dropping rows with a null order_id necessarily also drops
    inventory_updated and customer_registered events (both have order_id
    = null by the bronze contract) from this Silver events table — that's
    the literal, deliberate consequence of the null-key drop rule.
    Inventory state is tracked via the separate inventory.csv pathway
    instead, so this doesn't lose any inventory signal, just excludes
    non-order events from the order/customer-event grain of this table.
    """
    df = (
        events_df.withColumn("event_timestamp", F.to_timestamp("event_timestamp"))
        .withColumn("order_amount", F.col("order_amount").cast(DoubleType()))
        .withColumn("unit_price", F.col("unit_price").cast(DoubleType()))
        .withColumn("quantity", F.col("quantity").cast(IntegerType()))
        .withColumn("ingestion_date", F.lit(target_date).cast(DateType()))
        .withColumn("silver_processed_at", F.current_timestamp())
    )

    dedup_window = Window.partitionBy("event_id", "event_type").orderBy(F.col("event_timestamp").asc())
    df = df.withColumn("_rn", F.row_number().over(dedup_window)).where(F.col("_rn") == 1).drop("_rn")

    before_drop = df.count()
    df = df.where(F.col("event_id").isNotNull() & F.col("order_id").isNotNull() & F.col("customer_id").isNotNull())
    after_drop = df.count()
    dropped = before_drop - after_drop
    if dropped:
        logger.warning("Dropped %d streaming event row(s) with null event_id/order_id/customer_id", dropped)

    df = masker.mask_dataframe(df, event_type="streaming_events")
    return df, after_drop, dropped


def transform_customers(customers_df: DataFrame, masker: PresidioMasker) -> DataFrame:
    """Casts registration_date/total_spent/total_orders and null-invalidates
    any tier value outside (bronze, silver, gold) before masking."""
    df = (
        customers_df.withColumn("registration_date", F.to_date("registration_date"))
        .withColumn("total_spent", F.col("total_spent").cast(DoubleType()))
        .withColumn("total_orders", F.col("total_orders").cast(IntegerType()))
        .withColumn("tier", F.when(F.col("tier").isin("bronze", "silver", "gold"), F.col("tier")).otherwise(F.lit(None).cast(StringType())))
    )
    return masker.mask_dataframe(df, event_type="customers")


def transform_products(products_df: DataFrame) -> tuple[DataFrame, int]:
    """Casts numeric columns and drops rows with a null product_id.
    Returns (transformed_df, rows_dropped)."""
    before = products_df.count()
    df = (
        products_df.withColumn("unit_price", F.col("unit_price").cast(DoubleType()))
        .withColumn("cost_price", F.col("cost_price").cast(DoubleType()))
        .withColumn("reorder_threshold", F.col("reorder_threshold").cast(IntegerType()))
        .withColumn("current_stock", F.col("current_stock").cast(IntegerType()))
        .where(F.col("product_id").isNotNull())
    )
    after = df.count()
    return df, before - after


def transform_orders(orders_df: DataFrame, masker: PresidioMasker) -> DataFrame:
    """Casts order_date/order_amount/unit_price/quantity and masks
    shipping_address only — customer PII is masked once in the customers
    table, not re-masked here."""
    df = (
        orders_df.withColumn("order_date", F.to_date("order_date"))
        .withColumn("order_amount", F.col("order_amount").cast(DoubleType()))
        .withColumn("unit_price", F.col("unit_price").cast(DoubleType()))
        .withColumn("quantity", F.col("quantity").cast(IntegerType()))
    )
    return masker.mask_dataframe(df, event_type="orders")


def transform_inventory(inventory_df: DataFrame) -> tuple[DataFrame, int]:
    """Casts numeric columns and drops rows with a null product_id or
    date. Returns (transformed_df, rows_dropped)."""
    before = inventory_df.count()
    df = (
        inventory_df.withColumn("date", F.to_date("date"))
        .withColumn("stock_level", F.col("stock_level").cast(IntegerType()))
        .withColumn("reorder_threshold", F.col("reorder_threshold").cast(IntegerType()))
        .withColumn("units_sold", F.col("units_sold").cast(IntegerType()))
        .withColumn("units_received", F.col("units_received").cast(IntegerType()))
        .where(F.col("product_id").isNotNull() & F.col("date").isNotNull())
    )
    after = df.count()
    return df, before - after


def write_parquet(df: DataFrame, path: str, partition_by: str | None = None) -> None:
    """Idempotent overwrite write — safe to re-run the same --date twice."""
    writer = df.write.mode("overwrite").option("compression", "snappy")
    if partition_by:
        writer = writer.partitionBy(partition_by)
    writer.parquet(path)


def write_pipeline_audit_log(pg_conn_params: dict, run_id: str, start_time: datetime, end_time: datetime, records_processed: int, records_failed: int, pii_events_masked: int, status: str) -> None:
    """Writes/updates the single summary row for this run via psycopg2 —
    plain Python is simpler than a one-row Spark JDBC write here. Uses the
    postgres/gold admin credential: the pipeline_writer Postgres role has
    no password set yet (supabase_schema.sql leaves it unset by design, to
    be provisioned out of band), so the admin credential is the only
    currently-usable one — switch this to pipeline_writer once that
    password is provisioned in Vault."""
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
                    pii_events_masked = EXCLUDED.pii_events_masked,
                    status = EXCLUDED.status
                """,
                (run_id, "silver_transform", "pyspark_job", "airflow", start_time, end_time, records_processed, records_failed, None, pii_events_masked, status),
            )
    finally:
        conn.close()


def push_metrics(registry: CollectorRegistry) -> None:
    """No-op unless PROMETHEUS_PUSHGATEWAY_URL is set — Spark batch jobs
    aren't long-lived scrape targets, so they push instead."""
    pushgateway_url = os.environ.get("PROMETHEUS_PUSHGATEWAY_URL")
    if not pushgateway_url:
        return
    try:
        push_to_gateway(pushgateway_url, job="kovalyx_silver_transform", registry=registry)
    except Exception:  # noqa: BLE001
        logger.warning("Failed to push metrics to pushgateway at %s", pushgateway_url, exc_info=True)


def main() -> int:
    """Entry point: spark-submit silver_transform.py --run-id <uuid> --date <YYYY-MM-DD> --env [dev|prod]."""
    parser = argparse.ArgumentParser(description="Kovalyx Silver layer transform")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--date", default=None, help="YYYY-MM-DD, defaults to yesterday")
    parser.add_argument("--env", choices=["dev", "prod"], default="dev")
    args = parser.parse_args()

    target_date = args.date or (date.today() - timedelta(days=1)).isoformat()
    start_time = datetime.now(timezone.utc)

    registry = CollectorRegistry()
    records_processed_metric = Counter("kovalyx_silver_records_processed_total", "Rows written per Silver table", ["table"], registry=registry)
    records_failed_metric = Counter("kovalyx_silver_records_failed_total", "Rows dropped per Silver table", ["table", "reason"], registry=registry)
    pii_masked_metric = Counter("kovalyx_silver_pii_events_masked_total", "PII values masked this run", registry=registry)
    duration_metric = Gauge("kovalyx_silver_job_duration_seconds", "Wall-clock duration of the Silver transform job", registry=registry)

    vault_client = build_vault_client()
    minio_endpoint = get_secret_or_default(vault_client, "minio/silver", "endpoint", "KOVALYX_MINIO_ENDPOINT", "minio:9000")
    minio_access_key = get_secret(vault_client, "minio/silver", "access_key", "MINIO_SILVER_ACCESS_KEY")
    minio_secret_key = get_secret(vault_client, "minio/silver", "secret_key", "MINIO_SILVER_SECRET_KEY")

    postgres_host = get_secret_or_default(vault_client, "postgres/gold", "host", "GOLD_DB_HOST", "postgres-gold")
    postgres_port = get_secret_or_default(vault_client, "postgres/gold", "port", "GOLD_DB_PORT", "5432")
    postgres_database = get_secret_or_default(vault_client, "postgres/gold", "database", "GOLD_DB_NAME", "kovalyx_gold")
    postgres_user = get_secret(vault_client, "postgres/gold", "user", "GOLD_DB_USER")
    postgres_password = get_secret(vault_client, "postgres/gold", "password", "GOLD_DB_PASSWORD")

    jdbc_url = f"jdbc:postgresql://{postgres_host}:{postgres_port}/{postgres_database}"
    jdbc_props = {"user": postgres_user, "password": postgres_password, "driver": "org.postgresql.Driver"}
    pg_conn_params = {"host": postgres_host, "port": postgres_port, "dbname": postgres_database, "user": postgres_user, "password": postgres_password}

    spark = build_spark_session(minio_endpoint, minio_access_key, minio_secret_key)
    masker = PresidioMasker(run_id=args.run_id, jdbc_url=jdbc_url, jdbc_props=jdbc_props)

    # records_failed is a row-count metric (rows dropped for a null key)
    # and must stay one — mixing in a flat "+= 1" per whole-table
    # exception made it an incoherent unit (indistinguishable "37 rows
    # dropped" from "1 table failed"). Whole-table failures are tracked
    # separately in failed_tables and affect the final `status` below
    # instead, since a failed table means real missing Silver output —
    # that's a pipeline-level failure, not a per-row data-quality drop.
    records_processed = 0
    records_failed = 0
    failed_tables: list[str] = []

    try:
        try:
            raw_events = read_streaming_events(spark, target_date)
            events_df, ev_written, ev_dropped = transform_streaming_events(raw_events, target_date, masker)
            write_parquet(events_df, f"s3a://{SILVER_BUCKET}/events/date={target_date}/", partition_by="event_type")
            records_processed += ev_written
            records_failed += ev_dropped
            records_processed_metric.labels(table="events").inc(ev_written)
            if ev_dropped:
                records_failed_metric.labels(table="events", reason="null_key").inc(ev_dropped)
        except Exception:  # noqa: BLE001
            logger.exception("Streaming events transform failed — continuing with remaining tables")
            failed_tables.append("events")
            records_failed_metric.labels(table="events", reason="transform_exception").inc(1)

        try:
            raw_customers = read_batch_csv(spark, "customers", CUSTOMERS_SCHEMA)
            customers_df = transform_customers(raw_customers, masker)
            write_parquet(customers_df, f"s3a://{SILVER_BUCKET}/customers/")
            written = customers_df.count()
            records_processed += written
            records_processed_metric.labels(table="customers").inc(written)
        except Exception:  # noqa: BLE001
            logger.exception("Customers transform failed — continuing with remaining tables")
            failed_tables.append("customers")
            records_failed_metric.labels(table="customers", reason="transform_exception").inc(1)

        try:
            raw_products = read_batch_csv(spark, "products", PRODUCTS_SCHEMA)
            products_df, prod_dropped = transform_products(raw_products)
            write_parquet(products_df, f"s3a://{SILVER_BUCKET}/products/")
            written = products_df.count()
            records_processed += written
            records_failed += prod_dropped
            records_processed_metric.labels(table="products").inc(written)
            if prod_dropped:
                records_failed_metric.labels(table="products", reason="null_key").inc(prod_dropped)
        except Exception:  # noqa: BLE001
            logger.exception("Products transform failed — continuing with remaining tables")
            failed_tables.append("products")
            records_failed_metric.labels(table="products", reason="transform_exception").inc(1)

        try:
            raw_orders = read_batch_csv(spark, "orders", ORDERS_SCHEMA)
            orders_df = transform_orders(raw_orders, masker)
            write_parquet(orders_df, f"s3a://{SILVER_BUCKET}/orders/date={target_date}/")
            written = orders_df.count()
            records_processed += written
            records_processed_metric.labels(table="orders").inc(written)
        except Exception:  # noqa: BLE001
            logger.exception("Orders transform failed — continuing with remaining tables")
            failed_tables.append("orders")
            records_failed_metric.labels(table="orders", reason="transform_exception").inc(1)

        try:
            raw_inventory = read_batch_csv(spark, "inventory", INVENTORY_SCHEMA)
            inventory_df, inv_dropped = transform_inventory(raw_inventory)
            write_parquet(inventory_df, f"s3a://{SILVER_BUCKET}/inventory/date={target_date}/")
            written = inventory_df.count()
            records_processed += written
            records_failed += inv_dropped
            records_processed_metric.labels(table="inventory").inc(written)
            if inv_dropped:
                records_failed_metric.labels(table="inventory", reason="null_key").inc(inv_dropped)
        except Exception:  # noqa: BLE001
            logger.exception("Inventory transform failed — continuing with remaining tables")
            failed_tables.append("inventory")
            records_failed_metric.labels(table="inventory", reason="transform_exception").inc(1)

        masker.flush_audit_log(spark)
        pii_masked_metric.inc(masker.get_masked_count())

        end_time = datetime.now(timezone.utc)
        duration_metric.set((end_time - start_time).total_seconds())
        status = "failed" if failed_tables else "success"
        write_pipeline_audit_log(
            pg_conn_params,
            run_id=args.run_id,
            start_time=start_time,
            end_time=end_time,
            records_processed=records_processed,
            records_failed=records_failed,
            pii_events_masked=masker.get_masked_count(),
            status=status,
        )
        push_metrics(registry)

        logger.info(
            "Silver transform complete: run_id=%s date=%s status=%s processed=%d row_dropped=%d failed_tables=%s pii_masked=%d",
            args.run_id,
            target_date,
            status,
            records_processed,
            records_failed,
            failed_tables or "none",
            masker.get_masked_count(),
        )
        return 1 if failed_tables else 0

    except Exception:  # noqa: BLE001
        logger.exception("Unhandled failure in Silver transform job (run_id=%s)", args.run_id)
        end_time = datetime.now(timezone.utc)
        try:
            write_pipeline_audit_log(
                pg_conn_params,
                run_id=args.run_id,
                start_time=start_time,
                end_time=end_time,
                records_processed=records_processed,
                records_failed=records_failed,
                pii_events_masked=masker.get_masked_count(),
                status="failed",
            )
        except Exception:  # noqa: BLE001
            logger.exception("Also failed to write the failure audit row")
        push_metrics(registry)
        return 1
    finally:
        spark.stop()


if __name__ == "__main__":
    sys.exit(main())
