"""Tests for pulice.core.celery_backend — CeleryTaskBackend (fully mocked)."""

from __future__ import annotations
from unittest.mock import MagicMock
import pytest
from pulice.core.celery_backend import CeleryTaskBackend
from pulice.core.tasks import TaskBackend, TaskStatus


@pytest.fixture()
def mock_celery_app():
    app = MagicMock()
    # Prevent actual task registration from failing
    app.task.return_value = lambda fn: fn
    return app


@pytest.fixture()
def backend(mock_celery_app: MagicMock) -> CeleryTaskBackend:
    return CeleryTaskBackend(mock_celery_app)


class TestProtocolConformance:
    def test_satisfies_task_backend_protocol(self, backend: CeleryTaskBackend):
        assert isinstance(backend, TaskBackend)


class TestSubmit:
    def test_submit_returns_task_id(self, backend: CeleryTaskBackend, mock_celery_app: MagicMock):
        mock_result = MagicMock()
        mock_result.id = 'celery-task-123'
        mock_celery_app.send_task.return_value = mock_result

        task_id = backend.submit('stack.create', {'operation': 'create'})

        assert task_id == 'celery-task-123'
        mock_celery_app.send_task.assert_called_once_with(
            'stack.operation',
            kwargs={'operation': 'create'},
        )


class TestGetStatus:
    def test_pending_state(self, backend: CeleryTaskBackend, mock_celery_app: MagicMock):
        mock_result = MagicMock()
        mock_result.state = 'PENDING'
        mock_celery_app.AsyncResult.return_value = mock_result

        result = backend.get_status('t1')
        assert result.status == TaskStatus.PENDING

    def test_started_state(self, backend: CeleryTaskBackend, mock_celery_app: MagicMock):
        mock_result = MagicMock()
        mock_result.state = 'STARTED'
        mock_celery_app.AsyncResult.return_value = mock_result

        result = backend.get_status('t1')
        assert result.status == TaskStatus.RUNNING

    def test_success_state(self, backend: CeleryTaskBackend, mock_celery_app: MagicMock):
        mock_result = MagicMock()
        mock_result.state = 'SUCCESS'
        mock_result.result = {'stack_reference': 'abc'}
        mock_celery_app.AsyncResult.return_value = mock_result

        result = backend.get_status('t1')
        assert result.status == TaskStatus.SUCCESS
        assert result.result == {'stack_reference': 'abc'}

    def test_success_with_error_dict(self, backend: CeleryTaskBackend, mock_celery_app: MagicMock):
        mock_result = MagicMock()
        mock_result.state = 'SUCCESS'
        mock_result.result = {'__error__': 'ValueError: bad'}
        mock_celery_app.AsyncResult.return_value = mock_result

        result = backend.get_status('t1')
        assert result.status == TaskStatus.FAILED
        assert result.error == 'ValueError: bad'

    def test_failure_state(self, backend: CeleryTaskBackend, mock_celery_app: MagicMock):
        mock_result = MagicMock()
        mock_result.state = 'FAILURE'
        mock_result.result = Exception('boom')
        mock_celery_app.AsyncResult.return_value = mock_result

        result = backend.get_status('t1')
        assert result.status == TaskStatus.FAILED

    def test_revoked_state(self, backend: CeleryTaskBackend, mock_celery_app: MagicMock):
        mock_result = MagicMock()
        mock_result.state = 'REVOKED'
        mock_celery_app.AsyncResult.return_value = mock_result

        result = backend.get_status('t1')
        assert result.status == TaskStatus.CANCELLED

    def test_retry_state(self, backend: CeleryTaskBackend, mock_celery_app: MagicMock):
        mock_result = MagicMock()
        mock_result.state = 'RETRY'
        mock_celery_app.AsyncResult.return_value = mock_result

        result = backend.get_status('t1')
        assert result.status == TaskStatus.RETRYING


class TestCancel:
    def test_cancel_revokes(self, backend: CeleryTaskBackend, mock_celery_app: MagicMock):
        result = backend.cancel('t1')
        assert result is True
        mock_celery_app.control.revoke.assert_called_once_with('t1', terminate=True)
