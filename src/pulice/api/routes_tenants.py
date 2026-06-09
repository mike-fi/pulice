"""Tenant CRUD endpoints."""

from __future__ import annotations
from fastapi import APIRouter, HTTPException, Response
from pulice.api.models import TenantCreate, TenantResponse
from pulice.core.stack import SqliteBackendStorage

router = APIRouter()

_storage: SqliteBackendStorage | None = None


def get_storage() -> SqliteBackendStorage:
    global _storage
    if _storage is None:
        import os

        _storage = SqliteBackendStorage(root_dir=os.getenv('PULICE_STATE_DIR'))
    return _storage


def set_storage(storage: SqliteBackendStorage) -> None:
    """Override storage for testing."""
    global _storage
    _storage = storage


@router.post('', status_code=201, response_model=TenantResponse)
def create_tenant(body: TenantCreate) -> TenantResponse:
    storage = get_storage()
    try:
        tenant = storage.create_tenant(body.name)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return TenantResponse(id=tenant.id, name=tenant.name, created_at=tenant.created_at)


@router.get('', response_model=list[TenantResponse])
def list_tenants() -> list[TenantResponse]:
    storage = get_storage()
    tenants = storage.list_tenants()
    return [TenantResponse(id=t.id, name=t.name, created_at=t.created_at) for t in tenants]


@router.get('/{name}', response_model=TenantResponse)
def get_tenant(name: str) -> TenantResponse:
    storage = get_storage()
    try:
        tenant = storage.get_tenant(name)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Tenant '{name}' not found.")
    return TenantResponse(id=tenant.id, name=tenant.name, created_at=tenant.created_at)


@router.delete('/{name}', status_code=204)
def delete_tenant(name: str) -> Response:
    storage = get_storage()
    try:
        storage.delete_tenant(name)
    except ValueError as e:
        detail = str(e)
        if 'not found' in detail:
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)
    return Response(status_code=204)
