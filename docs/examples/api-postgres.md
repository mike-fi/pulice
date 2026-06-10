# API + PostgreSQL (Docker Compose)

This example runs the Pulice HTTP API with a Huey worker inside Docker, managing an AWS RDS PostgreSQL instance via async task execution.

## Architecture

```
┌─────────────────────────────────────────┐
│           Docker Compose                │
├───────────────────┬─────────────────────┤
│   api (uvicorn)   │   worker (huey)     │
│   port 8000       │   2 processes       │
├───────────────────┴─────────────────────┤
│         Shared volume: /data/pulice     │
└─────────────────────────────────────────┘
          │
          ▼
    AWS RDS PostgreSQL
```

## What It Creates

- **Security Group** — Allows inbound PostgreSQL traffic (port 5432)
- **DB Subnet Group** — Places the instance in your VPC subnets
- **RDS Instance** — PostgreSQL with configurable instance class and storage

## Prerequisites

- Docker and Docker Compose
- AWS credentials (passed as env vars to containers)
- A VPC with subnets for the RDS instance

## Setup

```bash
cd examples/api-postgres

# Set your AWS credentials
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=eu-central-1
```

## Running

```bash
docker compose up -d
```

## Usage (curl)

```bash
# Create a tenant
curl -X POST http://localhost:8000/tenants \
  -H "Content-Type: application/json" \
  -d '{"name": "staging"}'

# Submit a create operation
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

# Poll for completion
curl http://localhost:8000/tasks/abc123

# List stacks
curl "http://localhost:8000/stacks?tenant=staging"

# Destroy
curl -X POST http://localhost:8000/stacks/operations \
  -H "Content-Type: application/json" \
  -d '{
    "component_class": "postgres_infra.component.PostgresDatabase",
    "operation": "delete",
    "tenant": "staging",
    "passphrase": "db-secret",
    "stack_reference": "<ref-from-create-result>"
  }'
```

## Stopping

```bash
docker compose down
docker compose down -v  # also removes the state volume
```

## Source

See [`examples/api-postgres/`](https://github.com/mike-fi/pulice/tree/main/examples/api-postgres) for the full implementation.
