"""Stack operation submission and listing endpoints."""

from __future__ import annotations
import os
from fastapi import APIRouter, HTTPException, Query
from pulice.api.models import StackOperationRequest, StackOperationResponse, StackSummary
from pulice.api.routes_tenants import get_storage
from pulice.core.managed import resolve_component_class
from pulice.core.tasks import TaskBackend, TaskStatus, get_task_backend

router = APIRouter()

VALID_OPERATIONS = frozenset(
    {
        'create',
        'read',
        'update',
        'delete',
        'refresh',
        'status',
        'export',
        'import',
        'list',
    }
)

_backend_override: TaskBackend | None = None


def set_task_backend(backend: TaskBackend | None) -> None:
    """Override task backend for testing."""
    global _backend_override
    _backend_override = backend


def _get_backend() -> TaskBackend:
    if _backend_override is not None:
        return _backend_override
    return get_task_backend()


@router.post('/operations', status_code=202, response_model=StackOperationResponse)
def submit_operation(body: StackOperationRequest) -> StackOperationResponse:
    storage = get_storage()

    # 1. Validate tenant exists
    try:
        storage.get_tenant(body.tenant)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Tenant '{body.tenant}' not found.")

    # 2. Validate operation name
    if body.operation not in VALID_OPERATIONS:
        raise HTTPException(status_code=400, detail=f"Invalid operation '{body.operation}'.")

    # 3. Validate stack_reference for non-create/non-list ops
    if body.operation not in ('create', 'list') and not body.stack_reference:
        raise HTTPException(status_code=400, detail='stack_reference required for this operation.')

    # 4. Validate component_class is importable
    try:
        resolve_component_class(body.component_class)
    except (ImportError, AttributeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f'Cannot resolve component: {e}')

    # 5. Submit to task backend
    backend = _get_backend()
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


@router.get('', response_model=list[StackSummary])
def list_stacks(
    tenant: str = Query(..., description='Tenant name.'),
    component: str | None = Query(None, description='Component name filter.'),
) -> list[StackSummary]:
    storage = get_storage()
    try:
        tenant_obj = storage.get_tenant(tenant)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant}' not found.")
    stacks = storage.list_stacks(tenant_id=tenant_obj.id, component_name=component)
    return [StackSummary(**s) for s in stacks]
