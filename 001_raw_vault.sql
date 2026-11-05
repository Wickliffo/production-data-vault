BEGIN;

CREATE SCHEMA IF NOT EXISTS raw_vault;
CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS raw_vault.dv_load_batch (
    batch_id UUID PRIMARY KEY,
    record_source VARCHAR(200) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    completed_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'RUNNING'
        CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    row_count INTEGER NOT NULL DEFAULT 0 CHECK (row_count >= 0),
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS staging.customer_order_batch (
    batch_id UUID NOT NULL REFERENCES raw_vault.dv_load_batch(batch_id),
    row_number BIGINT GENERATED ALWAYS AS IDENTITY,
    customer_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    order_status TEXT,
    order_total NUMERIC(19, 4),
    source_updated_at TIMESTAMPTZ,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (batch_id, row_number)
);

CREATE TABLE IF NOT EXISTS raw_vault.hub_customer (
    hk_customer_id CHAR(64) PRIMARY KEY,
    customer_id TEXT NOT NULL,
    load_datetime TIMESTAMPTZ NOT NULL,
    record_source VARCHAR(200) NOT NULL,
    batch_id UUID NOT NULL REFERENCES raw_vault.dv_load_batch(batch_id),
    CONSTRAINT uq_hub_customer_business_key UNIQUE (record_source, customer_id)
);

CREATE TABLE IF NOT EXISTS raw_vault.hub_order (
    hk_order_id CHAR(64) PRIMARY KEY,
    order_id TEXT NOT NULL,
    load_datetime TIMESTAMPTZ NOT NULL,
    record_source VARCHAR(200) NOT NULL,
    batch_id UUID NOT NULL REFERENCES raw_vault.dv_load_batch(batch_id),
    CONSTRAINT uq_hub_order_business_key UNIQUE (record_source, order_id)
);

CREATE TABLE IF NOT EXISTS raw_vault.link_customer_order (
    hk_customer_order_id CHAR(64) PRIMARY KEY,
    hk_customer_id CHAR(64) NOT NULL REFERENCES raw_vault.hub_customer(hk_customer_id),
    hk_order_id CHAR(64) NOT NULL REFERENCES raw_vault.hub_order(hk_order_id),
    load_datetime TIMESTAMPTZ NOT NULL,
    record_source VARCHAR(200) NOT NULL,
    batch_id UUID NOT NULL REFERENCES raw_vault.dv_load_batch(batch_id),
    CONSTRAINT uq_link_customer_order UNIQUE (hk_customer_id, hk_order_id)
);

CREATE TABLE IF NOT EXISTS raw_vault.sat_customer_details (
    hk_customer_id CHAR(64) NOT NULL REFERENCES raw_vault.hub_customer(hk_customer_id),
    load_datetime TIMESTAMPTZ NOT NULL,
    hash_diff CHAR(64) NOT NULL,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    source_updated_at TIMESTAMPTZ,
    record_source VARCHAR(200) NOT NULL,
    batch_id UUID NOT NULL REFERENCES raw_vault.dv_load_batch(batch_id),
    PRIMARY KEY (hk_customer_id, load_datetime),
    CONSTRAINT uq_sat_customer_hash UNIQUE (hk_customer_id, hash_diff)
);

CREATE TABLE IF NOT EXISTS raw_vault.sat_order_details (
    hk_order_id CHAR(64) NOT NULL REFERENCES raw_vault.hub_order(hk_order_id),
    load_datetime TIMESTAMPTZ NOT NULL,
    hash_diff CHAR(64) NOT NULL,
    order_status TEXT,
    order_total NUMERIC(19, 4),
    source_updated_at TIMESTAMPTZ,
    record_source VARCHAR(200) NOT NULL,
    batch_id UUID NOT NULL REFERENCES raw_vault.dv_load_batch(batch_id),
    PRIMARY KEY (hk_order_id, load_datetime),
    CONSTRAINT uq_sat_order_hash UNIQUE (hk_order_id, hash_diff)
);

CREATE TABLE IF NOT EXISTS raw_vault.eff_sat_customer_order (
    hk_customer_order_id CHAR(64) NOT NULL REFERENCES raw_vault.link_customer_order(hk_customer_order_id),
    load_datetime TIMESTAMPTZ NOT NULL,
    effective_from TIMESTAMPTZ,
    effective_to TIMESTAMPTZ,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    record_source VARCHAR(200) NOT NULL,
    batch_id UUID NOT NULL REFERENCES raw_vault.dv_load_batch(batch_id),
    PRIMARY KEY (hk_customer_order_id, load_datetime),
    CONSTRAINT ck_effective_window CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

CREATE INDEX IF NOT EXISTS ix_sat_customer_latest
    ON raw_vault.sat_customer_details (hk_customer_id, load_datetime DESC);
CREATE INDEX IF NOT EXISTS ix_sat_order_latest
    ON raw_vault.sat_order_details (hk_order_id, load_datetime DESC);
CREATE INDEX IF NOT EXISTS ix_link_customer
    ON raw_vault.link_customer_order (hk_customer_id);
CREATE INDEX IF NOT EXISTS ix_link_order
    ON raw_vault.link_customer_order (hk_order_id);
CREATE INDEX IF NOT EXISTS ix_batch_source_started
    ON raw_vault.dv_load_batch (record_source, started_at DESC);

CREATE OR REPLACE VIEW raw_vault.v_customer_current AS
SELECT DISTINCT ON (s.hk_customer_id)
    h.customer_id,
    s.hk_customer_id,
    s.first_name,
    s.last_name,
    s.email,
    s.source_updated_at,
    s.load_datetime,
    s.record_source
FROM raw_vault.hub_customer h
JOIN raw_vault.sat_customer_details s USING (hk_customer_id)
ORDER BY s.hk_customer_id, s.load_datetime DESC;

CREATE OR REPLACE VIEW raw_vault.v_order_current AS
SELECT DISTINCT ON (s.hk_order_id)
    h.order_id,
    s.hk_order_id,
    s.order_status,
    s.order_total,
    s.source_updated_at,
    s.load_datetime,
    s.record_source
FROM raw_vault.hub_order h
JOIN raw_vault.sat_order_details s USING (hk_order_id)
ORDER BY s.hk_order_id, s.load_datetime DESC;

COMMIT;
