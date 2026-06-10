# Static Website (S3 + CloudFront)

This example provisions a static website hosting stack with S3 and CloudFront.

## What It Creates

- **S3 Bucket** — Configured for static website hosting (index.html / error.html)
- **Origin Access Identity** — Secure access from CloudFront to S3
- **Bucket Policy** — Allows CloudFront OAI to read objects
- **CloudFront Distribution** — CDN with configurable price class

## Prerequisites

- AWS account with credentials configured
- Pulumi CLI installed

## Setup

```bash
cd examples/static-website
uv sync

export AWS_REGION=us-east-1  # CloudFront requires us-east-1 for certificates
```

## Usage

```bash
# Create a tenant
static-website tenant create --name web

# Create a static website stack
static-website website create \
    --name my-blog \
    --price-class PriceClass_100 \
    --aws-region us-east-1 \
    --tenant web \
    --passphrase secret

# Check status
static-website website status \
    --stack-reference <ref> \
    --tenant web \
    --passphrase secret

# Upload content (after stack is created)
aws s3 cp ./site/ s3://my-blog-<unique>/ --recursive

# Update (e.g., change price class)
static-website website update \
    --name my-blog \
    --price-class PriceClass_200 \
    --stack-reference <ref> \
    --tenant web \
    --passphrase secret

# Destroy
static-website website delete \
    --stack-reference <ref> \
    --tenant web \
    --passphrase secret
```

## Custom Domain

Pass `--domain-name` to associate a custom domain with the CloudFront distribution:

```bash
static-website website create \
    --name company-site \
    --domain-name www.example.com \
    --tenant web \
    --passphrase secret
```

Note: You'll need to create a Route53 record or DNS alias pointing to the CloudFront distribution separately.

## Source

See [`examples/static-website/`](https://github.com/mike-fi/pulice/tree/main/examples/static-website) for the full implementation.
