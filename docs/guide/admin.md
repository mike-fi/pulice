# Admin Dashboard

Pulice includes a terminal-based admin dashboard for inspecting tenants, stacks, locks, tasks, and system health. It runs in the terminal via `pulice admin` and can optionally be served in the browser through the HTTP API.

## Installation

The admin TUI is an optional dependency:

```bash
pip install pulice[admin]
```

This installs [Textual](https://textual.textualize.io/) for the terminal UI and `textual-serve` for browser serving.

## Terminal Mode

Launch the dashboard in your terminal:

```bash
pulice admin
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--state-dir` | `$PULICE_STATE_DIR` | Path to the state directory |
| `--refresh` | `5` | Auto-refresh interval in seconds (0 to disable) |

### Example

```bash
# Point at a specific state directory with 10s refresh
pulice admin --state-dir /var/lib/pulice --refresh 10
```

## Browser Mode

When `textual-serve` is installed, the admin dashboard is automatically available at `/admin` on the HTTP API server:

```bash
uvicorn pulice.api:create_api --factory --host 0.0.0.0 --port 8000
# Dashboard available at http://localhost:8000/admin
```

No additional configuration is needed. If `textual-serve` is not installed, the `/admin` route is simply not mounted.

## Screens

The dashboard has five screens, accessible via numbered keys or tabs.

### Dashboard (1)

Summary view with key metrics:

- Tenant count
- Stack count
- Active lock count
- Task backend type
- State directory path and pulice version

### Tenants (2)

Table of all tenants showing name, ID, stack count, and creation date.

**Actions:**

| Key | Action |
|-----|--------|
| `d` | Delete tenant (with confirmation; fails if stacks exist) |

### Stacks (3)

Table of all stacks showing name, tenant, UUID, lock status, and creation date.

**Actions:**

| Key | Action |
|-----|--------|
| `l` | Release a stale lock (with confirmation) |

### Tasks (4)

Task inspection screen. Individual tasks can be cancelled or retried.

**Actions:**

| Key | Action |
|-----|--------|
| `c` | Cancel a pending/running task |
| `r` | Retry a failed task |

!!! note
    The Huey backend does not currently support listing all tasks. This screen will be expanded when a task index is available.

### System (5)

Read-only information panel showing:

- Pulice and Python versions
- State directory path and size on disk
- SQLite database size
- Task backend type
- Database stats (tenant, stack, lock counts)
- Active locks with age and operation

## Key Bindings

| Key | Scope | Action |
|-----|-------|--------|
| `1`–`5` | Global | Switch to screen by number |
| `q` | Global | Quit |
| `r` | Global | Force refresh |
| `Escape` | Modal | Close dialog |

## Data Access

The admin dashboard is **read-only** by default. The limited write actions are:

- Delete a tenant (fails if it still has stacks)
- Release a stale lock
- Cancel a pending/running task
- Retry a failed task

All write actions require confirmation via a modal dialog.

The dashboard reads from the same `PULICE_STATE_DIR` as the CLI and API — no additional state files or databases are introduced.

## Security

The admin dashboard has no built-in authentication. In production:

- **Terminal mode** is restricted to whoever can SSH into the machine
- **Browser mode** (`/admin`) should be placed behind a reverse proxy with auth, just like the REST API

## Programmatic Usage

You can create the admin app programmatically:

```python
from pulice.admin import create_admin_app

app = create_admin_app(state_dir="/var/lib/pulice", refresh_interval=10)
app.run()
```

Or mount it on your own FastAPI app:

```python
from fastapi import FastAPI
from pulice.admin.serve import mount_admin

app = FastAPI()
mount_admin(app)
```
