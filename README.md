# Pulice

A Python framework for managing infrastructure-as-code components via [Pulumi](https://www.pulumi.com/) with tenant isolation, async execution, and pluggable backends.

## Features

- **Component model** — Define cloud resources as `ManagedComponent` subclasses with Pydantic-validated inputs
- **Tenant isolation** — Named boundaries ensure stacks belonging to different environments never collide
- **9 lifecycle operations** — create, read, update, delete, refresh, list, status, export, import
- **CLI + HTTP API** — Synchronous CLI for interactive use; async FastAPI server for automation
- **Pluggable task backends** — Huey (SQLite, zero-dep) or Celery (Redis, distributed)
- **Passphrase-protected stacks** — scrypt-hashed passphrases validated before any Pulumi call
- **Advisory locking** — Prevents concurrent mutating operations on the same stack
- **Provider-agnostic** — Works with any Pulumi provider (AWS, GCP, Azure, Kubernetes, etc.)

## Installation

```bash
pip install pulice
```

With optional extras:

```bash
pip install pulice[api]      # FastAPI server + Huey worker
pip install pulice[celery]   # Celery backend for distributed deployments
pip install pulice[aws]      # AWS provider
```

## Quick Start

Define a component:

```python
from pulice import ComponentArgs, ManagedComponent
from pydantic import Field
import pulumi
import pulumi_aws as aws

class BucketArgs(ComponentArgs):
    region: str = Field(description="AWS region")

class Bucket(ManagedComponent):
    args_model = BucketArgs

    def __init__(self, name: str, args: BucketArgs, opts=None, **kwargs):
        super().__init__("pulice:aws:Bucket", name, {}, opts)
        aws.s3.BucketV2(f"{name}-bucket", opts=pulumi.ResourceOptions(parent=self))
```

Register and run:

```python
from typer import Typer
from pulice import PuliceCLI

app = Typer()
cli = PuliceCLI(app)
cli.register_component(Bucket, name="bucket")

if __name__ == "__main__":
    cli()
```

Use it:

```bash
pulice tenant create --name dev
pulice bucket create --name my-data --region eu-west-1 --tenant dev --passphrase secret
pulice bucket list --tenant dev
pulice bucket delete --stack-reference <ref> --tenant dev --passphrase secret
```

## HTTP API

```bash
pip install pulice[api]
uvicorn pulice.api:create_api --factory --host 0.0.0.0 --port 8000
huey_consumer pulice.worker.huey -w 2 -k process
```

Submit operations asynchronously:

```bash
curl -X POST http://localhost:8000/stacks/operations \
  -H "Content-Type: application/json" \
  -d '{"component_class": "myapp.Bucket", "operation": "create", "tenant": "dev", "passphrase": "secret", "args": {"name": "my-data", "region": "eu-west-1"}}'
```

## Documentation

Full documentation is available at the [project site](https://your-org.github.io/pulice/) or can be built locally:

```bash
pip install pulice[docs]
zensical serve
```

## License

[MIT](LICENSE) — Mike Fischer and Dani Vela Calderón
