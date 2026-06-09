# Feature Spec: Admin TUI

## Overview

Add an administrative dashboard for pulice that runs as a Textual TUI in the terminal (`pulice admin`) and can be served in the browser via the HTTP API (`/admin`). The dashboard provides a read-only (with limited write actions) interface for inspecting tenants, stacks, tasks, locks, and system health.

**Library:** [Textual](https://textual.textualize.io/) (terminal + browser via `textual-serve`)

---

## 1. Goals

1. **Single codebase** — One Textual `App` subclass powers both terminal and browser modes.
2. **Read-heavy** — Primary use is inspecting state. Write actions (delete tenant, cancel task, release stale lock) require confirmation.
3. **Live data** — Screens refresh from SQLite/task backend on a configurable interval (default 5s).
4. **No new state** — The TUI reads from existing `SqliteBackendStorage` and `TaskBackend`; it introduces no new tables or files.
5. **Optional dependency** — Textual is not required for core pulice functionality.

---

## 2. Entry Points

### 2.1 CLI: `pulice admin`

Launches the TUI in the current terminal.

```bash
pulice admin
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--state-dir` | `$PULICE_STATE_DIR` | Path to state directory |
| `--refresh` | `5` | Auto-refresh interval in seconds (0 to disable) |

### 2.2 API: `/admin`

Serves the TUI as a web application via `textual-serve`. Mounted on the existing FastAPI app.

```bash
# Starts API server with admin UI at http://localhost:8000/admin
uvicorn pulice.api:create_api --factory --host 0.0.0.0 --port 8000
```

The `/admin` route serves the Textual web app. The `/admin` endpoint is only available when `textual-serve` is installed.

---

## 3. Screens & Navigation

The TUI uses a tabbed layout with keyboard navigation.

### 3.1 Screen Map

```
┌──────────────────────────────────────────────────────────────┐
│  [1] Dashboard  [2] Tenants  [3] Stacks  [4] Tasks  [5] System │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│                     Active Screen                            │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  Status Bar: version │ state_dir │ backend │ refresh: 5s     │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 Dashboard (Home)

Summary view showing key metrics at a glance:

- Total tenants count
- Total stacks count (with breakdown by tenant)
- Active locks count
- Pending / running / failed task counts
- Pulice version
- State directory path
- Task backend type (huey/celery)
- Uptime (if served via API)

### 3.3 Tenants Screen

| Column | Description |
|--------|-------------|
| Name | Tenant name |
| ID | Tenant UUID (truncated) |
| Stacks | Number of stacks owned |
| Created | Creation timestamp |

**Actions:**
- `Enter` on a row → navigate to filtered Stacks screen for that tenant
- `d` → Delete tenant (with confirmation; fails if stacks exist)
- `/` → Filter/search by name

### 3.4 Stacks Screen

| Column | Description |
|--------|-------------|
| Stack Name | Full Pulumi stack name |
| Component | Component class name |
| Tenant | Owning tenant name |
| UUID | Stack reference UUID (truncated) |
| Locked | Lock status (icon + holder operation) |
| Created | Creation timestamp |

**Actions:**
- `Enter` on a row → Stack detail panel (reference info, lock status, passphrase hash presence)
- `l` → Release lock (with confirmation; only if stale)
- `/` → Filter by tenant, component, or name
- `t` → Filter to selected tenant

### 3.5 Tasks Screen

| Column | Description |
|--------|-------------|
| Task ID | Truncated task identifier |
| Status | Pending / Running / Success / Failed / Cancelled |
| Operation | Stack operation name |
| Submitted | Timestamp |
| Duration | Elapsed time (running) or total time (completed) |

**Actions:**
- `Enter` on a row → Task detail panel (full payload, result/error)
- `c` → Cancel task (with confirmation; only if pending/running)
- `r` → Retry task (with confirmation; only if failed)
- `/` → Filter by status

### 3.6 System Screen

Read-only information panel:

- **Version:** `pulice.__version__`
- **Python:** `sys.version`
- **State directory:** path, total size on disk, SQLite file size
- **Task backend:** type, configuration (broker URL for Celery, DB path for Huey)
- **Active locks:** list with age and operation
- **Database stats:** tenant count, stack count, lock count

---

## 4. Architecture

### 4.1 Module Layout

```
src/pulice/
├── admin/
│   ├── __init__.py         # Public API: create_admin_app()
│   ├── app.py              # PuliceAdmin(textual.App) — main application
│   ├── screens/
│   │   ├── __init__.py
│   │   ├── dashboard.py    # DashboardScreen
│   │   ├── tenants.py      # TenantsScreen
│   │   ├── stacks.py       # StacksScreen
│   │   ├── tasks.py        # TasksScreen
│   │   └── system.py       # SystemScreen
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── stat_card.py    # Metric card widget
│   │   └── confirm.py      # Confirmation modal
│   └── serve.py            # textual-serve integration for FastAPI
```

### 4.2 Data Access Layer

The TUI accesses data through existing public APIs — no direct SQLite queries:

```python
class AdminDataSource:
    """Read-only data provider for the admin TUI."""

    def __init__(self, state_dir: str | None = None) -> None:
        self._storage = SqliteBackendStorage(root_dir=state_dir)
        self._references = LocalStackReferenceStore(root_dir=state_dir)
        self._task_backend = get_task_backend(state_dir=state_dir)

    def get_tenants(self) -> list[Tenant]: ...
    def get_stacks(self, tenant_id: str | None = None) -> list[dict]: ...
    def get_locks(self) -> list[dict]: ...
    def get_task_status(self, task_id: str) -> TaskResult: ...
    def get_system_info(self) -> dict: ...
    def delete_tenant(self, name: str) -> None: ...
    def release_lock(self, stack_name: str) -> None: ...
    def cancel_task(self, task_id: str) -> bool: ...
    def retry_task(self, task_id: str) -> str: ...
```

### 4.3 Refresh Strategy

- `set_interval(self.refresh_interval, self.reload_data)` on each screen
- Only the active screen refreshes
- Data fetch happens in a worker thread (`run_worker`) to avoid blocking the UI
- On screen switch, immediately trigger a refresh

### 4.4 Browser Serving

`textual-serve` provides a WebSocket bridge that renders Textual apps in the browser. Integration with FastAPI:

```python
# pulice/admin/serve.py
from textual_serve.server import Server

def mount_admin(fastapi_app: FastAPI) -> None:
    """Mount the Textual admin app on /admin."""
    from pulice.admin.app import PuliceAdmin
    server = Server(PuliceAdmin)
    fastapi_app.mount("/admin", server.app)
```

The `create_api()` factory conditionally mounts `/admin` if `textual-serve` is importable:

```python
def create_api() -> FastAPI:
    app = FastAPI(...)
    # ... existing routers ...
    try:
        from pulice.admin.serve import mount_admin
        mount_admin(app)
    except ImportError:
        pass  # textual-serve not installed
    return app
```

---

## 5. Styling

Use Textual CSS (`.tcss` files) for layout and theming:

```
src/pulice/admin/
├── styles/
│   ├── app.tcss            # Global layout, color scheme
│   ├── dashboard.tcss      # Dashboard grid
│   └── tables.tcss         # DataTable styling
```

Color palette aligned with the Zensical docs theme:

| Element | Color |
|---------|-------|
| Primary accent | Indigo (`#3f51b5`) |
| Success | Green |
| Warning | Orange |
| Error | Red |
| Background | Terminal default (respects dark/light) |

---

## 6. Key Bindings

| Key | Scope | Action |
|-----|-------|--------|
| `1`–`5` | Global | Switch to screen by number |
| `q` | Global | Quit |
| `r` | Global | Force refresh |
| `/` | Table screens | Open search/filter |
| `Escape` | Modal/filter | Close |
| `Enter` | Table row | Open detail |
| `d` | Tenants | Delete tenant |
| `l` | Stacks | Release stale lock |
| `c` | Tasks | Cancel task |

---

## 7. Dependencies

### 7.1 New Optional Dependency Group

```toml
[project.optional-dependencies]
admin = [
    "textual>=3.0.0",
    "textual-serve>=1.1.0",
]
```

### 7.2 CLI Registration

The `pulice admin` command is always registered (part of the base CLI). If `textual` is not installed, it prints an install hint and exits:

```python
@app.command()
def admin(state_dir: str = None, refresh: int = 5):
    """Launch the admin dashboard."""
    try:
        from pulice.admin.app import PuliceAdmin
    except ImportError:
        print("Admin TUI requires 'pulice[admin]'. Install with: pip install pulice[admin]")
        raise typer.Exit(1)
    app = PuliceAdmin(state_dir=state_dir, refresh_interval=refresh)
    app.run()
```

---

## 8. API Integration

### 8.1 Mount Path

The admin UI is served at `/admin` on the existing FastAPI server. This is a separate ASGI app mounted via `app.mount()`.

### 8.2 Shared State

Both the API endpoints and the admin TUI read from the same `SqliteBackendStorage` instance (same `PULICE_STATE_DIR`). No state synchronization needed — both read the same SQLite file.

### 8.3 Auth Consideration

The admin TUI has the same authentication story as the REST API: none built-in. In production, both should sit behind a reverse proxy with auth. The `/admin` endpoint should be restricted to operators.

---

## 9. Testing Strategy

### 9.1 Unit Tests

- `AdminDataSource` methods tested against an in-memory `SqliteBackendStorage`
- Each screen widget tested via Textual's `pilot` testing framework
- Confirmation modals tested for accept/reject flows

### 9.2 Integration Tests

- Mount the admin on a test FastAPI client, verify `/admin` returns HTML
- Verify graceful degradation when `textual-serve` not installed (no `/admin` route)

### 9.3 Snapshot Tests

Textual supports SVG snapshot testing for visual regression:

```python
async def test_dashboard_snapshot(snap_compare):
    async with PuliceAdmin().run_test() as pilot:
        assert snap_compare(pilot.app)
```

---

## 10. Implementation Order

1. **Dependencies** — Add `admin` optional group to `pyproject.toml`
2. **Data layer** — Implement `AdminDataSource` with existing storage APIs
3. **App shell** — `PuliceAdmin` app with tab navigation and status bar
4. **Dashboard screen** — Stat cards with live metrics
5. **Tenants screen** — DataTable with CRUD actions
6. **Stacks screen** — DataTable with filtering and lock management
7. **Tasks screen** — DataTable with cancel/retry actions
8. **System screen** — Static info panel
9. **CLI command** — Register `pulice admin` with import guard
10. **Browser serving** — `textual-serve` mount on FastAPI
11. **Styling** — TCSS files and color theme
12. **Tests** — Unit, integration, and snapshot tests

---

## 11. Non-Goals

- Real-time WebSocket push from workers to the TUI (polling is sufficient)
- Write operations beyond delete-tenant, cancel-task, retry-task, release-lock
- User/role management within the TUI
- Custom plugin/extension system for adding screens
- Mobile-optimized browser layout (desktop browser is sufficient)

---

## 12. Open Questions

1. **textual-serve stability** — `textual-serve` is relatively new. If it proves unstable, fall back to serving the TUI only in the terminal and provide a separate lightweight HTML dashboard via Jinja templates.
2. **Lock listing** — `SqliteBackendStorage` doesn't currently expose a `list_locks()` method. This needs to be added (simple `SELECT * FROM stack_locks`).
3. **Task listing** — `HueyTaskBackend` doesn't support listing all tasks. Either add a `list_tasks()` method or maintain a separate index table for submitted tasks.
