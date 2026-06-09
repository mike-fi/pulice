"""Tests for Pulice API stack operation endpoints."""

from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from pulice.api import create_api
from pulice.api.routes_stacks import set_task_backend
from pulice.api.routes_tenants import set_storage
from pulice.core.stack import SqliteBackendStorage


@pytest.fixture()
def storage(tmp_path: Path) -> SqliteBackendStorage:
    s = SqliteBackendStorage(root_dir=str(tmp_path))
    s.create_tenant('acme')
    return s


@pytest.fixture()
def mock_backend():
    backend = MagicMock()
    backend.submit.return_value = 'task-abc123'
    return backend


@pytest.fixture()
def client(storage: SqliteBackendStorage, mock_backend: MagicMock):
    set_storage(storage)
    set_task_backend(mock_backend)
    app = create_api()
    with TestClient(app) as c:
        yield c
    set_storage(None)  # type: ignore[arg-type]
    set_task_backend(None)


class TestSubmitOperation:
    def test_valid_create_returns_202(self, client: TestClient, mock_backend: MagicMock):
        resp = client.post(
            '/stacks/operations',
            json={
                'component_class': 'tests.test_task_definitions.DemoComponent',
                'operation': 'create',
                'tenant': 'acme',
                'passphrase': 'secret',
                'args': {'name': 'my-stack'},
            },
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data['task_id'] == 'task-abc123'
        assert data['status'] == 'pending'
        mock_backend.submit.assert_called_once()

    def test_unknown_tenant_404(self, client: TestClient):
        resp = client.post(
            '/stacks/operations',
            json={
                'component_class': 'tests.test_task_definitions.DemoComponent',
                'operation': 'create',
                'tenant': 'nonexistent',
                'passphrase': 'secret',
                'args': {},
            },
        )
        assert resp.status_code == 404

    def test_invalid_operation_400(self, client: TestClient):
        resp = client.post(
            '/stacks/operations',
            json={
                'component_class': 'tests.test_task_definitions.DemoComponent',
                'operation': 'invalid_op',
                'tenant': 'acme',
                'passphrase': 'secret',
                'args': {},
            },
        )
        assert resp.status_code == 400
        assert 'Invalid operation' in resp.json()['detail']

    def test_missing_stack_reference_400(self, client: TestClient):
        resp = client.post(
            '/stacks/operations',
            json={
                'component_class': 'tests.test_task_definitions.DemoComponent',
                'operation': 'update',
                'tenant': 'acme',
                'passphrase': 'secret',
                'args': {},
                'stack_reference': None,
            },
        )
        assert resp.status_code == 400
        assert 'stack_reference required' in resp.json()['detail']

    def test_bad_component_class_400(self, client: TestClient):
        resp = client.post(
            '/stacks/operations',
            json={
                'component_class': 'nonexistent.module.Class',
                'operation': 'create',
                'tenant': 'acme',
                'passphrase': 'secret',
                'args': {},
            },
        )
        assert resp.status_code == 400
        assert 'Cannot resolve component' in resp.json()['detail']

    def test_submit_kwargs_passed_correctly(self, client: TestClient, mock_backend: MagicMock):
        client.post(
            '/stacks/operations',
            json={
                'component_class': 'tests.test_task_definitions.DemoComponent',
                'operation': 'delete',
                'tenant': 'acme',
                'passphrase': 'secret',
                'args': {},
                'stack_reference': 'ref-123',
            },
        )
        call_kwargs = mock_backend.submit.call_args
        submitted_kwargs = (
            call_kwargs.kwargs.get('kwargs') or call_kwargs[1].get('kwargs') or call_kwargs[0][1]
        )
        assert submitted_kwargs['operation'] == 'delete'
        assert submitted_kwargs['tenant_name'] == 'acme'
        assert submitted_kwargs['stack_reference'] == 'ref-123'


class TestListStacks:
    def test_list_stacks_200(self, client: TestClient, storage: SqliteBackendStorage):
        tenant = storage.get_tenant('acme')
        storage.ensure_stack_dir('acme-stack-1', tenant_id=tenant.id)
        resp = client.get('/stacks', params={'tenant': 'acme'})
        assert resp.status_code == 200
        names = [s['stack_name'] for s in resp.json()]
        assert 'acme-stack-1' in names

    def test_list_stacks_unknown_tenant_404(self, client: TestClient):
        resp = client.get('/stacks', params={'tenant': 'ghost'})
        assert resp.status_code == 404

    def test_list_stacks_with_component_filter(
        self, client: TestClient, storage: SqliteBackendStorage
    ):
        tenant = storage.get_tenant('acme')
        storage.ensure_stack_dir('demo-abc', tenant_id=tenant.id)
        storage.ensure_stack_dir('other-xyz', tenant_id=tenant.id)
        resp = client.get('/stacks', params={'tenant': 'acme', 'component': 'demo'})
        names = [s['stack_name'] for s in resp.json()]
        assert 'demo-abc' in names
        assert 'other-xyz' not in names
