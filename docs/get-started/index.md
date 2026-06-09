# Get Started

## Installation

Pulice requires Python 3.13 or later.

### With pip

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pulice
```

### With uv

```bash
uv add pulice
```

### Optional extras

| Extra | Install command | Provides |
|-------|----------------|----------|
| `aws` | `pip install pulice[aws]` | AWS Pulumi provider |
| `api` | `pip install pulice[api]` | FastAPI server, Huey task queue |
| `celery` | `pip install pulice[celery]` | Celery task backend (Redis) |

## Prerequisites

- [Pulumi CLI](https://www.pulumi.com/docs/install/) installed and on your `PATH`
- A Pulumi provider SDK for your target cloud (e.g., `pulumi-aws`, `pulumi-gcp`)

## Verify Installation

```bash
python -c "import pulice; print('pulice installed')"
```

## What's Next

1. [Concepts](concepts.md) — Understand the core abstractions
2. [First Component](first-component.md) — Build and deploy your first managed component
