"""
Kovalyx — Kafka consumer that drains `kovalyx.events` into the MinIO Bronze
zone.

Bronze contract: append-only, zero transformation, zero PII masking (that
happens in Silver). Events are buffered in memory per (event_type, date)
partition and flushed to MinIO as newline-delimited JSON objects under:

    bronze/event_type=<event_type>/date=<YYYY-MM-DD>/<batch_id>.json

Kafka offsets are committed only *after* a successful MinIO write, giving
at-least-once delivery into Bronze. Duplicate records are expected and are
deduplicated downstream in the Silver PySpark job (order_id + event_type
composite key), which is the standard medallion pattern for this failure
mode.

Consumes with a dedicated consumer-only SASL/PLAIN credential — never
shares credentials with the producer.
"""

from __future__ import annotations

import io
import json
import logging
import os
import signal
import sys
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone

import boto3
import hvac
from botocore.client import Config as BotoConfig
from confluent_kafka import Consumer, KafkaException
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.json_schema import JSONDeserializer
from confluent_kafka.serialization import MessageField, SerializationContext
from prometheus_client import Counter, Gauge, start_http_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kovalyx.kafka_consumer")

TOPIC = os.environ.get("KOVALYX_EVENTS_TOPIC", "kovalyx.events")
CONSUMER_GROUP = os.environ.get("KAFKA_CONSUMER_GROUP", "kovalyx-bronze-consumer")
BRONZE_BUCKET = os.environ.get("MINIO_BRONZE_BUCKET", "bronze")
FLUSH_BATCH_SIZE = int(os.environ.get("CONSUMER_FLUSH_BATCH_SIZE", "200"))
FLUSH_INTERVAL_SECONDS = float(os.environ.get("CONSUMER_FLUSH_INTERVAL_SECONDS", "15"))
METRICS_PORT = int(os.environ.get("CONSUMER_METRICS_PORT", "8001"))

RECORDS_PROCESSED = Counter(
    "kovalyx_records_processed_total",
    "Total events successfully written to MinIO bronze",
    ["event_type"],
)
RECORDS_FAILED = Counter(
    "kovalyx_records_failed_total",
    "Total events that failed to write to MinIO bronze",
    ["event_type"],
)
BUFFER_SIZE_GAUGE = Gauge(
    "kovalyx_consumer_buffer_size",
    "Current number of buffered, unflushed events",
)


def get_secret(vault_client: hvac.Client | None, path: str, field_name: str, env_fallback: str) -> str:
    if vault_client is not None:
        try:
            resp = vault_client.secrets.kv.v2.read_secret_version(mount_point="kovalyx", path=path, raise_on_deleted_version=True)
            value = resp["data"]["data"].get(field_name)
            if value:
                return value
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read kovalyx/%s from Vault (%s); falling back to env var %s", path, exc, env_fallback)
    value = os.environ.get(env_fallback)
    if not value:
        raise RuntimeError(f"No credential available for {path}/{field_name} (checked Vault and env var {env_fallback})")
    return value


def build_vault_client() -> hvac.Client | None:
    vault_addr = os.environ.get("VAULT_ADDR")
    vault_token = os.environ.get("VAULT_TOKEN")
    if not vault_addr or not vault_token:
        logger.warning("VAULT_ADDR/VAULT_TOKEN not set — reading credentials from env vars directly")
        return None
    client = hvac.Client(url=vault_addr, token=vault_token)
    if not client.is_authenticated():
        logger.warning("Vault authentication failed — falling back to env vars")
        return None
    return client


def build_minio_client(vault_client: hvac.Client | None) -> "boto3.client":
    access_key = get_secret(vault_client, "minio/bronze-writer", "access_key", "MINIO_ACCESS_KEY")
    secret_key = get_secret(vault_client, "minio/bronze-writer", "secret_key", "MINIO_SECRET_KEY")
    endpoint = os.environ.get("MINIO_ENDPOINT", "http://minio:9000")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )


def ensure_bucket(s3_client, bucket: str) -> None:
    try:
        s3_client.head_bucket(Bucket=bucket)
    except Exception:  # noqa: BLE001
        logger.info("Bucket %s not found — creating it", bucket)
        s3_client.create_bucket(Bucket=bucket)


class BronzeWriter:
    """Buffers events per (event_type, date) partition and flushes each
    buffer to MinIO as one newline-delimited JSON object."""

    def __init__(self, s3_client, bucket: str):
        self.s3_client = s3_client
        self.bucket = bucket
        self.buffers: dict[tuple[str, str], list[dict]] = defaultdict(list)
        self.buffered_count = 0
        self.last_flush = time.monotonic()

    def add(self, event: dict) -> None:
        event_type = event.get("event_type", "unknown")
        event_date = _event_date(event)
        self.buffers[(event_type, event_date)].append(event)
        self.buffered_count += 1
        BUFFER_SIZE_GAUGE.set(self.buffered_count)

    def should_flush(self) -> bool:
        return self.buffered_count >= FLUSH_BATCH_SIZE or (time.monotonic() - self.last_flush) >= FLUSH_INTERVAL_SECONDS

    def flush(self) -> int:
        if self.buffered_count == 0:
            self.last_flush = time.monotonic()
            return 0

        written = 0
        for (event_type, event_date), events in list(self.buffers.items()):
            if not events:
                continue
            body = "\n".join(json.dumps(e) for e in events).encode("utf-8")
            key = f"event_type={event_type}/date={event_date}/{uuid.uuid4().hex}.json"
            try:
                self.s3_client.put_object(Bucket=self.bucket, Key=key, Body=io.BytesIO(body), ContentType="application/x-ndjson")
                RECORDS_PROCESSED.labels(event_type=event_type).inc(len(events))
                written += len(events)
                logger.info("Flushed %d events to s3://%s/%s", len(events), self.bucket, key)
            except Exception:
                logger.exception("Failed to write batch to s3://%s/%s", self.bucket, key)
                RECORDS_FAILED.labels(event_type=event_type).inc(len(events))
                raise
            finally:
                self.buffers[(event_type, event_date)] = []

        self.buffered_count = 0
        BUFFER_SIZE_GAUGE.set(0)
        self.last_flush = time.monotonic()
        return written


def _event_date(event: dict) -> str:
    ts = event.get("event_timestamp")
    if not ts:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def main() -> int:
    start_http_server(METRICS_PORT)
    logger.info("Prometheus metrics exposed on :%d/metrics", METRICS_PORT)

    vault_client = build_vault_client()
    consumer_user = get_secret(vault_client, "kafka/consumer", "username", "KAFKA_CONSUMER_USER")
    consumer_password = get_secret(vault_client, "kafka/consumer", "password", "KAFKA_CONSUMER_PASSWORD")
    bootstrap_servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
    schema_registry_url = os.environ.get("SCHEMA_REGISTRY_URL", "http://schema-registry:8081")

    schema_registry_client = SchemaRegistryClient({"url": schema_registry_url})
    json_deserializer = JSONDeserializer(schema_str=None, schema_registry_client=schema_registry_client)

    s3_client = build_minio_client(vault_client)
    ensure_bucket(s3_client, BRONZE_BUCKET)
    writer = BronzeWriter(s3_client, BRONZE_BUCKET)

    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap_servers,
            "security.protocol": "SASL_PLAINTEXT",
            "sasl.mechanism": "PLAIN",
            "sasl.username": consumer_user,
            "sasl.password": consumer_password,
            "group.id": CONSUMER_GROUP,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([TOPIC])

    running = {"flag": True}

    def _shutdown(signum, frame):  # noqa: ANN001
        logger.info("Received signal %s, shutting down gracefully", signum)
        running["flag"] = False

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("Kovalyx consumer starting: topic=%s group=%s bucket=%s", TOPIC, CONSUMER_GROUP, BRONZE_BUCKET)

    try:
        while running["flag"]:
            msg = consumer.poll(timeout=1.0)
            if msg is not None:
                if msg.error():
                    raise KafkaException(msg.error())
                ctx = SerializationContext(TOPIC, MessageField.VALUE)
                try:
                    event = json_deserializer(msg.value(), ctx)
                    writer.add(event)
                except Exception:
                    logger.exception("Failed to deserialize message at offset %d — skipping", msg.offset())
                    RECORDS_FAILED.labels(event_type="unknown").inc()

            if writer.should_flush():
                writer.flush()
                consumer.commit(asynchronous=False)
    finally:
        logger.info("Final flush before shutdown...")
        writer.flush()
        consumer.commit(asynchronous=False)
        consumer.close()
        logger.info("Kovalyx consumer stopped cleanly")

    return 0


if __name__ == "__main__":
    sys.exit(main())
