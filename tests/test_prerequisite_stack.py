"""Tests for Phase 0 prerequisites: Tenant, PassphraseHasher, StackLock, new ops."""

from __future__ import annotations
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from pulice.core.stack import (
    LocalStackReferenceStore,
    PassphraseHasher,
    SqliteBackendStorage,
    StackLock,
    StackLockError,
    StackOperations,
    StackReference,
)

# ===================================================================
# Tenant CRUD
# ===================================================================


class TestTenantCRUD:
    def test_create_tenant(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        tenant = storage.create_tenant('acme')
        assert tenant.name == 'acme'
        assert len(tenant.id) == 32  # UUID hex
        assert tenant.created_at

    def test_create_duplicate_tenant_raises(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        storage.create_tenant('acme')
        with pytest.raises(ValueError, match='already exists'):
            storage.create_tenant('acme')

    def test_get_tenant(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        created = storage.create_tenant('acme')
        loaded = storage.get_tenant('acme')
        assert loaded.id == created.id
        assert loaded.name == 'acme'

    def test_get_tenant_not_found(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        with pytest.raises(ValueError, match='not found'):
            storage.get_tenant('nonexistent')

    def test_get_tenant_by_id(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        created = storage.create_tenant('acme')
        loaded = storage.get_tenant_by_id(created.id)
        assert loaded.name == 'acme'

    def test_get_tenant_by_id_not_found(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        with pytest.raises(ValueError, match='not found'):
            storage.get_tenant_by_id('nonexistent-id')

    def test_list_tenants(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        storage.create_tenant('alpha')
        storage.create_tenant('beta')
        tenants = storage.list_tenants()
        names = [t.name for t in tenants]
        assert 'default' in names  # Auto-created
        assert 'alpha' in names
        assert 'beta' in names

    def test_delete_tenant(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        storage.create_tenant('disposable')
        storage.delete_tenant('disposable')
        with pytest.raises(ValueError, match='not found'):
            storage.get_tenant('disposable')

    def test_delete_tenant_not_found(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        with pytest.raises(ValueError, match='not found'):
            storage.delete_tenant('ghost')

    def test_delete_tenant_with_stacks_raises(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        tenant = storage.create_tenant('busy')
        storage.ensure_stack_dir('test-stack', tenant_id=tenant.id)
        with pytest.raises(ValueError, match='still has'):
            storage.delete_tenant('busy')

    def test_default_tenant_exists_on_init(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        default = storage.get_tenant('default')
        assert default.id == 'default'


# ===================================================================
# Schema migration
# ===================================================================


class TestSchemaMigration:
    def test_migrates_old_stacks_table(self, tmp_path: Path):
        """Opening a DB with old schema adds tenant_id and passphrase_hash columns."""
        db_path = tmp_path / 'pulice_stacks.sqlite3'
        (tmp_path / 'stacks').mkdir()

        # Create old-style DB
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE stacks (
                    name TEXT PRIMARY KEY,
                    uuid TEXT NOT NULL UNIQUE,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "INSERT INTO stacks(name, uuid, path) VALUES ('old-stack', 'uuid-1', '/tmp/old')"
            )

        # Now open with new code — should migrate
        storage = SqliteBackendStorage(root_dir=str(tmp_path))

        cols = {
            row[1]
            for row in sqlite3.connect(db_path).execute('PRAGMA table_info(stacks)').fetchall()
        }
        assert 'tenant_id' in cols
        assert 'passphrase_hash' in cols

        # Old stack should be assigned to default tenant
        stacks = storage.list_stacks(tenant_id='default')
        assert any(s['stack_name'] == 'old-stack' for s in stacks)


# ===================================================================
# PassphraseHasher
# ===================================================================


class TestPassphraseHasher:
    def test_hash_format(self):
        h = PassphraseHasher.hash('secret')
        parts = h.split(':')
        assert len(parts) == 3
        assert parts[0] == 'scrypt'
        assert len(parts[1]) == 32  # 16 bytes hex
        assert len(parts[2]) == 64  # 32 bytes hex

    def test_verify_correct_passphrase(self):
        h = PassphraseHasher.hash('my-pass')
        assert PassphraseHasher.verify('my-pass', h) is True

    def test_verify_wrong_passphrase(self):
        h = PassphraseHasher.hash('correct')
        assert PassphraseHasher.verify('wrong', h) is False

    def test_verify_invalid_format(self):
        assert PassphraseHasher.verify('pass', 'not-a-hash') is False

    def test_different_hashes_for_same_input(self):
        h1 = PassphraseHasher.hash('same')
        h2 = PassphraseHasher.hash('same')
        assert h1 != h2  # Different salts
        assert PassphraseHasher.verify('same', h1)
        assert PassphraseHasher.verify('same', h2)

    def test_save_and_get_passphrase_hash(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        storage.ensure_stack_dir('hash-stack')
        h = PassphraseHasher.hash('secret')
        storage.save_passphrase_hash('hash-stack', h)
        loaded = storage.get_passphrase_hash('hash-stack')
        assert loaded == h

    def test_get_passphrase_hash_returns_none_for_unknown(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        assert storage.get_passphrase_hash('nonexistent') is None

    def test_get_passphrase_hash_returns_none_when_not_set(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        storage.ensure_stack_dir('no-hash-stack')
        assert storage.get_passphrase_hash('no-hash-stack') is None


# ===================================================================
# StackLock
# ===================================================================


class TestStackLock:
    def test_acquire_and_release(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        storage.ensure_stack_dir('lockable')
        with StackLock(storage, 'lockable', 'create'):
            # Lock should be held
            with storage._connect() as conn:
                row = conn.execute(
                    'SELECT holder, operation FROM stack_locks WHERE stack_name = ?',
                    ('lockable',),
                ).fetchone()
            assert row is not None
            assert row[1] == 'create'

        # Lock should be released
        with storage._connect() as conn:
            row = conn.execute(
                'SELECT * FROM stack_locks WHERE stack_name = ?',
                ('lockable',),
            ).fetchone()
        assert row is None

    def test_double_lock_times_out(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        storage.ensure_stack_dir('busy')
        with StackLock(storage, 'busy', 'create'):
            with pytest.raises(StackLockError, match='Cannot acquire lock'):
                with StackLock(storage, 'busy', 'update', timeout=0.3):
                    pass  # Should not reach here

    def test_stale_lock_cleanup(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        storage.ensure_stack_dir('stale')
        # Insert a stale lock manually
        stale_time = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        with storage._connect() as conn:
            conn.execute(
                'INSERT INTO stack_locks(stack_name, holder, operation, locked_at) '
                'VALUES (?, ?, ?, ?)',
                ('stale', 'old-holder', 'create', stale_time),
            )
        # Should be able to acquire despite stale lock
        with StackLock(storage, 'stale', 'update', timeout=1.0):
            pass

    def test_release_after_exception(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        storage.ensure_stack_dir('exc')
        with pytest.raises(RuntimeError):
            with StackLock(storage, 'exc', 'create'):
                raise RuntimeError('boom')

        # Lock should still be released
        with storage._connect() as conn:
            row = conn.execute(
                'SELECT * FROM stack_locks WHERE stack_name = ?',
                ('exc',),
            ).fetchone()
        assert row is None

    def test_sequential_locks_on_same_stack(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        storage.ensure_stack_dir('reusable')
        with StackLock(storage, 'reusable', 'create'):
            pass
        with StackLock(storage, 'reusable', 'update'):
            pass
        # No error


# ===================================================================
# list_stacks
# ===================================================================


class TestListStacks:
    def test_list_all_stacks(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        tenant = storage.create_tenant('t1')
        storage.ensure_stack_dir('stack-a', tenant_id=tenant.id)
        storage.ensure_stack_dir('stack-b', tenant_id=tenant.id)
        stacks = storage.list_stacks()
        names = [s['stack_name'] for s in stacks]
        assert 'stack-a' in names
        assert 'stack-b' in names

    def test_list_stacks_by_tenant(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        t1 = storage.create_tenant('t1')
        t2 = storage.create_tenant('t2')
        storage.ensure_stack_dir('t1-stack', tenant_id=t1.id)
        storage.ensure_stack_dir('t2-stack', tenant_id=t2.id)
        stacks = storage.list_stacks(tenant_id=t1.id)
        names = [s['stack_name'] for s in stacks]
        assert 't1-stack' in names
        assert 't2-stack' not in names

    def test_list_stacks_by_component(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        storage.ensure_stack_dir('demo-abc123')
        storage.ensure_stack_dir('other-xyz789')
        stacks = storage.list_stacks(component_name='demo')
        names = [s['stack_name'] for s in stacks]
        assert 'demo-abc123' in names
        assert 'other-xyz789' not in names

    def test_list_stacks_empty(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        t = storage.create_tenant('empty')
        stacks = storage.list_stacks(tenant_id=t.id)
        assert stacks == []


# ===================================================================
# New StackOperations methods (mocked automation)
# ===================================================================


class TestRefreshStack:
    @patch('pulice.core.stack.automation')
    def test_calls_refresh(self, mock_auto, tmp_path: Path):
        mock_stack = MagicMock()
        mock_auto.create_or_select_stack.return_value = mock_stack
        mock_auto.LocalWorkspaceOptions = MagicMock()
        mock_auto.ProjectSettings = MagicMock()
        mock_auto.ProjectBackend = MagicMock()

        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))
        workdir = str(tmp_path / 'wd')
        Path(workdir).mkdir()

        result = ops.refresh_stack(
            stack_name='s',
            project_name='p',
            workdir=workdir,
            program=lambda: None,
        )

        mock_stack.refresh.assert_called_once()
        assert result is mock_stack


class TestStackStatus:
    @patch('pulice.core.stack.automation')
    def test_returns_status_dict(self, mock_auto, tmp_path: Path):
        mock_stack = MagicMock()
        mock_info = MagicMock()
        mock_info.resource_count = 5
        mock_info.last_update = '2024-01-01'
        mock_info.url = 'http://example.com'
        mock_stack.info.return_value = mock_info
        mock_auto.create_or_select_stack.return_value = mock_stack
        mock_auto.LocalWorkspaceOptions = MagicMock()
        mock_auto.ProjectSettings = MagicMock()
        mock_auto.ProjectBackend = MagicMock()

        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))
        workdir = str(tmp_path / 'wd')
        Path(workdir).mkdir()

        status = ops.stack_status(
            stack_name='s',
            project_name='p',
            workdir=workdir,
            program=lambda: None,
        )

        assert status['stack_name'] == 's'
        assert status['resource_count'] == 5

    @patch('pulice.core.stack.automation')
    def test_handles_no_info(self, mock_auto, tmp_path: Path):
        mock_stack = MagicMock()
        mock_stack.info.return_value = None
        mock_auto.create_or_select_stack.return_value = mock_stack
        mock_auto.LocalWorkspaceOptions = MagicMock()
        mock_auto.ProjectSettings = MagicMock()
        mock_auto.ProjectBackend = MagicMock()

        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))
        workdir = str(tmp_path / 'wd')
        Path(workdir).mkdir()

        status = ops.stack_status(
            stack_name='s',
            project_name='p',
            workdir=workdir,
            program=lambda: None,
        )

        assert status['resource_count'] == 0
        assert status['last_update'] is None


class TestExportStack:
    @patch('pulice.core.stack.automation')
    def test_returns_deployment_dict(self, mock_auto, tmp_path: Path):
        mock_stack = MagicMock()
        mock_deployment = MagicMock()
        mock_deployment.deployment = {'resources': []}
        mock_stack.export_stack.return_value = mock_deployment
        mock_auto.create_or_select_stack.return_value = mock_stack
        mock_auto.LocalWorkspaceOptions = MagicMock()
        mock_auto.ProjectSettings = MagicMock()
        mock_auto.ProjectBackend = MagicMock()

        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))
        workdir = str(tmp_path / 'wd')
        Path(workdir).mkdir()

        result = ops.export_stack(
            stack_name='s',
            project_name='p',
            workdir=workdir,
            program=lambda: None,
        )

        assert result == {'resources': []}


class TestImportStack:
    @patch('pulice.core.stack.automation')
    def test_calls_import_stack(self, mock_auto, tmp_path: Path):
        mock_stack = MagicMock()
        mock_auto.create_or_select_stack.return_value = mock_stack
        mock_auto.LocalWorkspaceOptions = MagicMock()
        mock_auto.ProjectSettings = MagicMock()
        mock_auto.ProjectBackend = MagicMock()
        mock_auto.Deployment = MagicMock()

        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))
        workdir = str(tmp_path / 'wd')
        Path(workdir).mkdir()

        ops.import_stack(
            stack_name='s',
            project_name='p',
            workdir=workdir,
            program=lambda: None,
            state={'resources': []},
        )

        mock_stack.import_stack.assert_called_once()
        mock_auto.Deployment.assert_called_once_with(version=3, deployment={'resources': []})


# ===================================================================
# StackReference with tenant_id
# ===================================================================


class TestStackReferenceTenantId:
    def test_default_tenant_id_is_empty(self):
        ref = StackReference(
            id='r1',
            component_name='c',
            stack_name='s',
            project_name='p',
            workdir='/tmp/w',
        )
        assert ref.tenant_id == ''

    def test_explicit_tenant_id(self):
        ref = StackReference(
            id='r1',
            component_name='c',
            stack_name='s',
            project_name='p',
            workdir='/tmp/w',
            tenant_id='t123',
        )
        assert ref.tenant_id == 't123'

    def test_store_handles_missing_tenant_id_in_json(self, tmp_path: Path):
        """Old JSON files without tenant_id are loaded with default ''."""
        store = LocalStackReferenceStore(root_dir=str(tmp_path))
        # Write old-format JSON (no tenant_id)
        json_path = tmp_path / 'stack_refs' / 'old-ref.json'
        json_path.write_text(
            '{"id":"old-ref","component_name":"c","stack_name":"s",'
            '"project_name":"p","workdir":"/tmp/w"}',
            encoding='utf-8',
        )
        loaded = store.get('old-ref')
        assert loaded.tenant_id == ''

    def test_store_round_trip_with_tenant_id(self, tmp_path: Path):
        store = LocalStackReferenceStore(root_dir=str(tmp_path))
        ref = StackReference(
            id='new-ref',
            component_name='c',
            stack_name='s',
            project_name='p',
            workdir='/tmp/w',
            tenant_id='t123',
        )
        store.save(ref)
        loaded = store.get('new-ref')
        assert loaded.tenant_id == 't123'


# ===================================================================
# StackOperations.storage property
# ===================================================================


class TestStorageProperty:
    def test_exposes_storage(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        ops = StackOperations(storage=storage)
        assert ops.storage is storage
