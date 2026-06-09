# Feature Spec: Stack Lifecycle Management

## Overview

Add tenant-scoped stack lifecycle management to the **ManagedComponent** registration path in pulice. This introduces explicit tenant registration, passphrase validation at the storage layer, stack locking, and new lifecycle operations (refresh, list, status, export, import).

**Scope:** ManagedComponent stacks only (registered via `register_component` with a `ManagedComponent` subclass). The `WorkspaceController` path is unchanged.

---

## 1. Tenant Registration and Namespace Isolation

### 1.1 Tenant Entity

Add an explicit tenant concept. A tenant is a named isolation boundary that owns zero or more stacks. All ManagedComponent stacks must belong to a tenant.

**New dataclass** in `src/pulice/stack.py`:

```python
@dataclass(frozen=True)
class Tenant:
    id: str           # Internal UUID hex (primary key)
    name: str         # Human-readable unique name
    created_at: str   # ISO 8601 timestamp
```

### 1.2 SQLite Schema Addition

Add a `tenants` table to the SQLite backend alongside the existing `stacks` table. Add a `tenant_id` foreign key column to the `stacks` table.

```sql
CREATE TABLE IF NOT EXISTS tenants (
    id         TEXT PRIMARY KEY,        -- UUID hex
    name       TEXT NOT NULL UNIQUE,    -- Human-readable name
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

For new installations, the `stacks` table DDL becomes:

```sql
CREATE TABLE IF NOT EXISTS stacks (
    name            TEXT PRIMARY KEY,
    uuid            TEXT NOT NULL UNIQUE,
    path            TEXT NOT NULL,
    tenant_id       TEXT NOT NULL REFERENCES tenants(id),
    passphrase_hash TEXT,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Migration:** On first run with the new code, `SqliteBackendStorage._init_db()` must handle the case where the `stacks` table already exists without `tenant_id`. Use `PRAGMA table_info(stacks)` to detect missing columns and run `ALTER TABLE` as needed. Existing stacks without a tenant are assigned to a synthetic `"default"` tenant created automatically.

### 1.3 Tenant CRUD in SqliteBackendStorage

Add the following methods to `SqliteBackendStorage`:

| Method | Signature | Description |
|---|---|---|
| `create_tenant` | `(name: str) -> Tenant` | Insert a new tenant. Generate UUID internally. Raise `ValueError` if `name` already exists. |
| `get_tenant` | `(name: str) -> Tenant` | Look up tenant by name. Raise `ValueError` if not found. |
| `get_tenant_by_id` | `(tenant_id: str) -> Tenant` | Look up tenant by internal ID. Raise `ValueError` if not found. |
| `list_tenants` | `() -> list[Tenant]` | Return all tenants ordered by `created_at`. |
| `delete_tenant` | `(name: str) -> None` | Delete tenant. Raise `ValueError` if tenant still has stacks. |

### 1.4 Tenant-scoped Stack Operations

**Naming convention change.** Stack names must include the tenant ID to prevent collisions across tenants:

```
Current:   {component_name}-{uuid_hex}
New:       {tenant_id}-{component_name}-{uuid_hex}
```

Project names gain the tenant prefix:

```
Current:   pulice-{component_name}
New:       pulice-{tenant_id}-{component_name}
```

**Enforcement.** `_resolve_managed_stack_context()` must accept a `tenant_id` parameter. On `create`, validate that the tenant exists before proceeding. On `read`/`update`/`delete`, verify that the resolved stack reference belongs to the given tenant by checking the `tenant_id` column in the `stacks` table.

### 1.5 StackReference Changes

Add `tenant_id` field to the `StackReference` dataclass:

```python
@dataclass(frozen=True)
class StackReference:
    id: str
    tenant_id: str          # NEW
    component_name: str
    stack_name: str
    project_name: str
    workdir: str
```

Update `LocalStackReferenceStore.save()` and `.get()` to include the new field. Add a `tenant_id` field to the persisted JSON.

### 1.6 CLI Integration for Tenants

Add a `tenant` command group to `PuliceCLI` that exposes tenant management. This should be registered as built-in commands (not user-registered):

```
pulice tenant create --name <tenant-name>
pulice tenant list
pulice tenant delete --name <tenant-name>
```

For ManagedComponent commands, add a required `--tenant` option to every operation (`create`, `read`, `update`, `delete`, and the new operations defined in section 3):

- On `create`: resolve tenant by name, embed `tenant_id` in stack name and reference.
- On other operations: resolve tenant by name, validate the stack reference belongs to that tenant.

**Implementation:** Modify `_managed_component_operation_model()` to inject a `tenant: str` field (with `Field(..., description='Tenant name.')`) into every generated Pydantic model. Modify `_make_run_managed_component()` to extract the tenant name, resolve it to a `Tenant` via `SqliteBackendStorage.get_tenant()`, and pass the `tenant_id` through the call chain.

---

## 2. Passphrase Validation on Access

### 2.1 Passphrase Hash Storage

When a stack is created, hash the user-supplied passphrase and store it alongside the stack metadata. This allows validating the passphrase before invoking Pulumi operations, giving a clear error message instead of a cryptic Pulumi decryption failure.

**SQLite schema change** -- add to the `stacks` table:

```sql
ALTER TABLE stacks ADD COLUMN passphrase_hash TEXT;
```

This column is already included in the full `stacks` DDL shown in section 1.2.

### 2.2 Hashing Implementation

Add a `PassphraseHasher` utility class in `src/pulice/stack.py`:

```python
class PassphraseHasher:
    """Hash and verify passphrases using hashlib.scrypt (zero new dependencies)."""

    @staticmethod
    def hash(passphrase: str) -> str:
        """Return an scrypt hash string of the passphrase.

        Format: ``scrypt:<salt_hex>:<hash_hex>``
        """

    @staticmethod
    def verify(passphrase: str, passphrase_hash: str) -> bool:
        """Return True if the passphrase matches the stored hash."""
```

Use `hashlib.scrypt` from the standard library with a random 16-byte salt. The salt and derived key are stored together as hex in the format `scrypt:<salt_hex>:<hash_hex>`. No new dependencies required.

### 2.3 Integration Points

**On `create`:**
1. Hash the passphrase via `PassphraseHasher.hash()`.
2. Store the hash in the `stacks` table (via `SqliteBackendStorage.save_passphrase_hash(stack_name, hash)`).

**On `read`, `update`, `delete` (and `refresh`, `export`, `import`):**
1. Before calling any Pulumi Automation API method, look up the `passphrase_hash` for the stack from SQLite.
2. Call `PassphraseHasher.verify(passphrase, stored_hash)`.
3. If verification fails, raise a clear error: `"Invalid passphrase for stack '{stack_name}'. The passphrase does not match the one used at creation time."` and exit with code 1.
4. Only proceed with Pulumi operations if verification succeeds.

**Backward compatibility:** Existing stacks with `passphrase_hash = NULL` skip the validation step (they were created before this feature). A future migration command could backfill hashes.

### 2.4 New SqliteBackendStorage Methods

| Method | Signature | Description |
|---|---|---|
| `save_passphrase_hash` | `(stack_name: str, passphrase_hash: str) -> None` | Store the hash for a stack. |
| `get_passphrase_hash` | `(stack_name: str) -> str \| None` | Retrieve the stored hash, or `None` if not set. |

---

## 3. New Stack Lifecycle Operations

All new operations apply to the ManagedComponent path only. Each becomes a new CLI subcommand alongside `create`, `read`, `update`, `delete`.

### 3.1 Refresh

**Purpose:** Run `pulumi refresh` to reconcile Pulumi state with the actual cloud resources without modifying infrastructure.

**CLI:**
```
pulice <component> refresh --stack-reference <ref> --passphrase <pass> --tenant <tenant>
```

**Implementation:** Add `StackOperations.refresh_stack()`:

```python
def refresh_stack(
    self,
    stack_name: str,
    project_name: str,
    workdir: str,
    program: Callable,
    env_vars: Optional[dict] = None,
) -> automation.Stack:
    stack = automation.create_or_select_stack(
        stack_name=stack_name,
        project_name=project_name,
        program=program,
        opts=self._local_workspace_opts(project_name, workdir, env_vars),
    )
    stack.refresh(on_output=print)
    return stack
```

**Registry:** Add `'refresh'` to the set of recognized operations for ManagedComponent. `_managed_component_operation_model()` should generate a model for `refresh` identical to `read`/`delete` (requires `--stack-reference`, `--passphrase`, `--tenant`; no resource args).

### 3.2 List

**Purpose:** List all stacks, optionally filtered by tenant and/or component name.

**CLI:**
```
pulice <component> list --tenant <tenant>
```

**Implementation:**

Add `SqliteBackendStorage.list_stacks()`:

```python
def list_stacks(
    self,
    tenant_id: str | None = None,
    component_name: str | None = None,
) -> list[dict]:
    """Return stack records, optionally filtered by tenant and/or component."""
```

The list command does NOT require a passphrase or stack-reference. It queries the SQLite metadata store and prints a table of stacks with columns: `stack_name`, `tenant`, `component`, `created_at`.

**Registry:** Add `'list'` as a special operation for ManagedComponent. `_managed_component_operation_model()` should generate a model with only `--tenant` (required). `_make_run_managed_component()` should handle the `list` operation by querying the storage directly rather than invoking Pulumi.

### 3.3 Status

**Purpose:** Show the current status of a specific stack -- whether the Pulumi state exists, the last operation result, and resource count.

**CLI:**
```
pulice <component> status --stack-reference <ref> --passphrase <pass> --tenant <tenant>
```

**Implementation:**

Add `StackOperations.stack_status()`:

```python
def stack_status(
    self,
    stack_name: str,
    project_name: str,
    workdir: str,
    program: Callable,
    env_vars: Optional[dict] = None,
) -> dict:
    stack = automation.create_or_select_stack(
        stack_name=stack_name,
        project_name=project_name,
        program=program,
        opts=self._local_workspace_opts(project_name, workdir, env_vars),
    )
    info = stack.info()
    return {
        'stack_name': stack_name,
        'resource_count': info.resource_count if info else 0,
        'last_update': str(info.last_update) if info else None,
        'url': info.url if info else None,
    }
```

Output the result as a formatted table or JSON to stdout.

**Registry:** Add `'status'` as a recognized operation. Model is identical to `read`/`delete` (requires `--stack-reference`, `--passphrase`, `--tenant`).

### 3.4 Export

**Purpose:** Export the Pulumi stack state as JSON for backup or migration.

**CLI:**
```
pulice <component> export --stack-reference <ref> --passphrase <pass> --tenant <tenant> [--output <file>]
```

If `--output` is not provided, print the JSON to stdout.

**Implementation:**

Add `StackOperations.export_stack()`:

```python
def export_stack(
    self,
    stack_name: str,
    project_name: str,
    workdir: str,
    program: Callable,
    env_vars: Optional[dict] = None,
) -> dict:
    stack = automation.create_or_select_stack(
        stack_name=stack_name,
        project_name=project_name,
        program=program,
        opts=self._local_workspace_opts(project_name, workdir, env_vars),
    )
    deployment = stack.export_stack()
    return deployment.deployment
```

**Registry:** Add `'export'` as a recognized operation. Model is like `read`/`delete` plus an optional `output: str = Field(None, description='Output file path. Defaults to stdout.')`.

### 3.5 Import

**Purpose:** Import a previously exported Pulumi stack state.

**CLI:**
```
pulice <component> import --stack-reference <ref> --passphrase <pass> --tenant <tenant> --input <file>
```

**Implementation:**

Add `StackOperations.import_stack()`:

```python
def import_stack(
    self,
    stack_name: str,
    project_name: str,
    workdir: str,
    program: Callable,
    state: dict,
    env_vars: Optional[dict] = None,
) -> None:
    stack = automation.create_or_select_stack(
        stack_name=stack_name,
        project_name=project_name,
        program=program,
        opts=self._local_workspace_opts(project_name, workdir, env_vars),
    )
    stack.import_stack(automation.Deployment(version=3, deployment=state))
```

**Registry:** Add `'import'` as a recognized operation. Model is like `read`/`delete` plus a required `input: str = Field(..., description='Path to the exported state JSON file.')`.

---

## 4. Stack Locking

### 4.1 Purpose

Prevent concurrent operations on the same stack from corrupting state. This guards against multiple CLI invocations targeting the same stack on the same machine.

### 4.2 SQLite Advisory Lock Table

Add a `stack_locks` table:

```sql
CREATE TABLE IF NOT EXISTS stack_locks (
    stack_name TEXT PRIMARY KEY REFERENCES stacks(name),
    holder     TEXT NOT NULL,     -- UUID identifying the lock holder (process)
    operation  TEXT NOT NULL,     -- e.g. 'up', 'destroy', 'refresh'
    locked_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 4.3 StackLock Class

Add a `StackLock` context manager in `src/pulice/stack.py`:

```python
class StackLock:
    """Advisory lock for stack operations backed by SQLite."""

    def __init__(
        self,
        storage: SqliteBackendStorage,
        stack_name: str,
        operation: str,
        timeout: float = 30.0,
    ) -> None:
        ...

    def __enter__(self) -> StackLock:
        """Acquire the lock. Retry with backoff up to timeout.
        Raise StackLockError if lock cannot be acquired."""
        ...

    def __exit__(self, *exc_info) -> None:
        """Release the lock."""
        ...
```

**Acquisition logic:**
1. Generate a holder UUID for this process.
2. Attempt `INSERT INTO stack_locks(stack_name, holder, operation) VALUES (?, ?, ?)`.
3. If the insert succeeds, the lock is acquired.
4. If the insert fails (unique constraint on `stack_name`), check the existing lock:
   - If the `locked_at` timestamp is older than a configurable stale threshold (default: 10 minutes), treat it as stale, delete it, and retry.
   - Otherwise, wait with exponential backoff and retry until timeout.
5. On timeout, raise `StackLockError` with a message indicating which operation holds the lock and when it was acquired.

**Release logic:**
1. `DELETE FROM stack_locks WHERE stack_name = ? AND holder = ?`.
2. If no rows deleted, log a warning (lock was already released or stolen).

### 4.4 StackLockError

Add a custom exception:

```python
class StackLockError(Exception):
    """Raised when a stack lock cannot be acquired."""
```

### 4.5 Integration

Wrap every mutating stack operation in a `StackLock` context manager. Apply locking in `_make_run_managed_component()` around the calls to `create_or_update_stack`, `destroy_stack`, `refresh_stack`, and `import_stack`. Read-only operations (`preview_stack`, `export_stack`, `list`, `status`) do NOT require a lock.

```python
# Example integration in _make_run_managed_component
with StackLock(storage, context.stack_name, operation):
    stack_ops.create_or_update_stack(...)
```

---

## 5. Changes to Existing Code

### 5.1 `src/pulice/stack.py`

| Change | Description |
|---|---|
| Add `Tenant` dataclass | Frozen dataclass with `id`, `name`, `created_at`. |
| Add `PassphraseHasher` class | Static methods `hash()` and `verify()` using `hashlib.scrypt`. |
| Add `StackLock` context manager | SQLite-backed advisory lock. |
| Add `StackLockError` exception | Custom exception for lock failures. |
| Update `StackReference` | Add `tenant_id` field. |
| Update `SqliteBackendStorage._init_db()` | Create `tenants` and `stack_locks` tables. Add `tenant_id` and `passphrase_hash` columns to `stacks`. Handle migration from old schema. |
| Add `SqliteBackendStorage` tenant methods | `create_tenant`, `get_tenant`, `get_tenant_by_id`, `list_tenants`, `delete_tenant`. |
| Add `SqliteBackendStorage` passphrase methods | `save_passphrase_hash`, `get_passphrase_hash`. |
| Add `SqliteBackendStorage.list_stacks()` | Query stacks with optional tenant/component filters. |
| Add `StackOperations.refresh_stack()` | Calls `stack.refresh()`. |
| Add `StackOperations.stack_status()` | Calls `stack.info()`. |
| Add `StackOperations.export_stack()` | Calls `stack.export_stack()`. |
| Add `StackOperations.import_stack()` | Calls `stack.import_stack()`. |
| Update `StackOperations.__init__()` | Expose `self._storage` for lock usage. |
| Update `LocalStackReferenceStore` | Handle `tenant_id` in save/get. |

### 5.2 `src/pulice/registry.py`

| Change | Description |
|---|---|
| Update `_resolve_managed_stack_context()` | Accept `tenant_id` parameter. Prefix stack/project names with tenant ID. Validate tenant ownership on non-create operations. |
| Update `_make_run_managed_component()` | Extract `tenant` from args, resolve to `Tenant`. Call `PassphraseHasher.verify()` before Pulumi ops. Wrap mutating ops in `StackLock`. Handle new operations: `refresh`, `list`, `status`, `export`, `import`. Store passphrase hash on create. |
| Update `_managed_component_operation_model()` | Add `tenant` field to all operation models. Add operation-specific models for `refresh`, `list`, `status`, `export`, `import`. |
| Update `register_component()` | Expand default operations tuple or allow customization. Register tenant commands as built-in group. |
| Add `_register_tenant_commands()` | Register `tenant create`, `tenant list`, `tenant delete` on the Typer app. |

### 5.3 `src/pulice/app.py`

| Change | Description |
|---|---|
| Update `PuliceCLI.__init__()` | Register tenant commands automatically when the CLI is created. |
| Update `PuliceApp` protocol | No changes needed if tenant commands are built-in to PuliceCLI only. |

### 5.4 `src/pulice/__init__.py`

| Change | Description |
|---|---|
| Export new public types | Add `Tenant`, `StackLock`, `StackLockError` to `__all__` if they are part of the public API. |

### 5.5 `pyproject.toml`

No new dependencies required (`hashlib.scrypt` is stdlib).

---

## 6. CLI Command Summary

### Tenant Commands (built-in)

| Command | Options | Description |
|---|---|---|
| `pulice tenant create` | `--name` (required) | Register a new tenant. Prints internal ID. |
| `pulice tenant list` | (none) | List all tenants. |
| `pulice tenant delete` | `--name` (required) | Delete a tenant (must have no stacks). |

### ManagedComponent Commands (per registered component)

Given a component registered as `demo`:

| Command | Required Options | Description |
|---|---|---|
| `pulice demo create` | `--name`, `--passphrase`, `--tenant`, + resource fields | Create a new stack. Returns stack reference. |
| `pulice demo read` | `--stack-reference`, `--passphrase`, `--tenant` | Preview stack state. |
| `pulice demo update` | `--stack-reference`, `--passphrase`, `--tenant`, + resource fields | Update existing stack. |
| `pulice demo delete` | `--stack-reference`, `--passphrase`, `--tenant` | Destroy stack and resources. |
| `pulice demo refresh` | `--stack-reference`, `--passphrase`, `--tenant` | Refresh stack state from cloud. |
| `pulice demo list` | `--tenant` | List all stacks for this component and tenant. |
| `pulice demo status` | `--stack-reference`, `--passphrase`, `--tenant` | Show stack status and resource count. |
| `pulice demo export` | `--stack-reference`, `--passphrase`, `--tenant`, `[--output]` | Export stack state as JSON. |
| `pulice demo import` | `--stack-reference`, `--passphrase`, `--tenant`, `--input` | Import stack state from JSON. |

---

## 7. Operation Model Matrix

How `_managed_component_operation_model()` should generate models for each operation:

| Operation | `name` + resource fields | `--stack-reference` | `--passphrase` | `--tenant` | Extra fields |
|---|---|---|---|---|---|
| `create` | Yes | No | Yes | Yes | -- |
| `read` | No | Yes | Yes | Yes | -- |
| `update` | Yes | Yes | Yes | Yes | -- |
| `delete` | No | Yes | Yes | Yes | -- |
| `refresh` | No | Yes | Yes | Yes | -- |
| `list` | No | No | No | Yes | -- |
| `status` | No | Yes | Yes | Yes | -- |
| `export` | No | Yes | Yes | Yes | `--output` (optional) |
| `import` | No | Yes | Yes | Yes | `--input` (required) |

---

## 8. Testing Requirements

### 8.1 Unit Tests for New Components

| Test Module | Coverage Target |
|---|---|
| `tests/test_stack.py` (new) | `Tenant` dataclass, `PassphraseHasher.hash()`/`.verify()`, `StackLock` acquire/release/timeout/stale, `SqliteBackendStorage` tenant CRUD, passphrase hash storage, `list_stacks()`, schema migration from old to new. |
| `tests/test_stack_operations.py` (new) | `StackOperations.refresh_stack()`, `.stack_status()`, `.export_stack()`, `.import_stack()` -- mocking `pulumi.automation`. |

### 8.2 Updated Tests

| Test Module | Changes |
|---|---|
| `tests/test_registry.py` | Update all `TestRegisterManagedComponent` tests to include `--tenant` option. Add tests for new operations (`refresh`, `list`, `status`, `export`, `import`). Add tests for passphrase validation failure (wrong passphrase). Add tests for tenant validation failure (stack doesn't belong to tenant). Add tests for lock acquisition in mutating operations. |

### 8.3 Key Test Scenarios

1. **Tenant isolation:** Two tenants with same component name and resource name create separate stacks with distinct stack names.
2. **Passphrase validation:** Wrong passphrase on `update`/`delete`/`refresh` fails before any Pulumi call is made.
3. **Lock contention:** Two concurrent operations on the same stack -- second one waits then acquires after first releases.
4. **Stale lock cleanup:** A lock older than the stale threshold is automatically cleaned up.
5. **List filtering:** `list` returns only stacks for the given tenant and component.
6. **Export/Import round-trip:** Export a stack, import it, verify state is restored.
7. **Schema migration:** Open a database created by the old code, verify migration adds new columns and creates default tenant.
8. **Backward compatibility:** Existing stacks without `passphrase_hash` skip passphrase validation.

---

## 9. Implementation Order

Implement in this order to maintain a working system at each step:

1. **Schema migration + Tenant entity** -- Update `SqliteBackendStorage._init_db()` with new tables/columns and migration logic. Add `Tenant` dataclass and tenant CRUD methods. Tests for tenant CRUD and migration.
2. **Tenant CLI commands** -- Add `tenant create/list/delete` commands to `PuliceCLI`. Tests for CLI commands.
3. **Tenant-scoped stack naming** -- Update `_resolve_managed_stack_context()`, `_make_run_managed_component()`, and `_managed_component_operation_model()` to require and use `--tenant`. Update stack naming conventions. Update `StackReference` with `tenant_id`. Update all existing ManagedComponent tests.
4. **Passphrase hashing** -- Add `PassphraseHasher`, `save_passphrase_hash`/`get_passphrase_hash` methods. Integrate validation into `_make_run_managed_component()`. Tests for hash/verify and validation flow.
5. **Stack locking** -- Add `stack_locks` table, `StackLock` context manager, `StackLockError`. Wrap mutating operations. Tests for lock acquire/release/timeout/stale.
6. **New operations: refresh** -- Add `StackOperations.refresh_stack()`, wire up CLI. Tests.
7. **New operations: list + status** -- Add `list_stacks()`, `stack_status()`, wire up CLI. Tests.
8. **New operations: export + import** -- Add `export_stack()`, `import_stack()`, wire up CLI. Tests.

---

## 10. Non-Goals

The following are explicitly out of scope for this feature:

- Garbage collection of orphaned stack directories/state.
- Changes to the `WorkspaceController` registration path.
- Multi-machine/distributed locking (e.g., DynamoDB, Redis).
- Passphrase auto-generation or key derivation from a master secret.
- Tenant-level RBAC or permissions beyond stack ownership.
- Pulumi Cloud backend integration (remains file-based by default).
