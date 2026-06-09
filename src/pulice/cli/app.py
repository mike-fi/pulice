"""PuliceCLI — Typer-backed implementation of the PuliceApp protocol."""

from __future__ import annotations
from collections.abc import Sequence
from typer import Typer
from pulice.cli.registry import (
    register_admin_command,
    register_resource,
    register_tenant_commands,
)
from pulice.cli.registry import (
    register_component as registry_register_component,
)
from pulice.core.base import ManagedComponent
from pulice.core.controllers import (
    CRUD_OPERATIONS,
    ComponentController,
    WorkspaceController,
)
from typing import Any


class PuliceCLI:
    """Typer-backed implementation of :class:`PuliceApp`.

    Wraps a single :class:`~typer.Typer` instance and delegates registration
    to :mod:`pulice.cli.registry`.

    Parameters
    ----------
    app:
        A :class:`~typer.Typer` application instance.
    """

    def __init__(self, app: Typer) -> None:
        if not isinstance(app, Typer):
            raise TypeError(f'PuliceCLI only supports Typer apps, got {type(app)!r}.')
        self.app = app
        register_tenant_commands(self.app)
        register_admin_command(self.app)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Delegate to the underlying Typer app."""
        return self.app(*args, **kwargs)

    def register_resource(
        self,
        resource_cls: type[ManagedComponent],
        controller_cls: type[WorkspaceController],
        *,
        group: str,
        name: str,
        group_help: str = '',
        operations: tuple[str, ...] = CRUD_OPERATIONS,
    ) -> None:
        """Register *resource_cls* on the Typer app."""
        register_resource(
            self.app,
            resource_cls,
            controller_cls,
            group=group,
            name=name,
            group_help=group_help,
            operations=operations,
        )

    def register_component(
        self,
        component_cls: type[ManagedComponent] | type[ComponentController],
        name: str,
        *,
        help: str = '',
        operations: tuple[str, ...] | Sequence[str] | None = None,
    ) -> None:
        """Register *component_cls* on the Typer app."""
        registry_register_component(
            self.app,
            component_cls,
            name=name,
            help=help,
            operations=tuple(operations) if operations is not None else None,
        )
