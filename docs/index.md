# Pulice

Pulice is a Python framework for managing infrastructure-as-code components through a unified interface. Define your cloud resources as Pulumi components, register them with pulice, and get a full CLI and HTTP API with tenant isolation, passphrase-protected secrets, async execution, and pluggable task backends — all without writing boilerplate.

## Features

- **Provider-agnostic** — Works with any Pulumi provider (AWS, GCP, Azure, Kubernetes, etc.)
- **Tenant isolation** — Named boundaries that own stacks, preventing cross-tenant access
- **Full lifecycle management** — Create, read, update, delete, refresh, status, export, import operations out of the box
- **Dual interface** — Synchronous CLI for interactive use, async HTTP API for automation
- **Passphrase-protected stacks** — Validates passphrases before operations, with clear error messages
- **Pluggable task backends** — SQLite-backed Huey (default) or Redis-backed Celery for distributed deployments
- **Concurrency-safe** — SQLite-backed advisory locks prevent concurrent stack mutations

## Quick Install

```bash
pip install pulice
```

For AWS provider support:

```bash
pip install pulice[aws]
```

For the HTTP API and task worker:

```bash
pip install pulice[api]
```

## Quick Example

```python
from pydantic import Field
from pulice import ComponentArgs, ManagedComponent, PuliceCLI
from typer import Typer

class BucketArgs(ComponentArgs):
    region: str = Field("us-east-1", description="AWS region.")

class Bucket(ManagedComponent):
    args_model = BucketArgs

    def __init__(self, name, args, opts=None):
        super().__init__("my:Bucket", name, {}, opts)
        # Provision resources here using any Pulumi provider

app = Typer()
cli = PuliceCLI(app)
cli.register_component(Bucket, name="bucket")

if __name__ == "__main__":
    cli()
```

```bash
pulice tenant create --name dev
pulice bucket create --name my-bucket --region eu-west-1 --tenant dev --passphrase secret
```

## Next Steps

- [Get Started](get-started/index.md) — Install pulice and build your first component
- [Concepts](get-started/concepts.md) — Understand the mental model
- [CLI Guide](guide/cli.md) — Full CLI usage reference
- [API Reference](reference/index.md) — Auto-generated Python API docs
