# Static Website

A pulice example that provisions static website hosting with S3 and CloudFront.

## What It Creates

1. **S3 Bucket** — Configured for static website hosting (index.html / error.html)
2. **Origin Access Identity** — Secure CloudFront-to-S3 access
3. **Bucket Policy** — Grants read access to the CloudFront OAI
4. **CloudFront Distribution** — Global CDN with HTTPS

## Prerequisites

- AWS account with credentials configured
- Pulumi CLI installed

## Setup

```bash
cd examples/static-website
uv sync

export AWS_REGION=us-east-1
```

## Usage

```bash
# Create a tenant
static-website tenant create --name web

# Create the website stack
static-website website create \
    --name my-blog \
    --price-class PriceClass_100 \
    --tenant web \
    --passphrase secret

# Upload content
aws s3 cp ./my-site/ s3://<bucket-name>/ --recursive

# Check status
static-website website status \
    --stack-reference <ref> \
    --tenant web \
    --passphrase secret

# Destroy
static-website website delete \
    --stack-reference <ref> \
    --tenant web \
    --passphrase secret
```

## Component Args

| Argument | Default | Description |
|----------|---------|-------------|
| `name` | (required) | Logical name for the website |
| `domain-name` | `""` | Custom domain (optional) |
| `price-class` | `PriceClass_100` | CloudFront price class |
| `aws-region` | `us-east-1` | AWS region for S3 bucket |
