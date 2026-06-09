# Core Module

The `pulice.core` package contains the framework's foundation: base classes, stack operations, storage backends, locking, and task execution.

## Base Classes

::: pulice.core.base
    options:
      members:
        - ComponentArgs
        - ManagedComponent

## Stack Operations & Storage

::: pulice.core.stack
    options:
      members:
        - Tenant
        - StackReference
        - PassphraseHasher
        - StackLock
        - StackLockError
        - BackendStorage
        - SqliteBackendStorage
        - LocalStackReferenceStore
        - StackOperations

## Managed Component Helpers

::: pulice.core.managed
    options:
      members:
        - ManagedStackContext
        - resolve_component_class
        - resolve_managed_stack_context
        - build_managed_program
        - managed_component_operation_model

## Task Execution

::: pulice.core.tasks
    options:
      members:
        - TaskStatus
        - TaskResult
        - TaskBackend
        - HueyTaskBackend
        - create_huey_instance
        - get_task_backend

## Controllers

::: pulice.core.controllers
    options:
      members:
        - WorkspaceController
        - ComponentController
