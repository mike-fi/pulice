# Core Concepts

Pulice provides a thin framework on top of Pulumi's Automation API. Understanding these concepts will help you use it effectively.

## ManagedComponent

A `ManagedComponent` is a Pulumi `ComponentResource` subclass that declares its inputs through a Pydantic model. Pulice introspects this model to automatically generate CLI options, API request schemas, and validation logic.

```python
class Bucket(ManagedComponent):
    args_model = BucketArgs

    def __init__(self, name, args, opts=None):
        super().__init__("myapp:Bucket", name, {}, opts)
        # Create child resources here
```

## ComponentArgs

The Pydantic base class for all component inputs. Every subclass gets a required `name` field automatically. Additional fields become CLI options and API parameters.

```python
class BucketArgs(ComponentArgs):
    region: str = Field("us-east-1", description="AWS region.")
    versioning: bool = Field(False, description="Enable versioning.")
```

## Tenant

A named isolation boundary that owns zero or more stacks. Tenants prevent naming collisions and enforce ownership — a stack created under tenant "production" cannot be accessed with tenant "staging".

```
pulice tenant create --name production
pulice tenant create --name staging
```

## Stack

A Pulumi stack instance tied to a specific tenant and component. Stacks are named `{tenant_id}-{component_name}-{uuid}` to ensure uniqueness. Each stack has its own state, working directory, and passphrase.

## Stack Reference

A UUID handle returned when you create a stack. Use it to refer to the stack in subsequent operations (read, update, delete, refresh, etc.).

```
$ pulice bucket create --name my-bucket --tenant dev --passphrase secret
Stack reference: a1b2c3d4e5f6...
```

## Passphrase

A secret that protects the Pulumi encryption key for a stack. Pulice hashes the passphrase at creation time and validates it before every subsequent operation, giving clear error messages instead of cryptic Pulumi failures.

## StackLock

An SQLite-backed advisory lock that prevents concurrent mutating operations on the same stack. If two processes try to update the same stack simultaneously, the second one waits (with exponential backoff) or times out with a clear error.

## TaskBackend

An abstraction for async task execution. The CLI runs operations synchronously. The HTTP API submits operations to a task queue and returns immediately with a task ID.

| Backend | Transport | Best for |
|---------|-----------|----------|
| Huey (default) | SQLite | Single-machine deployments |
| Celery | Redis/RabbitMQ | Distributed, multi-worker deployments |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Component Authors                         │
│  Define ManagedComponent + ComponentArgs subclasses          │
└─────────────────────┬───────────────────────────────────────┘
                      │ register_component()
                      ▼
┌──────────────┐              ┌──────────────┐
│  PuliceCLI   │              │  PuliceAPI   │
│  (Typer)     │              │  (FastAPI)   │
│  synchronous │              │  async       │
└──────┬───────┘              └──────┬───────┘
       │                             │
       │    direct call              │    TaskBackend.submit()
       ▼                             ▼
┌──────────────────────────────────────────────┐
│              StackOperations                   │
│  Tenant validation, passphrase check,         │
│  StackLock, Pulumi Automation API calls       │
└──────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│         Pulumi Automation API                 │
│  create_or_select_stack, up, preview,         │
│  destroy, refresh, export, import             │
└──────────────────────────────────────────────┘
```
