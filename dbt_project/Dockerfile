# Standalone image for the `dbt` service in docker-compose.yml /
# docker-compose.prod.yml (profile "jobs"/"full") — a one-off job
# container, not a daemon: `docker compose run --rm dbt <dbt-args>`.
FROM python:3.11-slim

WORKDIR /opt/kovalyx/dbt_project

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DBT_PROFILES_DIR=/opt/kovalyx/dbt_project

ENTRYPOINT ["dbt"]
CMD ["--help"]
