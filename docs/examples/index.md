# Examples

Complete working examples demonstrating different ways to use pulice.

## Overview

| Example | Interface | Providers | Demonstrates |
|---------|-----------|-----------|--------------|
| [Bootstrap](bootstrap.md) | CLI | AWS + GitHub Enterprise | Multi-provider, webhooks, IAM, GHE |
| [API + Postgres](api-postgres.md) | HTTP API | AWS (RDS) | Docker Compose, async operations, polling |
| [Kubernetes](kubernetes.md) | CLI | Kubernetes | Non-cloud provider, minikube, RBAC |
| [Static Website](static-website.md) | CLI | AWS (S3 + CloudFront) | Multi-resource composition, CDN |

## Structure

Each example is a standalone Python project in the `examples/` directory:

```
examples/
├── bootstrap-usecase/      # GitHub Enterprise + CodeBuild runners
├── api-postgres/           # Docker Compose API deployment + RDS
├── kubernetes-deploy/      # Minikube namespace management
└── static-website/         # S3 + CloudFront static hosting
```

## Running an Example

```bash
cd examples/<example-name>
uv sync
# Follow the example's README for provider-specific setup
```

All examples share the same patterns:

1. Define a `ComponentArgs` subclass with your resource inputs
2. Define a `ManagedComponent` subclass that provisions resources
3. Register on a `PuliceCLI` (or expose via the HTTP API)
4. Use tenant isolation to separate environments
