# API + PostgreSQL (Docker Compose)

A pulice example that runs the HTTP API with a task worker in Docker, managing AWS RDS PostgreSQL instances via async operations.

## Architecture

```
┌─────────────────────────────────────────┐
│           Docker Compose                │
├───────────────────┬─────────────────────┤
│   api (uvicorn)   │   worker (huey)     │
│   port 8000       │   2 processes       │
├───────────────────┴─────────────────────┤
│     Shared volume: /data/pulice         │
└─────────────────────────────────────────┘
          │
          ▼
    AWS RDS PostgreSQL
```

## What It Creates

1. **Security Group** — Allows inbound PostgreSQL (5432) from private networks
2. **DB Subnet Group** — Places the RDS instance in your VPC subnets
3. **RDS Instance** — PostgreSQL with managed master password

## Prerequisites

- Docker and Docker Compose
- AWS credentials with RDS permissions
- A VPC with at least 2 subnets in different AZs

## Setup

```bash
cd examples/api-postgres

export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=eu-central-1
```

## Running

```bash
docker compose up -d
```

## Usage

### Create a Tenant

```bash
curl -X POST http://localhost:8000/tenants \
  -H "Content-Type: application/json" \
  -d '{"name": "staging"}'
```

### Create a Database

```bash
curl -X POST http://localhost:8000/stacks/operations \
  -H "Content-Type: application/json" \
  -d '{
    "component_class": "postgres_infra.component.PostgresDatabase",
    "operation": "create",
    "tenant": "staging",
    "passphrase": "db-secret",
    "args": {
      "name": "app-db",
      "instance_class": "db.t3.micro",
      "allocated_storage": 20,
      "engine_version": "16.4",
      "vpc_id": "vpc-0123456789abcdef0",
      "subnet_ids": "subnet-aaa,subnet-bbb"
    }
  }'
# Response: {"task_id": "abc123", "status": "pending"}
```

### Poll for Completion

```bash
curl http://localhost:8000/tasks/abc123
# Response: {"task_id": "abc123", "status": "success", "result": {"stack_reference": "..."}}
```

### List Stacks

```bash
curl "http://localhost:8000/stacks?tenant=staging"
```

### Destroy

```bash
curl -X POST http://localhost:8000/stacks/operations \
  -H "Content-Type: application/json" \
  -d '{
    "component_class": "postgres_infra.component.PostgresDatabase",
    "operation": "delete",
    "tenant": "staging",
    "passphrase": "db-secret",
    "stack_reference": "<ref>"
  }'
```

## Stopping

```bash
docker compose down        # stop containers
docker compose down -v     # also remove state volume
```

## Component Args

| Argument | Default | Description |
|----------|---------|-------------|
| `name` | (required) | Logical name for the database |
| `instance_class` | `db.t3.micro` | RDS instance type |
| `allocated_storage` | `20` | Storage in GB |
| `engine_version` | `16.4` | PostgreSQL version |
| `master_username` | `pulice_admin` | Master DB username |
| `vpc_id` | (required) | VPC for the security group |
| `subnet_ids` | (required) | Comma-separated subnet IDs |
