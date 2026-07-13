# Security Policy

## Security Architecture

- **Secrets management** — every credential (Kafka SASL users, MinIO keys,
  Postgres passwords, Airflow's Fernet/webserver keys) lives in HashiCorp
  Vault behind least-privilege AppRole policies (`kovalyx-bronze`,
  `kovalyx-silver`, `kovalyx-gold`, `kovalyx-airflow`). Nothing is
  hardcoded in source; `.env` is git-ignored and only documents which
  variables exist.
- **PII masking** — the Silver PySpark job runs Microsoft Presidio plus
  deterministic hashing/literal masking on every guaranteed-PII field
  before data ever reaches Gold. Masking guaranteed-PII fields does not
  depend on NER confidence thresholds, so a low-confidence detection
  can't let raw PII slip through.
- **Row Level Security** — Supabase's `marts` schema applies RLS via
  `marts.apply_analytics_rls()`/`marts.apply_pipeline_writer_rls()`,
  scoping the `analytics_reader` and `pipeline_writer` roles to exactly
  what the frontend and pipeline need, respectively.
- **Network isolation** — Docker Compose splits services across three
  networks (`kovalyx_bronze_net`, `kovalyx_silver_net`, `kovalyx_gold_net`);
  a service only joins the networks it actually needs to reach, and in
  production every public-facing port is only reachable through Nginx.

## Reporting a Vulnerability

Do not open a public GitHub issue for security vulnerabilities.

Email **security@kovalyx.dev** (placeholder address — replace with a real
monitored inbox before running this in any non-portfolio context). We
aim to respond within 72 hours.

Please include:
- A description of the vulnerability.
- Steps to reproduce it.
- Its potential impact.

## What's in Scope

- Credential exposure in any file in this repository.
- PII data reaching the Gold layer or the frontend unmasked.
- Vault policy misconfigurations (over-broad AppRole grants, etc.).
- Broken or bypassable authentication on any service.

## What's Out of Scope

- Issues in third-party dependencies — report those upstream.
- Theoretical attacks without a proof of concept.

## Security Assumptions

Kovalyx is a portfolio/educational project. Its security architecture
demonstrates production-grade patterns, but the codebase has not undergone
a formal penetration test. Do not use this project to store real PII or
other sensitive personal data.
