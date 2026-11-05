# Operations Runbook

## Batch lifecycle

1. Create a `dv_load_batch` row with a globally unique batch ID and source identifier.
2. Land and validate records. Invalid rows belong in a reject/quarantine flow in a full deployment.
3. Load hubs and links before satellites, inside one transaction for the reference slice.
4. Mark the batch `COMPLETED` only after all inserts and reconciliation checks pass.
5. On failure, roll back the transaction and persist a failed batch status from the orchestration layer.

## Idempotency and replay

Replaying an unchanged record is safe for hubs, links, and satellites because uniqueness constraints protect the facts. A production source adapter should also carry a source record ID and source event/version so a corrected event can be distinguished from a duplicate extract. Replays must be tested with the same batch ID and with a new batch ID.

## Observability

At minimum, publish metrics for batch duration, input/accepted/rejected counts, hub/link/satellite insert counts, duplicate rates, source lag, current watermark, failed batches, and database lock/connection pressure. Structured logs must include batch ID and source but must not log PII such as raw email addresses.

## Security and privacy

Use separate ingestion and read roles, TLS, managed secret storage, and masked non-production data. Customer email is PII: restrict access through views or column-level controls, define retention and deletion obligations, and audit privileged reads. Never commit `.env` files or credentials.

## Recovery targets

Production deployment must define RPO/RTO, backup frequency, point-in-time recovery, and restore rehearsal cadence. The Raw Vault is only replayable if landing data and source offsets are retained immutably outside the database.

## Scaling path

For larger volumes, replace row-by-row inserts with COPY into a batch staging table followed by set-based `INSERT ... SELECT` statements. Partition high-volume satellites by load date, add warehouse-specific clustering/distribution, and use connection pooling. Preserve the same hash and idempotency contract.

## Deployment gates

Before release:

- unit, integration, migration, and replay tests pass;
- hash golden vectors are unchanged or versioned;
- source-to-target counts reconcile;
- schema drift is reviewed;
- backup restore is proven;
- permissions and PII masking are checked;
- dashboards and failure runbooks are available.
