from datetime import UTC, datetime
from decimal import Decimal

import pytest

from dv_ingest.loader import RawVaultLoader
from dv_ingest.models import CustomerOrderRecord

pytestmark = pytest.mark.integration


def test_replay_is_idempotent_and_changes_create_history(connection):
    loader = RawVaultLoader(connection, "TEST_SOURCE")
    original = CustomerOrderRecord(
        "C-1", "O-1", "Ada", "Lovelace", "ada@example.com", "PAID",
        Decimal("10.00"), datetime(2026, 1, 1, tzinfo=UTC),
    )
    loader.load([original])
    loader.load([original])
    changed = CustomerOrderRecord(
        "C-1", "O-1", "Augusta", "Lovelace", "ada@example.com", "PAID",
        Decimal("10.00"), datetime(2026, 1, 2, tzinfo=UTC),
    )
    loader.load([changed])

    with connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw_vault.hub_customer WHERE customer_id = 'C-1'")
        assert cur.fetchone()[0] == 1
        cur.execute(
            """
            SELECT count(*)
            FROM raw_vault.sat_customer_details
            WHERE hk_customer_id = (
                SELECT hk_customer_id
                FROM raw_vault.hub_customer
                WHERE customer_id = 'C-1'
            )
            """
        )
        assert cur.fetchone()[0] == 2
        cur.execute(
            """
            SELECT count(*)
            FROM raw_vault.eff_sat_customer_order
            WHERE is_current
            """
        )
        assert cur.fetchone()[0] == 1
