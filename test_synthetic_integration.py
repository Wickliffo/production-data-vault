from datetime import UTC, datetime
from decimal import Decimal

import pytest

from dv_ingest.bulk_loader import BulkRawVaultLoader
from dv_ingest.loader import RawVaultLoader
from dv_ingest.models import CustomerOrderRecord, OrderItemRecord

pytestmark = pytest.mark.integration


def test_same_business_key_in_two_sources_is_not_merged(connection):
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    record = CustomerOrderRecord(
        "C-100", "O-900", "Ada", "Lovelace", order_status="PAID", source_updated_at=timestamp
    )
    RawVaultLoader(connection, "CRM_A").load([record])
    RawVaultLoader(connection, "ERP_B").load([record])

    with connection.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM raw_vault.hub_customer WHERE customer_id = 'C-100'"
        )
        assert cur.fetchone()[0] == 2
        cur.execute(
            """
            SELECT count(DISTINCT hk_customer_id)
            FROM raw_vault.hub_customer
            WHERE customer_id = 'C-100'
            """
        )
        assert cur.fetchone()[0] == 2


def test_small_volume_batch_loads_all_records(connection):
    records = [
        CustomerOrderRecord(
            customer_id=f"V-{index:04d}",
            order_id=f"VO-{index:04d}",
            first_name="Synthetic",
            last_name=str(index),
            order_status="PAID",
            order_total=Decimal("1.00"),
            source_updated_at=datetime(2026, 2, 1, tzinfo=UTC),
        )
        for index in range(250)
    ]
    BulkRawVaultLoader(connection, "VOLUME_TEST").load(records)

    with connection.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM raw_vault.hub_customer WHERE record_source = 'VOLUME_TEST'"
        )
        assert cur.fetchone()[0] == 250
        cur.execute(
            "SELECT count(*) FROM raw_vault.link_customer_order WHERE record_source = 'VOLUME_TEST'"
        )
        assert cur.fetchone()[0] == 250


def test_bulk_batch_replay_is_idempotent(connection):
    record = CustomerOrderRecord("C-BULK", "O-BULK", first_name="Replay")
    loader = BulkRawVaultLoader(connection, "BULK_REPLAY")
    batch_id = loader.load([record])
    loader.load([record], batch_id=batch_id)

    with connection.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM staging.customer_order_batch WHERE batch_id = %s",
            (batch_id,),
        )
        assert cur.fetchone()[0] == 1


def test_order_item_vertical_slice_loads_product_link_and_satellites(connection):
    record = OrderItemRecord(
        customer_id="C-ITEM",
        order_id="O-ITEM",
        order_item_id="OI-1",
        product_code="PROD-X",
        product_name="Cloud Server Node",
        category="Infrastructure",
        quantity=2,
        unit_price=Decimal("120.00"),
        source_updated_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    RawVaultLoader(connection, "ECOMMERCE_TEST").load_order_items([record])

    with connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw_vault.hub_product WHERE product_code = 'PROD-X'")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM raw_vault.link_order_item WHERE order_item_id = 'OI-1'")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM raw_vault.sat_order_item_details")
        assert cur.fetchone()[0] == 1
