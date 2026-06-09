# Kubernetes Namespace Management

A pulice example that manages Kubernetes namespaces with resource quotas and limit ranges. Designed for use with minikube.

## What It Creates

1. **Namespace** — With custom labels
2. **ResourceQuota** — CPU and memory caps for the namespace
3. **LimitRange** — Default container resource requests/limits

## Prerequisites

- [minikube](https://minikube.sigs.k8s.io/) installed and running
- `kubectl` configured
- Pulumi CLI installed

## Setup

```bash
minikube start
kubectl cluster-info

cd examples/kubernetes-deploy
uv sync
```

## Usage (CLI)

```bash
# Create a tenant
k8s-deploy tenant create --name ops

# Create a namespace with resource governance
k8s-deploy namespace create \
    --name team-backend \
    --labels "team=backend,env=dev" \
    --cpu-limit 8 \
    --memory-limit 16Gi \
    --default-cpu 200m \
    --default-memory 512Mi \
    --tenant ops \
    --passphrase secret

# List managed namespaces
k8s-deploy namespace list --tenant ops

# Verify with kubectl
kubectl get namespace team-backend
kubectl describe resourcequota -n team-backend
kubectl describe limitrange -n team-backend

# Update quotas
k8s-deploy namespace update \
    --name team-backend \
    --cpu-limit 16 \
    --memory-limit 32Gi \
    --stack-reference <ref> \
    --tenant ops \
    --passphrase secret

# Destroy
k8s-deploy namespace delete \
    --stack-reference <ref> \
    --tenant ops \
    --passphrase secret
```

## Deploying Pulice to Kubernetes

You can also run Pulice itself inside the cluster:

```bash
# Build the image in minikube's Docker
eval $(minikube docker-env)
docker build -t pulice-k8s:latest .

# Deploy
kubectl apply -f k8s/deployment.yaml

# Access the API
minikube service pulice-api -n pulice --url
# or
kubectl port-forward svc/pulice-api -n pulice 8000:8000
```

## Component Args

| Argument | Default | Description |
|----------|---------|-------------|
| `name` | (required) | Namespace name |
| `labels` | `""` | Comma-separated key=value pairs |
| `cpu-limit` | `4` | Total CPU quota |
| `memory-limit` | `8Gi` | Total memory quota |
| `default-cpu` | `100m` | Default container CPU |
| `default-memory` | `256Mi` | Default container memory |
