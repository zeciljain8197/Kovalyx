# Contributing to Kovalyx

Thanks for considering a contribution. Kovalyx is a portfolio-grade, open-source
medallion analytics pipeline — issues, PRs, and design feedback are all welcome.

## Getting Started

```bash
git clone https://github.com/zeciljain8197/Kovalyx.git
cd kovalyx
cp .env.example .env   # fill in real values — see the comments in .env.example
docker compose up -d
```

`.env.example` documents every variable the stack needs (Kafka SASL credentials,
MinIO keys, Postgres credentials, Airflow admin account, Vault addressing, etc.).
Local dev generates its own Vault dev-mode root token and self-contained
Postgres-gold instance, so you don't need a real Supabase project to run the
full stack locally.

## Project Architecture

- **Bronze** (`ingestion/`) — a Faker-driven Kafka producer streams synthetic
  retail events (SASL/PLAIN-authenticated) into `kovalyx.events`; a consumer
  drains them into MinIO's `bronze` bucket alongside batch CSV seed data.
- **Silver** (`spark/`, `quality/`) — a PySpark job reads Bronze, applies
  Microsoft Presidio + deterministic hashing to mask PII, and writes typed
  Parquet to MinIO's `silver` bucket; Great Expectations checkpoints gate
  every table before it's considered usable downstream.
- **Gold** (`scripts/silver_to_postgres_loader.py`, `dbt_project/`) — Silver
  Parquet is loaded into Postgres `staging`, then dbt transforms it through
  staging views into a Kimball-style star schema (`marts`) with an SCD2
  snapshot on customer dimension changes.
- **Orchestration** (`airflow/`) — an Airflow DAG runs the full Bronze → Silver
  → Gold chain every two hours, authenticating to Vault via AppRole rather
  than static credentials.
- **Frontend** (`frontend/`) — a Next.js dashboard on Vercel reads `marts.*`
  directly from Supabase for end users; `streamlit_monitor/` is an internal
  ops view over the `audit` schema.
- **Monitoring** (`monitoring/`, `nginx/`) — Prometheus + Grafana + Loki/Promtail
  for metrics and logs, fronted by Nginx as the single reverse-proxy entrypoint.

See the architecture diagram in [README.md](README.md) for how these connect.

## Development Workflow

- Branch naming: `feature/<short-description>` or `fix/<short-description>`.
- Open a PR against `main`. CI (`.github/workflows/ci.yml`) must pass —
  secret scanning, Dockerfile vulnerability scanning, dbt compile/test,
  Python compile checks, and a Docker build validation.
- Merges to `main` trigger `.github/workflows/deploy.yml`, which rolls the
  production stack on the Oracle Cloud VM. Treat `main` as always-deployable.

## Running Tests Locally

```bash
# dbt
cd dbt_project && dbt test --profiles-dir . --target dev

# Python syntax across the whole repo
find . -name "*.py" -not -path "./.git/*" | xargs python -m py_compile

# Great Expectations checkpoints against yesterday's Silver output
python quality/run_checkpoints.py --run-id local-test --date $(date -d yesterday +%F) --env dev
```

## Required GitHub Secrets

Configure these under Settings → Secrets and variables → Actions:

| Secret | Used by | Purpose |
|---|---|---|
| `CI_PG_HOST` | `ci.yml` | Postgres host for `dbt compile`/`dbt test` in CI |
| `CI_PG_PORT` | `ci.yml` | Postgres port for CI's dbt target |
| `CI_PG_DATABASE` | `ci.yml` | Database name for CI's dbt target |
| `CI_PG_USER` | `ci.yml` | Postgres user for CI's dbt target |
| `CI_PG_PASSWORD` | `ci.yml` | Postgres password for CI's dbt target |
| `ORACLE_VM_HOST` | `deploy.yml` | SSH host of the production Oracle Cloud VM |
| `ORACLE_VM_USER` | `deploy.yml` | SSH user for deployment |
| `ORACLE_VM_SSH_KEY` | `deploy.yml` | Private key for SSH deployment access |
| `STREAMLIT_WEBHOOK_URL` | `deploy.yml` | Triggers a Streamlit Community Cloud redeploy after a successful deploy |

## Code Style

- **Python**: no hardcoded credentials (everything comes from env vars or
  Vault), `logging` instead of `print`, and a docstring on every function,
  method, and class.
- **dbt SQL**: linted with SQLFluff, `postgres` dialect, 120-character line
  limit (`dbt_project/.sqlfluff`).
- **Commit messages**: [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `chore:`, `docs:`, ...).

## Responsible Disclosure

Found a security issue? Do not open a public issue — see [SECURITY.md](SECURITY.md).
