# CLI Usage

Pulice generates a full CLI from your registered components using [Typer](https://typer.tiangolo.com/).

## Tenant Commands

Built-in commands available on every `PuliceCLI` instance:

```bash
# Create a tenant
pulice tenant create --name <tenant-name>

# List all tenants
pulice tenant list

# Delete a tenant (must have no stacks)
pulice tenant delete --name <tenant-name>
```

## Component Commands

When you register a `ManagedComponent`, pulice generates commands for all lifecycle operations:

```bash
pulice <component> create    --name <n> --tenant <t> --passphrase <p> [resource fields...]
pulice <component> read      --stack-reference <ref> --tenant <t> --passphrase <p>
pulice <component> update    --name <n> --stack-reference <ref> --tenant <t> --passphrase <p> [resource fields...]
pulice <component> delete    --stack-reference <ref> --tenant <t> --passphrase <p>
pulice <component> refresh   --stack-reference <ref> --tenant <t> --passphrase <p>
pulice <component> list      --tenant <t>
pulice <component> status    --stack-reference <ref> --tenant <t> --passphrase <p>
pulice <component> export    --stack-reference <ref> --tenant <t> --passphrase <p> [--output <file>]
pulice <component> import    --stack-reference <ref> --tenant <t> --passphrase <p> --input <file>
```

## Common Options

| Option | Required | Description |
|--------|----------|-------------|
| `--tenant` | Always | Tenant name for isolation |
| `--passphrase` | All except `list` | Passphrase for stack secrets |
| `--stack-reference` | All except `create` and `list` | UUID returned by `create` |
| `--name` | `create` and `update` | Logical resource name |

## Resource-Specific Options

Options derived from your `ComponentArgs` subclass are available on `create` and `update`:

```python
class MyArgs(ComponentArgs):
    region: str = Field("us-east-1", description="AWS region.")
    count: int = Field(1, ge=0, description="Instance count.")
```

Becomes:

```bash
pulice my-component create --name x --region eu-west-1 --count 3 --tenant dev --passphrase secret
```

## Registering Operations

When registering a `ManagedComponent`, all 9 operations are enabled by default. To restrict to a subset:

```python
cli.register_component(
    MyComponent,
    name="my-component",
    operations=("create", "read", "delete", "list"),
)
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Validation error, passphrase mismatch, or tenant not found |
| 2 | Operation not implemented |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PULICE_STATE_DIR` | System temp dir | Root directory for all state |
| `PULICE_PULUMI_BACKEND_URL` | `file://<workdir>/.pulumi-state` | Pulumi state backend URL |
