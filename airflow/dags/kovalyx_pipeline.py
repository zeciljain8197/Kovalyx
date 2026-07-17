"""
Kovalyx — the full Bronze -> Silver -> Gold medallion pipeline DAG.

10 tasks: a 5-minute live-event burst + a batch-CSV drain feeding Bronze,
a PySpark Silver transform + Great Expectations validation, a loader that
bridges Silver Parquet into Supabase staging, dbt run/test/snapshot for
Gold, and a final audit-log write. Scheduled every 2 hours.

Deviations from a literal reading of the original task spec, each
because the referenced script doesn't actually support the flag/path as
written (verified against the real files rather than assumed):
  - kafka_producer.py has --duration-seconds, not --duration, and no
    --env flag at all.
  - kafka_consumer.py takes no CLI arguments whatsoever (config is env-var
    driven) — `timeout` alone bounds its runtime.
  - seed_data.py has no --env flag.
  - Every /opt/airflow/<component> path is /opt/kovalyx/<component> —
    that's where docker-compose.yml's x-airflow-common actually mounts
    ingestion/, spark/, quality/, scripts/, and dbt_project/.
  - The VaultSecretsHook import is `from vault_secrets_hook import
    VaultSecretsHook`, not `from kovalyx.vault_hook import ...` — Airflow
    adds airflow/plugins/ directly to sys.path, there's no `kovalyx`
    package wrapper.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import psycopg2
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from vault_secrets_hook import VaultSecretsHook

logger = logging.getLogger("kovalyx.dag")

# var.value.X raises if Airflow Variable X was never created — the
# `| default(...)` filter can't rescue a raised exception (only an
# undefined value), so var.value.get(name, default) is the actual
# correct idiom for an optional Variable with a fallback.
ENV_TEMPLATE = "{{ var.value.get('kovalyx_env', 'dev') }}"


def sla_miss_callback(dag, task_list, blocking_task_list, slas, blocking_tis) -> None:
    """Logs a WARNING on any SLA miss — intentionally log-only (no email)
    per the spec, to keep this simple and maintainable."""
    logger.warning(
        "SLA miss on DAG '%s': tasks=%s slas=%s",
        dag.dag_id,
        [sla.task_id for sla in slas],
        [str(sla.timestamp) for sla in slas],
    )


def write_final_audit_record(**context) -> None:
    """PythonOperator callable for the pipeline_audit_log task. If the DAG
    reached this task, every upstream task (including silver_ge_validation)
    already succeeded, so ge_passed is recorded as True."""
    hook = VaultSecretsHook(role_name="kovalyx-airflow")
    pg_secret = hook.get_secret("postgres/gold")

    run_id = context["run_id"]
    start_time = context["data_interval_start"]
    end_time = datetime.now(timezone.utc)

    conn = psycopg2.connect(
        host=pg_secret["host"],
        port=pg_secret["port"],
        dbname=pg_secret.get("database", pg_secret.get("dbname")),
        user=pg_secret["user"],
        password=pg_secret["password"],
    )
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
                    ge_passed = EXCLUDED.ge_passed,
                    status = EXCLUDED.status
                """,
                # records_processed/records_failed/pii_events_masked are 0,
                # not None: the row for this run_id normally already exists
                # by now (silver_transform.py's write_pipeline_audit_log()
                # wrote it during silver_pyspark_transform, with the real
                # counts), so the ON CONFLICT branch above — which never
                # touches these three columns — is what actually applies.
                # But the VALUES tuple still has to satisfy each column's
                # own NOT NULL constraint regardless of ON CONFLICT, since
                # Postgres validates the proposed row before checking for a
                # conflict; passing an explicit None bypassed each column's
                # DEFAULT 0 and violated NOT NULL on every run.
                (run_id, "kovalyx_medallion_pipeline", "pipeline_audit_log", "scheduler", start_time, end_time, 0, 0, True, 0, "success"),
            )
    finally:
        conn.close()
    logger.info("Wrote final pipeline_audit_log row for run_id=%s", run_id)


default_args = {
    "owner": "kovalyx",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    # No SMTP server exists anywhere in this self-hosted stack, so
    # email_on_failure=True previously guaranteed a second, unrelated
    # ConnectionRefusedError on every task failure — burying the real
    # error under an email-delivery traceback. Same "log-only, no email"
    # convention as sla_miss_callback below, for the same reason.
    "email_on_failure": False,
    "sla": timedelta(minutes=90),
}

with DAG(
    dag_id="kovalyx_medallion_pipeline",
    default_args=default_args,
    description="Kovalyx Bronze -> Silver -> Gold medallion pipeline",
    schedule_interval="0 */2 * * *",
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["kovalyx", "medallion", "production"],
    sla_miss_callback=sla_miss_callback,
) as dag:

    # kafka_producer.py's real flag is --duration-seconds (no --env flag
    # exists on this script). `|| test $? -eq 124` (not a blanket `|| true`)
    # because `timeout` returns exit code 124 when it kills the process at
    # the deadline, which is the expected/normal outcome here — but a
    # blanket `|| true` also swallowed genuine crashes (e.g. the script
    # exiting 1 on a missing Vault credential), which let this task report
    # SUCCESS after producing zero events, silently starving every
    # downstream task of data.
    kafka_producer_trigger = BashOperator(
        task_id="kafka_producer_trigger",
        bash_command=("timeout 300 python /opt/kovalyx/ingestion/kafka_producer.py --duration-seconds 300 --date {{ ds }} || test $? -eq 124"),
    )

    # kafka_consumer.py takes no CLI arguments at all (env-var driven) —
    # `timeout` alone bounds how long it drains the topic for, and its
    # exit code is always 124 (SIGTERM at the deadline) in the normal
    # case; see kafka_producer_trigger's comment for why this isn't `|| true`.
    bronze_kafka_consumer = BashOperator(
        task_id="bronze_kafka_consumer",
        bash_command=("timeout 60 python /opt/kovalyx/ingestion/kafka_consumer.py || test $? -eq 124"),
    )

    # seed_data.py has no --env flag; it's idempotent on its own via the
    # MinIO seed-completion marker (see already_seeded()/mark_seeded()).
    # --output-dir is explicit: its default (REPO_ROOT/data/seed, i.e.
    # /opt/kovalyx/data) sits on a bind-mount parent directory owned by
    # root, not writable by the non-root airflow user — /tmp is always
    # writable and this data is a disposable staging artifact ahead of
    # the MinIO upload anyway.
    bronze_batch_ingest = BashOperator(
        task_id="bronze_batch_ingest",
        bash_command="python /opt/kovalyx/scripts/seed_data.py --output-dir /tmp/kovalyx_seed",
    )

    # hadoop-aws/aws-java-sdk-bundle/postgresql are baked into both this
    # container's and spark-worker's $SPARK_HOME/jars/ at image-build time
    # (see airflow/Dockerfile's matching comment) — deliberately NOT
    # --packages: that resolved a second, separately-classloaded copy on
    # top of the executor's already-baked-in jars, which caused an
    # intermittent NoClassDefFoundError on whichever s3a:// access ran
    # first in a job.
    silver_pyspark_transform = BashOperator(
        task_id="silver_pyspark_transform",
        bash_command=(
            "spark-submit "
            "--master spark://spark-master:7077 "
            "--deploy-mode client "
            "--conf spark.executor.memory=2g "
            "--conf spark.driver.memory=1g "
            # Default spark.network.timeout (120s) / heartbeatInterval (10s)
            # are too tight for this job: the PII-masking UDFs run real
            # Presidio+spaCy NER inference per row (no batching), which on
            # a CPU-constrained Docker Desktop VM can starve the executor's
            # heartbeat thread long enough to trip the default timeout —
            # observed as "Lost executor 0 ... worker lost: Not receiving
            # heartbeat for 60 seconds" / "no recent heartbeats: N ms
            # exceeds timeout 120000 ms" even though the executor was still
            # actively working, not actually dead.
            "--conf spark.network.timeout=800s "
            "--conf spark.executor.heartbeatInterval=60s "
            # Without this, Spark auto-detects the driver's hostname as
            # this container's own (random, non-DNS-registered)
            # hostname — spark-worker's executor then can't connect
            # back to report in, so the master shows the app as
            # RUNNING with resources allocated while the driver sits
            # forever on "Initial job has not accepted any resources."
            # airflow-scheduler is the Compose service name, resolvable
            # from any container on the same networks (LocalExecutor
            # means this BashOperator always runs in that container).
            "--conf spark.driver.host=airflow-scheduler "
            # silver_transform.py's PII-masking UDFs close over
            # pii_masking.py — the driver can import it fine (same
            # filesystem, client deploy mode), but executors on
            # spark-worker need it shipped to them explicitly; without
            # --py-files, executor-side UDF calls fail with
            # ModuleNotFoundError: No module named 'pii_masking'.
            "--py-files /opt/kovalyx/spark/pii_masking.py "
            "/opt/kovalyx/spark/silver_transform.py "
            "--run-id {{ run_id }} "
            "--date {{ ds }} "
            f"--env {ENV_TEMPLATE}"
        ),
    )

    silver_ge_validation = BashOperator(
        task_id="silver_ge_validation",
        bash_command=(
            "python /opt/kovalyx/quality/run_checkpoints.py "
            "--run-id {{ run_id }} "
            "--date {{ ds }} "
            "--env " + ENV_TEMPLATE
        ),
    )

    silver_to_postgres_loader = BashOperator(
        task_id="silver_to_postgres_loader",
        bash_command=(
            "python /opt/kovalyx/scripts/silver_to_postgres_loader.py "
            "--run-id {{ run_id }} "
            "--date {{ ds }} "
            "--env " + ENV_TEMPLATE
        ),
    )

    gold_dbt_run = BashOperator(
        task_id="gold_dbt_run",
        bash_command=(
            "cd /opt/kovalyx/dbt_project && "
            "dbt run "
            "--profiles-dir /opt/kovalyx/dbt_project "
            f"--target {ENV_TEMPLATE} "
            '--vars \'{"run_date": "{{ ds }}"}\''
        ),
    )

    gold_dbt_test = BashOperator(
        task_id="gold_dbt_test",
        bash_command=(f"cd /opt/kovalyx/dbt_project && dbt test --profiles-dir /opt/kovalyx/dbt_project --target {ENV_TEMPLATE}"),
    )

    gold_dbt_snapshot = BashOperator(
        task_id="gold_dbt_snapshot",
        bash_command=(f"cd /opt/kovalyx/dbt_project && dbt snapshot --profiles-dir /opt/kovalyx/dbt_project --target {ENV_TEMPLATE}"),
    )

    pipeline_audit_log = PythonOperator(
        task_id="pipeline_audit_log",
        python_callable=write_final_audit_record,
    )

    # bronze_kafka_consumer and bronze_batch_ingest both depend on
    # kafka_producer_trigger but are independent of each other, so they
    # fan out in parallel and fan back in before Silver.
    kafka_producer_trigger >> [bronze_kafka_consumer, bronze_batch_ingest]
    [bronze_kafka_consumer, bronze_batch_ingest] >> silver_pyspark_transform
    silver_pyspark_transform >> silver_ge_validation
    silver_ge_validation >> silver_to_postgres_loader
    silver_to_postgres_loader >> gold_dbt_run
    gold_dbt_run >> gold_dbt_test
    gold_dbt_test >> gold_dbt_snapshot
    gold_dbt_snapshot >> pipeline_audit_log
