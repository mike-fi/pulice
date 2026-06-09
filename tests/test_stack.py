"""Tests for pulice.core.stack — full stack lifecycle spec.

Covers:
- SqliteBackendStorage: DB bootstrap, dir registration, idempotency, isolation
- LocalStackReferenceStore: round-trip, missing ref, JSON persistence
- StackOperations: workspace resolution, reference management, and the three
  Automation API lifecycle methods (create_or_update, preview, destroy) with
  mocked pulumi.automation
- _local_workspace_opts: backend URL, env var merging, passphrase override
"""

from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from pulice.core.stack import (
    BackendStorage,
    LocalStackReferenceStore,
    SqliteBackendStorage,
    StackOperations,
    StackReference,
)

# ===================================================================
# SqliteBackendStorage
# ===================================================================


class TestSqliteBackendStorage:
    def test_creates_db_and_stacks_dir_on_init(self, tmp_path: Path):
        _ = SqliteBackendStorage(root_dir=str(tmp_path))

        assert (tmp_path / 'pulice_stacks.sqlite3').exists()
        assert (tmp_path / 'stacks').is_dir()

    def test_custom_filenames(self, tmp_path: Path):
        _ = SqliteBackendStorage(
            root_dir=str(tmp_path),
            db_filename='custom.db',
            stacks_dirname='custom_stacks',
        )

        assert (tmp_path / 'custom.db').exists()
        assert (tmp_path / 'custom_stacks').is_dir()

    def test_schema_has_stacks_table(self, tmp_path: Path):
        SqliteBackendStorage(root_dir=str(tmp_path))

        with sqlite3.connect(tmp_path / 'pulice_stacks.sqlite3') as conn:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()

        assert ('stacks',) in tables

    def test_ensure_stack_dir_creates_directory_and_row(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        stack_dir = Path(storage.ensure_stack_dir('my-stack'))

        assert stack_dir.exists()
        assert stack_dir.is_dir()

        with sqlite3.connect(tmp_path / 'pulice_stacks.sqlite3') as conn:
            row = conn.execute(
                'SELECT name, uuid, path FROM stacks WHERE name = ?',
                ('my-stack',),
            ).fetchone()

        assert row is not None
        assert row[0] == 'my-stack'
        assert row[1]  # uuid is non-empty
        assert Path(row[2]) == stack_dir

    def test_same_stack_name_returns_same_path(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))

        first = storage.ensure_stack_dir('my-stack')
        second = storage.ensure_stack_dir('my-stack')

        assert first == second

    def test_same_stack_name_does_not_duplicate_rows(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))

        storage.ensure_stack_dir('my-stack')
        storage.ensure_stack_dir('my-stack')

        with sqlite3.connect(tmp_path / 'pulice_stacks.sqlite3') as conn:
            count = conn.execute(
                'SELECT COUNT(*) FROM stacks WHERE name = ?',
                ('my-stack',),
            ).fetchone()[0]

        assert count == 1

    def test_different_stack_names_get_different_uuids_and_paths(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))

        path_a = storage.ensure_stack_dir('stack-a')
        path_b = storage.ensure_stack_dir('stack-b')

        assert path_a != path_b

        with sqlite3.connect(tmp_path / 'pulice_stacks.sqlite3') as conn:
            rows = conn.execute('SELECT name, uuid FROM stacks ORDER BY name').fetchall()

        assert len(rows) == 2
        assert rows[0][0] == 'stack-a'
        assert rows[1][0] == 'stack-b'
        assert rows[0][1] != rows[1][1]

    def test_stack_dir_is_under_stacks_root(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        stack_dir = Path(storage.ensure_stack_dir('nested-check'))

        assert str(stack_dir).startswith(str(tmp_path / 'stacks'))

    def test_recreates_directory_if_deleted(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        stack_dir = Path(storage.ensure_stack_dir('ephemeral'))
        stack_dir.rmdir()
        assert not stack_dir.exists()

        # Second call should re-create the directory from the stored path.
        recovered = Path(storage.ensure_stack_dir('ephemeral'))
        assert recovered.exists()
        assert recovered == stack_dir

    def test_implements_backend_storage_abc(self):
        assert issubclass(SqliteBackendStorage, BackendStorage)

    def test_created_at_column_populated(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        storage.ensure_stack_dir('timestamped')

        with sqlite3.connect(tmp_path / 'pulice_stacks.sqlite3') as conn:
            row = conn.execute(
                'SELECT created_at FROM stacks WHERE name = ?',
                ('timestamped',),
            ).fetchone()

        assert row[0] is not None
        assert len(row[0]) > 0


# ===================================================================
# LocalStackReferenceStore
# ===================================================================


class TestLocalStackReferenceStore:
    def test_creates_refs_dir_on_init(self, tmp_path: Path):
        _ = LocalStackReferenceStore(root_dir=str(tmp_path))
        assert (tmp_path / 'stack_refs').is_dir()

    def test_custom_dirname(self, tmp_path: Path):
        _ = LocalStackReferenceStore(root_dir=str(tmp_path), dirname='my_refs')
        assert (tmp_path / 'my_refs').is_dir()

    def test_save_and_get_round_trip(self, tmp_path: Path):
        store = LocalStackReferenceStore(root_dir=str(tmp_path))
        ref = StackReference(
            id='ref-abc',
            component_name='mycomp',
            stack_name='mycomp-ref-abc',
            project_name='pulice-mycomp',
            workdir='/tmp/some-workdir',
        )

        store.save(ref)
        loaded = store.get('ref-abc')

        assert loaded.id == ref.id
        assert loaded.component_name == ref.component_name
        assert loaded.stack_name == ref.stack_name
        assert loaded.project_name == ref.project_name
        assert loaded.workdir == ref.workdir

    def test_get_unknown_reference_raises_value_error(self, tmp_path: Path):
        store = LocalStackReferenceStore(root_dir=str(tmp_path))

        with pytest.raises(ValueError, match='Unknown stack reference'):
            store.get('does-not-exist')

    def test_persists_as_json(self, tmp_path: Path):
        store = LocalStackReferenceStore(root_dir=str(tmp_path))
        ref = StackReference(
            id='ref-json',
            component_name='comp',
            stack_name='comp-ref-json',
            project_name='pulice-comp',
            workdir='/tmp/wd',
        )
        store.save(ref)

        json_path = tmp_path / 'stack_refs' / 'ref-json.json'
        assert json_path.exists()
        data = json.loads(json_path.read_text(encoding='utf-8'))
        assert data['id'] == 'ref-json'
        assert data['component_name'] == 'comp'

    def test_overwrite_existing_reference(self, tmp_path: Path):
        store = LocalStackReferenceStore(root_dir=str(tmp_path))
        ref_v1 = StackReference(
            id='ref-ow',
            component_name='comp',
            stack_name='comp-ref-ow',
            project_name='pulice-comp',
            workdir='/tmp/v1',
        )
        ref_v2 = StackReference(
            id='ref-ow',
            component_name='comp',
            stack_name='comp-ref-ow',
            project_name='pulice-comp',
            workdir='/tmp/v2',
        )

        store.save(ref_v1)
        store.save(ref_v2)
        loaded = store.get('ref-ow')

        assert loaded.workdir == '/tmp/v2'


# ===================================================================
# StackOperations — workspace & reference management
# ===================================================================


class TestStackOperationsWorkspace:
    def test_uses_backend_storage_by_stack_name(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        ops = StackOperations(storage=storage)

        first = ops.ensure_stack_workspace('ws-stack')
        second = ops.ensure_stack_workspace('ws-stack')

        assert first == second
        assert Path(first).exists()

    def test_explicit_workdir_takes_precedence(self, tmp_path: Path):
        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        ops = StackOperations(storage=storage)

        explicit = str(tmp_path / 'explicit-dir')
        result = ops.ensure_stack_workspace('ws-stack', workdir=explicit)

        assert result == explicit
        assert Path(explicit).exists()

    def test_ensure_workspace_creates_dir(self, tmp_path: Path):
        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))
        new_dir = str(tmp_path / 'new-workspace')
        result = ops.ensure_workspace(new_dir)

        assert result == new_dir
        assert Path(new_dir).exists()

    def test_ensure_workspace_none_creates_tempdir(self, tmp_path: Path):
        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))
        result = ops.ensure_workspace(None)

        assert Path(result).exists()
        assert 'pulumi-auto-' in result


class TestStackOperationsReferences:
    def test_save_and_get_round_trip(self, tmp_path: Path):
        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))

        saved = ops.save_stack_reference(
            reference_id='ref-123',
            component_name='mycomp',
            stack_name='mycomp-ref-123',
            project_name='pulice-mycomp',
            workdir=str(tmp_path / 'stacks' / 'workdir-a'),
        )
        loaded = ops.get_stack_reference('ref-123', expected_component_name='mycomp')

        assert loaded.id == saved.id
        assert loaded.component_name == saved.component_name
        assert loaded.stack_name == saved.stack_name
        assert loaded.project_name == saved.project_name
        assert loaded.workdir == saved.workdir

    def test_component_name_mismatch_raises(self, tmp_path: Path):
        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))
        ops.save_stack_reference(
            reference_id='ref-456',
            component_name='comp-a',
            stack_name='comp-a-ref-456',
            project_name='pulice-comp-a',
            workdir=str(tmp_path / 'stacks' / 'wd'),
        )

        with pytest.raises(ValueError, match='belongs to component'):
            ops.get_stack_reference('ref-456', expected_component_name='comp-b')

    def test_get_without_expected_component_skips_check(self, tmp_path: Path):
        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))
        ops.save_stack_reference(
            reference_id='ref-789',
            component_name='any-comp',
            stack_name='any-comp-ref-789',
            project_name='pulice-any-comp',
            workdir=str(tmp_path / 'stacks' / 'wd'),
        )

        loaded = ops.get_stack_reference('ref-789')
        assert loaded.component_name == 'any-comp'

    def test_unknown_reference_raises(self, tmp_path: Path):
        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))

        with pytest.raises(ValueError, match='Unknown stack reference'):
            ops.get_stack_reference('nonexistent')


# ===================================================================
# StackOperations — _local_workspace_opts
# ===================================================================


class TestLocalWorkspaceOpts:
    def _make_ops(self, tmp_path: Path) -> StackOperations:
        return StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))

    def test_creates_pulumi_state_subdir(self, tmp_path: Path):
        ops = self._make_ops(tmp_path)
        workdir = str(tmp_path / 'workdir')
        Path(workdir).mkdir()

        ops._local_workspace_opts('my-project', workdir)

        assert (tmp_path / 'workdir' / '.pulumi-state').is_dir()

    def test_default_backend_url_is_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv('PULICE_PULUMI_BACKEND_URL', raising=False)
        ops = self._make_ops(tmp_path)
        workdir = str(tmp_path / 'workdir')
        Path(workdir).mkdir()

        opts = ops._local_workspace_opts('my-project', workdir)

        expected_state_dir = tmp_path / 'workdir' / '.pulumi-state'
        assert opts.project_settings.backend.url == f'file://{expected_state_dir}'

    def test_env_var_overrides_backend_url(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv('PULICE_PULUMI_BACKEND_URL', 's3://my-bucket/state')
        ops = self._make_ops(tmp_path)
        workdir = str(tmp_path / 'workdir')
        Path(workdir).mkdir()

        opts = ops._local_workspace_opts('my-project', workdir)

        assert opts.project_settings.backend.url == 's3://my-bucket/state'

    def test_default_passphrase_is_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv('PULICE_PULUMI_BACKEND_URL', raising=False)
        ops = self._make_ops(tmp_path)
        workdir = str(tmp_path / 'workdir')
        Path(workdir).mkdir()

        opts = ops._local_workspace_opts('my-project', workdir)

        assert opts.env_vars['PULUMI_CONFIG_PASSPHRASE'] == ''

    def test_custom_env_vars_merged(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv('PULICE_PULUMI_BACKEND_URL', raising=False)
        ops = self._make_ops(tmp_path)
        workdir = str(tmp_path / 'workdir')
        Path(workdir).mkdir()

        opts = ops._local_workspace_opts('proj', workdir, env_vars={'MY_VAR': 'hello'})

        assert opts.env_vars['MY_VAR'] == 'hello'
        assert 'PULUMI_CONFIG_PASSPHRASE' in opts.env_vars

    def test_custom_passphrase_overrides_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv('PULICE_PULUMI_BACKEND_URL', raising=False)
        ops = self._make_ops(tmp_path)
        workdir = str(tmp_path / 'workdir')
        Path(workdir).mkdir()

        opts = ops._local_workspace_opts(
            'proj', workdir, env_vars={'PULUMI_CONFIG_PASSPHRASE': 's3cret'}
        )

        assert opts.env_vars['PULUMI_CONFIG_PASSPHRASE'] == 's3cret'

    def test_project_settings(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv('PULICE_PULUMI_BACKEND_URL', raising=False)
        ops = self._make_ops(tmp_path)
        workdir = str(tmp_path / 'workdir')
        Path(workdir).mkdir()

        opts = ops._local_workspace_opts('my-project', workdir)

        assert opts.project_settings.name == 'my-project'
        assert opts.project_settings.runtime == 'python'

    def test_work_dir_set(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv('PULICE_PULUMI_BACKEND_URL', raising=False)
        ops = self._make_ops(tmp_path)
        workdir = str(tmp_path / 'workdir')
        Path(workdir).mkdir()

        opts = ops._local_workspace_opts('proj', workdir)

        assert opts.work_dir == workdir


# ===================================================================
# StackOperations — Automation API lifecycle (mocked)
# ===================================================================


class TestStackLifecycleCreateOrUpdate:
    @patch('pulice.core.stack.automation')
    def test_calls_create_or_select_stack_then_up(self, mock_auto, tmp_path: Path):
        mock_stack = MagicMock()
        mock_auto.create_or_select_stack.return_value = mock_stack
        mock_auto.LocalWorkspaceOptions = MagicMock()
        mock_auto.ProjectSettings = MagicMock()
        mock_auto.ProjectBackend = MagicMock()

        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))
        workdir = str(tmp_path / 'wd')
        Path(workdir).mkdir()
        program = MagicMock()

        result = ops.create_or_update_stack(
            stack_name='test-stack',
            project_name='test-project',
            workdir=workdir,
            program=program,
        )

        mock_auto.create_or_select_stack.assert_called_once()
        call_kwargs = mock_auto.create_or_select_stack.call_args.kwargs
        assert call_kwargs['stack_name'] == 'test-stack'
        assert call_kwargs['project_name'] == 'test-project'
        assert call_kwargs['program'] is program
        mock_stack.up.assert_called_once()
        assert result is mock_stack

    @patch('pulice.core.stack.automation')
    def test_falls_back_to_select_on_already_exists(self, mock_auto, tmp_path: Path):
        mock_auto.StackAlreadyExistsError = type('StackAlreadyExistsError', (Exception,), {})
        mock_auto.create_or_select_stack.side_effect = mock_auto.StackAlreadyExistsError()
        mock_fallback_stack = MagicMock()
        mock_auto.select_stack.return_value = mock_fallback_stack
        mock_auto.LocalWorkspaceOptions = MagicMock()
        mock_auto.ProjectSettings = MagicMock()
        mock_auto.ProjectBackend = MagicMock()

        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))
        workdir = str(tmp_path / 'wd')
        Path(workdir).mkdir()

        result = ops.create_or_update_stack(
            stack_name='existing',
            project_name='proj',
            workdir=workdir,
            program=lambda: None,
        )

        mock_auto.select_stack.assert_called_once()
        mock_fallback_stack.up.assert_called_once()
        assert result is mock_fallback_stack

    @patch('pulice.core.stack.automation')
    def test_passes_env_vars_through(self, mock_auto, tmp_path: Path):
        mock_stack = MagicMock()
        mock_auto.create_or_select_stack.return_value = mock_stack
        mock_auto.LocalWorkspaceOptions = MagicMock()
        mock_auto.ProjectSettings = MagicMock()
        mock_auto.ProjectBackend = MagicMock()

        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))
        workdir = str(tmp_path / 'wd')
        Path(workdir).mkdir()

        ops.create_or_update_stack(
            stack_name='s',
            project_name='p',
            workdir=workdir,
            program=lambda: None,
            env_vars={'PULUMI_CONFIG_PASSPHRASE': 'secret'},
        )

        mock_stack.up.assert_called_once()

    @patch('pulice.core.stack.automation')
    def test_up_streams_to_print(self, mock_auto, tmp_path: Path):
        mock_stack = MagicMock()
        mock_auto.create_or_select_stack.return_value = mock_stack
        mock_auto.LocalWorkspaceOptions = MagicMock()
        mock_auto.ProjectSettings = MagicMock()
        mock_auto.ProjectBackend = MagicMock()

        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))
        workdir = str(tmp_path / 'wd')
        Path(workdir).mkdir()

        ops.create_or_update_stack(
            stack_name='s',
            project_name='p',
            workdir=workdir,
            program=lambda: None,
        )

        call_kwargs = mock_stack.up.call_args.kwargs
        assert call_kwargs['on_output'] is print


class TestStackLifecyclePreview:
    @patch('pulice.core.stack.automation')
    def test_calls_create_or_select_then_preview(self, mock_auto, tmp_path: Path):
        mock_stack = MagicMock()
        mock_auto.create_or_select_stack.return_value = mock_stack
        mock_auto.LocalWorkspaceOptions = MagicMock()
        mock_auto.ProjectSettings = MagicMock()
        mock_auto.ProjectBackend = MagicMock()

        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))
        workdir = str(tmp_path / 'wd')
        Path(workdir).mkdir()
        program = MagicMock()

        result = ops.preview_stack(
            stack_name='prev-stack',
            project_name='prev-proj',
            workdir=workdir,
            program=program,
        )

        mock_auto.create_or_select_stack.assert_called_once()
        call_kwargs = mock_auto.create_or_select_stack.call_args.kwargs
        assert call_kwargs['stack_name'] == 'prev-stack'
        assert call_kwargs['program'] is program
        mock_stack.preview.assert_called_once()
        assert result is mock_stack

    @patch('pulice.core.stack.automation')
    def test_preview_refreshes(self, mock_auto, tmp_path: Path):
        mock_stack = MagicMock()
        mock_auto.create_or_select_stack.return_value = mock_stack
        mock_auto.LocalWorkspaceOptions = MagicMock()
        mock_auto.ProjectSettings = MagicMock()
        mock_auto.ProjectBackend = MagicMock()

        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))
        workdir = str(tmp_path / 'wd')
        Path(workdir).mkdir()

        ops.preview_stack(
            stack_name='s',
            project_name='p',
            workdir=workdir,
            program=lambda: None,
        )

        call_kwargs = mock_stack.preview.call_args.kwargs
        assert call_kwargs['refresh'] is True

    @patch('pulice.core.stack.automation')
    def test_preview_streams_to_print(self, mock_auto, tmp_path: Path):
        mock_stack = MagicMock()
        mock_auto.create_or_select_stack.return_value = mock_stack
        mock_auto.LocalWorkspaceOptions = MagicMock()
        mock_auto.ProjectSettings = MagicMock()
        mock_auto.ProjectBackend = MagicMock()

        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))
        workdir = str(tmp_path / 'wd')
        Path(workdir).mkdir()

        ops.preview_stack(
            stack_name='s',
            project_name='p',
            workdir=workdir,
            program=lambda: None,
        )

        call_kwargs = mock_stack.preview.call_args.kwargs
        assert call_kwargs['on_output'] is print


class TestStackLifecycleDestroy:
    @patch('pulice.core.stack.automation')
    def test_calls_create_or_select_then_destroy(self, mock_auto, tmp_path: Path):
        mock_stack = MagicMock()
        mock_auto.create_or_select_stack.return_value = mock_stack
        mock_auto.LocalWorkspaceOptions = MagicMock()
        mock_auto.ProjectSettings = MagicMock()
        mock_auto.ProjectBackend = MagicMock()

        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))
        workdir = str(tmp_path / 'wd')
        Path(workdir).mkdir()
        program = MagicMock()

        result = ops.destroy_stack(
            stack_name='destroy-stack',
            project_name='destroy-proj',
            workdir=workdir,
            program=program,
        )

        mock_auto.create_or_select_stack.assert_called_once()
        call_kwargs = mock_auto.create_or_select_stack.call_args.kwargs
        assert call_kwargs['stack_name'] == 'destroy-stack'
        assert call_kwargs['program'] is program
        mock_stack.destroy.assert_called_once()
        assert result is mock_stack

    @patch('pulice.core.stack.automation')
    def test_destroy_refreshes(self, mock_auto, tmp_path: Path):
        mock_stack = MagicMock()
        mock_auto.create_or_select_stack.return_value = mock_stack
        mock_auto.LocalWorkspaceOptions = MagicMock()
        mock_auto.ProjectSettings = MagicMock()
        mock_auto.ProjectBackend = MagicMock()

        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))
        workdir = str(tmp_path / 'wd')
        Path(workdir).mkdir()

        ops.destroy_stack(
            stack_name='s',
            project_name='p',
            workdir=workdir,
            program=lambda: None,
        )

        call_kwargs = mock_stack.destroy.call_args.kwargs
        assert call_kwargs['refresh'] is True

    @patch('pulice.core.stack.automation')
    def test_destroy_streams_to_print(self, mock_auto, tmp_path: Path):
        mock_stack = MagicMock()
        mock_auto.create_or_select_stack.return_value = mock_stack
        mock_auto.LocalWorkspaceOptions = MagicMock()
        mock_auto.ProjectSettings = MagicMock()
        mock_auto.ProjectBackend = MagicMock()

        ops = StackOperations(storage=SqliteBackendStorage(root_dir=str(tmp_path)))
        workdir = str(tmp_path / 'wd')
        Path(workdir).mkdir()

        ops.destroy_stack(
            stack_name='s',
            project_name='p',
            workdir=workdir,
            program=lambda: None,
        )

        call_kwargs = mock_stack.destroy.call_args.kwargs
        assert call_kwargs['on_output'] is print


# ===================================================================
# Full lifecycle: create -> preview -> update -> destroy
# ===================================================================


class TestFullLifecycle:
    """End-to-end scenario verifying the four operations in sequence."""

    @patch('pulice.core.stack.automation')
    def test_create_preview_update_destroy_sequence(self, mock_auto, tmp_path: Path):
        mock_stack = MagicMock()
        mock_auto.create_or_select_stack.return_value = mock_stack
        mock_auto.LocalWorkspaceOptions = MagicMock()
        mock_auto.ProjectSettings = MagicMock()
        mock_auto.ProjectBackend = MagicMock()

        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        ops = StackOperations(storage=storage)

        stack_name = 'lifecycle-stack'
        project_name = 'lifecycle-project'
        workdir = ops.ensure_stack_workspace(stack_name)
        program = lambda: None  # noqa E731

        # 1. Create
        ops.create_or_update_stack(
            stack_name=stack_name,
            project_name=project_name,
            workdir=workdir,
            program=program,
        )
        assert mock_stack.up.call_count == 1

        # Save a reference as the CLI would after create
        _ = ops.save_stack_reference(
            reference_id='lifecycle-ref',
            component_name='mycomp',
            stack_name=stack_name,
            project_name=project_name,
            workdir=workdir,
        )

        # 2. Preview (read)
        ops.preview_stack(
            stack_name=stack_name,
            project_name=project_name,
            workdir=workdir,
            program=program,
        )
        mock_stack.preview.assert_called_once()

        # 3. Update — resolves reference, then runs up again
        loaded = ops.get_stack_reference('lifecycle-ref', expected_component_name='mycomp')
        assert loaded.stack_name == stack_name
        ops.create_or_update_stack(
            stack_name=loaded.stack_name,
            project_name=loaded.project_name,
            workdir=loaded.workdir,
            program=program,
        )
        assert mock_stack.up.call_count == 2

        # 4. Destroy
        ops.destroy_stack(
            stack_name=loaded.stack_name,
            project_name=loaded.project_name,
            workdir=loaded.workdir,
            program=program,
        )
        mock_stack.destroy.assert_called_once()

        # Verify workspace directory still exists (destroy doesn't delete it)
        assert Path(workdir).exists()

    @patch('pulice.core.stack.automation')
    def test_multiple_stacks_isolated(self, mock_auto, tmp_path: Path):
        """Two independent stacks don't interfere with each other."""
        mock_stack_a = MagicMock()
        mock_stack_b = MagicMock()
        mock_auto.create_or_select_stack.side_effect = [mock_stack_a, mock_stack_b]
        mock_auto.LocalWorkspaceOptions = MagicMock()
        mock_auto.ProjectSettings = MagicMock()
        mock_auto.ProjectBackend = MagicMock()

        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        ops = StackOperations(storage=storage)

        wd_a = ops.ensure_stack_workspace('stack-a')
        wd_b = ops.ensure_stack_workspace('stack-b')
        assert wd_a != wd_b

        ops.create_or_update_stack(
            stack_name='stack-a',
            project_name='proj-a',
            workdir=wd_a,
            program=lambda: None,
        )
        ops.create_or_update_stack(
            stack_name='stack-b',
            project_name='proj-b',
            workdir=wd_b,
            program=lambda: None,
        )

        mock_stack_a.up.assert_called_once()
        mock_stack_b.up.assert_called_once()

        # References are independent
        ops.save_stack_reference(
            reference_id='ref-a',
            component_name='comp-a',
            stack_name='stack-a',
            project_name='proj-a',
            workdir=wd_a,
        )
        ops.save_stack_reference(
            reference_id='ref-b',
            component_name='comp-b',
            stack_name='stack-b',
            project_name='proj-b',
            workdir=wd_b,
        )

        loaded_a = ops.get_stack_reference('ref-a')
        loaded_b = ops.get_stack_reference('ref-b')

        assert loaded_a.stack_name == 'stack-a'
        assert loaded_b.stack_name == 'stack-b'
        assert loaded_a.workdir != loaded_b.workdir
