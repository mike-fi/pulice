# Feature Spec: Project Documentation with Zensical + mkdocstrings

## Overview

Add a documentation site for pulice using **Zensical** (static site generator by the creators of Material for MkDocs) for conceptual/user documentation and **mkdocstrings** (Python handler) for auto-generated API reference from docstrings.

**Two audiences:**

1. **Component authors** — developers building `ManagedComponent` subclasses and registering them on a `PuliceCLI` or the HTTP API.
2. **Operators** — users running the CLI, deploying the API server + worker, and managing tenants/stacks.

---

## 1. Tooling

### 1.1 Dependencies

Add to `pyproject.toml`:

```toml
[dependency-groups]
docs = [
    "zensical>=0.0.37",
    "mkdocstrings[python]>=0.29.0",
]
```

Install with: `uv sync --group docs`

### 1.2 Configuration

Create `zensical.toml` at the project root:

```toml
[project]
site_name = "Pulice"
site_url = "https://pulice.dev"
site_description = "A framework for managing infrastructure-as-code components with tenant isolation, async execution, and pluggable backends."

[project.theme]
variant = "modern"
palette = [
    { media = "(prefers-color-scheme)", scheme = "default", primary = "indigo", accent = "indigo", toggle = { icon = "lucide/sun-moon", name = "Switch to light mode" } },
    { media = "(prefers-color-scheme: light)", scheme = "default", primary = "indigo", accent = "indigo", toggle = { icon = "lucide/sun", name = "Switch to dark mode" } },
    { media = "(prefers-color-scheme: dark)", scheme = "slate", primary = "indigo", accent = "orange", toggle = { icon = "lucide/moon-star", name = "Switch to system preference" } },
]
features = [
    "navigation.tabs",
    "navigation.sections",
    "navigation.expand",
    "navigation.top",
    "search.suggest",
    "search.highlight",
    "content.code.copy",
    "content.tabs.link",
]

[project.theme.icon]
repo = "fontawesome/brands/github"

[project.repo]
url = "https://github.com/FISCMIK/pulice"
name = "FISCMIK/pulice"

[project.plugins]
search = {}

[project.plugins.mkdocstrings]
handlers.python.options.show_source = true
handlers.python.options.show_root_heading = true
handlers.python.options.members_order = "source"
handlers.python.options.docstring_style = "google"
handlers.python.options.merge_init_into_class = true
handlers.python.options.show_signature_annotations = true

[project.markdown_extensions]
admonition = {}
pymdownx_highlight = { anchor_linenums = true }
pymdownx_superfences = {}
pymdownx_tabbed = { alternate_style = true }
pymdownx_details = {}
toc = { permalink = true }
```

### 1.3 CLI Commands

| Command | Purpose |
|---------|---------|
| `zensical serve` | Live preview at localhost:8000 |
| `zensical build` | Build static site to `site/` |
| `zensical new .` | Only needed once (we'll create the structure manually) |

---

## 2. Documentation Structure

```
docs/
├── index.md                    # Landing page / elevator pitch
├── get-started/
│   ├── index.md                # Installation + quickstart
│   ├── concepts.md             # Core concepts (components, stacks, tenants)
│   └── first-component.md     # Tutorial: build your first ManagedComponent
├── guide/
│   ├── cli.md                  # CLI usage reference
│   ├── api.md                  # HTTP API usage guide
│   ├── tenants.md              # Tenant management
│   ├── stack-operations.md    # All 9 lifecycle operations explained
│   ├── task-backends.md       # Huey vs Celery configuration
│   └── deployment.md          # Running API server + worker in production
├── reference/
│   ├── index.md                # API reference overview
│   ├── core.md                 # pulice.core module (auto-generated)
│   ├── cli.md                  # pulice.cli module (auto-generated)
│   ├── api.md                  # pulice.api module (auto-generated)
│   └── http-api.md            # OpenAPI / REST endpoint reference
└── contributing/
    ├── index.md                # How to contribute
    └── architecture.md        # Architecture decisions and design
```

### 2.1 Navigation

```toml
[project.nav]
nav = [
    { Home = "index.md" },
    { "Get Started" = [
        { Overview = "get-started/index.md" },
        { Concepts = "get-started/concepts.md" },
        { "First Component" = "get-started/first-component.md" },
    ]},
    { Guide = [
        { CLI = "guide/cli.md" },
        { "HTTP API" = "guide/api.md" },
        { Tenants = "guide/tenants.md" },
        { "Stack Operations" = "guide/stack-operations.md" },
        { "Task Backends" = "guide/task-backends.md" },
        { Deployment = "guide/deployment.md" },
    ]},
    { Reference = [
        { Overview = "reference/index.md" },
        { "Core Module" = "reference/core.md" },
        { "CLI Module" = "reference/cli.md" },
        { "API Module" = "reference/api.md" },
        { "HTTP Endpoints" = "reference/http-api.md" },
    ]},
    { Contributing = [
        { Overview = "contributing/index.md" },
        { Architecture = "contributing/architecture.md" },
    ]},
]
```

---

## 3. Page Content Specifications

### 3.1 Landing Page (`docs/index.md`)

- One-paragraph description of what pulice does
- Feature highlights (4-6 bullet points): tenant isolation, async execution, CLI + API, pluggable backends, passphrase-protected stacks, provider-agnostic
- Quick install snippet: `pip install pulice`
- Link to "Get Started"

### 3.2 Get Started — Concepts (`docs/get-started/concepts.md`)

Explain the mental model:

- **ManagedComponent** — a Pulumi ComponentResource subclass that declares its inputs via a Pydantic model
- **ComponentArgs** — the Pydantic base for resource inputs
- **Tenant** — an isolation boundary that owns stacks
- **Stack** — a Pulumi stack instance tied to a tenant + component
- **Stack Reference** — a UUID handle to locate an existing stack
- **Passphrase** — protects the Pulumi secrets in the stack
- **StackLock** — prevents concurrent mutating operations
- **TaskBackend** — abstraction for async execution (Huey / Celery)

Diagram showing: Component Author → registers component → CLI / API → StackOperations → Pulumi Automation API

### 3.3 Get Started — First Component (`docs/get-started/first-component.md`)

Complete tutorial:

1. Create a new Python project
2. Define a `ComponentArgs` subclass with fields
3. Define a `ManagedComponent` subclass that provisions AWS resources
4. Register on a `PuliceCLI`
5. Run `pulice tenant create --name dev`
6. Run `pulice <component> create --name my-thing --tenant dev --passphrase secret`
7. Inspect, update, delete

### 3.4 Guide Pages

Each guide page follows the pattern:
- What it does (1-2 sentences)
- Prerequisites
- Usage examples (CLI commands or curl/httpx calls)
- Configuration options (env vars, etc.)
- Troubleshooting

### 3.5 Reference — Auto-generated (`docs/reference/core.md`)

Uses mkdocstrings directives:

```markdown
# Core Module

::: pulice.core.base
    options:
      members:
        - ComponentArgs
        - ManagedComponent

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

::: pulice.core.managed
    options:
      members:
        - ManagedStackContext
        - resolve_component_class
        - resolve_managed_stack_context
        - build_managed_program
        - managed_component_operation_model

::: pulice.core.tasks
    options:
      members:
        - TaskStatus
        - TaskResult
        - TaskBackend
        - HueyTaskBackend
        - create_huey_instance
        - get_task_backend

::: pulice.core.controllers
    options:
      members:
        - WorkspaceController
        - ComponentController
```

### 3.6 Reference — CLI Module (`docs/reference/cli.md`)

```markdown
# CLI Module

::: pulice.cli.app
    options:
      members:
        - PuliceCLI

::: pulice.cli.registry
    options:
      members:
        - register_resource
        - register_component
        - register_tenant_commands
        - MANAGED_COMPONENT_OPERATIONS
```

### 3.7 Reference — API Module (`docs/reference/api.md`)

```markdown
# API Module

::: pulice.api
    options:
      members:
        - create_api

::: pulice.api.models

::: pulice.api.routes_tenants

::: pulice.api.routes_stacks

::: pulice.api.routes_tasks
```

### 3.8 Reference — HTTP Endpoints (`docs/reference/http-api.md`)

Manual documentation of the REST API with request/response examples, or link to the auto-generated `/docs` (Swagger UI) endpoint when the server is running. Include a table of all endpoints:

| Method | Path | Description |
|--------|------|-------------|
| POST | /tenants | Create tenant |
| GET | /tenants | List tenants |
| GET | /tenants/{name} | Get tenant |
| DELETE | /tenants/{name} | Delete tenant |
| POST | /stacks/operations | Submit stack operation |
| GET | /stacks | List stacks |
| GET | /tasks/{task_id} | Get task status |
| POST | /tasks/{task_id}/cancel | Cancel task |
| POST | /tasks/{task_id}/retry | Retry failed task |

---

## 4. Docstring Requirements

For mkdocstrings to produce useful output, key public classes and functions need docstrings. The following need docstrings added or improved:

### Must have docstrings (public API surface):

| Symbol | Current State | Action |
|--------|--------------|--------|
| `ComponentArgs` | Has docstring | Sufficient |
| `ManagedComponent` | Has docstring | Sufficient |
| `Tenant` | One-liner | Expand: fields, usage |
| `StackReference` | None | Add: what it is, when you get one |
| `PassphraseHasher` | Has docstring | Sufficient |
| `PassphraseHasher.hash` | Has docstring | Sufficient |
| `PassphraseHasher.verify` | Has docstring | Sufficient |
| `StackLock` | Has docstring | Add: example usage |
| `SqliteBackendStorage` | Has docstring | Add: constructor params |
| `StackOperations` | Has docstring | Add: constructor params, typical usage |
| `TaskStatus` | None | Add: enum value descriptions |
| `TaskResult` | None | Add: field descriptions |
| `TaskBackend` | Has docstring | Sufficient |
| `HueyTaskBackend` | Has docstring | Add: constructor params |
| `PuliceCLI` | Has docstring | Sufficient |
| `WorkspaceController` | Has docstring | Sufficient |
| `ComponentController` | Has docstring | Sufficient |
| `resolve_component_class` | Has docstring | Sufficient |
| `managed_component_operation_model` | Has docstring | Sufficient |
| `create_api` | Has docstring | Sufficient |

### Docstring style: Google format

```python
def example(param: str) -> bool:
    """Short description.

    Longer description if needed.

    Args:
        param: Description of param.

    Returns:
        Description of return value.

    Raises:
        ValueError: When something is wrong.
    """
```

---

## 5. Build and Deployment

### 5.1 Local Development

```bash
uv sync --group docs
zensical serve
```

### 5.2 Production Build

```bash
zensical build
# Output in site/ directory
```

### 5.3 GitHub Actions (`.github/workflows/docs.yml`)

```yaml
name: docs
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      - run: pip install uv
      - run: uv sync --group docs
      - run: uv run zensical build
      - if: github.ref == 'refs/heads/main'
        uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./site
```

### 5.4 `.gitignore` Addition

```
site/
```

---

## 6. Files to Create/Modify

### 6.1 New Files

| File | Description |
|------|-------------|
| `zensical.toml` | Site configuration |
| `docs/index.md` | Landing page |
| `docs/get-started/index.md` | Installation + quickstart |
| `docs/get-started/concepts.md` | Core concepts |
| `docs/get-started/first-component.md` | Tutorial |
| `docs/guide/cli.md` | CLI usage |
| `docs/guide/api.md` | HTTP API usage |
| `docs/guide/tenants.md` | Tenant management |
| `docs/guide/stack-operations.md` | Lifecycle operations |
| `docs/guide/task-backends.md` | Huey / Celery setup |
| `docs/guide/deployment.md` | Production deployment |
| `docs/reference/index.md` | Reference overview |
| `docs/reference/core.md` | Auto-generated core API |
| `docs/reference/cli.md` | Auto-generated CLI API |
| `docs/reference/api.md` | Auto-generated API module |
| `docs/reference/http-api.md` | REST endpoint docs |
| `docs/contributing/index.md` | Contributing guide |
| `docs/contributing/architecture.md` | Architecture overview |
| `.github/workflows/docs.yml` | CI for docs deployment |

### 6.2 Modified Files

| File | Change |
|------|--------|
| `pyproject.toml` | Add `docs` dependency group |
| `.gitignore` | Add `site/` |
| Source files (various) | Add/improve docstrings for public API |

---

## 7. Implementation Order

1. **Configuration** — Add `docs` group to `pyproject.toml`, create `zensical.toml`, add `site/` to `.gitignore`.
2. **Skeleton** — Create all `docs/` directories and files with placeholder content.
3. **Landing + Get Started** — Write `index.md`, installation, concepts, tutorial.
4. **Guide pages** — Write CLI, API, tenants, stack-operations, task-backends, deployment.
5. **Docstrings** — Add/improve docstrings on all public API symbols listed in §4.
6. **Reference pages** — Add mkdocstrings directives. Verify rendering with `zensical serve`.
7. **CI** — Add `.github/workflows/docs.yml`.
8. **Polish** — Review navigation, fix broken links, verify search works.

---

## 8. Non-Goals

- Versioned documentation (multiple versions of the docs for different releases).
- Internationalization / translated docs.
- Blog or changelog section (keep in CHANGELOG.md at repo root).
- Custom Zensical plugins or theme overrides beyond configuration.
- Hosting setup (GitHub Pages configuration is sufficient for v1).
