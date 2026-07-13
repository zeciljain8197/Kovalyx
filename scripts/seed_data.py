"""
Kovalyx — historical batch data seeder.

Generates 90 days of realistic, internally-consistent synthetic history for
a Shopify-like store (customers, products, orders, daily inventory
snapshots) and lands it as CSV in the MinIO Bronze zone under
`bronze/batch/<entity>/...`, mirroring the real-time Kafka event stream so
the Silver/Gold layers have enough volume to produce meaningful KPIs,
cohorts, and inventory alerts from day one.

Column shapes match the bronze CSV contract exactly: orders are modeled as
one row per order (single product per order — the contract has no
order_line_id/sku), customers.total_orders/total_spent are computed from
the generated orders (never randomized independently), and
products.current_stock is backfilled from the last day of the generated
inventory walk so the two tables never disagree.

Run automatically on first `docker compose up` (see the seed marker check
below), or manually:

    python scripts/seed_data.py --days 90 --num-customers 2000 --num-products 200

Requires: faker, pandas, boto3, hvac, python-dotenv
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import random
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import boto3
import hvac
import pandas as pd
from botocore.client import Config as BotoConfig
from dotenv import load_dotenv
from faker import Faker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kovalyx.seed_data")

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_MARKER_KEY = "batch/_SEED_COMPLETE"

CATEGORIES = ["Apparel", "Home Goods", "Electronics", "Beauty", "Outdoor", "Toys", "Pantry"]
SUBCATEGORIES_BY_CATEGORY = {
    "Apparel": ["Men's", "Women's", "Kids", "Accessories"],
    "Home Goods": ["Kitchen", "Bedding", "Decor", "Storage"],
    "Electronics": ["Audio", "Wearables", "Accessories", "Smart Home"],
    "Beauty": ["Skincare", "Makeup", "Haircare", "Fragrance"],
    "Outdoor": ["Camping", "Cycling", "Fitness", "Garden"],
    "Toys": ["Educational", "Action Figures", "Games", "Outdoor Play"],
    "Pantry": ["Snacks", "Beverages", "Baking", "Condiments"],
}
CUSTOMER_TIERS = ["bronze", "silver", "gold"]
CUSTOMER_TIER_WEIGHTS = [55, 30, 15]
CARD_TYPES = ["Visa", "Mastercard", "Amex", "Discover"]
ORDER_STATUSES = ["placed", "paid", "shipped", "delivered", "returned"]
ORDER_STATUS_WEIGHTS = [10, 15, 15, 50, 10]
SUPPLIER_IDS = [f"SUPP-{uuid.uuid4().hex[:8]}" for _ in range(15)]


def get_secret(vault_client: hvac.Client | None, path: str, field_name: str, env_fallback: str) -> str | None:
    """Pulls a credential from Vault; falls back to a plain env var for
    local dev when Vault isn't reachable."""
    if vault_client is not None:
        try:
            resp = vault_client.secrets.kv.v2.read_secret_version(mount_point="kovalyx", path=path, raise_on_deleted_version=True)
            value = resp["data"]["data"].get(field_name)
            if value:
                return value
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read kovalyx/%s from Vault (%s); falling back to env var %s", path, exc, env_fallback)
    return os.environ.get(env_fallback)


def build_vault_client() -> hvac.Client | None:
    """Builds an authenticated Vault client from VAULT_ADDR/VAULT_TOKEN, or
    None if Vault isn't configured (local dev without Vault running)."""
    vault_addr = os.environ.get("VAULT_ADDR")
    vault_token = os.environ.get("VAULT_TOKEN")
    if not vault_addr or not vault_token:
        return None
    client = hvac.Client(url=vault_addr, token=vault_token)
    return client if client.is_authenticated() else None


def build_minio_client(vault_client: hvac.Client | None):
    """Builds a boto3 S3 client pointed at MinIO using the bronze-writer
    credential, or None if no credentials are available (local-only run)."""
    access_key = get_secret(vault_client, "minio/bronze-writer", "access_key", "MINIO_BRONZE_WRITER_ACCESS_KEY")
    secret_key = get_secret(vault_client, "minio/bronze-writer", "secret_key", "MINIO_BRONZE_WRITER_SECRET_KEY")
    endpoint = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
    if not access_key or not secret_key:
        logger.warning("No MinIO credentials available — skipping upload, CSVs will only be written locally")
        return None
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )


def generate_e164_phone() -> str:
    """Generates a syntactically valid US E.164 number, matching the same
    convention used by ingestion/kafka_producer.py."""
    area_code = random.randint(200, 999)
    exchange = random.randint(200, 999)
    subscriber = random.randint(1000, 9999)
    return f"+1{area_code}{exchange}{subscriber}"


def format_shipping_address(faker: Faker) -> str:
    return f"{faker.street_address()}, {faker.city()}, {faker.state_abbr()} {faker.postcode()}"


def generate_products(faker: Faker, num_products: int) -> pd.DataFrame:
    """current_stock here is a *starting* seed for the 90-day inventory
    walk, not the final value — backfill_product_current_stock() overwrites
    it with the last day's stock_level once inventory.csv is generated, so
    products.csv and inventory.csv always agree on "today's" stock."""
    rows = []
    for i in range(num_products):
        category = random.choice(CATEGORIES)
        unit_price = round(random.uniform(8, 250), 2)
        rows.append(
            {
                "product_id": f"PROD-{i:04d}",
                "product_name": faker.catch_phrase(),
                "category": category,
                "subcategory": random.choice(SUBCATEGORIES_BY_CATEGORY[category]),
                "unit_price": unit_price,
                "cost_price": round(unit_price * random.uniform(0.35, 0.65), 2),
                "supplier_id": random.choice(SUPPLIER_IDS),
                "reorder_threshold": random.randint(15, 60),
                "current_stock": random.randint(80, 500),
            }
        )
    return pd.DataFrame(rows)


def generate_customers(faker: Faker, num_customers: int, days: int) -> pd.DataFrame:
    """total_orders/total_spent start at 0 here and are filled in by
    backfill_customer_order_stats() once orders.csv exists — never
    randomized independently, so the two tables can't disagree."""
    rows = []
    for _ in range(num_customers):
        registered_at = faker.date_time_between(start_date=f"-{days}d", end_date="now", tzinfo=timezone.utc)
        rows.append(
            {
                "customer_id": f"CUST-{uuid.uuid4().hex[:10]}",
                "customer_name": faker.name(),
                "customer_email": faker.unique.email(),
                "customer_phone": generate_e164_phone(),
                "shipping_address": format_shipping_address(faker),
                "registration_date": registered_at.strftime("%Y-%m-%d"),
                "tier": random.choices(CUSTOMER_TIERS, weights=CUSTOMER_TIER_WEIGHTS)[0],
                "total_orders": 0,
                "total_spent": 0.0,
            }
        )
    return pd.DataFrame(rows)


def generate_orders(customers: pd.DataFrame, products: pd.DataFrame, days: int) -> pd.DataFrame:
    """One row per order — the contract has no order_line_id/sku, so each
    order is modeled as a single-product-line transaction. A customer can
    place multiple distinct orders on the same or different days."""
    rows = []
    customer_records = customers.to_dict("records")
    today = date.today()

    for day_offset in range(days, 0, -1):
        order_date = today - timedelta(days=day_offset)
        # Weekend bump, slow ramp — gives the GMV trend chart real shape.
        base_orders = 40 if order_date.weekday() < 5 else 65
        num_orders_today = max(5, int(random.gauss(base_orders, base_orders * 0.2)))

        for _ in range(num_orders_today):
            customer = random.choice(customer_records)
            product = products.sample(n=1).iloc[0]
            quantity = random.randint(1, 4)
            unit_price = float(product["unit_price"])
            order_amount = round(quantity * unit_price, 2)
            rows.append(
                {
                    "order_id": f"ORD-{uuid.uuid4().hex[:12]}",
                    "customer_id": customer["customer_id"],
                    "product_id": product["product_id"],
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "order_amount": order_amount,
                    "order_date": order_date.strftime("%Y-%m-%d"),
                    "status": random.choices(ORDER_STATUSES, weights=ORDER_STATUS_WEIGHTS)[0],
                    "shipping_address": customer["shipping_address"],
                    "card_last4": f"{random.randint(0, 9999):04d}",
                    "card_type": random.choice(CARD_TYPES),
                }
            )
    return pd.DataFrame(rows)


def generate_inventory_snapshots(products: pd.DataFrame, days: int) -> pd.DataFrame:
    """Walks each product's stock forward from its products.csv seed value
    for `days` days. reorder_threshold is joined from products, never
    re-randomized, so inventory.csv and products.csv always match."""
    rows = []
    today = date.today()
    stock_levels = dict(zip(products["product_id"], products["current_stock"]))
    reorder_by_product = dict(zip(products["product_id"], products["reorder_threshold"]))

    for day_offset in range(days, -1, -1):
        snapshot_date = today - timedelta(days=day_offset)
        for product_id in products["product_id"]:
            units_sold = random.randint(0, 25)
            units_received = random.randint(0, 150) if random.random() < 0.1 else 0
            stock_levels[product_id] = max(0, stock_levels[product_id] - units_sold + units_received)
            rows.append(
                {
                    "inventory_id": f"INV-{uuid.uuid4().hex[:10]}",
                    "product_id": product_id,
                    "date": snapshot_date.strftime("%Y-%m-%d"),
                    "stock_level": stock_levels[product_id],
                    "reorder_threshold": reorder_by_product[product_id],
                    "units_sold": units_sold,
                    "units_received": units_received,
                }
            )
    return pd.DataFrame(rows)


def backfill_customer_order_stats(customers: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    """Derives total_orders/total_spent from the actual generated orders."""
    agg = orders.groupby("customer_id").agg(total_orders=("order_id", "count"), total_spent=("order_amount", "sum")).reset_index()
    customers = customers.drop(columns=["total_orders", "total_spent"]).merge(agg, on="customer_id", how="left")
    customers["total_orders"] = customers["total_orders"].fillna(0).astype(int)
    customers["total_spent"] = customers["total_spent"].fillna(0.0).round(2)
    return customers


def backfill_product_current_stock(products: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    """Overwrites each product's current_stock with its last inventory
    snapshot's stock_level, so "today's" stock agrees across both tables."""
    latest = inventory.sort_values("date").groupby("product_id").tail(1).set_index("product_id")["stock_level"]
    products = products.copy()
    products["current_stock"] = products["product_id"].map(latest).fillna(products["current_stock"]).astype(int)
    return products


def write_local_and_upload(df: pd.DataFrame, entity: str, output_dir: Path, s3_client, bucket: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    local_path = output_dir / f"{entity}.csv"
    df.to_csv(local_path, index=False)
    logger.info("Wrote %d rows to %s", len(df), local_path)

    if s3_client is not None:
        buffer = io.StringIO()
        df.to_csv(buffer, index=False)
        key = f"batch/{entity}/{entity}.csv"
        s3_client.put_object(Bucket=bucket, Key=key, Body=buffer.getvalue().encode("utf-8"), ContentType="text/csv")
        logger.info("Uploaded s3://%s/%s (%d rows)", bucket, key, len(df))

    return local_path


def already_seeded(s3_client, bucket: str) -> bool:
    if s3_client is None:
        return False
    try:
        s3_client.head_object(Bucket=bucket, Key=SEED_MARKER_KEY)
        return True
    except Exception:  # noqa: BLE001
        return False


def mark_seeded(s3_client, bucket: str) -> None:
    if s3_client is None:
        return
    s3_client.put_object(Bucket=bucket, Key=SEED_MARKER_KEY, Body=datetime.now(timezone.utc).isoformat().encode())


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed 90 days of synthetic Kovalyx history")
    parser.add_argument("--days", type=int, default=int(os.environ.get("SEED_DATA_DAYS", "90")))
    parser.add_argument("--num-customers", type=int, default=2000)
    parser.add_argument("--num-products", type=int, default=200)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "data" / "seed")
    parser.add_argument("--bucket", default=os.environ.get("MINIO_BRONZE_BUCKET", "bronze"))
    parser.add_argument("--seed", type=int, default=int(os.environ.get("FAKER_SEED", "42")))
    parser.add_argument("--force", action="store_true", help="Reseed even if a completion marker already exists in MinIO")
    parser.add_argument("--no-upload", action="store_true", help="Only write local CSVs, skip MinIO upload")
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    random.seed(args.seed)
    Faker.seed(args.seed)
    faker = Faker()

    vault_client = None if args.no_upload else build_vault_client()
    s3_client = None if args.no_upload else build_minio_client(vault_client)

    if not args.force and already_seeded(s3_client, args.bucket):
        logger.info("Seed marker already present at s3://%s/%s — skipping (use --force to reseed)", args.bucket, SEED_MARKER_KEY)
        return 0

    logger.info("Generating %d days of history: %d customers, %d products", args.days, args.num_customers, args.num_products)

    products = generate_products(faker, args.num_products)
    customers = generate_customers(faker, args.num_customers, args.days)
    orders = generate_orders(customers, products, args.days)
    inventory = generate_inventory_snapshots(products, args.days)

    customers = backfill_customer_order_stats(customers, orders)
    products = backfill_product_current_stock(products, inventory)

    write_local_and_upload(products, "products", args.output_dir, s3_client, args.bucket)
    write_local_and_upload(customers, "customers", args.output_dir, s3_client, args.bucket)
    write_local_and_upload(orders, "orders", args.output_dir, s3_client, args.bucket)
    write_local_and_upload(inventory, "inventory", args.output_dir, s3_client, args.bucket)

    mark_seeded(s3_client, args.bucket)
    logger.info(
        "Seed complete: %d products, %d customers, %d orders, %d inventory snapshots",
        len(products),
        len(customers),
        len(orders),
        len(inventory),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
