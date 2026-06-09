"""Shared helpers for managed-component lifecycle operations.

These are framework-agnostic building blocks reused by both the CLI and
(future) API front-ends: stack context resolution, Pulumi program
construction, and per-operation request model generation.
"""

from __future__ import annotations
import importlib
import uuid
from dataclasses import dataclass
from pydantic import BaseModel, Field, create_model
from pulice.core.base import ManagedComponent
from typing import Any, cast


def resolve_component_class(dotted_path: str) -> type[ManagedComponent]:
    """Import and return a ManagedComponent subclass from a dotted path."""
    module_path, class_name = dotted_path.rsplit('.', 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


@dataclass(frozen=True)
class ManagedStackContext:
    stack_reference: str
    stack_name: str
    project_name: str
    workdir: str


def resolve_managed_stack_context(
    stack_ops: Any,
    component_name: str,
    args: Any,
    operation: str,
    tenant_id: str = '',
) -> ManagedStackContext:
    """Resolve workspace and naming for a managed-component operation."""
    if operation == 'create':
        stack_reference = uuid.uuid4().hex
        if tenant_id:
            stack_name = f'{tenant_id}-{component_name}-{stack_reference}'
            project_name = f'pulice-{tenant_id}-{component_name}'
        else:
            stack_name = f'{component_name}-{stack_reference}'
            project_name = f'pulice-{component_name}'
        workdir = stack_ops.ensure_stack_workspace(stack_name)
        return ManagedStackContext(
            stack_reference=stack_reference,
            stack_name=stack_name,
            project_name=project_name,
            workdir=workdir,
        )

    stack_reference = getattr(args, 'stack_reference')
    reference = stack_ops.get_stack_reference(
        stack_reference,
        expected_component_name=component_name,
    )
    return ManagedStackContext(
        stack_reference=stack_reference,
        stack_name=reference.stack_name,
        project_name=reference.project_name,
        workdir=reference.workdir,
    )


def build_managed_component_args(
    component_cls: type[ManagedComponent],
    args: Any,
) -> Any:
    """Strip transport fields and validate through the component's args_model."""
    raw = args.model_dump() if hasattr(args, 'model_dump') else dict(args)
    raw.pop('stack_reference', None)
    raw.pop('passphrase', None)
    raw.pop('tenant', None)
    raw.pop('output', None)
    raw.pop('input', None)
    model = component_cls.args_model
    return model(**raw)  # pyrefly: ignore


def build_managed_program(
    component_cls: type[ManagedComponent],
    component_name: str,
    args: Any,
) -> Any:
    """Return a zero-arg Pulumi inline program closure."""

    def _pulumi_program() -> None:
        component_args = build_managed_component_args(component_cls, args)
        resource_name = getattr(component_args, 'name', component_name)
        component_factory = cast(Any, component_cls)
        try:
            component_factory(resource_name, component_args)
        except TypeError:
            component_factory(resource_name, component_args, None)

    return _pulumi_program


def managed_component_operation_model(
    component_cls: type[ManagedComponent],
    operation: str,
) -> type[BaseModel]:
    """Build a per-operation Pydantic model (adds passphrase / stack_reference / tenant)."""
    base_model = cast(type[BaseModel], component_cls.args_model)

    tenant_field = (
        str | None,
        Field(None, description='Tenant name. Prompted interactively if omitted.'),
    )
    passphrase_field = (
        str | None,
        Field(
            None,
            description='Passphrase for stack secrets encryption. Interactively if omitted.',
        ),
    )
    stack_ref_field = (str, Field(..., description='Stack reference id returned by create.'))

    if operation == 'create':
        return create_model(
            f'{base_model.__name__}Create',
            __base__=base_model,
            tenant=tenant_field,
            passphrase=passphrase_field,
        )

    if operation == 'update':
        return create_model(
            f'{base_model.__name__}Update',
            __base__=base_model,
            tenant=tenant_field,
            stack_reference=stack_ref_field,
            passphrase=passphrase_field,
        )

    if operation in ('read', 'delete', 'refresh', 'status'):
        return create_model(
            f'{base_model.__name__}{operation.capitalize()}',
            tenant=tenant_field,
            stack_reference=stack_ref_field,
            passphrase=passphrase_field,
        )

    if operation == 'export':
        return create_model(
            f'{base_model.__name__}Export',
            tenant=tenant_field,
            stack_reference=stack_ref_field,
            passphrase=passphrase_field,
            output=(str | None, Field(None, description='Output file path. Defaults to stdout.')),
        )

    if operation == 'import':
        return create_model(
            f'{base_model.__name__}Import',
            tenant=tenant_field,
            stack_reference=stack_ref_field,
            passphrase=passphrase_field,
            input=(str, Field(..., description='Path to the exported state JSON file.')),
        )

    if operation == 'list':
        return create_model(
            f'{base_model.__name__}List',
            tenant=tenant_field,
        )

    raise ValueError(f'Unsupported operation {operation!r}.')
