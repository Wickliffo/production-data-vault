BEGIN;

CREATE TABLE IF NOT EXISTS raw_vault.dv_hash_contract (
    hash_contract_version VARCHAR(100) PRIMARY KEY,
    algorithm VARCHAR(50) NOT NULL,
    serialization VARCHAR(200) NOT NULL,
    activated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO raw_vault.dv_hash_contract
    (hash_contract_version, algorithm, serialization)
VALUES
    ('sha256-length-prefixed-v1', 'SHA-256', 'UTF-8 canonical components with byte-length framing')
ON CONFLICT (hash_contract_version) DO NOTHING;

CREATE TABLE IF NOT EXISTS raw_vault.hub_product (
    hk_product_id CHAR(64) PRIMARY KEY,
    product_code TEXT NOT NULL,
    load_datetime TIMESTAMPTZ NOT NULL,
    record_source VARCHAR(200) NOT NULL,
    batch_id UUID NOT NULL REFERENCES raw_vault.dv_load_batch(batch_id),
    CONSTRAINT uq_hub_product_business_key UNIQUE (record_source, product_code)
);

CREATE TABLE IF NOT EXISTS staging.order_item_batch (
    batch_id UUID NOT NULL REFERENCES raw_vault.dv_load_batch(batch_id),
    row_number BIGINT GENERATED ALWAYS AS IDENTITY,
    customer_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    order_item_id TEXT NOT NULL,
    product_code TEXT NOT NULL,
    product_name TEXT,
    category TEXT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(19, 4) NOT NULL CHECK (unit_price >= 0),
    source_updated_at TIMESTAMPTZ,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (batch_id, row_number)
);

CREATE TABLE IF NOT EXISTS raw_vault.link_order_item (
    hk_order_item_id CHAR(64) PRIMARY KEY,
    hk_order_id CHAR(64) NOT NULL REFERENCES raw_vault.hub_order(hk_order_id),
    hk_product_id CHAR(64) NOT NULL REFERENCES raw_vault.hub_product(hk_product_id),
    hk_customer_id CHAR(64) NOT NULL REFERENCES raw_vault.hub_customer(hk_customer_id),
    order_item_id TEXT NOT NULL,
    load_datetime TIMESTAMPTZ NOT NULL,
    record_source VARCHAR(200) NOT NULL,
    batch_id UUID NOT NULL REFERENCES raw_vault.dv_load_batch(batch_id),
    CONSTRAINT uq_link_order_item_business_key UNIQUE (record_source, hk_order_id, order_item_id)
);

CREATE TABLE IF NOT EXISTS raw_vault.sat_product_details (
    hk_product_id CHAR(64) NOT NULL REFERENCES raw_vault.hub_product(hk_product_id),
    load_datetime TIMESTAMPTZ NOT NULL,
    hash_diff CHAR(64) NOT NULL,
    product_name TEXT,
    category TEXT,
    source_updated_at TIMESTAMPTZ,
    record_source VARCHAR(200) NOT NULL,
    batch_id UUID NOT NULL REFERENCES raw_vault.dv_load_batch(batch_id),
    PRIMARY KEY (hk_product_id, load_datetime),
    CONSTRAINT uq_sat_product_hash UNIQUE (hk_product_id, hash_diff)
);

CREATE TABLE IF NOT EXISTS raw_vault.sat_order_item_details (
    hk_order_item_id CHAR(64) NOT NULL REFERENCES raw_vault.link_order_item(hk_order_item_id),
    load_datetime TIMESTAMPTZ NOT NULL,
    hash_diff CHAR(64) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(19, 4) NOT NULL CHECK (unit_price >= 0),
    source_updated_at TIMESTAMPTZ,
    record_source VARCHAR(200) NOT NULL,
    batch_id UUID NOT NULL REFERENCES raw_vault.dv_load_batch(batch_id),
    PRIMARY KEY (hk_order_item_id, load_datetime),
    CONSTRAINT uq_sat_order_item_hash UNIQUE (hk_order_item_id, hash_diff)
);

CREATE INDEX IF NOT EXISTS ix_product_record_source_code
    ON raw_vault.hub_product (record_source, product_code);
CREATE INDEX IF NOT EXISTS ix_order_item_order
    ON raw_vault.link_order_item (hk_order_id);
CREATE INDEX IF NOT EXISTS ix_order_item_product
    ON raw_vault.link_order_item (hk_product_id);
CREATE INDEX IF NOT EXISTS ix_sat_product_latest
    ON raw_vault.sat_product_details (hk_product_id, load_datetime DESC);
CREATE INDEX IF NOT EXISTS ix_sat_order_item_latest
    ON raw_vault.sat_order_item_details (hk_order_item_id, load_datetime DESC);

CREATE OR REPLACE VIEW raw_vault.v_order_item_current AS
SELECT DISTINCT ON (li.hk_order_item_id)
    li.record_source,
    li.order_item_id,
    ho.order_id,
    hc.customer_id,
    hp.product_code,
    p.product_name,
    p.category,
    i.quantity,
    i.unit_price,
    i.source_updated_at,
    i.load_datetime
FROM raw_vault.link_order_item li
JOIN raw_vault.hub_order ho USING (hk_order_id)
JOIN raw_vault.hub_customer hc USING (hk_customer_id)
JOIN raw_vault.hub_product hp USING (hk_product_id)
JOIN raw_vault.sat_product_details p USING (hk_product_id)
JOIN raw_vault.sat_order_item_details i USING (hk_order_item_id)
ORDER BY li.hk_order_item_id, i.load_datetime DESC;

COMMIT;
