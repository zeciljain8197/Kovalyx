"""
Kovalyx — HashiCorp Vault bootstrap.

Initializes (production mode) or connects to (dev mode) the Vault server,
enables a KV v2 secrets engine at `kovalyx/`, writes every credential the
pipeline needs, and provisions least-privilege AppRole roles + policies
scoped to each medallion layer (bronze / silver / gold / airflow) so no
service ever needs the root token at runtime.

Usage:
    python scripts/vault_init.py --mode dev
    python scripts/vault_init.py --mode prod

Reads source-of-truth credential values from the process environment
(typically loaded from a local, git-ignored `.env` — see .env.example for
the full variable list) and never prints secret values to stdout.

In prod mode, the one-time unseal keys + initial root token are written to
`vault/.vault-init.json` with 0600 permissions. That file is git-ignored
and must be moved to secure offline storage immediately after first run —
it is the only copy of the unseal material.

Requires: hvac, python-dotenv  (pip install hvac python-dotenv)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import stat
import sys
import time
from pathlib import Path

import hvac
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kovalyx.vault_init")

REPO_ROOT = Path(__file__).resolve().parent.parent
VAULT_INIT_FILE = REPO_ROOT / "vault" / ".vault-init.json"
APPROLE_CREDS_FILE = REPO_ROOT / "vault" / ".approle-credentials.json"
KV_MOUNT = "kovalyx"
UNSEAL_KEY_SHARES = 5
UNSEAL_KEY_THRESHOLD = 3


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Set it in your .env before running vault_init.py."
        )
    return value


def build_client(vault_addr: str, token: str | None = None) -> hvac.Client:
    client = hvac.Client(url=vault_addr, token=token)
    return client


def wait_for_vault(client: hvac.Client, timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            client.sys.read_health_status(standby_ok=True)
            logger.info("Vault is reachable at %s", client.url)
            return
        except Exception:  # noqa: BLE001 - retry loop, any connection error is transient
            time.sleep(2)
    raise TimeoutError(f"Vault at {client.url} did not become reachable within {timeout_seconds}s")


def init_and_unseal_prod(client: hvac.Client) -> str:
    """Initializes Vault (raft storage, production mode) on first run, or
    unseals it on subsequent restarts. Returns a usable root token."""
    if VAULT_INIT_FILE.exists():
        logger.info("Found existing %s — unsealing with stored keys", VAULT_INIT_FILE)
        init_data = json.loads(VAULT_INIT_FILE.read_text())
    else:
        if client.sys.is_initialized():
            raise RuntimeError(
                "Vault reports already initialized but no local "
                f"{VAULT_INIT_FILE} exists. Unseal keys are lost unless you "
                "have a backup — refusing to proceed."
            )
        logger.info("Initializing Vault (raft, %d shares / %d threshold)", UNSEAL_KEY_SHARES, UNSEAL_KEY_THRESHOLD)
        init_data = client.sys.initialize(
            secret_shares=UNSEAL_KEY_SHARES,
            secret_threshold=UNSEAL_KEY_THRESHOLD,
        )
        VAULT_INIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        VAULT_INIT_FILE.write_text(json.dumps(init_data, indent=2))
        os.chmod(VAULT_INIT_FILE, stat.S_IRUSR | stat.S_IWUSR)
        logger.warning(
            "Wrote unseal keys + root token to %s (0600). "
            "Move this to secure offline storage NOW — it is the only copy.",
            VAULT_INIT_FILE,
        )

    if client.sys.is_sealed():
        for key in init_data["keys"][:UNSEAL_KEY_THRESHOLD]:
            client.sys.submit_unseal_key(key)
        logger.info("Vault unsealed")
    else:
        logger.info("Vault already unsealed")

    return init_data["root_token"]


def connect_dev(vault_addr: str) -> str:
    """Dev mode: the container is auto-unsealed and pre-configured with a
    known root token via VAULT_DEV_ROOT_TOKEN_ID (see docker-compose.yml)."""
    return _require_env("VAULT_TOKEN")


def ensure_kv_engine(client: hvac.Client) -> None:
    mounts = client.sys.list_mounted_secrets_engines()
    mount_path = f"{KV_MOUNT}/"
    if mount_path in mounts.get("data", mounts):
        logger.info("KV v2 engine already mounted at %s", mount_path)
        return
    client.sys.enable_secrets_engine(backend_type="kv", path=KV_MOUNT, options={"version": "2"})
    logger.info("Enabled KV v2 secrets engine at %s", mount_path)


def write_secret(client: hvac.Client, path: str, data: dict) -> None:
    clean = {k: v for k, v in data.items() if v not in (None, "")}
    client.secrets.kv.v2.create_or_update_secret(mount_point=KV_MOUNT, path=path, secret=clean)
    logger.info("Wrote secret kovalyx/%s (%d keys)", path, len(clean))


def write_all_secrets(client: hvac.Client, mode: str = "dev") -> None:
    write_secret(
        client,
        "kafka/broker",
        {
            "username": os.environ.get("KAFKA_BROKER_USER"),
            "password": os.environ.get("KAFKA_BROKER_PASSWORD"),
        },
    )
    write_secret(
        client,
        "kafka/producer",
        {
            "username": os.environ.get("KAFKA_PRODUCER_USER"),
            "password": os.environ.get("KAFKA_PRODUCER_PASSWORD"),
            "bootstrap_servers": os.environ.get("KOVALYX_KAFKA_BOOTSTRAP", "kafka:29092"),
        },
    )
    write_secret(
        client,
        "kafka/consumer",
        {
            "username": os.environ.get("KAFKA_CONSUMER_USER"),
            "password": os.environ.get("KAFKA_CONSUMER_PASSWORD"),
            "bootstrap_servers": os.environ.get("KOVALYX_KAFKA_BOOTSTRAP", "kafka:29092"),
        },
    )
    write_secret(
        client,
        "minio/root",
        {
            "access_key": os.environ.get("MINIO_ROOT_USER"),
            "secret_key": os.environ.get("MINIO_ROOT_PASSWORD"),
        },
    )
    write_secret(
        client,
        "minio/bronze-writer",
        {
            "access_key": os.environ.get("MINIO_BRONZE_WRITER_ACCESS_KEY"),
            "secret_key": os.environ.get("MINIO_BRONZE_WRITER_SECRET_KEY"),
            "endpoint": os.environ.get("KOVALYX_MINIO_ENDPOINT", "minio:9000"),
        },
    )
    write_secret(
        client,
        "minio/silver",
        {
            "access_key": os.environ.get("MINIO_SILVER_ACCESS_KEY"),
            "secret_key": os.environ.get("MINIO_SILVER_SECRET_KEY"),
            "endpoint": os.environ.get("KOVALYX_MINIO_ENDPOINT", "minio:9000"),
        },
    )
    write_secret(
        client,
        "minio/gold-reader",
        {
            "access_key": os.environ.get("MINIO_GOLD_READER_ACCESS_KEY"),
            "secret_key": os.environ.get("MINIO_GOLD_READER_SECRET_KEY"),
            "endpoint": os.environ.get("KOVALYX_MINIO_ENDPOINT", "minio:9000"),
        },
    )
    write_secret(
        client,
        "postgres/metadata",
        {
            "host": "postgres-metadata",
            "port": "5432",
            "user": os.environ.get("POSTGRES_METADATA_USER"),
            "password": os.environ.get("POSTGRES_METADATA_PASSWORD"),
            "airflow_db": os.environ.get("AIRFLOW_DB_NAME", "airflow"),
            "ge_db": os.environ.get("GE_METADATA_DB_NAME", "great_expectations"),
            "audit_db": os.environ.get("AUDIT_DB_NAME", "kovalyx_audit"),
        },
    )
    # mode-aware, not a blind `SUPABASE_DB_* or GOLD_DB_*` fallback chain:
    # SUPABASE_DB_NAME defaults to the non-blank literal "postgres" in
    # .env.example (Supabase projects are always named that), which is
    # truthy even in dev — so `or` never fell through to GOLD_DB_NAME
    # and every dev-mode Gold write silently landed in the wrong
    # database (Postgres's own "postgres" maintenance DB has no
    # audit/staging/marts schemas, since scripts/supabase_schema.sql
    # only ever runs against POSTGRES_DB=kovalyx_gold).
    if mode == "prod":
        gold_secret = {
            "host": os.environ.get("SUPABASE_DB_HOST"),
            "port": "5432",
            "database": os.environ.get("SUPABASE_DB_NAME", "postgres"),
            "user": os.environ.get("SUPABASE_DB_USER"),
            "password": os.environ.get("SUPABASE_DB_PASSWORD"),
        }
    else:
        gold_secret = {
            "host": os.environ.get("GOLD_DB_HOST", "postgres-gold"),
            "port": "5432",
            "database": os.environ.get("GOLD_DB_NAME", "kovalyx_gold"),
            "user": os.environ.get("GOLD_DB_USER"),
            "password": os.environ.get("GOLD_DB_PASSWORD"),
        }
    write_secret(client, "postgres/gold", gold_secret)
    write_secret(
        client,
        "supabase/api",
        {
            "url": os.environ.get("NEXT_PUBLIC_SUPABASE_URL"),
            "anon_key": os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY"),
            "service_role_key": os.environ.get("SUPABASE_SERVICE_ROLE_KEY"),
            "audit_reader_key": os.environ.get("SUPABASE_AUDIT_READER_KEY"),
        },
    )
    write_secret(
        client,
        "airflow/core",
        {
            "fernet_key": os.environ.get("AIRFLOW_FERNET_KEY"),
            "webserver_secret_key": os.environ.get("AIRFLOW_WEBSERVER_SECRET_KEY"),
            "admin_user": os.environ.get("AIRFLOW_ADMIN_USER"),
            "admin_password": os.environ.get("AIRFLOW_ADMIN_PASSWORD"),
            "admin_email": os.environ.get("AIRFLOW_ADMIN_EMAIL"),
        },
    )
    write_secret(
        client,
        "grafana/admin",
        {
            "user": os.environ.get("GRAFANA_ADMIN_USER"),
            "password": os.environ.get("GRAFANA_ADMIN_PASSWORD"),
        },
    )
    write_secret(
        client,
        "alerting/slack",
        {"webhook_url": os.environ.get("SLACK_WEBHOOK_URL")},
    )
    write_secret(
        client,
        "alerting/smtp",
        {
            "host": os.environ.get("SMTP_HOST"),
            "port": os.environ.get("SMTP_PORT", "587"),
            "user": os.environ.get("SMTP_USER"),
            "password": os.environ.get("SMTP_PASSWORD"),
            "alert_to": os.environ.get("ALERT_EMAIL_TO"),
        },
    )
    write_secret(
        client,
        "frontend/admin",
        {"password": os.environ.get("KOVALYX_ADMIN_PASSWORD")},
    )
    write_secret(
        client,
        "deployment/tls",
        {
            "domain": os.environ.get("KOVALYX_DOMAIN"),
            "letsencrypt_email": os.environ.get("LETSENCRYPT_EMAIL"),
        },
    )


# ---------------------------------------------------------------------
# Least-privilege AppRole policies — one per medallion layer, so a
# compromised producer container can never read Gold/Supabase secrets,
# and vice versa. Airflow gets a broad policy since it orchestrates
# every layer.
# ---------------------------------------------------------------------
POLICIES = {
    "kovalyx-bronze": """
        path "kovalyx/data/kafka/producer" { capabilities = ["read"] }
        path "kovalyx/data/kafka/consumer" { capabilities = ["read"] }
        path "kovalyx/data/kafka/broker" { capabilities = ["read"] }
        path "kovalyx/data/minio/bronze-writer" { capabilities = ["read"] }
    """,
    # postgres/gold is here (not just postgres/metadata) because the audit
    # tables the Silver PySpark job writes to (kovalyx_pii_audit_log,
    # kovalyx_pipeline_audit_log, ge_validation_results) live in
    # postgres-gold/Supabase's audit schema — that's the only Postgres the
    # Next.js dashboard and Streamlit monitor can query.
    "kovalyx-silver": """
        path "kovalyx/data/minio/bronze-writer" { capabilities = ["read"] }
        path "kovalyx/data/minio/silver" { capabilities = ["read"] }
        path "kovalyx/data/postgres/metadata" { capabilities = ["read"] }
        path "kovalyx/data/postgres/gold" { capabilities = ["read"] }
    """,
    "kovalyx-gold": """
        path "kovalyx/data/minio/gold-reader" { capabilities = ["read"] }
        path "kovalyx/data/minio/silver" { capabilities = ["read"] }
        path "kovalyx/data/postgres/gold" { capabilities = ["read"] }
        path "kovalyx/data/supabase/api" { capabilities = ["read"] }
    """,
    "kovalyx-airflow": """
        path "kovalyx/data/*" { capabilities = ["read"] }
    """,
}


def setup_policies_and_approles(client: hvac.Client) -> dict:
    auth_methods = client.sys.list_auth_methods()
    if "approle/" not in auth_methods.get("data", auth_methods):
        client.sys.enable_auth_method("approle")
        logger.info("Enabled AppRole auth method")

    credentials = {}
    for role_name, policy_hcl in POLICIES.items():
        client.sys.create_or_update_policy(name=role_name, policy=policy_hcl)
        client.auth.approle.create_or_update_approle(
            role_name=role_name,
            token_policies=[role_name],
            token_ttl="1h",
            token_max_ttl="4h",
            secret_id_num_uses=0,
        )
        role_id = client.auth.approle.read_role_id(role_name)["data"]["role_id"]
        secret_id = client.auth.approle.generate_secret_id(role_name)["data"]["secret_id"]
        credentials[role_name] = {"role_id": role_id, "secret_id": secret_id}
        logger.info("Provisioned AppRole '%s'", role_name)

    APPROLE_CREDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    APPROLE_CREDS_FILE.write_text(json.dumps(credentials, indent=2))
    os.chmod(APPROLE_CREDS_FILE, stat.S_IRUSR | stat.S_IWUSR)
    logger.info("Wrote AppRole role_id/secret_id pairs to %s (0600)", APPROLE_CREDS_FILE)
    return credentials


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap HashiCorp Vault for Kovalyx.")
    parser.add_argument("--mode", choices=["dev", "prod"], default="dev")
    parser.add_argument("--env-file", default=str(REPO_ROOT / ".env"))
    args = parser.parse_args()

    if Path(args.env_file).exists():
        load_dotenv(args.env_file)
    else:
        logger.warning("No .env file found at %s — relying on process environment only", args.env_file)

    vault_addr = os.environ.get("VAULT_ADDR", "http://localhost:8200")
    bootstrap_client = build_client(vault_addr)
    wait_for_vault(bootstrap_client)

    if args.mode == "prod":
        root_token = init_and_unseal_prod(bootstrap_client)
    else:
        root_token = connect_dev(vault_addr)

    client = build_client(vault_addr, token=root_token)
    if not client.is_authenticated():
        logger.error("Failed to authenticate to Vault with the resolved root token")
        return 1

    ensure_kv_engine(client)
    write_all_secrets(client, mode=args.mode)
    setup_policies_and_approles(client)

    logger.info("Vault bootstrap complete (mode=%s)", args.mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
