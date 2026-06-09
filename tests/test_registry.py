"""Tests for pulice.cli.registry."""

from __future__ import annotations
from unittest.mock import MagicMock, patch
import pytest
from pydantic import Field
from typer import Typer
from typer.testing import CliRunner
from pulice.core.base import ComponentArgs, ManagedComponent
from typing import Any

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class SimpleArgs(ComponentArgs):
    region: str = Field('us-east-1', description='AWS region.')
    count: int = Field(1, ge=0, description='Instance count.')


class RequiredArgs(ComponentArgs):
    bucket: str = Field(..., description='S3 bucket name.')


@pytest.fixture(autouse=True)
def clear_group_registry():
    from pulice.cli import registry

    registry._group_registry.clear()
    yield
    registry._group_registry.clear()


# ---------------------------------------------------------------------------
# _field_to_typer_option
# ---------------------------------------------------------------------------


class TestFieldToTyperOption:
    def test_option_info_default_holds_option_name(self):
        from pulice.cli.registry import _field_to_typer_option

        field_info = RequiredArgs.model_fields['bucket']
        opt = _field_to_typer_option('bucket', field_info)
        assert opt.default == '--bucket'

    def test_required_field_show_default_false(self):
        from pulice.cli.registry import _field_to_typer_option

        field_info = RequiredArgs.model_fields['bucket']
        opt = _field_to_typer_option('bucket', field_info)
        assert opt.show_default is False

    def test_optional_field_show_default_true(self):
        from pulice.cli.registry import _field_to_typer_option

        field_info = SimpleArgs.model_fields['region']
        opt = _field_to_typer_option('region', field_info)
        assert opt.show_default is True

    def test_option_name_uses_hyphens(self):
        from pulice.cli.registry import _field_to_typer_option

        class HyphenArgs(ComponentArgs):
            node_type_id: str = Field('m4.large')

        field_info = HyphenArgs.model_fields['node_type_id']
        opt = _field_to_typer_option('node_type_id', field_info)
        assert opt.default == '--node-type-id'

    def test_help_text_from_description(self):
        from pulice.cli.registry import _field_to_typer_option

        field_info = SimpleArgs.model_fields['region']
        opt = _field_to_typer_option('region', field_info)
        assert opt.help == 'AWS region.'


# ---------------------------------------------------------------------------
# _build_command
# ---------------------------------------------------------------------------


class TestBuildCommand:
    def test_signature_params_match_model_fields(self):
        import inspect
        from pulice.cli.registry import _build_command

        run = MagicMock()
        cmd = _build_command(SimpleArgs, run, 'create', 'Ctrl.create')
        sig = inspect.signature(cmd)
        assert set(sig.parameters) == {'name', 'region', 'count'}

    def test_required_field_has_empty_default_in_signature(self):
        import inspect
        from pulice.cli.registry import _build_command

        run = MagicMock()
        cmd = _build_command(RequiredArgs, run, 'create', 'Ctrl.create')
        sig = inspect.signature(cmd)
        assert sig.parameters['bucket'].default is inspect.Parameter.empty

    def test_optional_field_has_default_in_signature(self):
        import inspect
        from pulice.cli.registry import _build_command

        run = MagicMock()
        cmd = _build_command(SimpleArgs, run, 'create', 'Ctrl.create')
        sig = inspect.signature(cmd)
        assert sig.parameters['region'].default == 'us-east-1'

    def test_happy_path_calls_run_with_model_instance(self):
        from pulice.cli.registry import _build_command

        captured: list[ComponentArgs] = []

        def run(args: ComponentArgs) -> None:
            captured.append(args)

        cmd = _build_command(SimpleArgs, run, 'create', 'Ctrl.create')
        cmd(name='test', region='eu-west-1', count=2)

        assert len(captured) == 1
        assert captured[0].name == 'test'
        assert captured[0].region == 'eu-west-1'
        assert captured[0].count == 2

    def test_validation_error_exits_with_code_1(self):
        import typer
        from pulice.cli.registry import _build_command

        run = MagicMock()
        cmd = _build_command(SimpleArgs, run, 'create', 'Ctrl.create')

        with pytest.raises(typer.Exit) as exc_info:
            cmd(name='test', region='us-east-1', count=-1)

        assert exc_info.value.exit_code == 1
        run.assert_not_called()

    def test_command_name_set(self):
        from pulice.cli.registry import _build_command

        cmd = _build_command(SimpleArgs, MagicMock(), 'update', 'Ctrl.update')
        assert cmd.__name__ == 'update'


# ---------------------------------------------------------------------------
# ComponentController
# ---------------------------------------------------------------------------


class TestComponentController:
    def _make_controller(self):
        from pulice.core.controllers import ComponentController

        class MyCtrl(ComponentController):
            args_model = SimpleArgs

        return MyCtrl

    def test_create_raises_not_implemented(self):
        ctrl_cls = self._make_controller()
        ctrl = ctrl_cls(SimpleArgs(name='x'))
        with pytest.raises(NotImplementedError):
            ctrl.create()

    def test_read_raises_not_implemented(self):
        ctrl_cls = self._make_controller()
        ctrl = ctrl_cls(SimpleArgs(name='x'))
        with pytest.raises(NotImplementedError):
            ctrl.read()

    def test_update_raises_not_implemented(self):
        ctrl_cls = self._make_controller()
        ctrl = ctrl_cls(SimpleArgs(name='x'))
        with pytest.raises(NotImplementedError):
            ctrl.update()

    def test_delete_raises_not_implemented(self):
        ctrl_cls = self._make_controller()
        ctrl = ctrl_cls(SimpleArgs(name='x'))
        with pytest.raises(NotImplementedError):
            ctrl.delete()

    def test_args_stored_on_instance(self):
        ctrl_cls = self._make_controller()
        args = SimpleArgs(name='stored')
        ctrl = ctrl_cls(args)
        assert ctrl._args is args

    def test_overriding_create_works(self):
        from pulice.core.controllers import ComponentController

        results: list[str] = []

        class MyCtrl(ComponentController):
            args_model = SimpleArgs

            def create(self) -> None:
                results.append(self._args.name)

        ctrl = MyCtrl(SimpleArgs(name='invoked'))
        ctrl.create()
        assert results == ['invoked']


# ---------------------------------------------------------------------------
# WorkspaceController
# ---------------------------------------------------------------------------


class TestWorkspaceController:
    def _make_ws_controller(self):
        from pulice.core.controllers import WorkspaceController

        class ConcreteCtrl(WorkspaceController):
            def _make_provider(self) -> Any:
                return MagicMock()

        return ConcreteCtrl

    def _make_resource_cls(self):
        class MyArgs(ComponentArgs):
            pass

        class MyResource(ManagedComponent):
            args_model = MyArgs

        return MyResource, MyArgs

    @patch('pulice.core.stack.StackOperations')
    def test_make_provider_abstract(self, _mock_stack_ops):
        from pulice.core.controllers import WorkspaceController

        with pytest.raises(TypeError):
            WorkspaceController(MagicMock(), SimpleArgs(name='x'))  # type: ignore[abstract]

    @patch('pulice.core.stack.StackOperations')
    def test_stack_name_format(self, _mock_stack_ops):
        ctrl_cls = self._make_ws_controller()
        resource_cls, args_cls = self._make_resource_cls()
        args = args_cls(name='myresource')
        ctrl = ctrl_cls(resource_cls, args)
        expected = 'concretectrl-myresource-myresource'
        assert ctrl._stack_name() == expected

    @patch('pulice.core.stack.StackOperations')
    def test_project_name_format(self, _mock_stack_ops):
        ctrl_cls = self._make_ws_controller()
        resource_cls, args_cls = self._make_resource_cls()
        ctrl = ctrl_cls(resource_cls, args_cls(name='x'))
        assert ctrl._project_name() == 'pulice-myresource'

    @patch('pulice.core.stack.StackOperations')
    def test_create_calls_create_or_update_stack(self, mock_stack_ops_cls):
        mock_ops = MagicMock()
        mock_ops.ensure_stack_workspace.return_value = '/tmp/fake'
        mock_stack_ops_cls.return_value = mock_ops

        ctrl_cls = self._make_ws_controller()
        resource_cls, args_cls = self._make_resource_cls()
        ctrl = ctrl_cls(resource_cls, args_cls(name='dp'))
        ctrl.create()

        mock_ops.create_or_update_stack.assert_called_once()
        call_kwargs = mock_ops.create_or_update_stack.call_args.kwargs
        assert call_kwargs['stack_name'] == ctrl._stack_name()
        assert call_kwargs['project_name'] == ctrl._project_name()
        assert call_kwargs['workdir'] == '/tmp/fake'

    @patch('pulice.core.stack.StackOperations')
    def test_read_calls_preview_stack(self, mock_stack_ops_cls):
        mock_ops = MagicMock()
        mock_ops.ensure_stack_workspace.return_value = '/tmp/fake'
        mock_stack_ops_cls.return_value = mock_ops

        ctrl_cls = self._make_ws_controller()
        resource_cls, args_cls = self._make_resource_cls()
        ctrl = ctrl_cls(resource_cls, args_cls(name='dp'))
        ctrl.read()

        mock_ops.preview_stack.assert_called_once()

    @patch('pulice.core.stack.StackOperations')
    def test_delete_calls_destroy_stack(self, mock_stack_ops_cls):
        mock_ops = MagicMock()
        mock_ops.ensure_stack_workspace.return_value = '/tmp/fake'
        mock_stack_ops_cls.return_value = mock_ops

        ctrl_cls = self._make_ws_controller()
        resource_cls, args_cls = self._make_resource_cls()
        ctrl = ctrl_cls(resource_cls, args_cls(name='dp'))
        ctrl.delete()

        mock_ops.destroy_stack.assert_called_once()


# ---------------------------------------------------------------------------
# register_component
# ---------------------------------------------------------------------------


class TestRegisterComponent:
    def _make_controller(self, implemented: frozenset[str] = frozenset()):
        from pulice.core.controllers import ComponentController

        results: list[str] = []

        class MyCtrl(ComponentController):
            args_model = SimpleArgs

            def create(self) -> None:
                if 'create' not in implemented:
                    raise NotImplementedError
                results.append('create')

            def read(self) -> None:
                if 'read' not in implemented:
                    raise NotImplementedError
                results.append('read')

            def update(self) -> None:
                if 'update' not in implemented:
                    raise NotImplementedError
                results.append('update')

            def delete(self) -> None:
                if 'delete' not in implemented:
                    raise NotImplementedError
                results.append('delete')

        return MyCtrl, results

    def test_all_four_commands_registered(self):
        from pulice.cli.registry import register_component

        app = Typer()
        ctrl_cls, _ = self._make_controller()
        register_component(app, ctrl_cls, name='thing')

        result = runner.invoke(app, ['thing', '--help'])
        for op in ('create', 'read', 'update', 'delete'):
            assert op in result.output

    def test_option_names_from_model_fields(self):
        from pulice.cli.registry import register_component

        app = Typer()
        ctrl_cls, _ = self._make_controller()
        register_component(app, ctrl_cls, name='thing')

        result = runner.invoke(app, ['thing', 'create', '--help'])
        assert '--name' in result.output
        assert '--region' in result.output
        assert '--count' in result.output

    def test_validation_error_exits_1(self):
        from pulice.cli.registry import register_component

        app = Typer()
        ctrl_cls, _ = self._make_controller(implemented=frozenset({'create'}))
        register_component(app, ctrl_cls, name='thing')

        result = runner.invoke(app, ['thing', 'create', '--name', 'x', '--count', '-1'])
        assert result.exit_code == 1

    def test_not_implemented_exits_2(self):
        from pulice.cli.registry import register_component

        app = Typer()
        ctrl_cls, _ = self._make_controller()
        register_component(app, ctrl_cls, name='thing')

        result = runner.invoke(app, ['thing', 'create', '--name', 'x'])
        assert result.exit_code == 2

    def test_missing_args_model_raises_attribute_error(self):
        from pulice.cli.registry import register_component
        from pulice.core.controllers import ComponentController

        class NoModel(ComponentController):
            pass

        app = Typer()
        with pytest.raises(AttributeError):
            register_component(app, NoModel, name='bad')  # type: ignore[arg-type]

    def test_group_help_shown(self):
        from pulice.cli.registry import register_component

        app = Typer()
        ctrl_cls, _ = self._make_controller()
        register_component(app, ctrl_cls, name='thing', help='Custom help text.')

        result = runner.invoke(app, ['thing', '--help'])
        assert 'Custom help text.' in result.output


# ---------------------------------------------------------------------------
# register_resource
# ---------------------------------------------------------------------------


class TestRegisterResource:
    def _make_workspace_controller(self):
        from pulice.core.controllers import WorkspaceController

        class ConcreteCtrl(WorkspaceController):
            def _make_provider(self) -> Any:
                return MagicMock()

            def create(self) -> None:
                pass

            def read(self) -> None:
                pass

            def update(self) -> None:
                pass

            def delete(self) -> None:
                pass

        return ConcreteCtrl

    def _make_resource(self, name: str = 'MyResource') -> type[ManagedComponent]:
        class MyArgs(ComponentArgs):
            env: str = Field('dev', description='Environment.')

        resource = type(
            name,
            (ManagedComponent,),
            {'args_model': MyArgs},
        )
        return resource  # type: ignore[return-value]

    @patch('pulice.core.stack.StackOperations')
    def test_resource_sub_commands_are_registered(self, _mock):
        from pulice.cli.registry import register_resource

        ctrl_cls = self._make_workspace_controller()
        resource_cls = self._make_resource()
        app = Typer()

        register_resource(app, resource_cls, ctrl_cls, group='mygroup', name='my-resource')

        result = runner.invoke(app, ['mygroup', 'my-resource', '--help'])
        for op in ('create', 'read', 'update', 'delete'):
            assert op in result.output

    @patch('pulice.core.stack.StackOperations')
    def test_options_derived_from_resource_args_model(self, _mock):
        from pulice.cli.registry import register_resource

        ctrl_cls = self._make_workspace_controller()
        resource_cls = self._make_resource()
        app = Typer()

        register_resource(app, resource_cls, ctrl_cls, group='mygroup', name='my-resource')

        result = runner.invoke(app, ['mygroup', 'my-resource', 'create', '--help'])
        assert '--name' in result.output
        assert '--env' in result.output

    @patch('pulice.core.stack.StackOperations')
    def test_second_resource_reuses_group(self, _mock):
        from pulice.cli import registry
        from pulice.cli.registry import register_resource

        ctrl_cls = self._make_workspace_controller()
        res1 = self._make_resource('ResA')
        res2 = self._make_resource('ResB')
        app = Typer()

        register_resource(app, res1, ctrl_cls, group='shared', name='res-a')
        register_resource(app, res2, ctrl_cls, group='shared', name='res-b')

        group_key = ('shared', ctrl_cls)
        assert group_key in registry._group_registry

        result = runner.invoke(app, ['shared', '--help'])
        assert 'res-a' in result.output
        assert 'res-b' in result.output

    @patch('pulice.core.stack.StackOperations')
    def test_missing_args_model_raises(self, _mock):
        from pulice.cli.registry import register_resource

        class BareResource(ManagedComponent):
            pass

        ctrl_cls = self._make_workspace_controller()
        app = Typer()

        with pytest.raises(AttributeError):
            register_resource(app, BareResource, ctrl_cls, group='x', name='bare')  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# register managed component (ManagedComponent via register_component)
# ---------------------------------------------------------------------------


class TestRegisterManagedComponent:
    def _make_component(self) -> type[ManagedComponent]:
        class ManagedArgs(ComponentArgs):
            region: str = Field('us-east-1', description='AWS region.')

        class DemoComponent(ManagedComponent):
            args_model = ManagedArgs

        return DemoComponent

    def test_create_uses_args_model_not_stack_reference(self):
        from pulice.cli.registry import register_component

        app = Typer()
        component_cls = self._make_component()
        register_component(app, component_cls, name='demo')

        result = runner.invoke(app, ['demo', 'create', '--help'])
        assert '--name' in result.output
        assert '--region' in result.output
        assert '--passphrase' in result.output
        assert '--tenant' in result.output
        assert '--stack-reference' not in result.output

    def test_delete_requires_stack_reference_not_args_model(self):
        from pulice.cli.registry import register_component

        app = Typer()
        component_cls = self._make_component()
        register_component(app, component_cls, name='demo')

        result = runner.invoke(app, ['demo', 'delete', '--help'])
        assert '--stack-reference' in result.output
        assert '--passphrase' in result.output
        assert '--tenant' in result.output
        assert '--name' not in result.output
        assert '--region' not in result.output

    def test_update_requires_stack_reference_and_args(self):
        from pulice.cli.registry import register_component

        app = Typer()
        component_cls = self._make_component()
        register_component(app, component_cls, name='demo')

        result = runner.invoke(
            app,
            [
                'demo',
                'update',
                '--stack-reference',
                'ref-1',
                '--passphrase',
                'secret',
                '--tenant',
                'acme',
            ],
        )
        assert result.exit_code != 0

    @patch('pulice.core.stack.StackOperations')
    def test_create_saves_stack_reference_and_echoes_it(self, mock_stack_ops_cls, tmp_path):
        from pulice.cli.registry import register_component
        from pulice.core.stack import SqliteBackendStorage

        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        storage.create_tenant('acme')

        mock_ops = MagicMock()
        mock_ops.ensure_stack_workspace.return_value = '/tmp/fake-stack-dir'
        mock_ops.storage = storage
        mock_stack_ops_cls.return_value = mock_ops

        app = Typer()
        component_cls = self._make_component()
        register_component(app, component_cls, name='demo')

        result = runner.invoke(
            app,
            [
                'demo',
                'create',
                '--name',
                'example',
                '--region',
                'eu-west-1',
                '--passphrase',
                'secret',
                '--tenant',
                'acme',
            ],
        )

        assert result.exit_code == 0, result.output
        assert 'Stack reference:' in result.output
        mock_ops.save_stack_reference.assert_called_once()

    @patch('pulice.core.stack.StackOperations')
    def test_update_and_delete_resolve_stack_reference(self, mock_stack_ops_cls, tmp_path):
        from pulice.cli.registry import register_component
        from pulice.core.stack import SqliteBackendStorage

        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        storage.create_tenant('acme')

        mock_ops = MagicMock()
        mock_ops.storage = storage
        mock_ops.get_stack_reference.return_value = MagicMock(
            stack_name='democomponent-ref-1',
            project_name='pulice-democomponent',
            workdir='/tmp/ref-workdir',
        )
        mock_stack_ops_cls.return_value = mock_ops

        app = Typer()
        component_cls = self._make_component()
        register_component(app, component_cls, name='demo')

        update_result = runner.invoke(
            app,
            [
                'demo',
                'update',
                '--name',
                'example',
                '--region',
                'eu-west-1',
                '--stack-reference',
                'ref-1',
                '--passphrase',
                'secret',
                '--tenant',
                'acme',
            ],
        )
        delete_result = runner.invoke(
            app,
            [
                'demo',
                'delete',
                '--stack-reference',
                'ref-1',
                '--passphrase',
                'secret',
                '--tenant',
                'acme',
            ],
        )

        assert update_result.exit_code == 0, update_result.output
        assert delete_result.exit_code == 0, delete_result.output
        assert mock_ops.get_stack_reference.call_count == 2
        mock_ops.create_or_update_stack.assert_called_once()
        mock_ops.destroy_stack.assert_called_once()

    def test_list_command_registered(self):
        from pulice.cli.registry import MANAGED_COMPONENT_OPERATIONS, register_component

        app = Typer()
        component_cls = self._make_component()
        register_component(app, component_cls, name='demo', operations=MANAGED_COMPONENT_OPERATIONS)

        result = runner.invoke(app, ['demo', 'list', '--help'])
        assert '--tenant' in result.output
        assert '--passphrase' not in result.output

    def test_refresh_command_registered(self):
        from pulice.cli.registry import MANAGED_COMPONENT_OPERATIONS, register_component

        app = Typer()
        component_cls = self._make_component()
        register_component(app, component_cls, name='demo', operations=MANAGED_COMPONENT_OPERATIONS)

        result = runner.invoke(app, ['demo', 'refresh', '--help'])
        assert '--tenant' in result.output
        assert '--stack-reference' in result.output
        assert '--passphrase' in result.output

    def test_status_command_registered(self):
        from pulice.cli.registry import MANAGED_COMPONENT_OPERATIONS, register_component

        app = Typer()
        component_cls = self._make_component()
        register_component(app, component_cls, name='demo', operations=MANAGED_COMPONENT_OPERATIONS)

        result = runner.invoke(app, ['demo', 'status', '--help'])
        assert '--tenant' in result.output
        assert '--stack-reference' in result.output

    def test_export_command_registered(self):
        from pulice.cli.registry import MANAGED_COMPONENT_OPERATIONS, register_component

        app = Typer()
        component_cls = self._make_component()
        register_component(app, component_cls, name='demo', operations=MANAGED_COMPONENT_OPERATIONS)

        result = runner.invoke(app, ['demo', 'export', '--help'])
        assert '--tenant' in result.output
        assert '--output' in result.output

    def test_import_command_registered(self):
        from pulice.cli.registry import MANAGED_COMPONENT_OPERATIONS, register_component

        app = Typer()
        component_cls = self._make_component()
        register_component(app, component_cls, name='demo', operations=MANAGED_COMPONENT_OPERATIONS)

        result = runner.invoke(app, ['demo', 'import', '--help'])
        assert '--tenant' in result.output
        assert '--input' in result.output

    @patch('pulice.core.stack.StackOperations')
    def test_passphrase_validation_rejects_wrong_passphrase(self, mock_stack_ops_cls, tmp_path):
        from pulice.cli.registry import register_component
        from pulice.core.stack import PassphraseHasher, SqliteBackendStorage

        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        storage.create_tenant('acme')
        storage.ensure_stack_dir('democomponent-ref-1')
        storage.save_passphrase_hash('democomponent-ref-1', PassphraseHasher.hash('correct'))

        mock_ops = MagicMock()
        mock_ops.storage = storage
        mock_ops.get_stack_reference.return_value = MagicMock(
            stack_name='democomponent-ref-1',
            project_name='pulice-democomponent',
            workdir='/tmp/ref-workdir',
        )
        mock_stack_ops_cls.return_value = mock_ops

        app = Typer()
        component_cls = self._make_component()
        register_component(app, component_cls, name='demo')

        result = runner.invoke(
            app,
            [
                'demo',
                'delete',
                '--stack-reference',
                'ref-1',
                '--passphrase',
                'wrong',
                '--tenant',
                'acme',
            ],
        )

        assert result.exit_code == 1
        assert 'Invalid passphrase' in result.output

    @patch('pulice.core.stack.StackOperations')
    def test_unknown_tenant_fails(self, mock_stack_ops_cls, tmp_path):
        from pulice.cli.registry import register_component
        from pulice.core.stack import SqliteBackendStorage

        storage = SqliteBackendStorage(root_dir=str(tmp_path))
        mock_ops = MagicMock()
        mock_ops.storage = storage
        mock_stack_ops_cls.return_value = mock_ops

        app = Typer()
        component_cls = self._make_component()
        register_component(app, component_cls, name='demo')

        result = runner.invoke(
            app,
            [
                'demo',
                'create',
                '--name',
                'x',
                '--passphrase',
                'secret',
                '--tenant',
                'nonexistent',
            ],
        )

        assert result.exit_code == 1
        assert 'not found' in result.output
