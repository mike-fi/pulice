"""Task execution logic for Huey/Celery workers.

The ``execute_stack_operation`` function is the single entry point for all
async stack operations.  It resolves the component class, validates the
tenant and passphrase, acquires a lock for mutating operations, and
dispatches to the appropriate ``StackOperations`` method.
"""

from __future__ import annotations
import logging
import uuid
from pulice.core.managed import build_managed_program, resolve_component_class
from pulice.core.stack import (
    PassphraseHasher,
    SqliteBackendStorage,
    StackLock,
    StackOperations,
)

logger = logging.getLogger(__name__)

RETRYABLE_OPERATIONS = frozenset({'update', 'read', 'refresh', 'status', 'export'})
MUTATING_OPERATIONS = frozenset({'create', 'update', 'delete', 'refresh', 'import'})


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
    """Execute a stack lifecycle operation.

    This is the generic task function called by both Huey and Celery workers.
    """
    try:
        return _execute(
            component_class=component_class,
            operation=operation,
            tenant_name=tenant_name,
            passphrase=passphrase,
            args=args,
            stack_reference=stack_reference,
            state_dir=state_dir,
            backend_url=backend_url,
        )
    except Exception as exc:
        logger.exception('Task failed: %s', exc)
        return {'__error__': f'{type(exc).__name__}: {exc}'}


def _execute(
    component_class: str,
    operation: str,
    tenant_name: str,
    passphrase: str,
    args: dict,
    stack_reference: str | None,
    state_dir: str | None,
    backend_url: str | None,
) -> dict:
    # 1. Resolve component class
    component_cls = resolve_component_class(component_class)

    # 2. Instantiate StackOperations with state_dir
    storage = SqliteBackendStorage(root_dir=state_dir)
    stack_ops = StackOperations(storage=storage)

    # 3. Validate tenant
    tenant = storage.get_tenant(tenant_name)

    # 4. Build env vars
    env_vars = {'PULUMI_CONFIG_PASSPHRASE': passphrase}

    # 5. Determine stack context
    component_name = component_cls.__name__.lower()

    if operation == 'create':
        ref_id = uuid.uuid4().hex
        stack_name = f'{tenant.id}-{component_name}-{ref_id}'
        project_name = f'pulice-{tenant.id}-{component_name}'
        workdir = stack_ops.ensure_stack_workspace(stack_name)
    elif operation == 'list':
        # List doesn't need a stack reference
        return {
            'stacks': storage.list_stacks(
                tenant_id=tenant.id,
                component_name=component_name,
            ),
        }
    else:
        # Non-create ops require stack_reference
        if not stack_reference:
            raise ValueError(f'stack_reference is required for operation {operation!r}.')
        reference = stack_ops.get_stack_reference(
            stack_reference,
            expected_component_name=component_name,
        )
        ref_id = stack_reference
        stack_name = reference.stack_name
        project_name = reference.project_name
        workdir = reference.workdir

        # Validate passphrase against stored hash
        stored_hash = storage.get_passphrase_hash(stack_name)
        if stored_hash and not PassphraseHasher.verify(passphrase, stored_hash):
            raise ValueError(
                f"Invalid passphrase for stack '{stack_name}'. "
                'The passphrase does not match the one used at creation time.'
            )

    # 6. Build program closure
    program = build_managed_program(component_cls, component_name, args)

    # 7. Dispatch with optional lock
    def _dispatch() -> dict:
        if operation in ('create', 'update'):
            stack_ops.create_or_update_stack(
                stack_name=stack_name,
                project_name=project_name,
                program=program,
                workdir=workdir,
                env_vars=env_vars,
            )
            if operation == 'create':
                stack_ops.save_stack_reference(
                    reference_id=ref_id,
                    component_name=component_name,
                    stack_name=stack_name,
                    project_name=project_name,
                    workdir=workdir,
                    tenant_id=tenant.id,
                )
                ph = PassphraseHasher.hash(passphrase)
                storage.save_passphrase_hash(stack_name, ph)
                return {'stack_reference': ref_id, 'status': 'success'}
            return {'status': 'success'}

        if operation == 'read':
            stack_ops.preview_stack(
                stack_name=stack_name,
                project_name=project_name,
                program=lambda: None,
                workdir=workdir,
                env_vars=env_vars,
            )
            return {'status': 'success'}

        if operation == 'delete':
            stack_ops.destroy_stack(
                stack_name=stack_name,
                project_name=project_name,
                program=lambda: None,
                workdir=workdir,
                env_vars=env_vars,
            )
            return {'status': 'success'}

        if operation == 'refresh':
            stack_ops.refresh_stack(
                stack_name=stack_name,
                project_name=project_name,
                program=lambda: None,
                workdir=workdir,
                env_vars=env_vars,
            )
            return {'status': 'success'}

        if operation == 'status':
            status_info = stack_ops.stack_status(
                stack_name=stack_name,
                project_name=project_name,
                program=lambda: None,
                workdir=workdir,
                env_vars=env_vars,
            )
            return status_info

        if operation == 'export':
            deployment = stack_ops.export_stack(
                stack_name=stack_name,
                project_name=project_name,
                program=lambda: None,
                workdir=workdir,
                env_vars=env_vars,
            )
            return {'deployment': deployment}

        if operation == 'import':
            state = args.get('__import_state__', {})
            stack_ops.import_stack(
                stack_name=stack_name,
                project_name=project_name,
                program=lambda: None,
                workdir=workdir,
                state=state,
                env_vars=env_vars,
            )
            return {'status': 'success'}

        raise ValueError(f'Unsupported operation {operation!r}.')

    if operation in MUTATING_OPERATIONS:
        with StackLock(storage, stack_name, operation):
            return _dispatch()
    else:
        return _dispatch()
