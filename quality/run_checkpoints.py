"""
Kovalyx — Great Expectations runner for the Silver layer.

Validates every Silver Parquet table (events, customers, orders, inventory)
against its expectation suite in quality/ge_suites/, runs a freshness check
on the events partition, and writes every result to
audit.ge_validation_results (postgres-gold). Exits non-zero if any
checkpoint or the freshness check fails, so Airflow catches it as a task
failure.

Usage:
    python run_checkpoints.py --run-id <uuid> --date <YYYY-MM-DD> --env [dev|prod]

Data loading: Parquet is fetched from MinIO directly via boto3 + pyarrow
into a pandas DataFrame, then handed to Great Expectations' fluent
`sources.pandas_default` ad-hoc datasource for validation. GE 0.18's
native S3DataConnector expects YAML-era Checkpoint configuration that
doesn't fit cleanly into a from-scratch, in-code DataContext — the
boto3+pyarrow fetch is the practical equivalent of "S3DataConnector
pointing to MinIO" for this project, and `pandas_default` is the practical
equivalent of "RuntimeDataConnector for in-memory batch validation."

Expectation execution: rather than reconstructing GE's ExpectationSuite
object model (whose exact construction API has shifted more than once
across the 0.18.x line, and can't be pinned/verified without a running GE
install), each expectation in the suite JSON is dispatched directly to the
matching `validator.expect_<type>(**kwargs)` method — that per-expectation
Validator API has been stable across every GE version. GE's own validation
store stays ephemeral/in-memory (no Data Docs, as specified); the durable
record is the explicit psycopg2 INSERT below, which is what the "Results
Handling" requirements call for anyway.
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
import great_expectations as gx
import hvac
import pandas as pd
import psycopg2
import pyarrow.parquet as pq
from botocore.client import Config as BotoConfig
from prometheus_client import CollectorRegistry, Counter, Gauge, push_to_gateway
from psycopg2.extras import Json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kovalyx.run_checkpoints")

REPO_ROOT = Path(__file__).resolve().parent.parent
GE_SUITES_DIR = Path(__file__).resolve().parent / "ge_suites"
SILVER_BUCKET = "silver"  # real bucket name — see docker-compose.yml minio-init
FRESHNESS_SLA_HOURS = 2

TABLE_CONFIG = {
    "events": {"suite_file": "kovalyx_silver_events.json", "prefix_template": "events/date={date}/", "checkpoint_name": "checkpoint_silver_events"},
    "customers": {"suite_file": "kovalyx_silver_customers.json", "prefix_template": "customers/", "checkpoint_name": "checkpoint_silver_customers"},
    "orders": {"suite_file": "kovalyx_silver_orders.json", "prefix_template": "orders/date={date}/", "checkpoint_name": "checkpoint_silver_orders"},
    "inventory": {"suite_file": "kovalyx_silver_inventory.json", "prefix_template": "inventory/date={date}/", "checkpoint_name": "checkpoint_silver_inventory"},
}


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
    """Authenticates via the kovalyx-silver AppRole — GE runs as part of
    the Silver layer, so it shares the same role as silver_transform.py."""
    vault_addr = os.environ.get("VAULT_ADDR")
    if not vault_addr:
        logger.warning("VAULT_ADDR not set — reading credentials from env vars directly")
        return None

    creds_path = Path(os.environ.get("VAULT_APPROLE_CREDS_FILE", str(REPO_ROOT / "vault" / ".approle-credentials.json")))
    loaded = _load_approle_credentials(creds_path, "kovalyx-silver")
    role_id = os.environ.get("VAULT_SILVER_ROLE_ID") or (loaded[0] if loaded else None)
    secret_id = loaded[1] if loaded else None

    if not role_id or not secret_id:
        logger.warning("No AppRole role_id/secret_id available (checked VAULT_SILVER_ROLE_ID and %s) — falling back to env vars", creds_path)
        return None

    client = hvac.Client(url=vault_addr)
    try:
        client.auth.approle.login(role_id=role_id, secret_id=secret_id)
    except Exception:  # noqa: BLE001
        logger.warning("AppRole login failed for kovalyx-silver — falling back to env vars", exc_info=True)
        return None
    return client if client.is_authenticated() else None


def build_minio_client(vault_client: hvac.Client | None):
    """Builds a boto3 S3 client against MinIO using the silver secret."""
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
    """Postgres connection params for postgres-gold's audit schema."""
    return {
        "host": get_secret_or_default(vault_client, "postgres/gold", "host", "GOLD_DB_HOST", "postgres-gold"),
        "port": get_secret_or_default(vault_client, "postgres/gold", "port", "GOLD_DB_PORT", "5432"),
        "dbname": get_secret_or_default(vault_client, "postgres/gold", "database", "GOLD_DB_NAME", "kovalyx_gold"),
        "user": get_secret(vault_client, "postgres/gold", "user", "GOLD_DB_USER"),
        "password": get_secret(vault_client, "postgres/gold", "password", "GOLD_DB_PASSWORD"),
    }


def load_silver_parquet_as_pandas(s3_client, bucket: str, prefix: str) -> pd.DataFrame:
    """Reads every Parquet part file under `prefix` in MinIO into one
    pandas DataFrame — the genuine "read from S3" step (see module
    docstring for why this replaces GE's native S3DataConnector here)."""
    paginator = s3_client.get_paginator("list_objects_v2")
    frames = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".parquet"):
                continue
            body = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
            table = pq.read_table(io.BytesIO(body))
            frames.append(table.to_pandas())
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def run_expectations(validator, suite: dict) -> dict:
    """Dispatches each expectation in `suite` to the validator's matching
    expect_<type>() method (see module docstring for why) and tallies the
    results into the shape audit.ge_validation_results expects."""
    results = []
    for expectation in suite["expectations"]:
        method = getattr(validator, expectation["expectation_type"])
        result = method(**expectation.get("kwargs", {}))
        results.append(result)
    evaluated = len(results)
    successful = sum(1 for r in results if r.success)
    failed = evaluated - successful
    return {
        "success": failed == 0,
        "evaluated_expectations": evaluated,
        "successful_expectations": successful,
        "unsuccessful_expectations": failed,
        "result_detail": [r.to_json_dict() for r in results],
    }


def validate_table(context, table: str, df: pd.DataFrame) -> dict:
    """Loads the suite JSON for `table`, validates `df` against it, and
    returns the tallied result dict. An empty DataFrame is treated as an
    automatic failure (nothing to evaluate is itself a data-quality
    problem, not a pass)."""
    suite_path = GE_SUITES_DIR / TABLE_CONFIG[table]["suite_file"]
    suite = json.loads(suite_path.read_text())

    if df.empty:
        logger.error("No Silver data found for table=%s — treating as a failed checkpoint", table)
        return {
            "success": False,
            "evaluated_expectations": 0,
            "successful_expectations": 0,
            "unsuccessful_expectations": len(suite["expectations"]),
            "result_detail": [{"error": f"No rows found for table={table}"}],
        }

    validator = context.sources.pandas_default.read_dataframe(df)
    return run_expectations(validator, suite)


def check_freshness(events_df: pd.DataFrame, bucket: str, prefix: str) -> tuple[bool, str]:
    """Custom freshness check (outside GE): fails if the most recent
    event_timestamp in the events partition is more than
    FRESHNESS_SLA_HOURS old, or the partition is missing entirely."""
    if events_df.empty:
        return False, f"No Silver events partition found at s3://{bucket}/{prefix}"
    if "event_timestamp" not in events_df.columns:
        return False, "event_timestamp column missing from Silver events partition"

    most_recent = pd.to_datetime(events_df["event_timestamp"]).max()
    if most_recent is pd.NaT:
        return False, "All event_timestamp values are null in the Silver events partition"
    most_recent_utc = most_recent.tz_localize("UTC") if most_recent.tzinfo is None else most_recent.tz_convert("UTC")
    age = datetime.now(timezone.utc) - most_recent_utc.to_pydatetime()

    if age > timedelta(hours=FRESHNESS_SLA_HOURS):
        return False, f"Most recent event_timestamp {most_recent_utc.isoformat()} is {age} old (> {FRESHNESS_SLA_HOURS}h SLA)"
    return True, f"Most recent event_timestamp {most_recent_utc.isoformat()} ({age} old)"


def write_ge_result(pg_conn_params: dict, run_id: str, checkpoint_name: str, suite_name: str, result: dict) -> None:
    """Writes one row to audit.ge_validation_results via psycopg2."""
    conn = psycopg2.connect(**pg_conn_params)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit.ge_validation_results
                    (pipeline_run_id, checkpoint_name, expectation_suite_name, success,
                     evaluated_expectations, successful_expectations, unsuccessful_expectations,
                     run_time, result_detail)
                VALUES (%s, %s, %s, %s, %s, %s, %s, now(), %s)
                """,
                (
                    run_id,
                    checkpoint_name,
                    suite_name,
                    result["success"],
                    result["evaluated_expectations"],
                    result["successful_expectations"],
                    result["unsuccessful_expectations"],
                    Json(result["result_detail"]),
                ),
            )
    finally:
        conn.close()


def print_summary(rows: list[dict]) -> None:
    """Prints a plain-text pass/fail table to stdout — the one place
    print() is allowed per the project's logging convention."""
    header = f"{'Checkpoint':<32} {'Status':<6} {'Evaluated':>10} {'Passed':>8} {'Failed':>8}"
    print(header)
    print("-" * len(header))
    for row in rows:
        status = "PASS" if row["success"] else "FAIL"
        print(f"{row['checkpoint']:<32} {status:<6} {row['evaluated']:>10} {row['passed']:>8} {row['failed']:>8}")


def push_metrics(registry: CollectorRegistry) -> None:
    """No-op unless PROMETHEUS_PUSHGATEWAY_URL is set."""
    pushgateway_url = os.environ.get("PROMETHEUS_PUSHGATEWAY_URL")
    if not pushgateway_url:
        return
    try:
        push_to_gateway(pushgateway_url, job="kovalyx_ge_checkpoints", registry=registry)
    except Exception:  # noqa: BLE001
        logger.warning("Failed to push metrics to pushgateway at %s", pushgateway_url, exc_info=True)


def main() -> int:
    """Entry point: python run_checkpoints.py --run-id <uuid> --date <YYYY-MM-DD> --env [dev|prod]."""
    parser = argparse.ArgumentParser(description="Kovalyx Great Expectations checkpoint runner")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--date", default=None, help="YYYY-MM-DD, defaults to yesterday")
    parser.add_argument("--env", choices=["dev", "prod"], default="dev")
    args = parser.parse_args()

    target_date = args.date or (date.today() - timedelta(days=1)).isoformat()

    vault_client = build_vault_client()
    s3_client = build_minio_client(vault_client)
    pg_conn_params = build_pg_conn_params(vault_client)
    context = gx.get_context(mode="ephemeral")

    registry = CollectorRegistry()
    checkpoint_success_metric = Gauge("kovalyx_ge_checkpoint_success", "1.0 if the checkpoint passed, else 0.0", ["checkpoint_name"], registry=registry)
    expectations_passed_metric = Counter("kovalyx_ge_expectations_passed_total", "Expectations passed", ["checkpoint_name"], registry=registry)
    expectations_failed_metric = Counter("kovalyx_ge_expectations_failed_total", "Expectations failed", ["checkpoint_name"], registry=registry)

    summary_rows = []
    any_failed = False
    events_df: pd.DataFrame | None = None

    for table, config in TABLE_CONFIG.items():
        prefix = config["prefix_template"].format(date=target_date)
        logger.info("Validating table=%s prefix=s3://%s/%s", table, SILVER_BUCKET, prefix)
        df = load_silver_parquet_as_pandas(s3_client, SILVER_BUCKET, prefix)
        if table == "events":
            events_df = df

        result = validate_table(context, table, df)
        suite_name = json.loads((GE_SUITES_DIR / config["suite_file"]).read_text())["expectation_suite_name"]
        write_ge_result(pg_conn_params, args.run_id, config["checkpoint_name"], suite_name, result)

        checkpoint_success_metric.labels(checkpoint_name=config["checkpoint_name"]).set(1.0 if result["success"] else 0.0)
        expectations_passed_metric.labels(checkpoint_name=config["checkpoint_name"]).inc(result["successful_expectations"])
        expectations_failed_metric.labels(checkpoint_name=config["checkpoint_name"]).inc(result["unsuccessful_expectations"])

        summary_rows.append(
            {
                "checkpoint": config["checkpoint_name"],
                "success": result["success"],
                "evaluated": result["evaluated_expectations"],
                "passed": result["successful_expectations"],
                "failed": result["unsuccessful_expectations"],
            }
        )
        if not result["success"]:
            any_failed = True

    events_prefix = TABLE_CONFIG["events"]["prefix_template"].format(date=target_date)
    is_fresh, freshness_message = check_freshness(events_df if events_df is not None else pd.DataFrame(), SILVER_BUCKET, events_prefix)
    if not is_fresh:
        logger.warning("Freshness check failed: %s", freshness_message)
        write_ge_result(
            pg_conn_params,
            args.run_id,
            "checkpoint_silver_freshness",
            "kovalyx.silver_freshness",
            {
                "success": False,
                "evaluated_expectations": 1,
                "successful_expectations": 0,
                "unsuccessful_expectations": 1,
                "result_detail": [{"message": freshness_message}],
            },
        )
        summary_rows.append({"checkpoint": "checkpoint_silver_freshness", "success": False, "evaluated": 1, "passed": 0, "failed": 1})
        any_failed = True
        if events_df is None or events_df.empty:
            logger.error("Silver events partition for date=%s does not exist at all — aborting", target_date)
            print_summary(summary_rows)
            push_metrics(registry)
            return 1
    else:
        logger.info("Freshness check passed: %s", freshness_message)

    print_summary(summary_rows)
    push_metrics(registry)

    if any_failed:
        logger.error("One or more Great Expectations checkpoints failed for run_id=%s", args.run_id)
        return 1

    logger.info("All Great Expectations checkpoints passed for run_id=%s", args.run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
