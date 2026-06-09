# Stack Operations

Pulice supports 9 lifecycle operations on managed component stacks. Mutating operations (`create`, `update`, `delete`, `refresh`, `import`) acquire a lock to prevent concurrent modifications.

## Operations Matrix

| Operation | Creates resources | Requires stack-reference | Requires passphrase | Locked |
|-----------|:-:|:-:|:-:|:-:|
| `create` | Yes | No | Yes | Yes |
| `read` | No | Yes | Yes | No |
| `update` | Yes | Yes | Yes | Yes |
| `delete` | No | Yes | Yes | Yes |
| `refresh` | No | Yes | Yes | Yes |
| `list` | No | No | No | No |
| `status` | No | Yes | Yes | No |
| `export` | No | Yes | Yes | No |
| `import` | No | Yes | Yes | Yes |

## create

Provisions new cloud resources and creates a new stack. Returns a stack reference UUID.

```bash
pulice bucket create --name prod-data --region eu-west-1 --tenant prod --passphrase secret
# Stack reference: a1b2c3d4...
```

What happens internally:

1. Validates the tenant exists
2. Generates a UUID stack reference
3. Creates a working directory
4. Acquires a StackLock
5. Runs `pulumi up`
6. Saves the stack reference and passphrase hash
7. Releases the lock

## read

Runs `pulumi preview` to show what resources exist without making changes.

```bash
pulice bucket read --stack-reference a1b2c3d4 --tenant prod --passphrase secret
```

## update

Modifies an existing stack with new argument values. Runs `pulumi up` with updated inputs.

```bash
pulice bucket update --name prod-data --region us-west-2 \
    --stack-reference a1b2c3d4 --tenant prod --passphrase secret
```

## delete

Destroys all resources in the stack via `pulumi destroy`.

```bash
pulice bucket delete --stack-reference a1b2c3d4 --tenant prod --passphrase secret
```

## refresh

Reconciles Pulumi state with actual cloud resources without modifying infrastructure. Useful when resources were changed outside of Pulumi.

```bash
pulice bucket refresh --stack-reference a1b2c3d4 --tenant prod --passphrase secret
```

## list

Lists all stacks for a component and tenant. Does not require a passphrase or stack reference.

```bash
pulice bucket list --tenant prod
```

## status

Shows metadata about a stack: resource count, last update time.

```bash
pulice bucket status --stack-reference a1b2c3d4 --tenant prod --passphrase secret
```

## export

Exports the Pulumi stack state as JSON for backup or migration.

```bash
# To stdout
pulice bucket export --stack-reference a1b2c3d4 --tenant prod --passphrase secret

# To file
pulice bucket export --stack-reference a1b2c3d4 --tenant prod --passphrase secret --output backup.json
```

## import

Imports a previously exported stack state.

```bash
pulice bucket import --stack-reference a1b2c3d4 --tenant prod --passphrase secret --input backup.json
```

## Passphrase Validation

On every operation except `create` and `list`, pulice verifies the provided passphrase against the hash stored at creation time. If it doesn't match:

```
Error: Invalid passphrase for stack 'tenant-bucket-a1b2c3d4'.
```

This check happens **before** any Pulumi call, giving instant feedback rather than a cryptic decryption error deep in the Pulumi process.

## Stack Locking

Mutating operations acquire an advisory lock backed by SQLite. If another process holds the lock:

- The second process retries with exponential backoff (up to 30 seconds by default)
- If the lock is older than 10 minutes, it's considered stale and automatically cleaned up
- If the timeout is reached, a clear error is raised:

```
Cannot acquire lock for stack 'tenant-bucket-a1b2c3d4': held by another process (operation='update'). Timed out after 30.0s.
```
