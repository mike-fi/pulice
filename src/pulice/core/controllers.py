"""Framework-agnostic controller base classes.

``WorkspaceController``
    Pulumi Automation API controller — CRUD via stack up / preview / destroy.

``ComponentController``
    Simple controller for commands that do not use the Pulumi Automation API.
"""

from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from pulice.core.base import ComponentArgs, ManagedComponent
from typing import Any, ClassVar

logger = logging.getLogger(__name__)

CRUD_OPERATIONS: tuple[str, ...] = ('create', 'read', 'update', 'delete')


class WorkspaceController(ABC):
    """Generic controller that can provision any :class:`ManagedComponent`.

    A single subclass covers *all* resource types that share the same provider.
    Subclasses must implement :meth:`_make_provider`.
    """

    def __init__(
        self,
        resource_cls: type[ManagedComponent],
        args: ComponentArgs,
    ) -> None:
        from pulice.core.stack import StackOperations

        self._resource_cls = resource_cls
        self._args = args
        self._stack_ops = StackOperations()

    @abstractmethod
    def _make_provider(self) -> Any:
        """Return the provider instance for this workspace."""

    def _pulumi_program(self) -> None:
        # pyrefly: ignore
        self._resource_cls(
            f'{type(self).__name__.lower()}'
            f'-{self._resource_cls.__name__.lower()}'
            f'-{self._args.name}',
            args=self._args,  # pyrefly: ignore
            provider=self._make_provider(),  # pyrefly: ignore
        )

    def _stack_name(self) -> str:
        return (
            f'{type(self).__name__.lower()}-{self._resource_cls.__name__.lower()}-{self._args.name}'
        )

    def _project_name(self) -> str:
        return f'pulice-{self._resource_cls.__name__.lower()}'

    def _run_stack_action(self, action: str) -> None:
        stack_name = self._stack_name()
        project_name = self._project_name()
        workdir = self._stack_ops.ensure_stack_workspace(stack_name)

        if action == 'up':
            self._stack_ops.create_or_update_stack(
                stack_name=stack_name,
                project_name=project_name,
                program=self._pulumi_program,
                workdir=workdir,
            )
            return

        if action == 'preview':
            self._stack_ops.preview_stack(
                stack_name=stack_name,
                project_name=project_name,
                program=self._pulumi_program,
                workdir=workdir,
            )
            return

        if action == 'destroy':
            self._stack_ops.destroy_stack(
                stack_name=stack_name,
                project_name=project_name,
                program=self._pulumi_program,
                workdir=workdir,
            )
            return

        raise ValueError(f'Unsupported stack action {action!r}.')

    def create(self) -> None:
        logger.info('Creating %s: name=%s', self._resource_cls.__name__, self._args.name)
        self._run_stack_action('up')

    def read(self) -> None:
        logger.info('Reading %s: name=%s', self._resource_cls.__name__, self._args.name)
        self._run_stack_action('preview')

    def update(self) -> None:
        logger.info('Updating %s: name=%s', self._resource_cls.__name__, self._args.name)
        self._run_stack_action('up')

    def delete(self) -> None:
        logger.info('Deleting %s: name=%s', self._resource_cls.__name__, self._args.name)
        self._run_stack_action('destroy')


class ComponentController(ABC):
    """Simple controller for commands that do not use the Pulumi Automation API."""

    args_model: ClassVar[type[ComponentArgs]]

    def __init__(self, args: ComponentArgs) -> None:
        self._args = args

    def create(self) -> None:
        raise NotImplementedError(f"{type(self).__name__} does not implement 'create'.")

    def read(self) -> None:
        raise NotImplementedError(f"{type(self).__name__} does not implement 'read'.")

    def update(self) -> None:
        raise NotImplementedError(f"{type(self).__name__} does not implement 'update'.")

    def delete(self) -> None:
        raise NotImplementedError(f"{type(self).__name__} does not implement 'delete'.")
