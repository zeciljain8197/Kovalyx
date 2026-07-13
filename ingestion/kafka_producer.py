"""
Kovalyx — Kafka producer for the synthetic Shopify-like event stream.

Simulates a live e-commerce store using Faker: customers register, browse,
add items to cart, place orders, pay, get shipped/delivered/returned goods,
and inventory gets adjusted behind the scenes. Every event is published as
JSON (schema-validated against Confluent Schema Registry) to the
`kovalyx.events` topic, authenticated via Kafka SASL/PLAIN using a
producer-only credential pulled from Vault.

Bronze-layer contract: this producer performs zero transformation or PII
masking — that happens downstream in the Silver PySpark job via Presidio.
Every event carries the same flat 19-field envelope (fields not applicable
to a given event_type are explicitly null, never omitted) so Spark can read
an entire bronze partition with one fixed schema. Events intentionally
carry realistic PII (name, email, phone, address, card last4/type) so the
masking/audit layer has real work to do.

Run modes:
    python kafka_producer.py                        # run until killed
    python kafka_producer.py --duration-seconds 300  # burst mode (used by
                                                        # the Airflow DAG's
                                                        # kafka_producer_trigger task)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import signal
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import hvac
from confluent_kafka import Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.json_schema import JSONSerializer
from confluent_kafka.serialization import (
    MessageField,
    SerializationContext,
    StringSerializer,
)
from faker import Faker
from prometheus_client import Counter, start_http_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kovalyx.kafka_producer")

TOPIC = os.environ.get("KOVALYX_EVENTS_TOPIC", "kovalyx.events")
EVENTS_PER_SECOND = float(os.environ.get("PRODUCER_EVENTS_PER_SECOND", "5"))
METRICS_PORT = int(os.environ.get("PRODUCER_METRICS_PORT", "8000"))

EVENT_TYPES = [
    "customer_registered",
    "item_added_to_cart",
    "order_placed",
    "payment_processed",
    "order_shipped",
    "order_delivered",
    "order_returned",
    "inventory_updated",
]

# Roughly mirrors a real funnel: lots of browsing, fewer completed orders,
# fewer still returns.
EVENT_TYPE_WEIGHTS = {
    "customer_registered": 5,
    "item_added_to_cart": 30,
    "order_placed": 20,
    "payment_processed": 18,
    "order_shipped": 12,
    "order_delivered": 10,
    "order_returned": 3,
    "inventory_updated": 2,
}

# Bronze contract: the status value written onto every event of that type.
# inventory_updated carries no order-funnel status — it populates
# stock_level/reorder_threshold instead.
EVENT_STATUS = {
    "customer_registered": "active",
    "item_added_to_cart": "in_cart",
    "order_placed": "placed",
    "payment_processed": "paid",
    "order_shipped": "shipped",
    "order_delivered": "delivered",
    "order_returned": "returned",
    "inventory_updated": None,
}

CARD_TYPES = ["Visa", "Mastercard", "Amex", "Discover"]
CATEGORIES = ["Apparel", "Home Goods", "Electronics", "Beauty", "Outdoor", "Toys"]

def _build_product_catalog(size: int = 200) -> list[dict]:
    """Built once at import time with a scratch Faker instance (the shared,
    seeded Faker used for event generation is created later in main())."""
    catalog_faker = Faker()
    return [
        {
            "product_id": f"PROD-{i:04d}",
            "product_name": catalog_faker.catch_phrase(),
            "category": random.choice(CATEGORIES),
            "unit_price": round(random.uniform(8, 250), 2),
            "reorder_threshold": random.randint(15, 60),
        }
        for i in range(size)
    ]


PRODUCT_CATALOG = _build_product_catalog()

EVENTS_PRODUCED = Counter(
    "kovalyx_records_processed_total",
    "Total events successfully produced to Kafka",
    ["event_type"],
)
EVENTS_FAILED = Counter(
    "kovalyx_records_failed_total",
    "Total events that failed to produce to Kafka",
    ["event_type"],
)


def get_secret(vault_client: hvac.Client | None, path: str, field_name: str, env_fallback: str) -> str:
    """Pulls a credential from Vault; falls back to a plain env var for
    local dev when Vault isn't reachable (e.g. running the script outside
    docker compose)."""
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
        logger.warning("VAULT_ADDR/VAULT_TOKEN not set — reading Kafka credentials from env vars directly")
        return None
    client = hvac.Client(url=vault_addr, token=vault_token)
    if not client.is_authenticated():
        logger.warning("Vault authentication failed — falling back to env vars")
        return None
    return client


def generate_e164_phone() -> str:
    """Generates a syntactically valid US E.164 number (+1 followed by a
    10-digit NANP-shaped subscriber number), since Faker's phone_number()
    produces locale-formatted strings like "(555) 012-3456", not E.164."""
    area_code = random.randint(200, 999)
    exchange = random.randint(200, 999)
    subscriber = random.randint(1000, 9999)
    return f"+1{area_code}{exchange}{subscriber}"


def format_shipping_address(faker: Faker) -> str:
    return f"{faker.street_address()}, {faker.city()}, {faker.state_abbr()} {faker.postcode()}"


def make_customer(faker: Faker) -> dict:
    return {
        "customer_id": f"CUST-{uuid.uuid4().hex[:10]}",
        "customer_name": faker.name(),
        "customer_email": faker.unique.email(),
        "customer_phone": generate_e164_phone(),
        "shipping_address": format_shipping_address(faker),
        "card_last4": f"{random.randint(0, 9999):04d}",
        "card_type": random.choice(CARD_TYPES),
    }


def iso_timestamp_ms() -> str:
    """ISO 8601 with millisecond precision and a literal 'Z' suffix, e.g.
    2024-01-15T14:23:11.000Z — Python's isoformat() defaults to '+00:00'
    for UTC, which the bronze contract doesn't accept."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def base_envelope(event_type: str) -> dict:
    """Every key in the 19-field bronze contract, defaulted to null. Only
    event_id/event_type/event_timestamp/status are set here — callers fill
    in the rest per event type."""
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_timestamp": iso_timestamp_ms(),
        "order_id": None,
        "customer_id": None,
        "customer_name": None,
        "customer_email": None,
        "customer_phone": None,
        "product_id": None,
        "product_name": None,
        "category": None,
        "quantity": None,
        "unit_price": None,
        "order_amount": None,
        "shipping_address": None,
        "card_last4": None,
        "card_type": None,
        "status": EVENT_STATUS[event_type],
        "stock_level": None,
        "reorder_threshold": None,
    }


@dataclass
class StoreState:
    """In-memory simulation state so events reference each other
    consistently (a payment_processed always follows a real order_placed
    for the same order_id, etc.) instead of being pure noise."""

    faker: Faker
    customers: dict[str, dict] = field(default_factory=dict)
    carts: list[dict] = field(default_factory=list)
    open_orders: list[dict] = field(default_factory=list)

    def ensure_customer(self) -> dict:
        if not self.customers or random.random() < 0.15:
            customer = make_customer(self.faker)
            self.customers[customer["customer_id"]] = customer
            return customer
        return random.choice(list(self.customers.values()))


def _apply_customer_fields(event: dict, customer: dict) -> None:
    event["customer_id"] = customer["customer_id"]
    event["customer_name"] = customer["customer_name"]
    event["customer_email"] = customer["customer_email"]
    event["customer_phone"] = customer["customer_phone"]
    event["shipping_address"] = customer["shipping_address"]


def _apply_product_fields(event: dict, product: dict) -> None:
    event["product_id"] = product["product_id"]
    event["product_name"] = product["product_name"]
    event["category"] = product["category"]


def generate_event(state: StoreState) -> dict:
    """Builds one bronze-contract event. Cart items are given a real
    order_id at item_added_to_cart time (the contract only allows a null
    order_id for inventory_updated/customer_registered), which order_placed
    then either promotes into a full order or discards in favor of a fresh
    order_id if no cart is available to convert."""
    faker = state.faker
    event_type = random.choices(EVENT_TYPES, weights=[EVENT_TYPE_WEIGHTS[t] for t in EVENT_TYPES])[0]
    product = random.choice(PRODUCT_CATALOG)

    if event_type == "customer_registered":
        customer = make_customer(faker)
        state.customers[customer["customer_id"]] = customer
        event = base_envelope(event_type)
        _apply_customer_fields(event, customer)
        return event

    customer = state.ensure_customer()
    event = base_envelope(event_type)

    if event_type == "item_added_to_cart":
        quantity = random.randint(1, 4)
        cart = {
            "order_id": f"ORD-{uuid.uuid4().hex[:12]}",
            "customer_id": customer["customer_id"],
            "product_id": product["product_id"],
            "product_name": product["product_name"],
            "category": product["category"],
            "quantity": quantity,
            "unit_price": product["unit_price"],
            "order_amount": round(product["unit_price"] * quantity, 2),
        }
        state.carts.append(cart)
        event["order_id"] = cart["order_id"]
        _apply_customer_fields(event, customer)
        _apply_product_fields(event, product)
        event["quantity"] = cart["quantity"]
        event["unit_price"] = cart["unit_price"]
        event["order_amount"] = cart["order_amount"]
        # card_last4/card_type aren't captured until checkout (order_placed).

    elif event_type == "order_placed":
        customer_carts = [c for c in state.carts if c["customer_id"] == customer["customer_id"]]
        if customer_carts and random.random() < 0.6:
            cart = customer_carts[0]
            state.carts.remove(cart)
            order = dict(cart)
        else:
            quantity = random.randint(1, 4)
            order = {
                "order_id": f"ORD-{uuid.uuid4().hex[:12]}",
                "customer_id": customer["customer_id"],
                "product_id": product["product_id"],
                "product_name": product["product_name"],
                "category": product["category"],
                "quantity": quantity,
                "unit_price": product["unit_price"],
                "order_amount": round(product["unit_price"] * quantity, 2),
            }
        order["shipping_address"] = customer["shipping_address"]
        order["card_last4"] = customer["card_last4"]
        order["card_type"] = customer["card_type"]
        state.open_orders.append(order)

        event["order_id"] = order["order_id"]
        _apply_customer_fields(event, customer)
        event["product_id"] = order["product_id"]
        event["product_name"] = order["product_name"]
        event["category"] = order["category"]
        event["quantity"] = order["quantity"]
        event["unit_price"] = order["unit_price"]
        event["order_amount"] = order["order_amount"]
        event["card_last4"] = order["card_last4"]
        event["card_type"] = order["card_type"]

    elif event_type in ("payment_processed", "order_shipped", "order_delivered", "order_returned"):
        if state.open_orders:
            order = random.choice(state.open_orders)
            order_customer = state.customers.get(order["customer_id"], customer)
            event["order_id"] = order["order_id"]
            _apply_customer_fields(event, order_customer)
            event["product_id"] = order["product_id"]
            event["product_name"] = order["product_name"]
            event["category"] = order["category"]
            event["quantity"] = order["quantity"]
            event["unit_price"] = order["unit_price"]
            event["order_amount"] = order["order_amount"]
            event["card_last4"] = order["card_last4"]
            event["card_type"] = order["card_type"]
            if event_type == "order_returned":
                state.open_orders = [o for o in state.open_orders if o["order_id"] != order["order_id"]]
        else:
            # No open orders yet — degrade gracefully to a cart event so we
            # never emit a payment/shipping event with no backing order.
            event["event_type"] = "item_added_to_cart"
            event["status"] = EVENT_STATUS["item_added_to_cart"]
            quantity = 1
            cart = {
                "order_id": f"ORD-{uuid.uuid4().hex[:12]}",
                "customer_id": customer["customer_id"],
                "product_id": product["product_id"],
                "product_name": product["product_name"],
                "category": product["category"],
                "quantity": quantity,
                "unit_price": product["unit_price"],
                "order_amount": round(product["unit_price"] * quantity, 2),
            }
            state.carts.append(cart)
            event["order_id"] = cart["order_id"]
            _apply_customer_fields(event, customer)
            _apply_product_fields(event, product)
            event["quantity"] = cart["quantity"]
            event["unit_price"] = cart["unit_price"]
            event["order_amount"] = cart["order_amount"]

    elif event_type == "inventory_updated":
        # Warehouse-side event with no specific customer attached — the
        # bronze contract table doesn't call out an explicit null exception
        # for customer_id, but attributing a stock adjustment to a random
        # shopper would be semantically wrong, so customer_id/PII stay null
        # here same as order_id does.
        _apply_product_fields(event, product)
        event["stock_level"] = random.randint(0, 500)
        event["reorder_threshold"] = product["reorder_threshold"]

    return event


def register_schema(schema_registry_client: SchemaRegistryClient) -> JSONSerializer:
    schema_str = json.dumps(
        {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "KovalyxEvent",
            "type": "object",
            "required": ["event_id", "event_type", "event_timestamp"],
            "properties": {
                "event_id": {"type": "string"},
                "event_type": {"type": "string", "enum": EVENT_TYPES},
                "event_timestamp": {"type": "string"},
                "order_id": {"type": ["string", "null"]},
                "customer_id": {"type": ["string", "null"]},
                "customer_name": {"type": ["string", "null"]},
                "customer_email": {"type": ["string", "null"]},
                "customer_phone": {"type": ["string", "null"]},
                "product_id": {"type": ["string", "null"]},
                "product_name": {"type": ["string", "null"]},
                "category": {"type": ["string", "null"]},
                "quantity": {"type": ["integer", "null"]},
                "unit_price": {"type": ["number", "null"]},
                "order_amount": {"type": ["number", "null"]},
                "shipping_address": {"type": ["string", "null"]},
                "card_last4": {"type": ["string", "null"]},
                "card_type": {"type": ["string", "null"]},
                "status": {"type": ["string", "null"]},
                "stock_level": {"type": ["integer", "null"]},
                "reorder_threshold": {"type": ["integer", "null"]},
            },
        }
    )
    return JSONSerializer(schema_str, schema_registry_client, conf={"auto.register.schemas": True})


def delivery_report(err, msg) -> None:
    event_type = "unknown"
    try:
        headers = dict(msg.headers() or [])
        event_type = headers.get("event_type", b"unknown").decode()
    except Exception:  # noqa: BLE001
        pass
    if err is not None:
        logger.error("Delivery failed for record %s: %s", msg.key(), err)
        EVENTS_FAILED.labels(event_type=event_type).inc()
    else:
        EVENTS_PRODUCED.labels(event_type=event_type).inc()


def main() -> int:
    parser = argparse.ArgumentParser(description="Kovalyx Kafka event producer")
    parser.add_argument("--duration-seconds", type=int, default=None, help="Run for N seconds then exit (burst mode)")
    args = parser.parse_args()

    start_http_server(METRICS_PORT)
    logger.info("Prometheus metrics exposed on :%d/metrics", METRICS_PORT)

    vault_client = build_vault_client()
    producer_user = get_secret(vault_client, "kafka/producer", "username", "KAFKA_PRODUCER_USER")
    producer_password = get_secret(vault_client, "kafka/producer", "password", "KAFKA_PRODUCER_PASSWORD")
    bootstrap_servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
    schema_registry_url = os.environ.get("SCHEMA_REGISTRY_URL", "http://schema-registry:8081")

    schema_registry_client = SchemaRegistryClient({"url": schema_registry_url})
    json_serializer = register_schema(schema_registry_client)
    key_serializer = StringSerializer("utf_8")

    producer = Producer(
        {
            "bootstrap.servers": bootstrap_servers,
            "security.protocol": "SASL_PLAINTEXT",
            "sasl.mechanism": "PLAIN",
            "sasl.username": producer_user,
            "sasl.password": producer_password,
            "client.id": "kovalyx-kafka-producer",
            "linger.ms": 50,
            "acks": "all",
        }
    )

    Faker.seed(int(os.environ.get("FAKER_SEED", "42")))
    state = StoreState(faker=Faker())

    running = {"flag": True}

    def _shutdown(signum, frame):  # noqa: ANN001
        logger.info("Received signal %s, shutting down gracefully", signum)
        running["flag"] = False

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    interval = 1.0 / EVENTS_PER_SECOND if EVENTS_PER_SECOND > 0 else 1.0
    start_time = time.monotonic()
    produced = 0

    logger.info(
        "Kovalyx producer starting: topic=%s rate=%.2f events/sec duration=%s",
        TOPIC,
        EVENTS_PER_SECOND,
        args.duration_seconds or "unbounded",
    )

    while running["flag"]:
        if args.duration_seconds and (time.monotonic() - start_time) >= args.duration_seconds:
            logger.info("Duration limit reached (%ss) — stopping", args.duration_seconds)
            break

        event = generate_event(state)
        key = event["customer_id"] or event["event_id"]
        ctx = SerializationContext(TOPIC, MessageField.VALUE)
        try:
            producer.produce(
                topic=TOPIC,
                key=key_serializer(key, SerializationContext(TOPIC, MessageField.KEY)),
                value=json_serializer(event, ctx),
                headers={"event_type": event["event_type"]},
                on_delivery=delivery_report,
            )
        except BufferError:
            logger.warning("Local producer queue is full, flushing")
            producer.flush()
        producer.poll(0)
        produced += 1

        if produced % 100 == 0:
            logger.info("Produced %d events so far", produced)

        time.sleep(interval)

    logger.info("Flushing remaining messages...")
    producer.flush(timeout=30)
    logger.info("Kovalyx producer stopped. Total events produced: %d", produced)
    return 0


if __name__ == "__main__":
    sys.exit(main())
