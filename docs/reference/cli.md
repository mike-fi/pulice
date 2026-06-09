# CLI Module

The `pulice.cli` package provides the Typer-based command-line interface and component registration system.

## Application

::: pulice.cli.app
    options:
      members:
        - PuliceCLI

## Registration Helpers

::: pulice.cli.registry
    options:
      members:
        - register_resource
        - register_component
        - register_tenant_commands
        - MANAGED_COMPONENT_OPERATIONS
