# Staging-to-Raw-Vault Data Quality Gate

The repository includes a fail-fast PostgreSQL quality gate at `scripts/validate_raw_vault.sql`. It is executed in CI after the schema migration, integration tests, and demo load. The same gate is available locally with:

```bash
make quality-check
```

The command exits non-zero if any assertion fails, so it can be used as a deployment promotion gate as well as a pull-request check.

## Assertions

- Staging customer and order business keys are not blank.
- The active database hash contract is the expected versioned SHA-256 contract.
- Completed batch `row_count` reconciles exactly to staged rows.
- Every staged customer has a corresponding customer hub.
- Every staged order has a corresponding order hub.
- Every link has both parent hubs.
- Every customer satellite row has a customer hub.
- Every order satellite row has an order hub.
- Every effectivity row has a corresponding link.
- Every order-item staging row has a source-qualified product hub.
- Every order-item link has order, product, and customer parent hubs.
- Every product satellite has a product hub.
- Every order-item satellite has an order-item link.
- No relationship has more than one current effectivity row.
- All vault hash keys are lowercase 64-character SHA-256 hex values.
- All Raw Vault rows have a non-blank record source.

The SQL uses PostgreSQL `DO` assertions and `RAISE EXCEPTION`, which makes a failed check visible to both `psql` and GitHub Actions. The checks complement, rather than replace, database constraints: constraints protect writes while the gate detects completeness, reconciliation, and cross-table integrity defects.

CI loads the fixture with `BulkRawVaultLoader`, which exercises the COPY plus
set-based path rather than only the compatibility row loader.

## CI order

1. Start PostgreSQL 16.
2. Apply the versioned migration.
3. Install the Python package.
4. Run unit and integration tests.
5. Run the deterministic demo load.
6. Execute the quality gate.
7. Run Ruff and mypy.

For a production deployment, replace the demo load with the orchestration job for the target source and execute the same SQL gate before promoting the batch or deployment.
