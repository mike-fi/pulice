# Bootstrap: GitHub Enterprise + CodeBuild

This example bootstraps a GitHub Enterprise repository with AWS CodeBuild configured as a self-hosted GitHub Actions runner.

## What It Creates

- **GitHub Provider** — Configured for your GitHub Enterprise Server
- **GitHub Repository** — Under your organization on GHE
- **IAM Role** — CodeBuild service role with logging and reporting permissions
- **CodeBuild Project** — Configured as a GitHub Actions self-hosted runner
- **GitHub Webhook** — Triggers CodeBuild on `workflow_job` events

## Prerequisites

- AWS account with credentials configured
- GitHub Enterprise Server with a PAT (`repo` + `admin:repo_hook` scopes)
- Pulumi CLI installed

## Setup

```bash
cd examples/bootstrap-usecase
uv sync

export AWS_REGION=eu-central-1
export GITHUB_TOKEN=ghp_your_ghe_token
```

## Usage

```bash
# Create a tenant
bootstrap tenant create --name platform

# Bootstrap the repository
bootstrap bootstrap create \
    --name my-service \
    --github-org my-org \
    --github-base-url https://github.example.com/api/v3/ \
    --aws-region eu-central-1 \
    --tenant platform \
    --passphrase my-secret

# List stacks
bootstrap bootstrap list --tenant platform

# Tear down
bootstrap bootstrap delete \
    --stack-reference <ref> \
    --tenant platform \
    --passphrase my-secret
```

## After Provisioning

Workflows in the new repository can target the CodeBuild runner:

```yaml
jobs:
  build:
    runs-on: codebuild
    steps:
      - uses: actions/checkout@v4
      - run: echo "Running on CodeBuild!"
```

## Source

See [`examples/bootstrap-usecase/`](https://github.com/mike-fi/pulice/tree/main/examples/bootstrap-usecase) for the full implementation.
