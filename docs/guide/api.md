# HTTP API

Pulice includes a FastAPI-based HTTP API that executes stack operations asynchronously via a task queue. The CLI remains synchronous — the API is an additive feature for automation and multi-user deployments.

## Starting the Server

```bash
pip install pulice[api]
uvicorn pulice.api:create_api --factory --host 0.0.0.0 --port 8000
```

The API server does **not** execute Pulumi operations directly. It validates requests and submits them to a task queue. You also need a worker process:

```bash
huey_consumer pulice.worker.huey -w 2 -k process
```

## Interactive Docs

FastAPI provides auto-generated interactive documentation:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

## Endpoints

### Tenants

| Method | Path | Description |
|--------|------|-------------|
| POST | `/tenants` | Create a tenant |
| GET | `/tenants` | List all tenants |
| GET | `/tenants/{name}` | Get a single tenant |
| DELETE | `/tenants/{name}` | Delete a tenant |

### Stack Operations

| Method | Path | Description |
|--------|------|-------------|
| POST | `/stacks/operations` | Submit a stack operation (async) |
| GET | `/stacks?tenant=<name>` | List stacks for a tenant |

### Tasks

| Method | Path | Description |
|--------|------|-------------|
| GET | `/tasks/{task_id}` | Get task status and result |
| POST | `/tasks/{task_id}/cancel` | Cancel a pending/running task |
| POST | `/tasks/{task_id}/retry` | Retry a failed task |

## Example: Create a Stack

```bash
# 1. Submit the operation
curl -X POST http://localhost:8000/stacks/operations \
  -H "Content-Type: application/json" \
  -d '{
    "component_class": "myapp.components.Bucket",
    "operation": "create",
    "tenant": "dev",
    "passphrase": "my-secret",
    "args": {"name": "my-bucket", "region": "eu-west-1"}
  }'

# Response: {"task_id": "abc123", "status": "pending"}

# 2. Poll for completion
curl http://localhost:8000/tasks/abc123

# Response: {"task_id": "abc123", "status": "success", "result": {"stack_reference": "..."}}
```

## Request Model

The `POST /stacks/operations` endpoint accepts:

```json
{
  "component_class": "importable.dotted.path.to.Component",
  "operation": "create|read|update|delete|refresh|status|export|import|list",
  "tenant": "tenant-name",
  "passphrase": "stack-passphrase",
  "args": {},
  "stack_reference": null,
  "input_file": null,
  "output_file": null
}
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PULICE_STATE_DIR` | System temp dir | Root for state storage |
| `PULICE_TASK_BACKEND` | `huey` | Task backend: `huey` or `celery` |
| `PULICE_API_HOST` | `0.0.0.0` | API server bind host |
| `PULICE_API_PORT` | `8000` | API server bind port |
