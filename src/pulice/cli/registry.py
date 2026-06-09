"""CLI component registry — Typer-specific registration helpers.

Provides registration helpers that **automatically** bind a controller's CRUD
operations to a Typer command group, deriving each option from the controller's
associated :class:`~pulice.core.base.ComponentArgs` Pydantic model.
"""

from __future__ import annotations
import inspect
import logging
import typer
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from typer import Typer
from pulice.core.base import ComponentArgs, ManagedComponent
from pulice.core.controllers import (
    CRUD_OPERATIONS,
    ComponentController,
    WorkspaceController,
)
from pulice.core.managed import (
    build_managed_program,
    managed_component_operation_model,
    resolve_managed_stack_context,
)
from pulice.core.stack import SqliteBackendStorage
from typing import Annotated, Any, cast

logger = logging.getLogger(__name__)

# Maps (group_name, controller_cls) -> group Typer app so multiple
# register_resource calls can share the same top-level group.
_group_registry: dict[tuple[str, type], Typer] = {}


# ---------------------------------------------------------------------------
# Typer option helpers
# ---------------------------------------------------------------------------


def _field_to_typer_option(field_name: str, field_info: FieldInfo) -> typer.models.OptionInfo:
    """Convert a Pydantic ``FieldInfo`` into a ``typer.Option``."""
    option_name = f'--{field_name.replace("_", "-")}'
    description: str = field_info.description or ''
    return typer.Option(
        option_name,
        help=description,
        show_default=not field_info.is_required(),
    )


def _build_command(
    model_cls: type[BaseModel],
    run: Any,
    operation: str,
    qualname: str,
) -> Any:
    """Build a Typer-compatible function whose signature mirrors *model_cls*.

    Pydantic validation runs before *run* is called, so invalid inputs surface
    as clear error messages rather than runtime failures.
    """
    import typing

    fields = model_cls.model_fields
    params: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {'return': None}

    # Required parameters first so inspect.Signature accepts the ordering.
    ordered_fields = [
        *(item for item in fields.items() if item[1].is_required()),
        *(item for item in fields.items() if not item[1].is_required()),
    ]

    for field_name, field_info in ordered_fields:
        option = _field_to_typer_option(field_name, field_info)
        raw = field_info.annotation or Any
        annotated = typing.Annotated[raw, option]
        annotations[field_name] = annotated

        if field_info.is_required():
            default_value = inspect.Parameter.empty
        elif field_info.default_factory is not None:
            default_value = field_info.default_factory()  # pyrefly: ignore
        else:
            default_value = field_info.default

        params.append(
            inspect.Parameter(
                name=field_name,
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=default_value,
                annotation=annotated,
            )
        )

    def _command(**kwargs: Any) -> None:
        try:
            args = model_cls(**kwargs)
        except Exception as exc:  # noqa: BLE001
            typer.echo(f'Input validation error:\n{exc}', err=True)
            raise typer.Exit(code=1) from exc
        run(args)

    _command.__name__ = operation
    _command.__qualname__ = qualname
    _command.__doc__ = f'{operation.capitalize()} the resource.'
    _command.__signature__ = inspect.Signature(params)  # type: ignore[assignment]
    _command.__annotations__ = annotations
    return _command


# ---------------------------------------------------------------------------
# Run helpers
# ---------------------------------------------------------------------------


def _make_run_resource(
    controller_cls: type[WorkspaceController],
    resource_cls: type[ManagedComponent],
    operation: str,
) -> Any:
    def _run(args: ComponentArgs) -> None:
        controller = controller_cls(resource_cls, args)
        _invoke_operation(controller, operation, controller_cls.__name__)

    return _run


def _make_run_component(
    controller_cls: type[ComponentController],
    operation: str,
) -> Any:
    def _run(args: ComponentArgs) -> None:
        controller = controller_cls(args)
        _invoke_operation(controller, operation, controller_cls.__name__)

    return _run


def _invoke_operation(target: Any, operation: str, target_name: str) -> None:
    try:
        getattr(target, operation)()
    except NotImplementedError:
        typer.echo(
            f"Operation '{operation}' is not implemented for {target_name}.",
            err=True,
        )
        raise typer.Exit(code=2) from None


def _prompt_tenant(storage: Any) -> str:  # pyrefly: ignore
    """Interactively prompt the user to select a tenant from available tenants."""
    tenants = storage.list_tenants()
    if not tenants:
        typer.echo(
            'Error: No tenants exist. Create one with: tenant create --name <name>', err=True
        )
        raise typer.Exit(code=1)  # pyrefly: ignore

    if len(tenants) == 1:
        typer.echo(f'Using tenant: {tenants[0].name}')
        return tenants[0].name

    typer.echo('Select a tenant:')
    for i, t in enumerate(tenants, 1):
        typer.echo(f'  [{i}] {t.name}')

    while True:
        choice = typer.prompt('Tenant number')
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(tenants):
                return tenants[idx].name
        except ValueError:
            pass
        typer.echo(f'Invalid choice. Enter a number between 1 and {len(tenants)}.', err=True)


def _prompt_passphrase() -> str:
    """Interactively prompt for a passphrase with masked input."""
    import getpass

    passphrase = getpass.getpass('Passphrase: ')
    if not passphrase:
        typer.echo('Error: Passphrase cannot be empty.', err=True)
        raise typer.Exit(code=1)
    return passphrase


def _make_run_managed_component(
    component_cls: type[ManagedComponent],
    operation: str,
) -> Any:
    def _run(args: Any) -> None:
        import json as _json
        from pulice.core.stack import (
            PassphraseHasher,
            StackLock,
            StackOperations,
        )

        stack_ops = StackOperations()
        storage = cast(SqliteBackendStorage, stack_ops.storage)
        component_name = component_cls.__name__.lower()

        # Resolve tenant — prompt interactively if not provided
        tenant_name = getattr(args, 'tenant', None)
        if not tenant_name:
            tenant_name = _prompt_tenant(storage)

        try:
            tenant = storage.get_tenant(tenant_name)
        except ValueError as e:
            typer.echo(f'Error: {e}', err=True)
            raise typer.Exit(code=1) from None

        # Handle list operation (no passphrase, no stack reference)
        if operation == 'list':
            refs = stack_ops._references.list(
                tenant_id=tenant.id,
                component_name=component_name,
            )
            if not refs:
                typer.echo('No stacks found.')
            else:
                for ref in refs:
                    typer.echo(f'{ref.stack_name}  ref={ref.id}')
            return

        # Resolve passphrase — prompt interactively if not provided
        passphrase = getattr(args, 'passphrase', None)
        if not passphrase:
            passphrase = _prompt_passphrase()
        env_vars = {'PULUMI_CONFIG_PASSPHRASE': passphrase}
        context = resolve_managed_stack_context(
            stack_ops,
            component_name,
            args,
            operation,
            tenant_id=tenant.id,
        )

        # Passphrase validation for non-create operations
        if operation != 'create':
            stored_hash = storage.get_passphrase_hash(context.stack_name)
            if stored_hash and not PassphraseHasher.verify(passphrase, stored_hash):
                typer.echo(
                    f"Error: Invalid passphrase for stack '{context.stack_name}'.",
                    err=True,
                )
                raise typer.Exit(code=1)

        program = build_managed_program(component_cls, component_name, args)
        noop_program = lambda: None  # noqa E731
        mutating_ops = frozenset({'create', 'update', 'delete', 'refresh', 'import'})

        # Persist the stack reference before running Pulumi so it's
        # recoverable even if the operation fails.
        if operation == 'create':
            stack_ops.save_stack_reference(
                reference_id=context.stack_reference,
                component_name=component_name,
                stack_name=context.stack_name,
                project_name=context.project_name,
                workdir=context.workdir,
                tenant_id=tenant.id,
            )
            ph = PassphraseHasher.hash(passphrase)
            storage.save_passphrase_hash(context.stack_name, ph)
            typer.echo(f'Stack reference: {context.stack_reference}')

        def _dispatch() -> None:
            if operation in ('create', 'update'):
                stack_ops.create_or_update_stack(
                    stack_name=context.stack_name,
                    project_name=context.project_name,
                    program=program,
                    workdir=context.workdir,
                    env_vars=env_vars,
                )

            elif operation == 'read':
                stack_ops.preview_stack(
                    stack_name=context.stack_name,
                    project_name=context.project_name,
                    program=noop_program,
                    workdir=context.workdir,
                    env_vars=env_vars,
                )

            elif operation == 'delete':
                stack_ops.destroy_stack(
                    stack_name=context.stack_name,
                    project_name=context.project_name,
                    program=noop_program,
                    workdir=context.workdir,
                    env_vars=env_vars,
                )
                stack_ops._references.delete(context.stack_reference)
                storage.delete_stack(context.stack_name)
                typer.echo(f'Stack {context.stack_reference} destroyed and removed.')

            elif operation == 'refresh':
                stack_ops.refresh_stack(
                    stack_name=context.stack_name,
                    project_name=context.project_name,
                    program=noop_program,
                    workdir=context.workdir,
                    env_vars=env_vars,
                )

            elif operation == 'status':
                status_info = stack_ops.stack_status(
                    stack_name=context.stack_name,
                    project_name=context.project_name,
                    program=noop_program,
                    workdir=context.workdir,
                    env_vars=env_vars,
                )
                for k, v in status_info.items():
                    typer.echo(f'{k}: {v}')

            elif operation == 'export':
                deployment = stack_ops.export_stack(
                    stack_name=context.stack_name,
                    project_name=context.project_name,
                    program=noop_program,
                    workdir=context.workdir,
                    env_vars=env_vars,
                )
                output_path = getattr(args, 'output', None)
                json_str = _json.dumps(deployment, indent=2)
                if output_path:
                    from pathlib import Path

                    Path(output_path).write_text(json_str, encoding='utf-8')
                    typer.echo(f'Exported to {output_path}')
                else:
                    typer.echo(json_str)

            elif operation == 'import':
                from pathlib import Path

                input_path = getattr(args, 'input')
                state = _json.loads(Path(input_path).read_text(encoding='utf-8'))
                stack_ops.import_stack(
                    stack_name=context.stack_name,
                    project_name=context.project_name,
                    program=noop_program,
                    workdir=context.workdir,
                    state=state,
                    env_vars=env_vars,
                )
                typer.echo('Import complete.')

            else:
                raise ValueError(f'Unsupported operation {operation!r}.')

        if operation in mutating_ops:
            with StackLock(storage, context.stack_name, operation):
                _dispatch()
        else:
            _dispatch()

    return _run


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------


def register_resource(
    app: Typer,
    resource_cls: type[ManagedComponent],
    controller_cls: type[WorkspaceController],
    *,
    group: str,
    name: str,
    group_help: str = '',
    operations: tuple[str, ...] = CRUD_OPERATIONS,
) -> Typer:
    """Register *resource_cls* as ``<group> <name> <op>`` commands."""
    if not hasattr(resource_cls, 'args_model'):
        raise AttributeError(f"{resource_cls.__name__} must define an 'args_model' class variable.")

    group_key = (group, controller_cls)
    if group_key not in _group_registry:
        group_app = Typer(name=group, help=group_help or f'Manage {group} resources.')
        app.add_typer(group_app, name=group)
        _group_registry[group_key] = group_app
    else:
        group_app = _group_registry[group_key]

    resource_app = Typer(name=name, help=f'Manage {name}.')
    group_app.add_typer(resource_app, name=name)

    model_cls: type[BaseModel] = resource_cls.args_model
    for operation in operations:
        cmd_fn = _build_command(
            model_cls=model_cls,
            run=_make_run_resource(controller_cls, resource_cls, operation),
            operation=operation,
            qualname=f'{controller_cls.__name__}.{resource_cls.__name__}.{operation}',
        )
        resource_app.command(operation)(cmd_fn)
        logger.debug("Registered '%s %s %s'.", group, name, operation)

    return resource_app


def register_component(
    app: Typer,
    component_or_controller_cls: type[ManagedComponent] | type[ComponentController],
    name: str,
    help: str = '',
    operations: tuple[str, ...] | None = None,
) -> Typer:
    """Register a component or controller as a flat command group on *app*."""
    if not hasattr(component_or_controller_cls, 'args_model'):
        raise AttributeError(
            f"{component_or_controller_cls.__name__} must define an 'args_model' class variable."
        )

    component_app = Typer(name=name, help=help or f'Manage {name} resources.')
    model_cls: type[BaseModel] = component_or_controller_cls.args_model

    is_controller = issubclass(component_or_controller_cls, ComponentController)
    is_component = issubclass(component_or_controller_cls, ManagedComponent)

    if not (is_controller or is_component):
        raise TypeError(
            f'Unsupported command target type {component_or_controller_cls.__name__!r}. '
            'Expected ComponentController or ManagedComponent subclass.'
        )

    if operations is None:
        operations = MANAGED_COMPONENT_OPERATIONS if is_component else CRUD_OPERATIONS

    for operation in operations:
        if is_controller:
            controller_cls = cast(type[ComponentController], component_or_controller_cls)
            run = _make_run_component(controller_cls, operation)
            qualname = f'{component_or_controller_cls.__name__}.{operation}'
            command_model = model_cls
        else:
            component_cls = cast(type[ManagedComponent], component_or_controller_cls)
            run = _make_run_managed_component(component_cls, operation)
            qualname = f'{component_or_controller_cls.__name__}.{operation}'
            command_model = managed_component_operation_model(component_cls, operation)

        cmd_fn = _build_command(
            model_cls=command_model,
            run=run,
            operation=operation,
            qualname=qualname,
        )
        component_app.command(operation)(cmd_fn)
        logger.debug("Registered command '%s %s'.", name, operation)

    app.add_typer(component_app, name=name)
    return component_app


# ---------------------------------------------------------------------------
# Tenant commands
# ---------------------------------------------------------------------------


MANAGED_COMPONENT_OPERATIONS: tuple[str, ...] = (
    'create',
    'read',
    'update',
    'delete',
    'refresh',
    'list',
    'status',
    'export',
    'import',
)


def register_admin_command(app: Typer) -> None:
    """Register ``pulice admin`` command to launch the TUI dashboard."""

    @app.command('admin')
    def admin(
        state_dir: Annotated[
            str | None,
            typer.Option('--state-dir', help='Path to state directory.'),
        ] = None,
        refresh: Annotated[
            int,
            typer.Option('--refresh', help='Auto-refresh interval in seconds (0 to disable).'),
        ] = 5,
    ) -> None:
        """Launch the admin dashboard."""
        try:
            from pulice.admin.app import PuliceAdmin
        except ImportError:
            typer.echo(
                "Admin TUI requires 'pulice[admin]'. Install with: pip install pulice[admin]"
            )
            raise typer.Exit(1)
        tui = PuliceAdmin(state_dir=state_dir, refresh_interval=refresh)
        tui.run()


def _tenant_storage() -> Any:
    import os
    from pulice.core.stack import SqliteBackendStorage

    return SqliteBackendStorage(root_dir=os.getenv('PULICE_STATE_DIR'))


def _exit_on_value_error(action: Any) -> Any:
    try:
        return action()
    except ValueError as e:
        typer.echo(f'Error: {e}', err=True)
        raise typer.Exit(code=1) from None


def register_tenant_commands(app: Typer) -> None:
    """Register ``pulice tenant create/list/delete`` commands."""
    tenant_app = Typer(name='tenant', help='Manage tenants.')

    @tenant_app.command('create')
    def tenant_create(
        name: Annotated[str, typer.Option('--name', help='Tenant name.')],
    ) -> None:
        """Create a new tenant."""
        storage = _tenant_storage()
        tenant = _exit_on_value_error(lambda: storage.create_tenant(name))
        typer.echo(f'Tenant created: {tenant.name} (id: {tenant.id})')

    @tenant_app.command('list')
    def tenant_list() -> None:
        """List all tenants."""
        storage = _tenant_storage()
        tenants = storage.list_tenants()
        if not tenants:
            typer.echo('No tenants found.')
            return
        for t in tenants:
            typer.echo(f'{t.name}  (id: {t.id}, created: {t.created_at})')

    @tenant_app.command('delete')
    def tenant_delete(
        name: Annotated[str, typer.Option('--name', help='Tenant name.')],
    ) -> None:
        """Delete a tenant (must have no stacks)."""
        storage = _tenant_storage()
        _exit_on_value_error(lambda: storage.delete_tenant(name))
        typer.echo(f'Tenant deleted: {name}')

    app.add_typer(tenant_app, name='tenant')
