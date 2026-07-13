"""
Kovalyx — Airflow plugin: HashiCorp Vault AppRole hook.

Wraps the mounted-credentials-file AppRole pattern already used by
spark/silver_transform.py, quality/run_checkpoints.py, and
scripts/silver_to_postgres_loader.py, packaged as a reusable Airflow
BaseHook so DAG tasks can fetch secrets without duplicating that logic a
fourth time.

Airflow auto-adds airflow/plugins/ to sys.path, so DAGs import this
directly: `from vault_secrets_hook import VaultSecretsHook`.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import hvac
from airflow.hooks.base import BaseHook

logger = logging.getLogger("kovalyx.vault_hook")


class VaultSecretsHook(BaseHook):
    """Custom Airflow hook for HashiCorp Vault AppRole authentication.
    Provides get_secret(path) for use in DAG tasks. Reads role_id and
    secret_id from the mounted AppRole credentials file, keyed by role
    name."""

    def __init__(self, role_name: str, creds_file: str | None = None, vault_addr: str | None = None):
        """
        Args:
            role_name: key in vault/.approle-credentials.json (e.g.
                'kovalyx-airflow').
            creds_file: path to the mounted approle-credentials.json
                (default from the VAULT_APPROLE_CREDS_FILE env var).
            vault_addr: Vault server address (default from the VAULT_ADDR
                env var).
        """
        super().__init__()
        self.role_name = role_name
        self.creds_file = Path(creds_file or os.environ.get("VAULT_APPROLE_CREDS_FILE", "/opt/kovalyx/vault/.approle-credentials.json"))
        self.vault_addr = vault_addr or os.environ.get("VAULT_ADDR", "http://vault:8200")
        self._client: hvac.Client | None = None

    def _load_credentials(self) -> tuple[str, str]:
        """Reads role_id/secret_id for self.role_name out of the mounted
        AppRole credentials file. Raises ValueError if missing."""
        if not self.creds_file.exists():
            raise ValueError(f"AppRole credentials file not found: {self.creds_file}")
        data = json.loads(self.creds_file.read_text())
        entry = data.get(self.role_name)
        if not entry or "role_id" not in entry or "secret_id" not in entry:
            raise ValueError(f"No role_id/secret_id for role '{self.role_name}' in {self.creds_file}")
        return entry["role_id"], entry["secret_id"]

    def get_conn(self) -> hvac.Client:
        """Authenticates against Vault using AppRole and returns an
        authenticated hvac.Client. Caches the client for reuse within the
        same hook instance."""
        if self._client is not None and self._client.is_authenticated():
            return self._client

        role_id, secret_id = self._load_credentials()
        client = hvac.Client(url=self.vault_addr)
        client.auth.approle.login(role_id=role_id, secret_id=secret_id)
        if not client.is_authenticated():
            raise ValueError(f"Vault AppRole authentication failed for role '{self.role_name}'")

        logger.info("Authenticated to Vault as role '%s'", self.role_name)
        self._client = client
        return self._client

    def get_secret(self, path: str) -> dict:
        """Reads a KV v2 secret at the given path. Returns the secret data
        dict. Raises ValueError if the secret isn't found. Example:
        hook.get_secret('postgres/gold') returns {'host': ..., 'port':
        ..., 'database': ..., 'user': ..., 'password': ...}."""
        client = self.get_conn()
        try:
            resp = client.secrets.kv.v2.read_secret_version(mount_point="kovalyx", path=path, raise_on_deleted_version=True)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Secret not found at kovalyx/{path}: {exc}") from exc
        return resp["data"]["data"]

    def get_secret_value(self, path: str, key: str) -> str:
        """Convenience method: returns a single key from a secret.
        Example: hook.get_secret_value('minio/silver', 'access_key')."""
        secret = self.get_secret(path)
        if key not in secret:
            raise ValueError(f"Key '{key}' not found in secret kovalyx/{path}")
        return secret[key]
