#!/usr/bin/env bash
# =====================================================================
# Kovalyx — one-time bootstrap for a fresh Oracle Cloud Always Free
# Ubuntu 22.04 ARM instance. Idempotent where practical, but intended to
# be run once against a brand-new VM, top to bottom.
#
# Pre-check finding: docker-compose.prod.yml defines no `vault-init` or
# `seed-data` service, and its x-airflow-common only mounts
# airflow/dags + airflow/plugins (read-only) — none of scripts/, vault/,
# spark/, quality/, dbt_project/ are mounted into any production
# container. Wiring that up is an infra change beyond this script's
# scope (docker-compose.prod.yml is frozen this session), so the two
# one-off Python jobs below (vault_init.py, seed_data.py) run in plain
# `docker run` throwaway containers on kovalyx_bronze_net instead of via
# `docker compose run` — bronze_net alone reaches vault/minio/kafka
# (vault and minio are dual/triple-homed across all three networks),
# and dependencies are pip-installed inline since no existing image
# bundles hvac+boto3+pandas+faker+python-dotenv together.
# =====================================================================
set -euo pipefail

KOVALYX_DIR="/opt/kovalyx"
ONEOFF_DEPS="hvac==2.3.0 boto3==1.34.131 pandas==2.2.2 faker==25.8.0 python-dotenv==1.0.1"

# ---------------------------------------------------------------------
# 1. System update and dependencies
# ---------------------------------------------------------------------
echo "==> Updating system packages..."
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y --no-install-recommends \
    curl git ufw certbot python3-certbot-nginx \
    apt-transport-https ca-certificates gnupg lsb-release

# ---------------------------------------------------------------------
# 2. Docker installation (official Docker repo, not the snap package)
# ---------------------------------------------------------------------
echo "==> Installing Docker Engine..."
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo systemctl enable docker
sudo systemctl start docker
# Lets the current user run `docker` without sudo after their next login.
sudo usermod -aG docker "$USER"

# ---------------------------------------------------------------------
# 3. Clone the Kovalyx repo
# ---------------------------------------------------------------------
echo "==> Cloning Kovalyx..."
if [ ! -d "$KOVALYX_DIR" ]; then
    sudo git clone https://github.com/zeciljain8197/Kovalyx.git "$KOVALYX_DIR"
    sudo chown -R "$USER":"$USER" "$KOVALYX_DIR"
fi
cd "$KOVALYX_DIR"

echo "Copy your .env file to $KOVALYX_DIR/.env before continuing."
read -r -p "Press Enter when .env is in place..."

# ---------------------------------------------------------------------
# 4. Vault production initialization
# ---------------------------------------------------------------------
echo "==> Starting Vault..."
docker compose -f docker-compose.prod.yml up -d vault

echo "==> Waiting for Vault to be ready..."
timeout 60 bash -c \
    'until curl -sf "http://localhost:8200/v1/sys/health?standbyok=true" > /dev/null; do sleep 3; done'

echo "==> Running vault_init.py (production mode)..."
# vault_init.py's real flag is --mode (dev|prod), not --env, and it loads
# credentials via `load_dotenv(REPO_ROOT / ".env")` where REPO_ROOT is
# resolved from its own file location — inside this container that's
# /opt/kovalyx, so .env must be mounted there too, or every
# os.environ.get(...) call in the script silently returns None.
docker run --rm \
    --network kovalyx_bronze_net \
    -e VAULT_ADDR="http://vault:8200" \
    -v "$KOVALYX_DIR/scripts:/opt/kovalyx/scripts:ro" \
    -v "$KOVALYX_DIR/vault:/opt/kovalyx/vault" \
    -v "$KOVALYX_DIR/.env:/opt/kovalyx/.env:ro" \
    -w /opt/kovalyx/scripts \
    python:3.11-slim \
    bash -c "pip install -q $ONEOFF_DEPS && python vault_init.py --mode prod"

echo "IMPORTANT: Save the vault_init.py output above — unseal keys and the root token are shown once only."
read -r -p "Confirm you have saved the Vault credentials: "

# ---------------------------------------------------------------------
# 5. Nginx + Let's Encrypt SSL
# ---------------------------------------------------------------------
read -r -p "Enter your domain name (e.g. kovalyx.yourdomain.com): " DOMAIN

echo "==> Starting Nginx (HTTP-only, for the certbot ACME challenge)..."
docker compose -f docker-compose.prod.yml up -d nginx

echo "==> Requesting a Let's Encrypt certificate for $DOMAIN..."
sudo certbot certonly --webroot \
    -w /var/www/certbot \
    -d "$DOMAIN" \
    --non-interactive \
    --agree-tos \
    -m "admin@$DOMAIN"

echo "==> Copying certs into nginx/certs/..."
sudo cp "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" nginx/certs/
sudo cp "/etc/letsencrypt/live/$DOMAIN/privkey.pem" nginx/certs/
sudo chown "$USER":"$USER" nginx/certs/*.pem

docker compose -f docker-compose.prod.yml exec nginx nginx -s reload

# ---------------------------------------------------------------------
# 6. UFW firewall
# ---------------------------------------------------------------------
echo "==> Configuring the firewall..."
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (certbot challenge + redirect to HTTPS)
sudo ufw allow 443/tcp   # HTTPS
sudo ufw --force enable
# All other ports (8080/Airflow, 3000/Grafana, 9001/MinIO, 9090/Prometheus)
# are reachable only through Nginx on 443 — never exposed directly.

# ---------------------------------------------------------------------
# 7. Start the full stack
# ---------------------------------------------------------------------
echo "==> Starting the full Kovalyx stack..."
docker compose -f docker-compose.prod.yml --profile full up -d

echo "==> Waiting for services to report healthy (up to 300s)..."
timeout 300 bash -c \
    'until [ "$(docker compose -f docker-compose.prod.yml ps --format json | grep -c "\"Health\":\"healthy\"")" -gt 0 ]; do sleep 5; done' || \
    echo "WARNING: not all services reported healthy within 300s — check 'docker compose ps' manually."

docker compose -f docker-compose.prod.yml ps

# ---------------------------------------------------------------------
# 8. Seed initial data
# ---------------------------------------------------------------------
echo "==> Seeding initial batch data..."
# seed_data.py has no --env/--mode flag; like vault_init.py it loads
# REPO_ROOT/.env directly, so .env must be mounted at /opt/kovalyx here too.
docker run --rm \
    --network kovalyx_bronze_net \
    -e KOVALYX_MINIO_ENDPOINT=minio:9000 \
    -e VAULT_ADDR="http://vault:8200" \
    -v "$KOVALYX_DIR/scripts:/opt/kovalyx/scripts:ro" \
    -v "$KOVALYX_DIR/vault:/opt/kovalyx/vault:ro" \
    -v "$KOVALYX_DIR/.env:/opt/kovalyx/.env:ro" \
    -w /opt/kovalyx/scripts \
    python:3.11-slim \
    bash -c "pip install -q $ONEOFF_DEPS && python seed_data.py"

# ---------------------------------------------------------------------
# 9. Certbot auto-renewal cron
# ---------------------------------------------------------------------
echo "==> Installing the certbot renewal cron job..."
CRON_LINE="0 0 * * * certbot renew --quiet && docker compose -f $KOVALYX_DIR/docker-compose.prod.yml exec nginx nginx -s reload"
(crontab -l 2>/dev/null | grep -vF "certbot renew"; echo "$CRON_LINE") | crontab -

# ---------------------------------------------------------------------
# 10. Final instructions
# ---------------------------------------------------------------------
cat <<EOF

==============================================================
Kovalyx is up.

  Airflow UI:         https://$DOMAIN/airflow (admin credentials from .env)
  Grafana:             https://$DOMAIN/grafana (admin/admin, change on first login)
  MinIO:               https://$DOMAIN/minio
  Pipeline monitor:    https://$DOMAIN/pipeline-monitor
  Next.js dashboard:   https://kovalyx.vercel.app (deployed via Vercel)

Next steps:
  1. Add the GitHub Secrets listed in CONTRIBUTING.md to your repo.
  2. Push to main to trigger the first deployment via GitHub Actions.
  3. Configure Airflow variables: kovalyx_env, kovalyx_alert_email.
==============================================================
EOF
