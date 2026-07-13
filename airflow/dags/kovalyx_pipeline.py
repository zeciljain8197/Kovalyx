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

ENV_TEMPLATE = "{{ var.value.kovalyx_env | default('dev') }}"


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
                (run_id, "kovalyx_medallion_pipeline", "pipeline_audit_log", "scheduler", start_time, end_time, None, None, True, None, "success"),
            )
    finally:
        conn.close()
    logger.info("Wrote final pipeline_audit_log row for run_id=%s", run_id)


default_args = {
    "owner": "kovalyx",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "email_on_failure": True,
    "email": ["{{ var.value.kovalyx_alert_email }}"],
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
    # exists on this script). `|| true` because `timeout` returns exit
    # code 124 when it kills the process at the deadline, which is the
    # expected/normal outcome here, not a failure.
    kafka_producer_trigger = BashOperator(
        task_id="kafka_producer_trigger",
        bash_command=("timeout 300 python /opt/kovalyx/ingestion/kafka_producer.py --duration-seconds 300 || true"),
    )

    # kafka_consumer.py takes no CLI arguments at all (env-var driven) —
    # `timeout` alone bounds how long it drains the topic for.
    bronze_kafka_consumer = BashOperator(
        task_id="bronze_kafka_consumer",
        bash_command=("timeout 60 python /opt/kovalyx/ingestion/kafka_consumer.py || true"),
    )

    # seed_data.py has no --env flag; it's idempotent on its own via the
    # MinIO seed-completion marker (see already_seeded()/mark_seeded()).
    bronze_batch_ingest = BashOperator(
        task_id="bronze_batch_ingest",
        bash_command="python /opt/kovalyx/scripts/seed_data.py",
    )

    # --packages pulls hadoop-aws/aws-java-sdk-bundle/postgresql onto both
    # the driver (running here, in this container, in client deploy mode)
    # and the executors — spark-master/spark-worker's own images already
    # have these jars baked in (spark/Dockerfile), but a client-mode
    # driver submitted from the Airflow container needs them resolved too.
    silver_pyspark_transform = BashOperator(
        task_id="silver_pyspark_transform",
        bash_command=(
            "spark-submit "
            "--master spark://spark-master:7077 "
            "--deploy-mode client "
            "--packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262,org.postgresql:postgresql:42.7.3 "
            "--conf spark.executor.memory=2g "
            "--conf spark.driver.memory=1g "
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
