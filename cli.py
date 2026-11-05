from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import psycopg

from .bulk_loader import BulkRawVaultLoader
from .models import CustomerOrderRecord


def main() -> None:
    parser = argparse.ArgumentParser(description="Load records into the Data Vault Raw Vault")
    subparsers = parser.add_subparsers(dest="command", required=True)
    demo = subparsers.add_parser("demo-load", help="load a small deterministic demo batch")
    demo.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    demo.add_argument("--record-source", default=os.getenv("DV_RECORD_SOURCE", "CRM_POSTGRES"))
    fixture = subparsers.add_parser("load-fixture", help="load a JSON fixture grouped by source")
    fixture.add_argument("fixture_path", type=Path)
    fixture.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    args = parser.parse_args()

    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")

    if args.command == "load-fixture":
        rows = json.loads(args.fixture_path.read_text())
        grouped: dict[str, list[CustomerOrderRecord]] = {}
        for row in rows:
            grouped.setdefault(row["record_source"], []).append(
                CustomerOrderRecord(
                    customer_id=row["customer_id"],
                    order_id=row["order_id"],
                    first_name=row.get("first_name"),
                    last_name=row.get("last_name"),
                    email=row.get("email"),
                    order_status=row.get("order_status"),
                    order_total=Decimal(row["order_total"]) if row.get("order_total") else None,
                    source_updated_at=(
                        datetime.fromisoformat(row["source_updated_at"])
                        if row.get("source_updated_at")
                        else None
                    ),
                    payload=row.get("payload", {}),
                )
            )
        with psycopg.connect(args.database_url, application_name="dv-ingest-fixture") as conn:
            for source, source_records in grouped.items():
                batch_id = BulkRawVaultLoader(conn, source).load(source_records)
                print(f"loaded {source} batch {batch_id} ({len(source_records)} records)")
        return

    records = [
        CustomerOrderRecord(
            customer_id="CUST-1001", order_id="ORD-5001", first_name="Ada",
            last_name="Lovelace", email="ada@example.com", order_status="PAID",
            order_total=Decimal("125.50"), source_updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            payload={"source_table": "crm.orders"},
        ),
        CustomerOrderRecord(
            customer_id="CUST-1002", order_id="ORD-5002", first_name="Grace",
            last_name="Hopper", email="grace@example.com", order_status="PENDING",
            order_total=Decimal("80.00"), source_updated_at=datetime(2026, 1, 2, tzinfo=UTC),
            payload={"source_table": "crm.orders"},
        ),
    ]
    with psycopg.connect(args.database_url, application_name="dv-ingest") as conn:
        batch_id = BulkRawVaultLoader(conn, args.record_source).load(records)
    print(f"loaded batch {batch_id} ({len(records)} records)")


if __name__ == "__main__":
    main()
