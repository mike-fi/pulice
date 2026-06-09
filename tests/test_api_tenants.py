"""Tests for Pulice API tenant endpoints."""

from __future__ import annotations
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from pulice.api import create_api
from pulice.api.routes_tenants import set_storage
from pulice.core.stack import SqliteBackendStorage


@pytest.fixture()
def client(tmp_path: Path):
    storage = SqliteBackendStorage(root_dir=str(tmp_path))
    set_storage(storage)
    app = create_api()
    with TestClient(app) as c:
        yield c
    set_storage(None)  # type: ignore[arg-type]


class TestCreateTenant:
    def test_create_tenant_201(self, client: TestClient):
        resp = client.post('/tenants', json={'name': 'acme'})
        assert resp.status_code == 201
        data = resp.json()
        assert data['name'] == 'acme'
        assert 'id' in data
        assert 'created_at' in data

    def test_create_duplicate_409(self, client: TestClient):
        client.post('/tenants', json={'name': 'acme'})
        resp = client.post('/tenants', json={'name': 'acme'})
        assert resp.status_code == 409


class TestListTenants:
    def test_list_includes_default(self, client: TestClient):
        resp = client.get('/tenants')
        assert resp.status_code == 200
        names = [t['name'] for t in resp.json()]
        assert 'default' in names

    def test_list_after_create(self, client: TestClient):
        client.post('/tenants', json={'name': 'alpha'})
        client.post('/tenants', json={'name': 'beta'})
        resp = client.get('/tenants')
        names = [t['name'] for t in resp.json()]
        assert 'alpha' in names
        assert 'beta' in names


class TestGetTenant:
    def test_get_existing(self, client: TestClient):
        client.post('/tenants', json={'name': 'acme'})
        resp = client.get('/tenants/acme')
        assert resp.status_code == 200
        assert resp.json()['name'] == 'acme'

    def test_get_nonexistent_404(self, client: TestClient):
        resp = client.get('/tenants/ghost')
        assert resp.status_code == 404


class TestDeleteTenant:
    def test_delete_204(self, client: TestClient):
        client.post('/tenants', json={'name': 'disposable'})
        resp = client.delete('/tenants/disposable')
        assert resp.status_code == 204

    def test_delete_nonexistent_404(self, client: TestClient):
        resp = client.delete('/tenants/ghost')
        assert resp.status_code == 404

    def test_delete_with_stacks_400(self, client: TestClient, tmp_path: Path):
        client.post('/tenants', json={'name': 'busy'})
        # Manually add a stack to this tenant
        from pulice.api.routes_tenants import get_storage

        storage = get_storage()
        tenant = storage.get_tenant('busy')
        storage.ensure_stack_dir('busy-stack', tenant_id=tenant.id)
        resp = client.delete('/tenants/busy')
        assert resp.status_code == 400
        assert 'still has' in resp.json()['detail']
