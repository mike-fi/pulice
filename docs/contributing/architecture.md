# Architecture

This document describes the high-level design decisions behind pulice.

## Design Goals

1. **Provider-agnostic** — Works with any Pulumi provider, not tied to AWS/GCP/Azure
2. **Framework, not application** — Users define components; pulice provides lifecycle management
3. **Multiple interfaces** — Same operations available via CLI (sync) and HTTP API (async)
4. **Tenant isolation** — Named boundaries prevent cross-environment resource collisions
5. **Zero external dependencies for core** — Only Pulumi SDK and Pydantic required

## Layer Diagram

```
┌─────────────────────────────────────────────┐
│           User Code (Components)            │
│  ManagedComponent + ComponentArgs subclass  │
├─────────────────────────────────────────────┤
│              Interface Layer                 │
│         CLI (Typer)  │  API (FastAPI)       │
├──────────────────────┼──────────────────────┤
│                      │   Task Queue         │
│                      │  (Huey / Celery)     │
├─────────────────────────────────────────────┤
│              Core Layer                     │
│  StackOperations, StackLock, Tenants,      │
│  PassphraseHasher, BackendStorage          │
├─────────────────────────────────────────────┤
│         Pulumi Automation API              │
└─────────────────────────────────────────────┘
```

## Core Concepts

### ManagedComponent

A Pulumi `ComponentResource` subclass paired with a Pydantic `ComponentArgs` model. The args model serves dual purpose:

- **Validation** — Input is validated before any cloud calls
- **Schema derivation** — CLI options and API request models are auto-generated from the Pydantic fields

### Stack Naming

Stacks are named deterministically:

```
{tenant_id}-{component_name}-{stack_uuid}
```

This ensures uniqueness across tenants while remaining human-readable in Pulumi state.

### Operation Lifecycle

All 9 operations go through the same pipeline:

1. Resolve the component class (dotted import path)
2. Resolve the tenant (lookup by name)
3. Validate passphrase (scrypt hash comparison)
4. Acquire lock (mutating operations only)
5. Build the Pulumi program closure
6. Execute via Pulumi Automation API
7. Release lock

### Storage Architecture

```
BackendStorage (ABC)
└── SqliteBackendStorage
    ├── Tenant CRUD (tenants table)
    ├── Stack metadata (stacks table)
    ├── Passphrase hashes (stacks.passphrase_hash)
    ├── Advisory locks (stack_locks table)
    └── Stack working directories (filesystem)

LocalStackReferenceStore
    └── JSON files mapping UUID → stack metadata
```

SQLite was chosen for the default backend because:

- Zero external dependencies
- Sufficient for single-machine deployments (~100 concurrent stacks)
- Atomic writes via WAL mode
- Easy to back up (single file)

### Task Backends

The `TaskBackend` protocol abstracts async execution:

| Backend | Transport | Use Case |
|---------|-----------|----------|
| Huey | SQLite | Single machine, development |
| Celery | Redis/RabbitMQ | Multi-machine, production |

The API server submits operations to the queue; worker processes execute them. This separation means the API stays responsive regardless of how long Pulumi operations take.

### Passphrase Security

Passphrases protect Pulumi stack secrets (encryption key). Pulice adds a fast pre-check:

1. On `create`, hash the passphrase with scrypt and store it
2. On subsequent operations, verify the provided passphrase against the stored hash
3. Only if verification passes, set `PULUMI_CONFIG_PASSPHRASE` and invoke Pulumi

This gives instant feedback on wrong passphrases rather than waiting for Pulumi to fail deep in a decryption step.

### Locking Strategy

`StackLock` uses SQLite row-level locking:

- Insert a row into `stack_locks` → lock acquired
- Delete the row → lock released
- `IntegrityError` on insert → lock held by another process
- Exponential backoff with configurable timeout (default 30s)
- Stale lock cleanup after 10 minutes (crash recovery)

This is sufficient for single-machine deployments. For distributed locking, use Celery with Redis (Redis provides its own coordination).
