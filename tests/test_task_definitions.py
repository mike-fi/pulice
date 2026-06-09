"""Tests for pulice.core.task_definitions — stack operation dispatch."""

from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from pydantic import Field
from pulice.core.base import ComponentArgs, ManagedComponent
from pulice.core.managed import resolve_component_class
from pulice.core.stack import (
    PassphraseHasher,
    SqliteBackendStorage,
)
from pulice.core.task_definitions import execute_stack_operation

# ---------------------------------------------------------------------------
# Test component for resolution
# ---------------------------------------------------------------------------


class DemoArgs(ComponentArgs):
    region: str = Field('us-east-1', description='AWS region.')


class DemoComponent(ManagedComponent):
    args_model = DemoArgs


# ---------------------------------------------------------------------------
# resolve_component_class
# ---------------------------------------------------------------------------


class TestResolveComponentClass:
    def test_resolves_valid_class(self):
        cls = resolve_component_class('tests.test_task_definitions.DemoComponent')
        assert cls is DemoComponent

    def test_missing_module_raises(self):
        with pytest.raises(ModuleNotFoundError):
            resolve_component_class('nonexistent.module.Class')

    def test_missing_class_raises(self):
        with pytest.raises(AttributeError):
            resolve_component_class('tests.test_task_definitions.NonexistentClass')


# ---------------------------------------------------------------------------
# execute_stack_operation
# ---------------------------------------------------------------------------


class TestExecuteStackOperation:
    def _setup_storage(self, tmp_path: Path) -> SqliteBackendStorage:
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        storage.create_tenant('acme')
        return storage

    @patch('pulice.core.task_definitions.StackOperations')
    @patch('pulice.core.task_definitions.SqliteBackendStorage')
    def test_create_operation(self, mock_storage_cls, mock_ops_cls, tmp_path: Path):
        # Set up mocks
        mock_storage = MagicMock()
        mock_storage.get_tenant.return_value = MagicMock(id='tenant-123', name='acme')
        mock_storage_cls.return_value = mock_storage

        mock_ops = MagicMock()
        mock_ops.ensure_stack_workspace.return_value = str(tmp_path / 'workdir')
        mock_ops_cls.return_value = mock_ops

        result = execute_stack_operation(
            component_class='tests.test_task_definitions.DemoComponent',
            operation='create',
            tenant_name='acme',
            passphrase='secret',
            args={'name': 'my-stack', 'region': 'eu-west-1'},
            stack_reference=None,
            state_dir=str(tmp_path),
            backend_url=None,
        )

        assert result.get('stack_reference')
        assert result.get('status') == 'success'
        mock_ops.create_or_update_stack.assert_called_once()
        mock_ops.save_stack_reference.assert_called_once()
        mock_storage.save_passphrase_hash.assert_called_once()

    @patch('pulice.core.task_definitions.StackOperations')
    @patch('pulice.core.task_definitions.SqliteBackendStorage')
    def test_read_operation(self, mock_storage_cls, mock_ops_cls, tmp_path: Path):
        mock_storage = MagicMock()
        mock_storage.get_tenant.return_value = MagicMock(id='t1', name='acme')
        mock_storage.get_passphrase_hash.return_value = None
        mock_storage_cls.return_value = mock_storage

        mock_ops = MagicMock()
        mock_ops.get_stack_reference.return_value = MagicMock(
            stack_name='t1-demo-ref1',
            project_name='pulice-t1-demo',
            workdir='/tmp/wd',
        )
        mock_ops_cls.return_value = mock_ops

        result = execute_stack_operation(
            component_class='tests.test_task_definitions.DemoComponent',
            operation='read',
            tenant_name='acme',
            passphrase='secret',
            args={},
            stack_reference='ref1',
            state_dir=str(tmp_path),
            backend_url=None,
        )

        assert result['status'] == 'success'
        mock_ops.preview_stack.assert_called_once()

    @patch('pulice.core.task_definitions.StackOperations')
    @patch('pulice.core.task_definitions.SqliteBackendStorage')
    def test_delete_operation(self, mock_storage_cls, mock_ops_cls, tmp_path: Path):
        mock_storage = MagicMock()
        mock_storage.get_tenant.return_value = MagicMock(id='t1', name='acme')
        mock_storage.get_passphrase_hash.return_value = None
        mock_storage_cls.return_value = mock_storage

        mock_ops = MagicMock()
        mock_ops.get_stack_reference.return_value = MagicMock(
            stack_name='s',
            project_name='p',
            workdir='/tmp/wd',
        )
        mock_ops_cls.return_value = mock_ops

        result = execute_stack_operation(
            component_class='tests.test_task_definitions.DemoComponent',
            operation='delete',
            tenant_name='acme',
            passphrase='secret',
            args={},
            stack_reference='ref1',
            state_dir=str(tmp_path),
            backend_url=None,
        )

        assert result['status'] == 'success'
        mock_ops.destroy_stack.assert_called_once()

    @patch('pulice.core.task_definitions.StackOperations')
    @patch('pulice.core.task_definitions.SqliteBackendStorage')
    def test_refresh_operation(self, mock_storage_cls, mock_ops_cls, tmp_path: Path):
        mock_storage = MagicMock()
        mock_storage.get_tenant.return_value = MagicMock(id='t1', name='acme')
        mock_storage.get_passphrase_hash.return_value = None
        mock_storage_cls.return_value = mock_storage

        mock_ops = MagicMock()
        mock_ops.get_stack_reference.return_value = MagicMock(
            stack_name='s',
            project_name='p',
            workdir='/tmp/wd',
        )
        mock_ops_cls.return_value = mock_ops

        result = execute_stack_operation(
            component_class='tests.test_task_definitions.DemoComponent',
            operation='refresh',
            tenant_name='acme',
            passphrase='secret',
            args={},
            stack_reference='ref1',
            state_dir=str(tmp_path),
            backend_url=None,
        )

        assert result['status'] == 'success'
        mock_ops.refresh_stack.assert_called_once()

    @patch('pulice.core.task_definitions.StackOperations')
    @patch('pulice.core.task_definitions.SqliteBackendStorage')
    def test_status_operation(self, mock_storage_cls, mock_ops_cls, tmp_path: Path):
        mock_storage = MagicMock()
        mock_storage.get_tenant.return_value = MagicMock(id='t1', name='acme')
        mock_storage.get_passphrase_hash.return_value = None
        mock_storage_cls.return_value = mock_storage

        mock_ops = MagicMock()
        mock_ops.get_stack_reference.return_value = MagicMock(
            stack_name='s',
            project_name='p',
            workdir='/tmp/wd',
        )
        mock_ops.stack_status.return_value = {
            'stack_name': 's',
            'resource_count': 3,
            'last_update': None,
            'url': None,
        }
        mock_ops_cls.return_value = mock_ops

        result = execute_stack_operation(
            component_class='tests.test_task_definitions.DemoComponent',
            operation='status',
            tenant_name='acme',
            passphrase='secret',
            args={},
            stack_reference='ref1',
            state_dir=str(tmp_path),
            backend_url=None,
        )

        assert result['resource_count'] == 3

    @patch('pulice.core.task_definitions.StackOperations')
    @patch('pulice.core.task_definitions.SqliteBackendStorage')
    def test_list_operation(self, mock_storage_cls, mock_ops_cls, tmp_path: Path):
        mock_storage = MagicMock()
        mock_storage.get_tenant.return_value = MagicMock(id='t1', name='acme')
        mock_storage.list_stacks.return_value = [{'stack_name': 's1'}]
        mock_storage_cls.return_value = mock_storage

        result = execute_stack_operation(
            component_class='tests.test_task_definitions.DemoComponent',
            operation='list',
            tenant_name='acme',
            passphrase='',
            args={},
            stack_reference=None,
            state_dir=str(tmp_path),
            backend_url=None,
        )

        assert result['stacks'] == [{'stack_name': 's1'}]
        mock_storage.list_stacks.assert_called_once()

    @patch('pulice.core.task_definitions.StackOperations')
    @patch('pulice.core.task_definitions.SqliteBackendStorage')
    def test_passphrase_validation_fails(self, mock_storage_cls, mock_ops_cls, tmp_path: Path):
        mock_storage = MagicMock()
        mock_storage.get_tenant.return_value = MagicMock(id='t1', name='acme')
        # Return a hash that won't match
        mock_storage.get_passphrase_hash.return_value = PassphraseHasher.hash('correct')
        mock_storage_cls.return_value = mock_storage

        mock_ops = MagicMock()
        mock_ops.get_stack_reference.return_value = MagicMock(
            stack_name='s',
            project_name='p',
            workdir='/tmp/wd',
        )
        mock_ops_cls.return_value = mock_ops

        result = execute_stack_operation(
            component_class='tests.test_task_definitions.DemoComponent',
            operation='update',
            tenant_name='acme',
            passphrase='wrong',
            args={'name': 'x'},
            stack_reference='ref1',
            state_dir=str(tmp_path),
            backend_url=None,
        )

        assert '__error__' in result
        assert 'Invalid passphrase' in result['__error__']
        mock_ops.create_or_update_stack.assert_not_called()

    @patch('pulice.core.task_definitions.StackOperations')
    @patch('pulice.core.task_definitions.SqliteBackendStorage')
    def test_bad_component_class_returns_error(
        self, mock_storage_cls, mock_ops_cls, tmp_path: Path
    ):
        result = execute_stack_operation(
            component_class='nonexistent.module.Class',
            operation='create',
            tenant_name='acme',
            passphrase='secret',
            args={},
            stack_reference=None,
            state_dir=str(tmp_path),
            backend_url=None,
        )

        assert '__error__' in result

    @patch('pulice.core.task_definitions.StackOperations')
    @patch('pulice.core.task_definitions.SqliteBackendStorage')
    def test_missing_stack_reference_for_update(
        self, mock_storage_cls, mock_ops_cls, tmp_path: Path
    ):
        mock_storage = MagicMock()
        mock_storage.get_tenant.return_value = MagicMock(id='t1', name='acme')
        mock_storage_cls.return_value = mock_storage

        result = execute_stack_operation(
            component_class='tests.test_task_definitions.DemoComponent',
            operation='update',
            tenant_name='acme',
            passphrase='secret',
            args={},
            stack_reference=None,
            state_dir=str(tmp_path),
            backend_url=None,
        )

        assert '__error__' in result
        assert 'stack_reference is required' in result['__error__']

    @patch('pulice.core.task_definitions.StackOperations')
    @patch('pulice.core.task_definitions.SqliteBackendStorage')
    def test_unsupported_operation(self, mock_storage_cls, mock_ops_cls, tmp_path: Path):
        mock_storage = MagicMock()
        mock_storage.get_tenant.return_value = MagicMock(id='t1', name='acme')
        mock_storage.get_passphrase_hash.return_value = None
        mock_storage_cls.return_value = mock_storage

        mock_ops = MagicMock()
        mock_ops.get_stack_reference.return_value = MagicMock(
            stack_name='s',
            project_name='p',
            workdir='/tmp/wd',
        )
        mock_ops_cls.return_value = mock_ops

        result = execute_stack_operation(
            component_class='tests.test_task_definitions.DemoComponent',
            operation='invalid_op',
            tenant_name='acme',
            passphrase='secret',
            args={},
            stack_reference='ref1',
            state_dir=str(tmp_path),
            backend_url=None,
        )

        assert '__error__' in result
        assert 'Unsupported operation' in result['__error__']
