"""Pydantic request/response models for the Pulice API."""

from __future__ import annotations
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
        description='Operation to perform: create, read, update, delete, refresh, status, export, import.',  # noqa E501
    )
    tenant: str = Field(..., description='Tenant name.')
    passphrase: str = Field(..., description='Stack passphrase.')
    args: dict = Field(default_factory=dict, description='Resource arguments (model_dump).')
    stack_reference: str | None = Field(
        None,
        description='Stack reference ID (required for non-create ops).',
    )
    input_file: str | None = Field(
        None,
        description='Path to import file (for import operation).',
    )
    output_file: str | None = Field(
        None,
        description='Path to export file (for export operation).',
    )


class StackOperationResponse(BaseModel):
    task_id: str
    status: str


class StackSummary(BaseModel):
    stack_name: str
    uuid: str
    path: str
    tenant_id: str
    created_at: str


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
