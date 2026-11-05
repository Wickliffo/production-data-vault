\set ON_ERROR_STOP on

-- This script is intentionally executable by psql in CI and production jobs.
-- Every failed assertion raises a non-zero exit status.

DO $$
DECLARE
    violations BIGINT;
BEGIN
    SELECT count(*) INTO violations
    FROM raw_vault.dv_hash_contract
    WHERE is_active;
    IF violations <> 1 THEN
        RAISE EXCEPTION 'DQ000: exactly one active hash contract is required';
    END IF;

    SELECT count(*) INTO violations
    FROM raw_vault.dv_hash_contract
    WHERE hash_contract_version = 'sha256-length-prefixed-v1'
      AND algorithm = 'SHA-256'
      AND is_active;
    IF violations <> 1 THEN
        RAISE EXCEPTION 'DQ000: expected active SHA-256 hash contract is missing';
    END IF;

    SELECT count(*) INTO violations
    FROM staging.customer_order_batch
    WHERE btrim(customer_id) = '' OR btrim(order_id) = '';
    IF violations > 0 THEN
        RAISE EXCEPTION 'DQ001: % staging rows have blank customer_id/order_id', violations;
    END IF;

    SELECT count(*) INTO violations
    FROM (
        SELECT b.batch_id
        FROM raw_vault.dv_load_batch b
        LEFT JOIN (
            SELECT batch_id, count(*) AS staged_count
            FROM (
                SELECT batch_id FROM staging.customer_order_batch
                UNION ALL
                SELECT batch_id FROM staging.order_item_batch
            ) staged_rows
            GROUP BY batch_id
        ) s USING (batch_id)
        WHERE b.status = 'COMPLETED'
          AND b.row_count <> coalesce(s.staged_count, 0)
    ) mismatched_batches;
    IF violations > 0 THEN
        RAISE EXCEPTION 'DQ002: completed batch row_count does not reconcile with staging';
    END IF;

    SELECT count(*) INTO violations
    FROM staging.customer_order_batch s
    JOIN raw_vault.dv_load_batch b USING (batch_id)
    LEFT JOIN raw_vault.hub_customer h
        ON h.customer_id = btrim(s.customer_id)
       AND h.record_source = b.record_source
    WHERE h.hk_customer_id IS NULL;
    IF violations > 0 THEN
        RAISE EXCEPTION 'RI001: % staging rows have no customer hub', violations;
    END IF;

    SELECT count(*) INTO violations
    FROM staging.customer_order_batch s
    JOIN raw_vault.dv_load_batch b USING (batch_id)
    LEFT JOIN raw_vault.hub_order h
        ON h.order_id = btrim(s.order_id)
       AND h.record_source = b.record_source
    WHERE h.hk_order_id IS NULL;
    IF violations > 0 THEN
        RAISE EXCEPTION 'RI002: % staging rows have no order hub', violations;
    END IF;

    SELECT count(*) INTO violations
    FROM raw_vault.link_customer_order l
    LEFT JOIN raw_vault.hub_customer c USING (hk_customer_id)
    LEFT JOIN raw_vault.hub_order o USING (hk_order_id)
    WHERE c.hk_customer_id IS NULL OR o.hk_order_id IS NULL;
    IF violations > 0 THEN
        RAISE EXCEPTION 'RI003: % orphaned customer-order links', violations;
    END IF;

    SELECT count(*) INTO violations
    FROM raw_vault.sat_customer_details s
    LEFT JOIN raw_vault.hub_customer h USING (hk_customer_id)
    WHERE h.hk_customer_id IS NULL;
    IF violations > 0 THEN
        RAISE EXCEPTION 'RI004: % customer satellite rows have no hub', violations;
    END IF;

    SELECT count(*) INTO violations
    FROM raw_vault.sat_order_details s
    LEFT JOIN raw_vault.hub_order h USING (hk_order_id)
    WHERE h.hk_order_id IS NULL;
    IF violations > 0 THEN
        RAISE EXCEPTION 'RI005: % order satellite rows have no hub', violations;
    END IF;

    SELECT count(*) INTO violations
    FROM raw_vault.eff_sat_customer_order e
    LEFT JOIN raw_vault.link_customer_order l USING (hk_customer_order_id)
    WHERE l.hk_customer_order_id IS NULL;
    IF violations > 0 THEN
        RAISE EXCEPTION 'RI006: % effectivity rows have no link', violations;
    END IF;

    SELECT count(*) INTO violations
    FROM (
        SELECT hk_customer_order_id
        FROM raw_vault.eff_sat_customer_order
        WHERE is_current
        GROUP BY hk_customer_order_id
        HAVING count(*) > 1
    ) current_rows;
    IF violations > 0 THEN
        RAISE EXCEPTION 'DQ003: % relationships have more than one current effectivity row', violations;
    END IF;

    SELECT count(*) INTO violations
    FROM (
        SELECT hk_customer_id AS hash_key FROM raw_vault.hub_customer
        UNION ALL SELECT hk_order_id FROM raw_vault.hub_order
        UNION ALL SELECT hk_customer_order_id FROM raw_vault.link_customer_order
        UNION ALL SELECT hk_customer_id FROM raw_vault.sat_customer_details
        UNION ALL SELECT hk_order_id FROM raw_vault.sat_order_details
        UNION ALL SELECT hk_customer_order_id FROM raw_vault.eff_sat_customer_order
    ) hashes
    WHERE length(btrim(hash_key)) <> 64 OR btrim(hash_key) !~ '^[0-9a-f]{64}$';
    IF violations > 0 THEN
        RAISE EXCEPTION 'DQ004: % hash keys are not lowercase SHA-256 hex values', violations;
    END IF;

    SELECT count(*) INTO violations
    FROM (
        SELECT record_source FROM raw_vault.hub_customer
        UNION ALL SELECT record_source FROM raw_vault.hub_order
        UNION ALL SELECT record_source FROM raw_vault.link_customer_order
        UNION ALL SELECT record_source FROM raw_vault.sat_customer_details
        UNION ALL SELECT record_source FROM raw_vault.sat_order_details
        UNION ALL SELECT record_source FROM raw_vault.eff_sat_customer_order
    ) sources
    WHERE btrim(record_source) = '';
    IF violations > 0 THEN
        RAISE EXCEPTION 'DQ005: % Raw Vault rows have blank record_source', violations;
    END IF;

    SELECT count(*) INTO violations
    FROM staging.order_item_batch s
    JOIN raw_vault.dv_load_batch b USING (batch_id)
    LEFT JOIN raw_vault.hub_product p
        ON p.product_code = btrim(s.product_code)
       AND p.record_source = b.record_source
    WHERE p.hk_product_id IS NULL;
    IF violations > 0 THEN
        RAISE EXCEPTION 'RI007: % order-item staging rows have no product hub', violations;
    END IF;

    SELECT count(*) INTO violations
    FROM raw_vault.link_order_item li
    LEFT JOIN raw_vault.hub_order o USING (hk_order_id)
    LEFT JOIN raw_vault.hub_product p USING (hk_product_id)
    LEFT JOIN raw_vault.hub_customer c USING (hk_customer_id)
    WHERE o.hk_order_id IS NULL OR p.hk_product_id IS NULL OR c.hk_customer_id IS NULL;
    IF violations > 0 THEN
        RAISE EXCEPTION 'RI008: % order-item links have missing parent hubs', violations;
    END IF;

    SELECT count(*) INTO violations
    FROM raw_vault.sat_product_details s
    LEFT JOIN raw_vault.hub_product h USING (hk_product_id)
    WHERE h.hk_product_id IS NULL;
    IF violations > 0 THEN
        RAISE EXCEPTION 'RI009: % product satellite rows have no hub', violations;
    END IF;

    SELECT count(*) INTO violations
    FROM raw_vault.sat_order_item_details s
    LEFT JOIN raw_vault.link_order_item l USING (hk_order_item_id)
    WHERE l.hk_order_item_id IS NULL;
    IF violations > 0 THEN
        RAISE EXCEPTION 'RI010: % order-item satellite rows have no link', violations;
    END IF;
END $$;

SELECT 'raw_vault_quality_gate_passed' AS quality_gate_status;
