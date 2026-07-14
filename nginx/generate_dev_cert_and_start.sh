#!/bin/sh
# Dropped into /docker-entrypoint.d/, which nginx's own image already
# auto-runs (in filename order) before starting nginx — no ENTRYPOINT
# override needed.
#
# nginx.conf's :443 server block references fullchain.pem/privkey.pem
# unconditionally, so nginx fails to even parse its config without them
# — not just for local dev: deploy/oracle_cloud_setup.sh's own flow
# starts nginx *before* certbot has run (to serve the ACME challenge on
# :80), so this same gap exists there too. A self-signed placeholder is
# generated here if no real cert is present yet; oracle_cloud_setup.sh
# overwrites it with the real Let's Encrypt cert once certbot completes.
set -eu

CERT_DIR=/etc/nginx/certs

if [ ! -f "$CERT_DIR/fullchain.pem" ] || [ ! -f "$CERT_DIR/privkey.pem" ]; then
    echo "No TLS certificate found in $CERT_DIR — generating a self-signed placeholder"
    openssl req -x509 -nodes -days 365 \
        -newkey rsa:2048 \
        -keyout "$CERT_DIR/privkey.pem" \
        -out "$CERT_DIR/fullchain.pem" \
        -subj "/CN=kovalyx.local"
fi
