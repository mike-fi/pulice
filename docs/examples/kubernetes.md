# Kubernetes Namespace Management

This example uses Pulice with the `pulumi-kubernetes` provider to manage Kubernetes namespaces with resource quotas and limit ranges. Designed to run against a local minikube cluster.

## What It Creates

- **Namespace** — With custom labels
- **ResourceQuota** — CPU and memory limits for the namespace
- **LimitRange** — Default container resource requests/limits

## Prerequisites

- [minikube](https://minikube.sigs.k8s.io/) installed and running
- `kubectl` configured to talk to minikube
- Pulumi CLI installed

## Setup

```bash
# Start minikube
minikube start

# Verify connectivity
kubectl cluster-info

cd examples/kubernetes-deploy
uv sync
```

## Usage

```bash
# Create a tenant
k8s-deploy tenant create --name ops

# Create a namespace with resource quotas
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

# Check status
k8s-deploy namespace status \
    --stack-reference <ref> \
    --tenant ops \
    --passphrase secret

# Verify in kubectl
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

The `k8s/deployment.yaml` manifest deploys Pulice itself to the cluster:

```bash
kubectl apply -f k8s/deployment.yaml
kubectl port-forward svc/pulice-api 8000:8000
```

This gives you an in-cluster Pulice API that can manage namespaces via HTTP.

## Source

See [`examples/kubernetes-deploy/`](https://github.com/your-org/pulice/tree/main/examples/kubernetes-deploy) for the full implementation.
