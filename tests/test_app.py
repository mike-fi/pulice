"""Tests for pulice.cli.app — PuliceApp protocol and PuliceCLI."""

import pytest
from pydantic import Field
from typer import Typer
from typer.testing import CliRunner
from pulice.cli.app import PuliceCLI
from pulice.core.base import ComponentArgs, ManagedComponent
from pulice.core.controllers import ComponentController
from pulice.core.protocol import PuliceApp
from typing import Any

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class SimpleArgs(ComponentArgs):
    region: str = Field('us-east-1', description='AWS region.')


class SimpleController(ComponentController):
    args_model = SimpleArgs

    def create(self) -> None:
        pass


# ---------------------------------------------------------------------------
# PuliceCLI
# ---------------------------------------------------------------------------


class TestPuliceCLI:
    def test_accepts_typer_app(self):
        cli = PuliceCLI(Typer(name='test'))
        assert isinstance(cli.app, Typer)

    def test_rejects_non_typer(self):
        with pytest.raises(TypeError, match='PuliceCLI only supports Typer apps'):
            PuliceCLI('not a typer')  # type: ignore[arg-type]

    def test_satisfies_protocol(self):
        cli = PuliceCLI(Typer())
        assert isinstance(cli, PuliceApp)

    def test_register_component_with_controller(self):
        cli = PuliceCLI(Typer(name='test'))
        cli.register_component(SimpleController, name='simple')
        # No error raised — commands registered successfully.

    def test_register_component_with_managed_component(self):
        class MyComponent(ManagedComponent):
            args_model = SimpleArgs

        cli = PuliceCLI(Typer(name='test'))
        cli.register_component(MyComponent, name='my-comp')

    def test_callable(self):
        """PuliceCLI instances are callable (delegates to Typer)."""
        cli = PuliceCLI(Typer(name='test'))
        assert callable(cli)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_pulice_cli_is_runtime_checkable(self):
        assert isinstance(PuliceCLI(Typer()), PuliceApp)

    def test_arbitrary_object_not_conforming(self):
        assert not isinstance('hello', PuliceApp)

    def test_custom_implementation_conforms(self):
        """A duck-typed object satisfying the protocol passes isinstance."""

        class CustomApp:
            def __call__(self, *args: Any, **kwargs: Any) -> Any:
                pass

            def register_resource(self, resource_cls, controller_cls, **kw) -> None:
                pass

            def register_component(self, component_cls, name, **kw) -> None:
                pass

        assert isinstance(CustomApp(), PuliceApp)


# ---------------------------------------------------------------------------
# Tenant CLI commands
# ---------------------------------------------------------------------------


class TestTenantCommands:
    def test_tenant_create(self, tmp_path, monkeypatch):
        monkeypatch.setenv('PULICE_STATE_DIR', str(tmp_path))
        cli = PuliceCLI(Typer(name='pulice'))
        result = runner.invoke(cli.app, ['tenant', 'create', '--name', 'acme'])
        assert result.exit_code == 0
        assert 'Tenant created: acme' in result.output

    def test_tenant_create_duplicate_fails(self, tmp_path, monkeypatch):
        monkeypatch.setenv('PULICE_STATE_DIR', str(tmp_path))
        cli = PuliceCLI(Typer(name='pulice'))
        runner.invoke(cli.app, ['tenant', 'create', '--name', 'acme'])
        result = runner.invoke(cli.app, ['tenant', 'create', '--name', 'acme'])
        assert result.exit_code == 1
        assert 'already exists' in result.output

    def test_tenant_list(self, tmp_path, monkeypatch):
        monkeypatch.setenv('PULICE_STATE_DIR', str(tmp_path))
        cli = PuliceCLI(Typer(name='pulice'))
        runner.invoke(cli.app, ['tenant', 'create', '--name', 'acme'])
        result = runner.invoke(cli.app, ['tenant', 'list'])
        assert result.exit_code == 0
        assert 'default' in result.output
        assert 'acme' in result.output

    def test_tenant_delete(self, tmp_path, monkeypatch):
        monkeypatch.setenv('PULICE_STATE_DIR', str(tmp_path))
        cli = PuliceCLI(Typer(name='pulice'))
        runner.invoke(cli.app, ['tenant', 'create', '--name', 'disposable'])
        result = runner.invoke(cli.app, ['tenant', 'delete', '--name', 'disposable'])
        assert result.exit_code == 0
        assert 'Tenant deleted' in result.output

    def test_tenant_delete_nonexistent_fails(self, tmp_path, monkeypatch):
        monkeypatch.setenv('PULICE_STATE_DIR', str(tmp_path))
        cli = PuliceCLI(Typer(name='pulice'))
        result = runner.invoke(cli.app, ['tenant', 'delete', '--name', 'ghost'])
        assert result.exit_code == 1
        assert 'not found' in result.output
