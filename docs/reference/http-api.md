# HTTP Endpoints

Complete reference of the pulice REST API. When the server is running, interactive docs are available at `/docs` (Swagger UI) and `/redoc` (ReDoc).

## Base URL

```
http://localhost:8000
```

## Endpoints

### Tenants

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/tenants` | Create a new tenant |
| `GET` | `/tenants` | List all tenants |
| `GET` | `/tenants/{name}` | Get a single tenant by name |
| `DELETE` | `/tenants/{name}` | Delete a tenant (must have no stacks) |

#### Create Tenant

```http
POST /tenants
Content-Type: application/json

{"name": "production"}
```

**Response** `201 Created`:

```json
{
  "id": "a1b2c3d4...",
  "name": "production",
  "created_at": "2024-06-15T10:30:00+00:00"
}
```

#### List Tenants

```http
GET /tenants
```

**Response** `200 OK`:

```json
[
  {"id": "default", "name": "default", "created_at": "2024-01-01T00:00:00"},
  {"id": "a1b2c3d4...", "name": "production", "created_at": "2024-06-15T10:30:00+00:00"}
]
```

#### Delete Tenant

```http
DELETE /tenants/staging
```

**Response** `204 No Content`

**Error** `409 Conflict` — tenant still has stacks.

---

### Stack Operations

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/stacks/operations` | Submit an async stack operation |
| `GET` | `/stacks` | List stacks (filtered by tenant) |

#### Submit Operation

```http
POST /stacks/operations
Content-Type: application/json

{
  "component_class": "myapp.components.Bucket",
  "operation": "create",
  "tenant": "production",
  "passphrase": "my-secret-passphrase",
  "args": {"name": "data-lake", "region": "eu-west-1"}
}
```

**Response** `202 Accepted`:

```json
{
  "task_id": "abc123def456",
  "status": "pending"
}
```

#### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `component_class` | `string` | Yes | Dotted import path to a `ManagedComponent` subclass |
| `operation` | `string` | Yes | One of: `create`, `read`, `update`, `delete`, `refresh`, `list`, `status`, `export`, `import` |
| `tenant` | `string` | Yes | Tenant name |
| `passphrase` | `string` | Conditional | Required for all operations except `list` |
| `args` | `object` | Conditional | Component arguments (required for `create` and `update`) |
| `stack_reference` | `string` | Conditional | Required for all operations except `create` and `list` |
| `input_file` | `string` | No | Path to input file (for `import`) |
| `output_file` | `string` | No | Path to output file (for `export`) |

#### List Stacks

```http
GET /stacks?tenant=production
```

**Response** `200 OK`:

```json
[
  {
    "stack_name": "a1b2-bucket-c3d4",
    "uuid": "c3d4e5f6...",
    "tenant_id": "a1b2c3d4...",
    "created_at": "2024-06-15T11:00:00"
  }
]
```

---

### Tasks

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/tasks/{task_id}` | Get task status and result |
| `POST` | `/tasks/{task_id}/cancel` | Cancel a pending task |
| `POST` | `/tasks/{task_id}/retry` | Retry a failed task |

#### Get Task Status

```http
GET /tasks/abc123def456
```

**Response** `200 OK` (pending):

```json
{
  "task_id": "abc123def456",
  "status": "pending",
  "result": null,
  "error": null
}
```

**Response** `200 OK` (success):

```json
{
  "task_id": "abc123def456",
  "status": "success",
  "result": {"stack_reference": "e7f8g9h0..."},
  "error": null
}
```

**Response** `200 OK` (failed):

```json
{
  "task_id": "abc123def456",
  "status": "failed",
  "result": null,
  "error": "Pulumi error: resource already exists"
}
```

#### Cancel Task

```http
POST /tasks/abc123def456/cancel
```

**Response** `200 OK`:

```json
{"cancelled": true}
```

#### Retry Task

```http
POST /tasks/abc123def456/retry
```

**Response** `200 OK`:

```json
{
  "task_id": "new-task-id-789",
  "status": "pending"
}
```

---

## Error Responses

All error responses follow a consistent format:

```json
{
  "detail": "Human-readable error message"
}
```

| Status Code | Meaning |
|-------------|---------|
| `400` | Invalid request (bad operation, missing fields) |
| `404` | Resource not found (tenant, task, stack reference) |
| `409` | Conflict (tenant has stacks, lock held) |
| `422` | Validation error (Pydantic) |
| `500` | Internal server error |
