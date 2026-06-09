# Bootstrap Usecase

A pulice example that bootstraps a GitHub Enterprise repository with AWS CodeBuild self-hosted GitHub Action runners.

## What It Creates

1. **GitHub Enterprise Provider** — Configured for your GHE server
2. **GitHub Repository** — A new repo under your organization on GHE
3. **AWS CodeBuild Project** — Configured as a self-hosted GitHub Actions runner (GITHUB_ENTERPRISE source)
4. **IAM Role** — Permissions for CodeBuild to run builds and write logs
5. **GitHub Webhook** — Triggers CodeBuild on `workflow_job` events

## Prerequisites

- An active AWS account with credentials configured (`aws configure` or env vars)
- A GitHub Enterprise Server with a personal access token (`repo` and `admin:repo_hook` scopes)
- Pulumi CLI installed

## Setup

```bash
cd examples/bootstrap-usecase
uv sync

# Configure providers
export AWS_REGION=eu-central-1
export GITHUB_TOKEN=ghp_your_token_here  # GHE personal access token
```

## Usage

```bash
# Create a tenant
bootstrap tenant create --name myteam

# Bootstrap the repository + CodeBuild runner
bootstrap bootstrap create \
    --name my-service \
    --github-org your-org \
    --github-base-url https://github.example.com/api/v3/ \
    --repo-description "My service repository" \
    --repo-visibility private \
    --aws-region eu-central-1 \
    --runner-labels codebuild \
    --tenant myteam \
    --passphrase my-secret

# Check status
bootstrap bootstrap status \
    --stack-reference <ref-from-create> \
    --tenant myteam \
    --passphrase my-secret

# Tear it down
bootstrap bootstrap delete \
    --stack-reference <ref-from-create> \
    --tenant myteam \
    --passphrase my-secret
```

## How It Works

After provisioning, any GitHub Actions workflow in the new repository can target the self-hosted runner:

```yaml
# .github/workflows/build.yml
jobs:
  build:
    runs-on: codebuild
    steps:
      - uses: actions/checkout@v4
      - run: echo "Running on CodeBuild!"
```

The `workflow_job` webhook notifies CodeBuild, which picks up the job and executes it.

## Component Args

| Argument | Default | Description |
|----------|---------|-------------|
| `name` | (required) | Logical name for the resource group |
| `github-org` | (required) | GitHub organization or user |
| `github-base-url` | (required) | GHE API URL (e.g. `https://github.example.com/api/v3/`) |
| `repo-description` | `""` | Repository description |
| `repo-visibility` | `private` | `public` or `private` |
| `aws-region` | `eu-central-1` | AWS region for CodeBuild |
| `compute-type` | `BUILD_GENERAL1_SMALL` | CodeBuild compute type |
| `image` | `amazonlinux2-x86_64-standard:5.0` | Build environment image |
| `runner-labels` | `codebuild` | Comma-separated runner labels |
