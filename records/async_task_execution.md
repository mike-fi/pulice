# Feature Spec: Asynchronous and Distributed Task Execution

## Overview

Add an HTTP API layer to pulice that executes stack lifecycle operations asynchronously via a task queue. The CLI remains synchronous (unchanged). The API submits operations as background tasks, returning a task ID that clients poll for status and results.

Uses **Huey** (SQLite backend) as the default task queue with a protocol-based abstraction that allows swapping to **Celery** (Redis/RabbitMQ backend) for distributed deployments. Uses **FastAPI** for the HTTP API.

**Scope:** ManagedComponent stack operations and tenant CRUD, exposed over HTTP. The CLI path (`PuliceCLI`) is not modified.

**Prerequisite:** The stack lifecycle management spec (`specs/stack_lifecycle.md`) should be implemented first. This spec builds on top of tenants, passphrase validation, stack locking, and the expanded operation set defined there.

---

## 1. Architecture

```
                          ┌──────────────┐
  CLI (typer, sync)       │  PuliceCLI   │──── direct call ───► StackOperations
                          └──────────────┘                      (synchronous)

                          ┌──────────────┐     ┌────────────┐   ┌──────────────────┐
  HTTP API (FastAPI)      │  PuliceAPI   │────►│ TaskBackend │──►│  Worker process   │
                          │  (async)     │     │ (protocol)  │   │  (Huey consumer)  │
                          └──────────────┘     └────────────┘   │                    │
                                │                   │           │  StackOperations   │
                                │              ┌────┴────┐      │  (synchronous)     │
                                │              │ Huey    │      └──────────────────┘
                                │              │ Celery  │
                                │              └─────────┘
                                │
                          ┌─────┴────────┐
                          │ SQLite /     │
                          │ Shared state │
                          └──────────────┘
```

### Key principles

1. **CLI is unchanged.** All existing synchronous CLI behavior stays as-is. The API is an additive feature.
2. **Shared core.** Both CLI and API use the same `StackOperations`, `SqliteBackendStorage`, `PassphraseHasher`, and `StackLock` from `stack.py`. No duplication of business logic.
3. **Task backend is swappable.** A `TaskBackend` protocol defines the contract. `HueyTaskBackend` is the default. `CeleryTaskBackend` is an alternative for distributed deployments.
4. **Separate processes.** The API server and task worker run as independent processes. Scale workers horizontally without touching the API server.

---

## 2. TaskBackend Protocol

### 2.1 Protocol Definition

Add a new module `src/pulice/tasks.py` with the `TaskBackend` protocol:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class TaskStatus(Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    SUCCESS = 'success'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    RETRYING = 'retrying'


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    status: TaskStatus
    result: Any | None = None        # Return value on success
    error: str | None = None         # Error message/traceback on failure
    created_at: str | None = None    # ISO 8601
    started_at: str | None = None    # ISO 8601
    completed_at: str | None = None  # ISO 8601


@runtime_checkable
class TaskBackend(Protocol):
    """Contract for async task execution backends."""

    def submit(
        self,
        task_name: str,
        kwargs: dict[str, Any],
    ) -> str:
        """Submit a task for async execution. Return a task ID."""
        ...

    def get_status(self, task_id: str) -> TaskResult:
        """Return the current status and result of a task."""
        ...

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending or running task. Return True if cancelled."""
        ...

    def retry(self, task_id: str) -> str:
        """Retry a failed task. Return the new task ID."""
        ...
```

### 2.2 Task Names

Task names map 1:1 to stack operations. The `task_name` parameter is a string like:

| task_name | Stack Operation |
|---|---|
| `stack.create` | `StackOperations.create_or_update_stack` |
| `stack.read` | `StackOperations.preview_stack` |
| `stack.update` | `StackOperations.create_or_update_stack` |
| `stack.delete` | `StackOperations.destroy_stack` |
| `stack.refresh` | `StackOperations.refresh_stack` |
| `stack.status` | `StackOperations.stack_status` |
| `stack.export` | `StackOperations.export_stack` |
| `stack.import` | `StackOperations.import_stack` |

### 2.3 Task kwargs

The `kwargs` dict contains everything the worker needs to execute the task without access to the original request context:

```python
{
    "component_class": "mypackage.components.DemoComponent",  # importable dotted path
    "operation": "create",
    "tenant_name": "acme",
    "passphrase": "secret",                                    # encrypted at rest (see §2.5)
    "args": {"name": "my-stack", "region": "eu-west-1"},       # Pydantic model_dump()
    "stack_reference": None,                                    # or UUID hex for non-create ops
    "state_dir": "/path/to/pulice-state",
    "backend_url": "file:///path/to/.pulumi-state",            # or None for default
}
```

### 2.4 Task Serialization Boundary

The Pulumi program callable (`_build_managed_program()`) is a closure and **cannot be serialized**. Instead, serialize the inputs needed to reconstruct it:

- `component_class`: The importable dotted path of the `ManagedComponent` subclass (e.g., `"myapp.components.DemoComponent"`).
- `args`: The Pydantic model dumped to a dict via `model_dump()`.

The worker reconstructs the closure at execution time:

```python
import importlib

def _resolve_component_class(dotted_path: str) -> type[ManagedComponent]:
    module_path, class_name = dotted_path.rsplit('.', 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)
```

### 2.5 Passphrase Handling in Task Payloads

The passphrase is part of the task kwargs because the worker needs it as `PULUMI_CONFIG_PASSPHRASE`. For security:

1. **In-transit:** The passphrase travels from the API server to the task queue backend. For SQLite (same machine), this is acceptable. For Redis/RabbitMQ (distributed), TLS should be used on the broker connection.
2. **At-rest:** Huey's SQLite storage stores task payloads as pickled/serialized blobs. The passphrase is embedded in the payload. This is no worse than the current `PULUMI_CONFIG_PASSPHRASE` environment variable approach, but should be documented as a known limitation.
3. **Future improvement (out of scope):** Encrypt task payloads at rest, or pass the passphrase via a short-lived secret reference rather than inline.

---

## 3. HueyTaskBackend

### 3.1 Dependencies

Add to `pyproject.toml`:

```toml
dependencies = [
    # ... existing ...
    "huey>=2.5.0",
]
```

Huey's SQLite backend (`SqliteHuey`) has zero additional dependencies.

### 3.2 Huey Instance Configuration

Add a factory function in `src/pulice/tasks.py`:

```python
def create_huey_instance(state_dir: str | None = None) -> SqliteHuey:
    from huey.contrib.sql_huey import SqliteHuey

    root = state_dir or os.getenv('PULICE_STATE_DIR') or str(
        Path(tempfile.gettempdir()) / 'pulice-state'
    )
    db_path = str(Path(root) / 'pulice-tasks.db')
    return SqliteHuey(filename=db_path, immediate=False)
```

The `immediate=False` parameter ensures tasks are always queued (not executed inline), even in development.

### 3.3 HueyTaskBackend Implementation

```python
class HueyTaskBackend:
    """Huey-backed implementation of TaskBackend."""

    def __init__(self, huey_instance: SqliteHuey) -> None:
        self._huey = huey_instance
        self._register_tasks()

    def _register_tasks(self) -> None:
        """Register all stack operation tasks with the Huey instance."""
        # Each task_name maps to a Huey @task-decorated function.
        ...

    def submit(self, task_name: str, kwargs: dict[str, Any]) -> str:
        task_fn = self._tasks[task_name]
        result = task_fn(**kwargs)
        return result.id

    def get_status(self, task_id: str) -> TaskResult:
        ...

    def cancel(self, task_id: str) -> bool:
        return self._huey.revoke_by_id(task_id)

    def retry(self, task_id: str) -> str:
        ...
```

### 3.4 Huey Task Definitions

Each task is a Huey `@task`-decorated function that:

1. Resolves the component class from its dotted path.
2. Instantiates `StackOperations` with the provided `state_dir`.
3. Resolves the tenant and validates the passphrase (using `PassphraseHasher.verify()`).
4. Acquires a `StackLock` for mutating operations.
5. Calls the appropriate `StackOperations` method.
6. Returns the result (stack reference on create, status dict on status, exported JSON on export, etc.).

```python
@huey.task(retries=2, retry_delay=10)
def execute_stack_operation(
    component_class: str,
    operation: str,
    tenant_name: str,
    passphrase: str,
    args: dict,
    stack_reference: str | None,
    state_dir: str | None,
    backend_url: str | None,
) -> dict:
    """Generic task executor for all stack operations."""
    ...
```

A single generic task function handles all operations, dispatching internally based on `operation`. This keeps the Huey task registry simple and avoids registering 8+ separate task functions.

### 3.5 Retry and Failure Semantics

| Operation | Retryable | Rationale |
|---|---|---|
| `create` | No | Partial state may exist. User should inspect and decide. |
| `update` | Yes (idempotent) | `pulumi up` is idempotent. |
| `read` | Yes | Read-only preview. |
| `delete` | No | Partial destroy may leave resources. User should inspect. |
| `refresh` | Yes | Idempotent state reconciliation. |
| `status` | Yes | Read-only. |
| `export` | Yes | Read-only. |
| `import` | No | State mutation. User should inspect. |

Non-retryable operations are submitted with `retries=0`. Retryable operations use `retries=2, retry_delay=10` as defaults, configurable via environment variables.

---

## 4. CeleryTaskBackend

### 4.1 Dependencies

Celery is an **optional** dependency. Add to `pyproject.toml` as an extra:

```toml
[project.optional-dependencies]
celery = [
    "celery[redis]>=5.4.0",
]
```

Users install with `pip install pulice[celery]` or `uv add pulice[celery]`.

### 4.2 CeleryTaskBackend Implementation

```python
class CeleryTaskBackend:
    """Celery-backed implementation of TaskBackend."""

    def __init__(self, celery_app: Any) -> None:
        self._app = celery_app
        self._register_tasks()

    def submit(self, task_name: str, kwargs: dict[str, Any]) -> str:
        result = self._app.send_task(task_name, kwargs=kwargs)
        return result.id

    def get_status(self, task_id: str) -> TaskResult:
        result = self._app.AsyncResult(task_id)
        ...

    def cancel(self, task_id: str) -> bool:
        self._app.control.revoke(task_id, terminate=True)
        return True

    def retry(self, task_id: str) -> str:
        ...
```

### 4.3 Celery Task Definitions

Mirror the Huey task structure. A single `@shared_task` handles all operations:

```python
@shared_task(bind=True, name='stack.operation')
def execute_stack_operation(self, **kwargs):
    # Same logic as the Huey task
    ...
```

### 4.4 Configuration

Celery requires a broker URL and result backend:

```python
celery_app = Celery(
    'pulice',
    broker=os.getenv('PULICE_CELERY_BROKER_URL', 'redis://localhost:6379/0'),
    backend=os.getenv('PULICE_CELERY_RESULT_BACKEND', 'redis://localhost:6379/1'),
)
```

---

## 5. Backend Selection and Configuration

### 5.1 Environment-based Selection

The active task backend is selected via the `PULICE_TASK_BACKEND` environment variable:

| Value | Backend | Requirements |
|---|---|---|
| `huey` (default) | `HueyTaskBackend` with `SqliteHuey` | None (SQLite is built-in) |
| `celery` | `CeleryTaskBackend` | `pulice[celery]` installed, Redis/RabbitMQ running |

### 5.2 Backend Factory

Add to `src/pulice/tasks.py`:

```python
def get_task_backend() -> TaskBackend:
    backend_type = os.getenv('PULICE_TASK_BACKEND', 'huey')

    if backend_type == 'huey':
        huey_instance = create_huey_instance()
        return HueyTaskBackend(huey_instance)

    if backend_type == 'celery':
        try:
            from pulice.celery_backend import create_celery_backend
        except ImportError:
            raise ImportError(
                "Celery backend requires 'pulice[celery]'. "
                "Install with: pip install pulice[celery]"
            )
        return create_celery_backend()

    raise ValueError(f"Unknown task backend: {backend_type!r}. Use 'huey' or 'celery'.")
```

---

## 6. FastAPI HTTP API

### 6.1 Dependencies

Add to `pyproject.toml`:

```toml
dependencies = [
    # ... existing ...
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
]
```

### 6.2 API Module Structure

```
src/pulice/
├── api/
│   ├── __init__.py          # FastAPI app factory
│   ├── models.py            # Pydantic request/response models
│   ├── routes_tenants.py    # Tenant CRUD endpoints
│   ├── routes_stacks.py     # Stack operation endpoints
│   └── routes_tasks.py      # Task status/cancel/retry endpoints
```

### 6.3 API Application Factory

In `src/pulice/api/__init__.py`:

```python
from fastapi import FastAPI
from pulice.api.routes_tenants import router as tenant_router
from pulice.api.routes_stacks import router as stack_router
from pulice.api.routes_tasks import router as task_router


def create_api() -> FastAPI:
    app = FastAPI(title='Pulice API', version='0.1.0')
    app.include_router(tenant_router, prefix='/tenants', tags=['tenants'])
    app.include_router(stack_router, prefix='/stacks', tags=['stacks'])
    app.include_router(task_router, prefix='/tasks', tags=['tasks'])
    return app
```

### 6.4 Request/Response Models

In `src/pulice/api/models.py`. All models use Pydantic:

```python
from pydantic import BaseModel, Field


# --- Tenant models ---

class TenantCreate(BaseModel):
    name: str = Field(..., description='Unique tenant name.')

class TenantResponse(BaseModel):
    id: str
    name: str
    created_at: str


# --- Stack operation models ---

class StackOperationRequest(BaseModel):
    component_class: str = Field(
        ...,
        description='Importable dotted path to the ManagedComponent subclass.',
    )
    operation: str = Field(
        ...,
        description='Operation to perform: create, read, update, delete, refresh, status, export, import.',
    )
    tenant: str = Field(..., description='Tenant name.')
    passphrase: str = Field(..., description='Stack passphrase.')
    args: dict = Field(default_factory=dict, description='Resource arguments (model_dump).')
    stack_reference: str | None = Field(
        None, description='Stack reference ID (required for non-create ops).',
    )
    input_file: str | None = Field(
        None, description='Path to import file (for import operation).',
    )
    output_file: str | None = Field(
        None, description='Path to export file (for export operation).',
    )

class StackOperationResponse(BaseModel):
    task_id: str
    status: str  # TaskStatus value


# --- Task models ---

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: dict | None = None
    error: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None

class TaskCancelResponse(BaseModel):
    task_id: str
    cancelled: bool

class TaskRetryResponse(BaseModel):
    old_task_id: str
    new_task_id: str
    status: str
```

### 6.5 Tenant Endpoints

In `src/pulice/api/routes_tenants.py`:

| Method | Path | Description | Status Code |
|---|---|---|---|
| `POST` | `/tenants` | Create a tenant | 201 |
| `GET` | `/tenants` | List all tenants | 200 |
| `GET` | `/tenants/{name}` | Get a single tenant | 200 |
| `DELETE` | `/tenants/{name}` | Delete a tenant (must have no stacks) | 204 |

These call `SqliteBackendStorage` directly (synchronous, fast, no task queue).

```python
from fastapi import APIRouter, HTTPException
from pulice.api.models import TenantCreate, TenantResponse

router = APIRouter()

@router.post('', status_code=201, response_model=TenantResponse)
def create_tenant(body: TenantCreate):
    storage = _get_storage()
    try:
        tenant = storage.create_tenant(body.name)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return TenantResponse(id=tenant.id, name=tenant.name, created_at=tenant.created_at)
```

### 6.6 Stack Operation Endpoints

In `src/pulice/api/routes_stacks.py`:

| Method | Path | Description | Status Code |
|---|---|---|---|
| `POST` | `/stacks/operations` | Submit a stack operation | 202 (Accepted) |
| `GET` | `/stacks` | List stacks (filtered by tenant, component) | 200 |

The `POST /stacks/operations` endpoint performs synchronous validation, then submits the task:

```python
@router.post('/operations', status_code=202, response_model=StackOperationResponse)
async def submit_operation(body: StackOperationRequest):
    # 1. Validate tenant exists
    storage = _get_storage()
    try:
        tenant = storage.get_tenant(body.tenant)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Tenant '{body.tenant}' not found.")

    # 2. Validate operation name
    valid_ops = {'create', 'read', 'update', 'delete', 'refresh', 'status', 'export', 'import'}
    if body.operation not in valid_ops:
        raise HTTPException(status_code=400, detail=f"Invalid operation '{body.operation}'.")

    # 3. Validate stack_reference is provided for non-create ops
    if body.operation != 'create' and not body.stack_reference:
        raise HTTPException(status_code=400, detail='stack_reference required for this operation.')

    # 4. Validate component_class is importable
    try:
        _resolve_component_class(body.component_class)
    except (ImportError, AttributeError) as e:
        raise HTTPException(status_code=400, detail=f"Cannot resolve component: {e}")

    # 5. Submit to task backend
    backend = get_task_backend()
    task_id = backend.submit(
        task_name=f'stack.{body.operation}',
        kwargs={
            'component_class': body.component_class,
            'operation': body.operation,
            'tenant_name': body.tenant,
            'passphrase': body.passphrase,
            'args': body.args,
            'stack_reference': body.stack_reference,
            'state_dir': os.getenv('PULICE_STATE_DIR'),
            'backend_url': os.getenv('PULICE_PULUMI_BACKEND_URL'),
        },
    )
    return StackOperationResponse(task_id=task_id, status=TaskStatus.PENDING.value)
```

`GET /stacks` calls `SqliteBackendStorage.list_stacks()` directly (no task queue):

```python
@router.get('', response_model=list[StackSummary])
def list_stacks(tenant: str, component: str | None = None):
    storage = _get_storage()
    tenant_obj = storage.get_tenant(tenant)
    return storage.list_stacks(tenant_id=tenant_obj.id, component_name=component)
```

### 6.7 Task Endpoints

In `src/pulice/api/routes_tasks.py`:

| Method | Path | Description | Status Code |
|---|---|---|---|
| `GET` | `/tasks/{task_id}` | Get task status and result | 200 |
| `POST` | `/tasks/{task_id}/cancel` | Cancel a task | 200 |
| `POST` | `/tasks/{task_id}/retry` | Retry a failed task | 202 |

```python
@router.get('/{task_id}', response_model=TaskStatusResponse)
def get_task_status(task_id: str):
    backend = get_task_backend()
    result = backend.get_status(task_id)
    return TaskStatusResponse(
        task_id=result.task_id,
        status=result.status.value,
        result=result.result,
        error=result.error,
        created_at=result.created_at,
        started_at=result.started_at,
        completed_at=result.completed_at,
    )

@router.post('/{task_id}/cancel', response_model=TaskCancelResponse)
def cancel_task(task_id: str):
    backend = get_task_backend()
    cancelled = backend.cancel(task_id)
    return TaskCancelResponse(task_id=task_id, cancelled=cancelled)

@router.post('/{task_id}/retry', status_code=202, response_model=TaskRetryResponse)
def retry_task(task_id: str):
    backend = get_task_backend()
    old_result = backend.get_status(task_id)
    if old_result.status != TaskStatus.FAILED:
        raise HTTPException(status_code=400, detail='Only failed tasks can be retried.')
    new_task_id = backend.retry(task_id)
    return TaskRetryResponse(
        old_task_id=task_id,
        new_task_id=new_task_id,
        status=TaskStatus.PENDING.value,
    )
```

---

## 7. Worker Process

### 7.1 Worker Entry Point

For Huey, the worker is a standard Huey consumer. Add a helper in `src/pulice/worker.py`:

```python
"""Pulice task worker entry point."""

from pulice.tasks import create_huey_instance

# The Huey instance must be module-level for the consumer to discover it.
huey = create_huey_instance()

# Import task definitions so they register with the huey instance.
import pulice.task_definitions  # noqa: F401
```

Start with: `huey_consumer pulice.worker.huey -w 2 -k process`

- `-w 2`: Two worker processes (tune per machine).
- `-k process`: Process-based workers (required since Pulumi SDK is not thread-safe).

### 7.2 Worker for Celery

For Celery: `celery -A pulice.celery_backend worker --concurrency=2 --pool=prefork`

### 7.3 API Server Entry Point

Serve with uvicorn:

```bash
uvicorn pulice.api:create_api --factory --host 0.0.0.0 --port 8000
```

Or programmatically:

```python
import uvicorn
from pulice.api import create_api

uvicorn.run(create_api(), host='0.0.0.0', port=8000)
```

---

## 8. Task Execution Flow

### 8.1 Create Operation (end-to-end)

```
1. Client  ->  POST /stacks/operations
               { component_class: "app.Demo", operation: "create",
                 tenant: "acme", passphrase: "secret",
                 args: { name: "my-db", region: "eu-west-1" } }

2. API     ->  Validates tenant exists, component class importable.
               Submits task via TaskBackend.submit().
               Returns 202 { task_id: "abc123", status: "pending" }

3. Worker  ->  Picks up task from queue.
               Resolves component class: importlib -> app.Demo
               Resolves tenant: SqliteBackendStorage.get_tenant("acme")
               Generates stack reference UUID.
               Builds stack name: "{tenant_id}-demo-{uuid}"
               Ensures workdir via StackOperations.ensure_stack_workspace()
               Hashes passphrase -> PassphraseHasher.hash()
               Acquires StackLock(stack_name, "create")
               Calls StackOperations.create_or_update_stack(
                   stack_name, project_name, workdir, program, env_vars)
               Saves stack reference via StackOperations.save_stack_reference()
               Saves passphrase hash via SqliteBackendStorage.save_passphrase_hash()
               Releases StackLock.
               Returns { stack_reference: "uuid-hex", status: "success" }

4. Client  ->  GET /tasks/abc123
               Returns { task_id: "abc123", status: "success",
                         result: { stack_reference: "uuid-hex" } }
```

### 8.2 Cancel Flow

```
1. Client  ->  POST /tasks/abc123/cancel
2. Backend ->  Huey: huey.revoke_by_id("abc123")
               Celery: app.control.revoke("abc123", terminate=True)
3. Worker  ->  If task is pending: removed from queue.
               If task is running: Huey marks for skip on next check;
               Celery sends SIGTERM.
4. Client  ->  Returns { task_id: "abc123", cancelled: true }
```

**Limitation:** Huey's revocation is advisory -- a running task will complete its current step before checking the revocation flag. Pulumi operations are not interruptible mid-execution. The task will be marked cancelled but the underlying Pulumi process may continue until its current resource operation finishes. This is documented behavior and acceptable for infrastructure operations.

### 8.3 Retry Flow

```
1. Client  ->  POST /tasks/abc123/retry
2. API     ->  Validates task abc123 is in FAILED state.
               Retrieves original kwargs from task storage.
               Submits a new task with the same kwargs.
               Returns 202 { old_task_id: "abc123", new_task_id: "def456",
                              status: "pending" }
3. Worker  ->  Executes the new task normally.
```

---

## 9. Changes to Existing Code

### 9.1 New Files

| File | Description |
|---|---|
| `src/pulice/tasks.py` | `TaskBackend` protocol, `TaskStatus` enum, `TaskResult` dataclass, `HueyTaskBackend`, backend factory, Huey instance factory. |
| `src/pulice/task_definitions.py` | Huey `@task`-decorated functions that execute stack operations. |
| `src/pulice/celery_backend.py` | `CeleryTaskBackend`, Celery app factory, Celery task definitions. |
| `src/pulice/worker.py` | Worker entry point (Huey consumer). |
| `src/pulice/api/__init__.py` | FastAPI app factory. |
| `src/pulice/api/models.py` | Pydantic request/response models. |
| `src/pulice/api/routes_tenants.py` | Tenant CRUD endpoints. |
| `src/pulice/api/routes_stacks.py` | Stack operation submission + listing. |
| `src/pulice/api/routes_tasks.py` | Task status, cancel, retry endpoints. |

### 9.2 Modified Files

| File | Change |
|---|---|
| `src/pulice/__init__.py` | Export `TaskBackend`, `TaskStatus`, `TaskResult` in `__all__`. |
| `src/pulice/stack.py` | Expose `SqliteBackendStorage` instance from `StackOperations` as a public property (`storage`) for use by task definitions. No logic changes. |
| `pyproject.toml` | Add `huey>=2.5.0`, `fastapi>=0.115.0`, `uvicorn[standard]>=0.30.0` to `dependencies`. Add `celery = ["celery[redis]>=5.4.0"]` to `[project.optional-dependencies]`. |

### 9.3 Files NOT Modified

- `src/pulice/app.py` -- CLI is unchanged.
- `src/pulice/registry.py` -- CLI registration is unchanged.
- `src/pulice/base.py` -- Component/args definitions are unchanged.

---

## 10. Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PULICE_TASK_BACKEND` | `huey` | Task backend selection: `huey` or `celery`. |
| `PULICE_STATE_DIR` | `{tempdir}/pulice-state` | Root directory for all state (existing). |
| `PULICE_PULUMI_BACKEND_URL` | `file://{workdir}/.pulumi-state` | Pulumi backend URL (existing). |
| `PULICE_CELERY_BROKER_URL` | `redis://localhost:6379/0` | Celery broker URL (only when backend=celery). |
| `PULICE_CELERY_RESULT_BACKEND` | `redis://localhost:6379/1` | Celery result backend (only when backend=celery). |
| `PULICE_API_HOST` | `0.0.0.0` | API server bind host. |
| `PULICE_API_PORT` | `8000` | API server bind port. |

---

## 11. Testing Requirements

### 11.1 New Test Modules

| Test Module | Coverage Target |
|---|---|
| `tests/test_tasks.py` | `TaskBackend` protocol conformance for `HueyTaskBackend`. `submit()` returns a task ID. `get_status()` returns correct status through lifecycle. `cancel()` revokes pending tasks. `retry()` resubmits failed tasks with same kwargs. |
| `tests/test_task_definitions.py` | Task execution functions (mocking `StackOperations`). Verify each operation dispatches correctly. Verify passphrase validation runs before Pulumi calls. Verify `StackLock` is acquired for mutating ops. Verify component class resolution from dotted path. |
| `tests/test_api_tenants.py` | FastAPI test client. Tenant CRUD endpoints. 201 on create, 409 on duplicate, 204 on delete, 400 on delete with stacks. |
| `tests/test_api_stacks.py` | Stack operation submission. 202 on valid request. 404 on unknown tenant. 400 on invalid operation. 400 on missing stack_reference. Verify task is submitted to backend. |
| `tests/test_api_tasks.py` | Task status, cancel, retry endpoints. 200 on status. Cancel returns success. Retry fails for non-failed tasks. |
| `tests/test_celery_backend.py` | `CeleryTaskBackend` protocol conformance (mocking Celery app). |

### 11.2 Key Test Scenarios

1. **End-to-end create via API:** Submit create, poll until success, verify stack reference in result.
2. **Task failure propagation:** Submit with bad component class, verify task fails with clear error.
3. **Passphrase validation in worker:** Submit update with wrong passphrase, verify task fails before Pulumi call.
4. **Cancel pending task:** Submit, immediately cancel, verify status is cancelled.
5. **Retry failed task:** Submit task that fails, retry, verify new task succeeds.
6. **Backend swap:** Run same test with both `HueyTaskBackend` and `CeleryTaskBackend` (via parametrize).
7. **Concurrent API requests:** Submit multiple operations for different stacks, verify they execute in parallel on the worker.
8. **Component class resolution:** Verify `_resolve_component_class()` handles valid paths, missing modules, and missing classes correctly.

---

## 12. Implementation Order

1. **TaskBackend protocol + TaskStatus + TaskResult** -- Define the abstraction in `tasks.py`. No implementation yet, just the protocol and data types. Tests for protocol structure.
2. **HueyTaskBackend** -- Implement Huey-backed backend with `SqliteHuey`. Task submission, status polling, cancel, retry. Tests with actual Huey instance (immediate mode for testing).
3. **Task definitions** -- Implement the generic `execute_stack_operation` task function. Component class resolution, tenant/passphrase validation, operation dispatch to `StackOperations`. Tests mocking `StackOperations`.
4. **FastAPI app + tenant endpoints** -- App factory, tenant CRUD routes. Tests with FastAPI test client.
5. **Stack operation endpoints** -- `POST /stacks/operations`, `GET /stacks`. Validation logic, task submission. Tests.
6. **Task endpoints** -- `GET /tasks/{id}`, cancel, retry. Tests.
7. **CeleryTaskBackend** -- Implement Celery-backed backend behind the same protocol. Tests mocking Celery app.
8. **Worker entry point** -- `pulice.worker` module for Huey consumer. Documentation for starting API + worker.

---

## 13. Non-Goals

- CLI changes (CLI remains synchronous, no `--async` flag).
- Task output/log streaming (Pulumi `on_output` capture for async tasks).
- API authentication and authorization.
- WebSocket or SSE for real-time task status updates.
- Task scheduling (cron-like recurring operations).
- Task priority queues.
- Distributed state (SQLite remains single-machine; distributed deployments must use shared filesystem or swap to a shared DB).
