#!/usr/bin/env bash
# Referenced by docker-compose.yml / docker-compose.prod.yml's
# postgres-metadata service (mounted into docker-entrypoint-initdb.d/).
# The official postgres image only creates one database via POSTGRES_DB
# — this reads the comma-separated POSTGRES_MULTIPLE_DATABASES env var
# (airflow, great_expectations, kovalyx_audit) and creates each one,
# owned by POSTGRES_USER, in the same Postgres instance.
set -euo pipefail

function create_database() {
    local database=$1
    echo "  Creating database '$database'"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
        CREATE DATABASE "$database";
        GRANT ALL PRIVILEGES ON DATABASE "$database" TO "$POSTGRES_USER";
EOSQL
}

if [ -n "${POSTGRES_MULTIPLE_DATABASES:-}" ]; then
    echo "Multiple database creation requested: $POSTGRES_MULTIPLE_DATABASES"
    IFS=',' read -ra DBS <<< "$POSTGRES_MULTIPLE_DATABASES"
    for db in "${DBS[@]}"; do
        create_database "$db"
    done
    echo "Multiple databases created"
fi
