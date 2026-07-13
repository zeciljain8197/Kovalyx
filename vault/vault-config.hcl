# Kovalyx — HashiCorp Vault production-mode configuration.
#
# Used only by docker-compose.prod.yml (`vault server -config=/vault/config/vault-config.hcl`).
# Local dev instead runs Vault in dev mode via VAULT_DEV_ROOT_TOKEN_ID in
# docker-compose.yml, which needs no config file.
#
# TLS is intentionally disabled on the listener: Vault is never published to
# the host (no `ports:` entry in docker-compose.prod.yml) and is reachable
# only from the kovalyx_bronze_net / kovalyx_silver_net / kovalyx_gold_net
# Docker networks it shares with trusted services. All external traffic is
# terminated at nginx, which Vault sits behind. If Vault is ever exposed
# beyond the Docker host, this listener must be reconfigured with real
# certificates before that happens.

ui = true

storage "raft" {
  path    = "/vault/file"
  node_id = "kovalyx-vault-1"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1
}

api_addr     = "http://vault:8200"
cluster_addr = "http://vault:8201"

disable_mlock = false

# Vault starts sealed after every restart. scripts/vault_init.py performs
# the one-time `vault operator init` on first boot (persisting the unseal
# keys + initial root token to a file with 0600 perms outside the repo,
# per its own instructions) and `vault operator unseal` on every restart.
default_lease_ttl = "168h"
max_lease_ttl      = "720h"

log_level = "info"
