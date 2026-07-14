#!/usr/bin/env bash
# confluentinc/cp-kafka's own /etc/confluent/docker/configure script only
# *checks* that KAFKA_OPTS references java.security.auth.login.config
# when SASL listeners are detected — it never generates that file. Left
# missing, the broker (and its internal ZooKeeper client, which also
# reads the same JVM-wide JAAS config) crashes at startup. A static
# mounted file can't work here since the credentials come from .env at
# runtime, not repo-committed values — so this wrapper writes the file
# from the same env vars already used for the per-listener
# KAFKA_LISTENER_NAME_*_SASL_JAAS_CONFIG values.
#
# Only a KafkaServer section is written, no Client section — ZooKeeper
# itself has no SASL configured in this stack (SASL_PLAINTEXT here is
# for client<->broker auth only), so Kafka's own internal ZooKeeper
# client correctly skips SASL when no Client section exists.
#
# The image's default entrypoint (/etc/confluent/docker/run) is NOT
# used here: its `ensure` step runs `cub zk-ready`, a separate preflight
# tool that (unlike the broker's own ZooKeeper client) always attempts
# SASL when KAFKA_OPTS references a login config, regardless of whether
# ZooKeeper actually supports it — that attempt fails and aborts the
# whole entrypoint chain before kafka-server-start is ever reached, even
# though the broker itself starts up fine. Verified directly: invoking
# `configure` + `kafka-server-start` (skipping `ensure`) starts cleanly.
# This is safe to skip because docker-compose.yml's `depends_on:
# condition: service_healthy` on zookeeper already guarantees it's up
# before this container starts.
set -euo pipefail

cat > /etc/kafka/kafka_server_jaas.conf <<EOF
KafkaServer {
   org.apache.kafka.common.security.plain.PlainLoginModule required
   username="${KAFKA_BROKER_USER}"
   password="${KAFKA_BROKER_PASSWORD}"
   user_${KAFKA_BROKER_USER}="${KAFKA_BROKER_PASSWORD}"
   user_${KAFKA_PRODUCER_USER}="${KAFKA_PRODUCER_PASSWORD}"
   user_${KAFKA_CONSUMER_USER}="${KAFKA_CONSUMER_PASSWORD}";
};
EOF

# Also write a real client properties file for the healthcheck (and any
# other in-container SASL/PLAIN client tool) to use via --command-config
# — that flag needs a client config with security.protocol/sasl.mechanism/
# sasl.jaas.config, not a raw JAAS file like kafka_server_jaas.conf above.
cat > /etc/kafka/kafka_client.properties <<EOF
security.protocol=SASL_PLAINTEXT
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="${KAFKA_BROKER_USER}" password="${KAFKA_BROKER_PASSWORD}";
EOF

/etc/confluent/docker/configure
exec kafka-server-start /etc/kafka/kafka.properties
