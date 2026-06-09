# Deployment

This guide covers running pulice in production with the HTTP API and task workers.

## Architecture

A production deployment consists of three processes:

1. **API server** — Handles HTTP requests, validates input, submits tasks
2. **Task worker** — Executes Pulumi operations from the queue
3. **State storage** — SQLite (single-machine) or shared filesystem

```
Client → API Server (uvicorn) → Task Queue → Worker → Pulumi
                                                 ↕
                                          SQLite / Shared FS
```

## Single-Machine Deployment

The simplest setup runs all processes on one machine with SQLite.

### Environment

```bash
export PULICE_STATE_DIR=/var/lib/pulice
export PULICE_TASK_BACKEND=huey
```

### Start the API server

```bash
uvicorn pulice.api:create_api --factory --host 0.0.0.0 --port 8000
```

### Start the worker

```bash
huey_consumer pulice.worker.huey -w 2 -k process
```

### Systemd Units

Create `/etc/systemd/system/pulice-api.service`:

```ini
[Unit]
Description=Pulice API Server
After=network.target

[Service]
Type=simple
User=pulice
Environment=PULICE_STATE_DIR=/var/lib/pulice
ExecStart=/usr/local/bin/uvicorn pulice.api:create_api --factory --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/pulice-worker.service`:

```ini
[Unit]
Description=Pulice Task Worker
After=network.target

[Service]
Type=simple
User=pulice
Environment=PULICE_STATE_DIR=/var/lib/pulice
ExecStart=/usr/local/bin/huey_consumer pulice.worker.huey -w 2 -k process
Restart=always

[Install]
WantedBy=multi-user.target
```

## Distributed Deployment (Celery + Redis)

For multi-machine setups, use Celery with Redis.

### Prerequisites

- Redis instance accessible from API server and workers
- Shared filesystem (NFS, EFS) mounted at the same path on all machines for Pulumi state

### Environment (all machines)

```bash
export PULICE_STATE_DIR=/mnt/shared/pulice
export PULICE_TASK_BACKEND=celery
export PULICE_CELERY_BROKER_URL=redis://redis.internal:6379/0
export PULICE_CELERY_RESULT_BACKEND=redis://redis.internal:6379/1
```

### API server

```bash
pip install pulice[api]
uvicorn pulice.api:create_api --factory --host 0.0.0.0 --port 8000
```

### Workers (scale independently)

```bash
pip install pulice[celery]
celery -A pulice.core.celery_backend worker --concurrency=2 --pool=prefork
```

## State Directory

The `PULICE_STATE_DIR` contains:

```
/var/lib/pulice/
├── pulice_stacks.sqlite3    # Stack metadata, tenants, locks
├── pulice-tasks.db          # Huey task queue (Huey only)
├── stacks/                  # Per-stack working directories
│   ├── <uuid>/
│   │   └── .pulumi-state/  # Pulumi state files
│   └── ...
└── stack_refs/              # Stack reference JSON files
    ├── <ref-id>.json
    └── ...
```

Ensure this directory is:

- Writable by the pulice user
- Backed up regularly (especially `pulice_stacks.sqlite3` and `stacks/`)
- On a shared filesystem for distributed deployments

## Security Considerations

- **Passphrases** are transmitted in request bodies. Use HTTPS in production.
- **Task payloads** contain passphrases (stored in the queue DB). Restrict filesystem access to the state directory.
- **No authentication** is built in. Place the API behind a reverse proxy with auth (OAuth2, API keys, mTLS).
- **SQLite locking** works on a single machine. For distributed locking, use Celery with proper Redis configuration.

## Health Checks

The FastAPI app responds to any valid route. For a lightweight health check:

```bash
curl http://localhost:8000/tenants
# 200 OK confirms API + database connectivity
```

## Scaling Guidelines

| Dimension | Recommendation |
|-----------|---------------|
| API servers | Stateless — scale horizontally behind a load balancer |
| Workers | Scale based on operation throughput; each worker runs 1 Pulumi process at a time |
| SQLite | Single-writer; sufficient for ~100 concurrent stacks on one machine |
| Redis (Celery) | Standard Redis HA (Sentinel or Cluster) for production |
