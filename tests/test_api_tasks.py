"""Tests for Pulice API task endpoints."""

from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from pulice.api import create_api
from pulice.api.routes_stacks import set_task_backend
from pulice.api.routes_tenants import set_storage
from pulice.core.stack import SqliteBackendStorage
from pulice.core.tasks import TaskResult, TaskStatus


@pytest.fixture()
def mock_backend():
    return MagicMock()


@pytest.fixture()
def client(tmp_path: Path, mock_backend: MagicMock):
    storage = SqliteBackendStorage(root_dir=str(tmp_path))
    set_storage(storage)
    set_task_backend(mock_backend)
    app = create_api()
    with TestClient(app) as c:
        yield c
    set_storage(None)  # type: ignore[arg-type]
    set_task_backend(None)


class TestGetTaskStatus:
    def test_pending_status(self, client: TestClient, mock_backend: MagicMock):
        mock_backend.get_status.return_value = TaskResult(
            task_id='t1',
            status=TaskStatus.PENDING,
        )
        resp = client.get('/tasks/t1')
        assert resp.status_code == 200
        data = resp.json()
        assert data['task_id'] == 't1'
        assert data['status'] == 'pending'

    def test_success_status_with_result(self, client: TestClient, mock_backend: MagicMock):
        mock_backend.get_status.return_value = TaskResult(
            task_id='t2',
            status=TaskStatus.SUCCESS,
            result={'stack_reference': 'abc'},
        )
        resp = client.get('/tasks/t2')
        assert resp.status_code == 200
        data = resp.json()
        assert data['status'] == 'success'
        assert data['result'] == {'stack_reference': 'abc'}

    def test_failed_status_with_error(self, client: TestClient, mock_backend: MagicMock):
        mock_backend.get_status.return_value = TaskResult(
            task_id='t3',
            status=TaskStatus.FAILED,
            error='ValueError: bad input',
        )
        resp = client.get('/tasks/t3')
        data = resp.json()
        assert data['status'] == 'failed'
        assert data['error'] == 'ValueError: bad input'


class TestCancelTask:
    def test_cancel_returns_success(self, client: TestClient, mock_backend: MagicMock):
        mock_backend.cancel.return_value = True
        resp = client.post('/tasks/t1/cancel')
        assert resp.status_code == 200
        data = resp.json()
        assert data['task_id'] == 't1'
        assert data['cancelled'] is True


class TestRetryTask:
    def test_retry_failed_task_202(self, client: TestClient, mock_backend: MagicMock):
        mock_backend.get_status.return_value = TaskResult(
            task_id='t1',
            status=TaskStatus.FAILED,
            error='boom',
        )
        mock_backend.retry.return_value = 'new-t1'
        resp = client.post('/tasks/t1/retry')
        assert resp.status_code == 202
        data = resp.json()
        assert data['old_task_id'] == 't1'
        assert data['new_task_id'] == 'new-t1'
        assert data['status'] == 'pending'

    def test_retry_non_failed_task_400(self, client: TestClient, mock_backend: MagicMock):
        mock_backend.get_status.return_value = TaskResult(
            task_id='t1',
            status=TaskStatus.SUCCESS,
        )
        resp = client.post('/tasks/t1/retry')
        assert resp.status_code == 400
        assert 'Only failed tasks' in resp.json()['detail']

    def test_retry_unknown_kwargs_400(self, client: TestClient, mock_backend: MagicMock):
        mock_backend.get_status.return_value = TaskResult(
            task_id='t1',
            status=TaskStatus.FAILED,
            error='boom',
        )
        mock_backend.retry.side_effect = ValueError('original kwargs not found')
        resp = client.post('/tasks/t1/retry')
        assert resp.status_code == 400
