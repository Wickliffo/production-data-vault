"""Set-based Raw Vault loading path for production-sized batches."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from .hash import hash_diff, hub_hash, link_hash
from .loader import RawVaultLoader
from .models import CustomerOrderRecord


class BulkRawVaultLoader(RawVaultLoader):
    """Load customer/order records with one COPY and set-based SQL statements."""

    def load(self, records: Iterable[CustomerOrderRecord], batch_id: UUID | None = None) -> UUID:
        return self.bulk_load(records, batch_id=batch_id)

    def bulk_load(
        self, records: Iterable[CustomerOrderRecord], batch_id: UUID | None = None
    ) -> UUID:
        batch_id = batch_id or uuid4()
        materialized = list(records)
        for record in materialized:
            record.validate()

        load_time = datetime.now(UTC)
        with self.connection.transaction():
            with self.connection.cursor() as cur:
                cur.execute(
                    "SELECT status, row_count FROM raw_vault.dv_load_batch WHERE batch_id = %s",
                    (batch_id,),
                )
                existing = cur.fetchone()
                if existing:
                    if existing[0] == "COMPLETED" and existing[1] == len(materialized):
                        return batch_id
                    raise ValueError(f"batch {batch_id} already exists with status {existing[0]}")

                cur.execute(
                    """
                    INSERT INTO raw_vault.dv_load_batch
                        (batch_id, record_source, started_at, status, row_count)
                    VALUES (%s, %s, %s, 'RUNNING', %s)
                    """,
                    (batch_id, self.record_source, load_time, len(materialized)),
                )
                cur.execute(
                    """
                    CREATE TEMP TABLE tmp_customer_order (
                        customer_id TEXT NOT NULL,
                        order_id TEXT NOT NULL,
                        first_name TEXT,
                        last_name TEXT,
                        email TEXT,
                        order_status TEXT,
                        order_total NUMERIC(19, 4),
                        source_updated_at TIMESTAMPTZ,
                        payload TEXT NOT NULL,
                        hk_customer_id CHAR(64) NOT NULL,
                        hk_order_id CHAR(64) NOT NULL,
                        hk_customer_order_id CHAR(64) NOT NULL,
                        customer_hash_diff CHAR(64) NOT NULL,
                        order_hash_diff CHAR(64) NOT NULL,
                        effective_from TIMESTAMPTZ NOT NULL
                    ) ON COMMIT DROP
                    """
                )
                with cur.copy(
                    """
                    COPY tmp_customer_order (
                        customer_id, order_id, first_name, last_name, email,
                        order_status, order_total, source_updated_at, payload,
                        hk_customer_id, hk_order_id, hk_customer_order_id,
                        customer_hash_diff, order_hash_diff, effective_from
                    ) FROM STDIN
                    """
                ) as copy:
                    for record in materialized:
                        customer_id = record.customer_id.strip()
                        order_id = record.order_id.strip()
                        hk_customer = hub_hash("CUSTOMER", customer_id, self.record_source)
                        hk_order = hub_hash("ORDER", order_id, self.record_source)
                        hk_link = link_hash("CUSTOMER_ORDER", hk_customer, hk_order)
                        effective_from = record.source_updated_at or load_time
                        copy.write_row(
                            (
                                customer_id,
                                order_id,
                                record.first_name,
                                record.last_name,
                                record.email,
                                record.order_status,
                                record.order_total,
                                record.source_updated_at,
                                json.dumps(record.payload or {}, separators=(",", ":")),
                                hk_customer,
                                hk_order,
                                hk_link,
                                hash_diff(
                                    (record.first_name, record.last_name, record.email,
                                     record.source_updated_at)
                                ),
                                hash_diff((record.order_status, record.order_total,
                                           record.source_updated_at)),
                                effective_from,
                            )
                        )

                cur.execute(
                    """
                    INSERT INTO staging.customer_order_batch
                      (batch_id, customer_id, order_id, first_name, last_name, email,
                       order_status, order_total, source_updated_at, payload)
                    SELECT %s, customer_id, order_id, first_name, last_name, email,
                           order_status, order_total, source_updated_at, payload::jsonb
                    FROM tmp_customer_order
                    """,
                    (batch_id,),
                )
                cur.execute(
                    """
                    INSERT INTO raw_vault.hub_customer
                      (hk_customer_id, customer_id, load_datetime, record_source, batch_id)
                    SELECT DISTINCT hk_customer_id, customer_id, %s, %s, %s
                    FROM tmp_customer_order
                    ON CONFLICT (hk_customer_id) DO NOTHING
                    """,
                    (load_time, self.record_source, batch_id),
                )
                cur.execute(
                    """
                    INSERT INTO raw_vault.hub_order
                      (hk_order_id, order_id, load_datetime, record_source, batch_id)
                    SELECT DISTINCT hk_order_id, order_id, %s, %s, %s
                    FROM tmp_customer_order
                    ON CONFLICT (hk_order_id) DO NOTHING
                    """,
                    (load_time, self.record_source, batch_id),
                )
                cur.execute(
                    """
                    INSERT INTO raw_vault.link_customer_order
                      (hk_customer_order_id, hk_customer_id, hk_order_id, load_datetime,
                       record_source, batch_id)
                    SELECT DISTINCT hk_customer_order_id, hk_customer_id, hk_order_id,
                                    %s, %s, %s
                    FROM tmp_customer_order
                    ON CONFLICT (hk_customer_order_id) DO NOTHING
                    """,
                    (load_time, self.record_source, batch_id),
                )
                cur.execute(
                    """
                    INSERT INTO raw_vault.sat_customer_details
                      (hk_customer_id, load_datetime, hash_diff, first_name, last_name, email,
                       source_updated_at, record_source, batch_id)
                    SELECT DISTINCT ON (hk_customer_id, customer_hash_diff)
                           hk_customer_id, %s, customer_hash_diff, first_name, last_name, email,
                           source_updated_at, %s, %s
                    FROM tmp_customer_order
                    ORDER BY hk_customer_id, customer_hash_diff
                    ON CONFLICT (hk_customer_id, hash_diff) DO NOTHING
                    """,
                    (load_time, self.record_source, batch_id),
                )
                cur.execute(
                    """
                    INSERT INTO raw_vault.sat_order_details
                      (hk_order_id, load_datetime, hash_diff, order_status, order_total,
                       source_updated_at, record_source, batch_id)
                    SELECT DISTINCT ON (hk_order_id, order_hash_diff)
                           hk_order_id, %s, order_hash_diff, order_status, order_total,
                           source_updated_at, %s, %s
                    FROM tmp_customer_order
                    ORDER BY hk_order_id, order_hash_diff
                    ON CONFLICT (hk_order_id, hash_diff) DO NOTHING
                    """,
                    (load_time, self.record_source, batch_id),
                )
                cur.execute(
                    """
                    UPDATE raw_vault.eff_sat_customer_order e
                    SET effective_to = t.effective_from, is_current = FALSE
                    FROM (
                        SELECT DISTINCT hk_customer_order_id, effective_from
                        FROM tmp_customer_order
                    ) t
                    WHERE e.hk_customer_order_id = t.hk_customer_order_id
                      AND e.is_current
                      AND NOT EXISTS (
                          SELECT 1 FROM raw_vault.eff_sat_customer_order prior
                          WHERE prior.hk_customer_order_id = t.hk_customer_order_id
                            AND prior.effective_from = t.effective_from
                      )
                    """
                )
                cur.execute(
                    """
                    INSERT INTO raw_vault.eff_sat_customer_order
                      (hk_customer_order_id, load_datetime, effective_from, effective_to,
                       is_current, record_source, batch_id)
                    SELECT DISTINCT hk_customer_order_id, %s, effective_from, NULL,
                                    TRUE, %s, %s
                    FROM tmp_customer_order t
                    WHERE NOT EXISTS (
                        SELECT 1 FROM raw_vault.eff_sat_customer_order e
                        WHERE e.hk_customer_order_id = t.hk_customer_order_id
                          AND e.effective_from = t.effective_from
                    )
                    """,
                    (load_time, self.record_source, batch_id),
                )
                cur.execute(
                    """
                    UPDATE raw_vault.dv_load_batch
                    SET completed_at = clock_timestamp(), status = 'COMPLETED'
                    WHERE batch_id = %s
                    """,
                    (batch_id,),
                )
        return batch_id
