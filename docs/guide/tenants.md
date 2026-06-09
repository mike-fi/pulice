# Tenant Management

Tenants are named isolation boundaries that own stacks. Every stack operation requires a tenant, ensuring that resources belonging to different environments, teams, or customers are completely separated.

## Why Tenants

- **Namespace isolation** — Two tenants can have identically-named components without collision
- **Access control** — A stack reference only works with the correct tenant
- **Lifecycle management** — Delete a tenant only when all its stacks are cleaned up

## Creating Tenants

### CLI

```bash
pulice tenant create --name production
pulice tenant create --name staging
```

### API

```bash
curl -X POST http://localhost:8000/tenants \
  -H "Content-Type: application/json" \
  -d '{"name": "production"}'
```

## Listing Tenants

### CLI

```bash
pulice tenant list
```

Output:

```
default  (id: default, created: 2024-01-01T00:00:00)
production  (id: a1b2c3..., created: 2024-06-15T10:30:00)
staging  (id: d4e5f6..., created: 2024-06-15T10:31:00)
```

### API

```bash
curl http://localhost:8000/tenants
```

## The Default Tenant

Pulice automatically creates a `default` tenant on first use. This exists for backward compatibility with stacks created before the tenant system was introduced. For new projects, create named tenants.

## Deleting Tenants

A tenant can only be deleted when it has no stacks:

```bash
# This fails if stacks exist
pulice tenant delete --name staging

# First delete all stacks, then the tenant
pulice my-component delete --stack-reference <ref> --tenant staging --passphrase <p>
pulice tenant delete --name staging
```

## Stack Naming

Stacks are named with the tenant ID prefix to prevent collisions:

```
{tenant_id}-{component_name}-{stack_uuid}
```

This means two tenants can each have a component named "database" with a stack named "primary" without conflict.

## Tenant-Scoped Queries

When listing stacks, results are always scoped to a tenant:

```bash
# CLI
pulice my-component list --tenant production

# API
curl "http://localhost:8000/stacks?tenant=production"
```
