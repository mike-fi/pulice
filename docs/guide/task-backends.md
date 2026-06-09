# Task Backends

The HTTP API uses a task queue to execute stack operations asynchronously. Pulice provides two backends behind a common `TaskBackend` protocol.

## Huey (Default)

[Huey](https://huey.readthedocs.io/) with an SQLite storage backend. Zero external dependencies — works out of the box on a single machine.

### Setup

```bash
pip install pulice[api]
```

### Start the worker

```bash
huey_consumer pulice.worker.huey -w 2 -k process
```

- `-w 2` — Two worker processes (tune per machine)
- `-k process` — Process-based workers (required since Pulumi SDK is not thread-safe)

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PULICE_TASK_BACKEND` | `huey` | Set to `huey` (or omit) |
| `PULICE_STATE_DIR` | System temp dir | Location for the task SQLite database |

## Celery

[Celery](https://docs.celeryq.dev/) with Redis for distributed, multi-machine deployments.

### Setup

```bash
pip install pulice[celery]
```

Requires a running Redis instance (or RabbitMQ with different configuration).

### Start the worker

```bash
celery -A pulice.core.celery_backend worker --concurrency=2 --pool=prefork
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PULICE_TASK_BACKEND` | — | Set to `celery` |
| `PULICE_CELERY_BROKER_URL` | `redis://localhost:6379/0` | Celery broker URL |
| `PULICE_CELERY_RESULT_BACKEND` | `redis://localhost:6379/1` | Celery result backend |

## Choosing a Backend

| | Huey | Celery |
|---|---|---|
| External dependencies | None | Redis or RabbitMQ |
| Horizontal scaling | Single machine | Multiple machines |
| Setup complexity | Minimal | Moderate |
| Monitoring | Basic | Flower, Prometheus |
| Best for | Development, single-server | Production, team deployments |

## Retry Semantics

| Operation | Retryable | Rationale |
|-----------|-----------|-----------|
| `create` | No | Partial state may exist |
| `update` | Yes | `pulumi up` is idempotent |
| `read` | Yes | Read-only preview |
| `delete` | No | Partial destroy may leave resources |
| `refresh` | Yes | Idempotent state reconciliation |
| `status` | Yes | Read-only |
| `export` | Yes | Read-only |
| `import` | No | State mutation |

## Task Lifecycle

```
PENDING → RUNNING → SUCCESS
                  → FAILED → (retry) → PENDING
       → CANCELLED
```

Poll task status via:

```bash
curl http://localhost:8000/tasks/{task_id}
```

Cancel a pending task:

```bash
curl -X POST http://localhost:8000/tasks/{task_id}/cancel
```

Retry a failed task:

```bash
curl -X POST http://localhost:8000/tasks/{task_id}/retry
```
