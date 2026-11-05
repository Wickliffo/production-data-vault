# Synthetic Source Contract

This fixture is deliberately adversarial and is not production data. It is the pre-production contract used to exercise the loader before a real source contract is supplied.

## Sources

| Source | Entities | Business key rule | Relationship | Cadence |
|---|---|---|---|---|
| `CRM_A` | customer/order | unique only within source | customer owns order | daily batch |
| `ERP_B` | customer/order | unique only within source | customer owns order | daily batch |

`C-100` and `O-900` intentionally occur in both sources. The Raw Vault must preserve two source-qualified hub identities. Cross-source mastering is explicitly out of scope for the Raw Vault.

## Contract rules

- Customer and order IDs are required and are trimmed/canonicalized by the loader.
- Names and email are nullable.
- `order_total` is a non-negative decimal.
- `source_updated_at` is an ISO-8601 timestamp with timezone.
- Replayed records are expected and must not create duplicate hub/link/satellite states.
- Changed attributes create a new satellite state.
- A source cancellation is represented by `order_status = CANCELLED`; a production source must additionally document hard-delete/tombstone behavior.
- Source payload is retained as JSONB for replay and lineage.

## Cases included

- Normal record
- Exact replay
- Attribute correction
- Same business key in two sources
- Null and whitespace values
- Unicode values
- Late-arriving source timestamp

Invalid-record cases to add once the real source contract is supplied include blank business keys, negative order totals, malformed timestamps, unknown status values, and broken source-record identifiers.
