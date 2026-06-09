"""Base classes for pulice component resources and their arguments.

``ComponentArgs``
    Pydantic model base for all resource inputs.  The ``name`` field is
    mandatory for every resource so consumers always have a stable identifier.
    Subclasses add resource-specific fields validated before any cloud calls
    are made.

``ManagedComponent``
    ``pulumi.ComponentResource`` base class that pairs a Pulumi resource with
    its ``args_model`` class variable.  Front-ends (CLI, API, ...) introspect
    ``args_model`` to derive input schemas automatically.
"""

from __future__ import annotations
import pulumi
from pydantic import BaseModel, ConfigDict, Field
from typing import ClassVar


class ComponentArgs(BaseModel):
    """Base class for all pulice component argument models.

    Every subclass automatically gets a required ``name`` field that acts as
    both the Pulumi logical resource name and the human-readable identifier.

    Add resource-specific fields using Pydantic ``Field`` annotations.
    """

    name: str = Field(..., description='Unique logical name for the resource.')

    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True,
    )


class ManagedComponent(pulumi.ComponentResource):
    """Base class for all pulice-managed Pulumi component resources.

    Subclasses must:

    1. Set ``args_model`` to a :class:`ComponentArgs` subclass.
    2. Accept ``(name, args, opts=None)`` in ``__init__`` and call::

           super().__init__('<type-token>', name, {}, opts)
    """

    args_model: ClassVar[type[ComponentArgs]]
