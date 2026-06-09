# Your First Component

This tutorial walks through building a complete managed component from scratch.

## 1. Project Setup

```bash
mkdir my-infra && cd my-infra
uv init
uv add pulice pulice[aws]
```

## 2. Define Your Args Model

Create `components.py`:

```python
from pydantic import Field
from pulice import ComponentArgs, ManagedComponent
import pulumi
import pulumi_aws as aws


class LogGroupArgs(ComponentArgs):
    """Arguments for a CloudWatch Log Group."""

    retention_days: int = Field(14, description="Log retention in days.")
    region: str = Field("us-east-1", description="AWS region.")
```

## 3. Define Your Component

```python
class LogGroup(ManagedComponent):
    """A managed CloudWatch Log Group."""

    args_model = LogGroupArgs

    def __init__(self, name, args, opts=None):
        super().__init__("myinfra:LogGroup", name, {}, opts)

        self.log_group = aws.cloudwatch.LogGroup(
            f"{name}-logs",
            name=f"/myinfra/{args.name}",
            retention_in_days=args.retention_days,
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.register_outputs({"arn": self.log_group.arn})
```

## 4. Register and Create the CLI

Create `app.py`:

```python
from typer import Typer
from pulice import PuliceCLI
from pulice.cli import MANAGED_COMPONENT_OPERATIONS
from components import LogGroup

app = Typer(name="myinfra")
cli = PuliceCLI(app)
cli.register_component(
    LogGroup,
    name="log-group",
    operations=MANAGED_COMPONENT_OPERATIONS,
)

if __name__ == "__main__":
    cli()
```

## 5. Use It

### Create a tenant

```bash
python app.py tenant create --name dev
```

### Create a stack

```bash
python app.py log-group create \
    --name my-app-logs \
    --retention-days 30 \
    --tenant dev \
    --passphrase my-secret
```

Output:

```
Stack reference: a1b2c3d4e5f67890...
```

### Check status

```bash
python app.py log-group status \
    --stack-reference a1b2c3d4e5f67890 \
    --tenant dev \
    --passphrase my-secret
```

### Update

```bash
python app.py log-group update \
    --name my-app-logs \
    --retention-days 7 \
    --stack-reference a1b2c3d4e5f67890 \
    --tenant dev \
    --passphrase my-secret
```

### Delete

```bash
python app.py log-group delete \
    --stack-reference a1b2c3d4e5f67890 \
    --tenant dev \
    --passphrase my-secret
```

## 6. What Happened Under the Hood

1. `register_component` introspected `LogGroupArgs` and generated CLI commands for all 9 operations with the correct options.
2. On `create`, pulice resolved the tenant, generated a stack reference UUID, created a working directory, hashed the passphrase, acquired a lock, and ran `pulumi up` via the Automation API.
3. The stack reference was saved as a JSON file so subsequent operations can find the stack.
4. On `delete`, pulice verified the passphrase, acquired a lock, ran `pulumi destroy`, and cleaned up.

## Next Steps

- [CLI Guide](../guide/cli.md) — All available commands and options
- [Stack Operations](../guide/stack-operations.md) — The 9 lifecycle operations in detail
- [HTTP API](../guide/api.md) — Expose your components over HTTP
