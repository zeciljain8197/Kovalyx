#!/usr/bin/env bash
# =====================================================================
# Kovalyx — one-command local bootstrap.
#
# Brings up the entire stack and gets it into a working state, so you
# never have to remember which follow-up script to run after `docker
# compose up`. In particular: HashiCorp Vault runs in dev mode locally
# (see docker-compose.yml's vault service), which means it is
# in-memory only and loses every secret whenever its container
# restarts — that's the #1 cause of pipeline tasks crash-looping with
# "No credential available" errors. This script always reseeds Vault
# after bringing the stack up, whether it was already running or not,
# so that failure mode simply can't happen from forgetting a step.
#
# Usage:
#   ./start.sh              # bring up everything, reseed Vault
#   ./start.sh --build       # also rebuild images before starting
# =====================================================================
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

BUILD_FLAG=""
for arg in "$@"; do
  case "$arg" in
    --build) BUILD_FLAG="--build" ;;
    *) echo "Unknown flag: $arg" >&2; exit 1 ;;
  esac
done

if [ ! -f .env ]; then
  echo "No .env found. Copy .env.example to .env and fill in real values first:" >&2
  echo "    cp .env.example .env" >&2
  exit 1
fi

echo "==> Starting the full stack (docker compose --profile full up -d $BUILD_FLAG)"
# shellcheck disable=SC2086
docker compose --profile full up -d $BUILD_FLAG

echo "==> Waiting for Vault to come up"
VAULT_READY=0
for i in $(seq 1 30); do
  status="$(docker inspect --format='{{.State.Health.Status}}' kovalyx-vault 2>/dev/null || echo "starting")"
  if [ "$status" = "healthy" ]; then
    VAULT_READY=1
    break
  fi
  sleep 2
done
if [ "$VAULT_READY" -ne 1 ]; then
  echo "Vault never became healthy after 60s — check 'docker compose logs vault'." >&2
  exit 1
fi

echo "==> Reseeding Vault (dev mode loses all secrets on every restart, so this always runs)"
if ! python -c "import hvac, dotenv" >/dev/null 2>&1; then
  echo "Missing Python deps for vault_init.py. Install them once with:" >&2
  echo "    pip install hvac python-dotenv" >&2
  exit 1
fi
VAULT_ADDR=http://localhost:8200 python scripts/vault_init.py --mode dev

echo "==> Waiting for Airflow webserver to come up"
AIRFLOW_READY=0
for i in $(seq 1 60); do
  status="$(docker inspect --format='{{.State.Health.Status}}' kovalyx-airflow-webserver 2>/dev/null || echo "starting")"
  if [ "$status" = "healthy" ]; then
    AIRFLOW_READY=1
    break
  fi
  sleep 3
done
if [ "$AIRFLOW_READY" -ne 1 ]; then
  echo "Airflow webserver didn't report healthy within 3 minutes — it may still be starting; check 'docker compose logs airflow-webserver'." >&2
else
  echo "Airflow webserver is healthy."
fi

echo ""
echo "==================================================================="
echo " Kovalyx is up."
echo "==================================================================="
echo " Frontend (dashboard):   http://localhost:3001"
echo " Airflow UI:             http://localhost:8090/airflow"
echo " Grafana:                http://localhost:8090/grafana"
echo " MinIO console:          http://localhost:8090/minio"
echo " Pipeline monitor:       http://localhost:8090/pipeline-monitor"
echo " Vault UI:               http://localhost:8200/ui  (token in .env: VAULT_TOKEN)"
echo "==================================================================="
echo " Vault has been reseeded. If a DAG run was mid-retry from before"
echo " this restart, clear it in the Airflow UI (or 'airflow tasks clear')"
echo " to force an immediate retry instead of waiting on backoff."
echo "==================================================================="
