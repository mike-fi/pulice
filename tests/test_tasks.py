"""Tests for pulice.core.tasks — TaskBackend protocol and HueyTaskBackend."""

from __future__ import annotations
from pathlib import Path
from unittest.mock import patch
import pytest
from pulice.core.tasks import (
    HueyTaskBackend,
    TaskBackend,
    TaskResult,
    TaskStatus,
    create_huey_instance,
    get_task_backend,
)

# ===================================================================
# TaskStatus + TaskResult
# ===================================================================


class TestTaskStatusAndResult:
    def test_task_status_values(self):
        assert TaskStatus.PENDING.value == 'pending'
        assert TaskStatus.RUNNING.value == 'running'
        assert TaskStatus.SUCCESS.value == 'success'
        assert TaskStatus.FAILED.value == 'failed'
        assert TaskStatus.CANCELLED.value == 'cancelled'
        assert TaskStatus.RETRYING.value == 'retrying'

    def test_task_result_defaults(self):
        r = TaskResult(task_id='t1', status=TaskStatus.PENDING)
        assert r.result is None
        assert r.error is None
        assert r.created_at is None

    def test_task_result_with_values(self):
        r = TaskResult(
            task_id='t1',
            status=TaskStatus.SUCCESS,
            result={'stack_reference': 'abc'},
        )
        assert r.result == {'stack_reference': 'abc'}


# ===================================================================
# TaskBackend protocol
# ===================================================================


class TestTaskBackendProtocol:
    def test_huey_backend_satisfies_protocol(self, tmp_path: Path):
        huey = create_huey_instance(state_dir=str(tmp_path), immediate=True)
        backend = HueyTaskBackend(huey)
        assert isinstance(backend, TaskBackend)

    def test_arbitrary_object_not_conforming(self):
        assert not isinstance('hello', TaskBackend)

    def test_duck_typed_object_conforms(self):
        class MyBackend:
            def submit(self, task_name, kwargs):
                return 'id'

            def get_status(self, task_id):
                return TaskResult(task_id=task_id, status=TaskStatus.PENDING)

            def cancel(self, task_id):
                return True

            def retry(self, task_id):
                return 'new-id'

        assert isinstance(MyBackend(), TaskBackend)


# ===================================================================
# create_huey_instance
# ===================================================================


class TestCreateHueyInstance:
    def test_creates_huey_with_state_dir(self, tmp_path: Path):
        huey = create_huey_instance(state_dir=str(tmp_path))
        assert huey is not None

    def test_creates_db_path(self, tmp_path: Path):
        create_huey_instance(state_dir=str(tmp_path))
        # Huey doesn't create the DB file until first use, but dir should exist
        assert tmp_path.exists()

    def test_immediate_mode(self, tmp_path: Path):
        huey = create_huey_instance(state_dir=str(tmp_path), immediate=True)
        assert huey.immediate is True


# ===================================================================
# HueyTaskBackend
# ===================================================================


class TestHueyTaskBackend:
    def _make_backend(self, tmp_path: Path) -> HueyTaskBackend:
        huey = create_huey_instance(state_dir=str(tmp_path), immediate=True)
        return HueyTaskBackend(huey)

    @patch('pulice.core.task_definitions.execute_stack_operation')
    def test_submit_returns_task_id(self, mock_exec, tmp_path: Path):
        mock_exec.return_value = {'stack_reference': 'abc'}
        backend = self._make_backend(tmp_path)
        task_id = backend.submit(
            'stack.create',
            {
                'component_class': 'test.Demo',
                'operation': 'create',
                'tenant_name': 'acme',
                'passphrase': 'secret',
                'args': {'name': 'my-stack'},
                'stack_reference': None,
                'state_dir': str(tmp_path),
                'backend_url': None,
            },
        )
        assert isinstance(task_id, str)
        assert len(task_id) > 0

    @patch('pulice.core.task_definitions.execute_stack_operation')
    def test_get_status_success(self, mock_exec, tmp_path: Path):
        mock_exec.return_value = {'stack_reference': 'abc'}
        backend = self._make_backend(tmp_path)
        task_id = backend.submit(
            'stack.create',
            {
                'component_class': 'test.Demo',
                'operation': 'create',
                'tenant_name': 'acme',
                'passphrase': 'secret',
                'args': {},
                'stack_reference': None,
                'state_dir': str(tmp_path),
                'backend_url': None,
            },
        )
        result = backend.get_status(task_id)
        assert result.status == TaskStatus.SUCCESS
        assert result.result == {'stack_reference': 'abc'}

    @patch('pulice.core.task_definitions.execute_stack_operation')
    def test_cancel(self, mock_exec, tmp_path: Path):
        mock_exec.return_value = {}
        backend = self._make_backend(tmp_path)
        task_id = backend.submit(
            'stack.create',
            {
                'component_class': 'test.Demo',
                'operation': 'create',
                'tenant_name': 'acme',
                'passphrase': 'secret',
                'args': {},
                'stack_reference': None,
                'state_dir': str(tmp_path),
                'backend_url': None,
            },
        )
        assert backend.cancel(task_id) is True

    @patch('pulice.core.task_definitions.execute_stack_operation')
    def test_retry_resubmits(self, mock_exec, tmp_path: Path):
        mock_exec.return_value = {'status': 'ok'}
        backend = self._make_backend(tmp_path)
        kwargs = {
            'component_class': 'test.Demo',
            'operation': 'create',
            'tenant_name': 'acme',
            'passphrase': 'secret',
            'args': {},
            'stack_reference': None,
            'state_dir': str(tmp_path),
            'backend_url': None,
        }
        task_id = backend.submit('stack.create', kwargs)
        new_id = backend.retry(task_id)
        assert isinstance(new_id, str)
        assert new_id != task_id

    def test_retry_unknown_task_raises(self, tmp_path: Path):
        backend = self._make_backend(tmp_path)
        with pytest.raises(ValueError, match='original kwargs not found'):
            backend.retry('nonexistent-id')


# ===================================================================
# get_task_backend factory
# ===================================================================


class TestGetTaskBackend:
    def test_default_is_huey(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv('PULICE_TASK_BACKEND', raising=False)
        backend = get_task_backend(state_dir=str(tmp_path))
        assert isinstance(backend, HueyTaskBackend)

    def test_huey_explicit(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv('PULICE_TASK_BACKEND', 'huey')
        backend = get_task_backend(state_dir=str(tmp_path))
        assert isinstance(backend, HueyTaskBackend)

    def test_unknown_backend_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv('PULICE_TASK_BACKEND', 'unknown')
        with pytest.raises(ValueError, match='Unknown task backend'):
            get_task_backend()

    def test_celery_without_install_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv('PULICE_TASK_BACKEND', 'celery')
        with pytest.raises(ImportError, match='pulice\\[celery\\]'):
            get_task_backend()
