"""Transactional loader from typed records into the PostgreSQL Raw Vault."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from .hash import hash_diff, hub_hash, link_hash
from .models import CustomerOrderRecord, OrderItemRecord


class RawVaultLoader:
    def __init__(self, connection: psycopg.Connection, record_source: str) -> None:
        self.connection = connection
        self.record_source = record_source

    def load(self, records: Iterable[CustomerOrderRecord], batch_id: UUID | None = None) -> UUID:
        """Load a batch atomically and return its batch id.

        Hubs and links are protected by unique constraints. Satellite rows use a
        unique (hub key, hash diff) constraint, making retries safe even when a
        source replays an unchanged record.
        """
        batch_id = batch_id or uuid4()
        materialized = list(records)
        for record in materialized:
            record.validate()

        now = datetime.now(UTC)
        with self.connection.transaction():
            with self.connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO raw_vault.dv_load_batch
                        (batch_id, record_source, started_at, status, row_count)
                    VALUES (%s, %s, %s, 'RUNNING', %s)
                    ON CONFLICT (batch_id) DO NOTHING
                    """,
                    (batch_id, self.record_source, now, len(materialized)),
                )

                for record in materialized:
                    self._load_record(cur, batch_id, now, record)

                cur.execute(
                    """
                    UPDATE raw_vault.dv_load_batch
                    SET completed_at = clock_timestamp(), status = 'COMPLETED'
                    WHERE batch_id = %s
                    """,
                    (batch_id,),
                )
        return batch_id

    def load_order_items(
        self, records: Iterable[OrderItemRecord], batch_id: UUID | None = None
    ) -> UUID:
        """Load the e-commerce order-item grain into migration 002 objects."""
        batch_id = batch_id or uuid4()
        materialized = list(records)
        for record in materialized:
            record.validate()

        load_time = datetime.now(UTC)
        with self.connection.transaction():
            with self.connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO raw_vault.dv_load_batch
                        (batch_id, record_source, started_at, status, row_count)
                    VALUES (%s, %s, %s, 'RUNNING', %s)
                    ON CONFLICT (batch_id) DO NOTHING
                    """,
                    (batch_id, self.record_source, load_time, len(materialized)),
                )
                for record in materialized:
                    self._load_order_item(cur, batch_id, load_time, record)
                cur.execute(
                    """
                    UPDATE raw_vault.dv_load_batch
                    SET completed_at = clock_timestamp(), status = 'COMPLETED'
                    WHERE batch_id = %s
                    """,
                    (batch_id,),
                )
        return batch_id

    def _load_order_item(
        self,
        cur: psycopg.Cursor,
        batch_id: UUID,
        load_time: datetime,
        record: OrderItemRecord,
    ) -> None:
        customer_id = record.customer_id.strip()
        order_id = record.order_id.strip()
        order_item_id = record.order_item_id.strip()
        product_code = record.product_code.strip()
        hk_customer = hub_hash("CUSTOMER", customer_id, self.record_source)
        hk_order = hub_hash("ORDER", order_id, self.record_source)
        hk_product = hub_hash("PRODUCT", product_code, self.record_source)
        hk_item = link_hash(
            "ORDER_ITEM", hk_order, hk_product, hk_customer, order_item_id, self.record_source
        )
        product_diff = hash_diff((record.product_name, record.category, record.source_updated_at))
        item_diff = hash_diff((record.quantity, record.unit_price, record.source_updated_at))

        cur.execute(
            """
            INSERT INTO staging.order_item_batch
              (batch_id, customer_id, order_id, order_item_id, product_code,
               product_name, category, quantity, unit_price, source_updated_at, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                batch_id,
                customer_id,
                order_id,
                order_item_id,
                product_code,
                record.product_name,
                record.category,
                record.quantity,
                record.unit_price,
                record.source_updated_at,
                Jsonb(record.payload or {}),
            ),
        )
        cur.execute(
            """
            INSERT INTO raw_vault.hub_customer
              (hk_customer_id, customer_id, load_datetime, record_source, batch_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (hk_customer_id) DO NOTHING
            """,
            (hk_customer, customer_id, load_time, self.record_source, batch_id),
        )
        cur.execute(
            """
            INSERT INTO raw_vault.hub_order
              (hk_order_id, order_id, load_datetime, record_source, batch_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (hk_order_id) DO NOTHING
            """,
            (hk_order, order_id, load_time, self.record_source, batch_id),
        )
        cur.execute(
            """
            INSERT INTO raw_vault.hub_product
              (hk_product_id, product_code, load_datetime, record_source, batch_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (hk_product_id) DO NOTHING
            """,
            (hk_product, product_code, load_time, self.record_source, batch_id),
        )
        cur.execute(
            """
            INSERT INTO raw_vault.link_order_item
              (hk_order_item_id, hk_order_id, hk_product_id, hk_customer_id,
               order_item_id, load_datetime, record_source, batch_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (hk_order_item_id) DO NOTHING
            """,
            (
                hk_item,
                hk_order,
                hk_product,
                hk_customer,
                order_item_id,
                load_time,
                self.record_source,
                batch_id,
            ),
        )
        cur.execute(
            """
            INSERT INTO raw_vault.sat_product_details
              (hk_product_id, load_datetime, hash_diff, product_name, category,
               source_updated_at, record_source, batch_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (hk_product_id, hash_diff) DO NOTHING
            """,
            (
                hk_product,
                load_time,
                product_diff,
                record.product_name,
                record.category,
                record.source_updated_at,
                self.record_source,
                batch_id,
            ),
        )
        cur.execute(
            """
            INSERT INTO raw_vault.sat_order_item_details
              (hk_order_item_id, load_datetime, hash_diff, quantity, unit_price,
               source_updated_at, record_source, batch_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (hk_order_item_id, hash_diff) DO NOTHING
            """,
            (
                hk_item,
                load_time,
                item_diff,
                record.quantity,
                record.unit_price,
                record.source_updated_at,
                self.record_source,
                batch_id,
            ),
        )

    def _load_record(
        self,
        cur: psycopg.Cursor,
        batch_id: UUID,
        load_time: datetime,
        record: CustomerOrderRecord,
    ) -> None:
        customer_id = record.customer_id.strip()
        order_id = record.order_id.strip()
        hk_customer = hub_hash("CUSTOMER", customer_id, self.record_source)
        hk_order = hub_hash("ORDER", order_id, self.record_source)
        hk_link = link_hash("CUSTOMER_ORDER", hk_customer, hk_order)
        customer_diff = hash_diff(
            (record.first_name, record.last_name, record.email, record.source_updated_at)
        )
        order_diff = hash_diff((record.order_status, record.order_total, record.source_updated_at))
        effective_from = record.source_updated_at or load_time

        cur.execute(
            """
            INSERT INTO staging.customer_order_batch
              (batch_id, customer_id, order_id, first_name, last_name, email,
               order_status, order_total, source_updated_at, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (batch_id, customer_id, order_id, record.first_name, record.last_name,
             record.email, record.order_status, record.order_total,
             record.source_updated_at, Jsonb(record.payload or {})),
        )
        cur.execute(
            """
            INSERT INTO raw_vault.hub_customer
              (hk_customer_id, customer_id, load_datetime, record_source, batch_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (hk_customer_id) DO NOTHING
            """,
            (hk_customer, customer_id, load_time, self.record_source, batch_id),
        )
        cur.execute(
            """
            INSERT INTO raw_vault.hub_order
              (hk_order_id, order_id, load_datetime, record_source, batch_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (hk_order_id) DO NOTHING
            """,
            (hk_order, order_id, load_time, self.record_source, batch_id),
        )
        cur.execute(
            """
            INSERT INTO raw_vault.link_customer_order
              (hk_customer_order_id, hk_customer_id, hk_order_id, load_datetime,
               record_source, batch_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (hk_customer_order_id) DO NOTHING
            """,
            (hk_link, hk_customer, hk_order, load_time, self.record_source, batch_id),
        )
        cur.execute(
            """
            INSERT INTO raw_vault.sat_customer_details
              (hk_customer_id, load_datetime, hash_diff, first_name, last_name, email,
               source_updated_at, record_source, batch_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (hk_customer_id, hash_diff) DO NOTHING
            """,
            (hk_customer, load_time, customer_diff, record.first_name, record.last_name,
             record.email, record.source_updated_at, self.record_source, batch_id),
        )
        cur.execute(
            """
            INSERT INTO raw_vault.sat_order_details
              (hk_order_id, load_datetime, hash_diff, order_status, order_total,
               source_updated_at, record_source, batch_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (hk_order_id, hash_diff) DO NOTHING
            """,
            (hk_order, load_time, order_diff, record.order_status, record.order_total,
             record.source_updated_at, self.record_source, batch_id),
        )
        cur.execute(
            """
            UPDATE raw_vault.eff_sat_customer_order
            SET effective_to = %s, is_current = FALSE
            WHERE hk_customer_order_id = %s
              AND is_current = TRUE
              AND NOT EXISTS (
                  SELECT 1
                  FROM raw_vault.eff_sat_customer_order
                  WHERE hk_customer_order_id = %s
                    AND effective_from = %s
              )
            """,
            (effective_from, hk_link, hk_link, effective_from),
        )
        cur.execute(
            """
            INSERT INTO raw_vault.eff_sat_customer_order
              (hk_customer_order_id, load_datetime, effective_from, effective_to,
               is_current, record_source, batch_id)
            SELECT %s, %s, %s, NULL, TRUE, %s, %s
            WHERE NOT EXISTS (
                SELECT 1
                FROM raw_vault.eff_sat_customer_order
                WHERE hk_customer_order_id = %s
                  AND effective_from = %s
            )
            """,
            (
                hk_link,
                load_time,
                effective_from,
                self.record_source,
                batch_id,
                hk_link,
                effective_from,
            ),
        )
