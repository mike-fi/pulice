"""PuliceApp — the interface every front-end implementation must satisfy."""

from __future__ import annotations
from collections.abc import Sequence
from pulice.core.base import ManagedComponent
from pulice.core.controllers import (
    CRUD_OPERATIONS,
    ComponentController,
    WorkspaceController,
)
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PuliceApp(Protocol):
    """Interface for a pulice application backend.

    Any object satisfying this protocol can serve as the application shell
    that components and resources register themselves onto.

    * **register_resource** — bind a :class:`ManagedComponent` +
      :class:`WorkspaceController` pair as a grouped command / route tree.
    * **register_component** — bind a :class:`ManagedComponent` or
      :class:`ComponentController` as a flat command / route group.

    The instance must also be callable so it can act as an entry-point.
    """

    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...

    def register_resource(
        self,
        resource_cls: type[ManagedComponent],
        controller_cls: type[WorkspaceController],
        *,
        group: str,
        name: str,
        group_help: str = '',
        operations: tuple[str, ...] = CRUD_OPERATIONS,
    ) -> None: ...

    def register_component(
        self,
        component_cls: type[ManagedComponent] | type[ComponentController],
        name: str,
        *,
        help: str = '',
        operations: tuple[str, ...] | Sequence[str] = CRUD_OPERATIONS,
    ) -> None: ...
