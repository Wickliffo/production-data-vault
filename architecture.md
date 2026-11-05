# Data Vault 2.0 Architecture

## Layers

### Landing and staging

The loader writes every source record to `staging.customer_order_batch` before vault insertion. The batch row preserves source payload and operational metadata. In a larger deployment, landing should be immutable object storage plus a typed staging table, with a source offset or file identifier and schema version.

### Raw Vault

- `hub_customer`: one row per source-qualified canonical customer business key.
- `hub_order`: one row per source-qualified canonical order business key.
- `hub_product`: one row per source-qualified canonical product business key.
- `link_customer_order`: one row per customer/order relationship.
- `link_order_item`: one row per source order-line identity, relating an order,
  product, and customer at the order-item grain.
- `sat_customer_details`: append-only customer descriptive history.
- `sat_order_details`: append-only order descriptive history.
- `sat_product_details`: append-only product descriptive history.
- `sat_order_item_details`: append-only quantity and price history for an order line.
- `eff_sat_customer_order`: relationship validity/effectivity history.

Every vault row carries a load timestamp, record source, and batch ID. No descriptive attribute is stored in a hub or link.

## Hashing contract

The implementation uses SHA-256 represented as lowercase 64-character hexadecimal under the versioned contract `sha256-length-prefixed-v1`. Canonicalization trims leading/trailing whitespace, uppercases text, collapses repeated whitespace, and represents null as `<NULL>`. Components are serialized with UTF-8 byte-length framing rather than a delimiter, and entity namespaces plus source qualification are included where required. The active contract is persisted in `raw_vault.dv_hash_contract`.

This is a reference contract, not a universal enterprise standard. Before onboarding another language or warehouse, publish golden vectors and require parity tests. Any change to canonicalization, serialization, or algorithm must create a new contract version and a controlled rehash migration.

The production-oriented path is `BulkRawVaultLoader`, which uses PostgreSQL `COPY` into a temporary relation followed by set-based hub, link, satellite, and effectivity statements. The row-oriented loader remains available for small administrative or compatibility loads.

## Business-key qualification

The loader qualifies hub hash keys with `record_source`, and the hub uniqueness
constraints are `(record_source, business_key)`. This is the safer default for
enterprise integration because CRM, ERP, billing, and regional systems may all
reuse identifiers such as `C-100`. Cross-source identity mastering belongs in a
Business Vault or MDM process; the Raw Vault must not silently merge records.

If the enterprise proves that a business key is globally unique, the source
qualification can be removed only through a versioned migration and a new hash
contract. The change must be tested against collision and replay fixtures.

## History semantics

A satellite row represents a distinct descriptive state observed at load time. `hash_diff` prevents duplicate unchanged states. Load timestamp and source-updated timestamp are separate: load time answers “when did the platform observe it?”, while source time answers “when did the source say it changed?”.

Effectivity is modelled separately because relationship validity is not the same thing as descriptive history. For production use, define how source deletions, corrections, and late-arriving relationship events close effectivity intervals; do not infer business validity solely from ingestion order.

## Business Vault and marts

This repository stops at a Raw Vault plus current-state views. Add Business Vault objects only for explicit business rules:

- PIT tables for efficient as-of joins across satellites
- Bridges for common relationship traversals
- Rule-based derived satellites
- Effectivity transformations and survivorship rules
- Information marts for consumer-specific dimensional or wide-table access

Raw Vault tables should remain stable while Business Vault and marts evolve with consumer requirements.
