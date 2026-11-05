[README (3).md](https://github.com/user-attachments/files/34431479/README.3.md)

# Production Data Vault 2.0

[![CI](https://github.com/YOUR_GITHUB_USERNAME/production-data-vault/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_GITHUB_USERNAME/production-data-vault/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/postgresql-16%2B-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A production-oriented reference implementation of a **Data Vault 2.0 Raw Vault** for multi-source enterprise and e-commerce integration.

This repository combines a clear Data Vault modelling approach with operational controls that are usually missing from small examples: source-qualified business keys, deterministic SHA-256 hashing, immutable staging payloads, batch lineage, replay-safe loading, set-based PostgreSQL ingestion, effectivity history, data-quality assertions, and CI-backed integration tests.

> **Project status: pre-production reference implementation.** The code is designed to be extended into a production platform, but production adoption still requires a source-specific contract, PostgreSQL execution evidence, security review, performance benchmarks, backup/restore validation, and operational SLOs.

## Why this project exists

Traditional 3NF and dimensional models often make source onboarding expensive: new systems introduce schema changes, foreign-key refactoring, and downstream breakage. Data Vault separates the concerns that change at different rates:

- **Hubs** preserve stable business keys.
- **Links** preserve relationships and their grain.
- **Satellites** preserve descriptive history and source context.
- **Effectivity satellites** preserve relationship validity.
- **Control and staging tables** preserve operational lineage and replayability.

The result is a Raw Vault that can accept new source systems without rewriting existing historical structures. Business Vault rules and consumer marts remain downstream and purpose-specific.

## Architecture

```text
┌──────────────────────┐
│ Source systems        │  CRM / ERP / billing / e-commerce
└──────────┬───────────┘
           │ immutable payload + source metadata
           v
┌──────────────────────┐
│ Landing / staging     │  typed rows, JSONB payload, batch ID
└──────────┬───────────┘
           │ COPY + set-based SQL
           v
┌────────────────────────────────────────────────────────────┐
│ Raw Data Vault                                           │
│  Hubs       Links              Satellites                  │
│  Customer   Customer–Order     Customer Details            │
│  Order      Order Item         Order Details               │
│  Product                       Product Details             │
│                                Order Item Details          │
│                                Relationship Effectivity   │
└──────────┬─────────────────────────────────────────────────┘
           v
┌──────────────────────┐
│ Business Vault        │  PITs, bridges, rules, survivorship
└──────────┬───────────┘
           v
┌──────────────────────┐
│ Information marts     │  reporting and consumer models
└──────────────────────┘
```

## Implemented model

| Object | Type | Grain / purpose |
|---|---|---|
| `hub_customer` | Hub | Source-qualified customer business key |
| `hub_order` | Hub | Source-qualified order business key |
| `hub_product` | Hub | Source-qualified product business key |
| `link_customer_order` | Link | Customer-to-order relationship |
| `link_order_item` | Link | One source order-line identity to order, product, and customer |
| `sat_customer_details` | Satellite | Customer descriptive history |
| `sat_order_details` | Satellite | Order status and amount history |
| `sat_product_details` | Satellite | Product name and category history |
| `sat_order_item_details` | Satellite | Order-line quantity and price history |
| `eff_sat_customer_order` | Effectivity satellite | Relationship validity and current-row state |
| `dv_load_batch` | Control | Batch lifecycle, source, status, and reconciliation count |
| `staging.*` | Staging | Typed source data plus replayable JSONB payload |

### Source-qualified identity

The same business key may legitimately appear in multiple source systems. The Raw Vault therefore preserves source-qualified identity:

```text
CRM_A / C-100  → one customer hub identity
ERP_B / C-100  → another customer hub identity
```

Cross-source identity mastering belongs in an MDM or Business Vault process. The Raw Vault does not silently merge source records.

### Hash contract

Hash keys and hash diffs use the versioned contract:

```text
sha256-length-prefixed-v1
```

The contract uses SHA-256, canonicalized values, explicit null representation, UTF-8 byte-length framing, and lowercase 64-character hexadecimal output. Length framing avoids ambiguous delimiter-based composites. The active contract is recorded in `raw_vault.dv_hash_contract` and validated by the quality gate.

## Repository structure

```text
production-data-vault/
├── .github/
│   └── workflows/
│       └── ci.yml                         # PostgreSQL-backed CI pipeline
├── docs/
│   ├── architecture.md                   # Data Vault modelling decisions
│   ├── data-quality.md                   # Quality gate and assertions
│   ├── operations.md                    # Runbook, recovery, security, scaling
│   └── source-contract.synthetic.md      # Synthetic source contract
├── migrations/
│   ├── 001_raw_vault.sql                 # Core control, staging, hubs, links, sats
│   └── 002_ecommerce_domain.sql          # Product and order-item vertical slice
├── scripts/
│   └── validate_raw_vault.sql            # Fail-fast DQ and RI gate
├── src/dv_ingest/
│   ├── __init__.py                       # Public package exports
│   ├── bulk_loader.py                    # COPY + set-based production loader
│   ├── cli.py                            # Demo and fixture commands
│   ├── hash.py                           # Canonicalization and hash contract
│   ├── loader.py                         # Compatibility row-oriented loader
│   └── models.py                         # Typed source record contracts
├── tests/
│   ├── fixtures/
│   │   └── adversarial_records.json       # Sanitized multi-source fixture
│   ├── conftest.py                       # PostgreSQL integration fixture
│   ├── test_adversarial_unit.py          # Hash and contract edge cases
│   ├── test_hash_and_models.py           # Core unit tests
│   ├── test_integration.py               # Replay and satellite history tests
│   └── test_synthetic_integration.py     # Multi-source, volume, and order-item tests
├── .dockerignore                          # Docker build exclusions
├── .env.example                          # Safe local configuration template
├── .gitignore
├── CHANGELOG.md
├── CONTRIBUTING.md
├── docker-compose.yml                    # Local PostgreSQL 16 runtime
├── LICENSE
├── Makefile                              # Repeatable developer commands
├── pyproject.toml                        # Packaging and tool configuration
└── SECURITY.md
```

## Quick start

### Prerequisites

- Docker and Docker Compose
- Python 3.11 or newer
- PostgreSQL client tools (`psql`) for the quality gate

### 1. Start a clean local database

The migrations are mounted into the PostgreSQL initialization directory. Use `-v` when recreating a disposable local database after changing migrations.

```bash
docker compose down -v
docker compose up -d postgres
```

The default local connection is:

```text
postgresql://vault:vault@localhost:5432/vault
```

For a non-local database, set `DATABASE_URL` through your secret manager or shell environment. Do not commit credentials.

### 2. Install the package

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
export DATABASE_URL='postgresql://vault:vault@localhost:5432/vault'
```

### 3. Load the adversarial fixture

The fixture contains normal records, exact replays, corrections, nulls, whitespace variations, Unicode, late-arriving data, and the same business keys in two source systems.

```bash
make load-fixture
```

Equivalent CLI command:

```bash
python -m dv_ingest.cli load-fixture \
  tests/fixtures/adversarial_records.json \
  --database-url "$DATABASE_URL"
```

### 4. Run tests and quality validation

```bash
make test
make lint
make typecheck
make quality-check
```

The quality gate fails with a non-zero exit code if it finds invalid staging records, batch-count mismatches, missing hubs, orphaned links, orphaned satellites, invalid hashes, multiple current effectivity rows, or missing source lineage.

## CI/CD pipeline

GitHub Actions runs a PostgreSQL-backed pipeline on pushes and pull requests:

```text
Start PostgreSQL 16
        ↓
Apply ordered migrations
        ↓
Install package and development tools
        ↓
Run unit and integration tests
        ↓
Load adversarial multi-source fixture using BulkRawVaultLoader
        ↓
Run data-quality and referential-integrity SQL gate
        ↓
Run Ruff linting
        ↓
Run mypy type checking
```

Workflow file: `.github/workflows/ci.yml`.

Before pushing, replace `YOUR_GITHUB_USERNAME/production-data-vault` in the README badge URLs with your actual GitHub repository path.

## Ingestion paths

### Production-oriented bulk path

`BulkRawVaultLoader` uses PostgreSQL `COPY` into a temporary relation, then executes set-based inserts into hubs, links, satellites, and effectivity tables. This is the path used by the CLI fixture loader and CI.

```python
from dv_ingest import BulkRawVaultLoader

loader = BulkRawVaultLoader(connection, record_source="CRM_A")
batch_id = loader.load(records)
```

The loader validates records before opening the database transaction and treats a completed replay with the same batch ID and row count as idempotent.

### Compatibility path

`RawVaultLoader` remains available for small administrative loads and simple integrations. It uses row-oriented statements and should not be the default for high-volume production ingestion.

## Data-quality and operational guarantees

The repository enforces or validates the following behaviours:

- Business keys are required and canonicalized.
- Hubs, links, and satellites carry load timestamp, record source, and batch ID.
- SHA-256 hash keys are deterministic and source-qualified.
- Satellites preserve descriptive changes without overwriting prior states.
- Link effectivity maintains at most one current row per relationship.
- Foreign keys protect parent-child relationships.
- Completed batch row counts reconcile to staged rows.
- Replayed batches do not create duplicate facts through the bulk path.
- Raw source payloads remain available in staging for replay and lineage.

These are reference guarantees. Production systems should add source record IDs, watermarks, reject/quarantine tables, schema version capture, orchestration retries, metrics, alerting, and immutable landing storage.

## Production adoption checklist

Before using this repository for production workloads, complete the following:

- Replace the synthetic fixture with a reviewed, versioned source contract.
- Confirm business-key scope for every source and entity.
- Define source record IDs, watermarks, late-arrival rules, corrections, deletes, and tombstones.
- Define batch freshness, throughput, RPO, RTO, retention, and reconciliation targets.
- Run PostgreSQL integration tests in your environment and test concurrent loaders.
- Benchmark expected batch sizes and tune indexes, connection pooling, and partitioning.
- Configure TLS, least-privilege roles, secret rotation, PII masking, retention, and access auditing.
- Retain immutable landing data outside PostgreSQL so historical loads can be replayed.
- Exercise backup restoration and failure recovery before cutover.
- Add Business Vault PIT, bridge, survivorship, and mart models only for confirmed consumer needs.

## Development commands

| Command | Purpose |
|---|---|
| `make install` | Install the package and development dependencies |
| `make up` | Start local PostgreSQL |
| `make down` | Stop local PostgreSQL |
| `make test` | Run the test suite |
| `make lint` | Run Ruff |
| `make format` | Format Python files with Ruff |
| `make typecheck` | Run mypy |
| `make load-fixture` | Load the adversarial multi-source fixture |
| `make quality-check` | Run the PostgreSQL DQ/RI gate |

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Changes to hash canonicalization, migrations, source contracts, or relationship grain require tests and documentation updates. Do not commit credentials or real customer data.

## Security

See [SECURITY.md](SECURITY.md) for responsible disclosure and data-handling guidance.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
