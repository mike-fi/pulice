# How to Work with Pulice

A practical guide walking through a complete lifecycle: tenant setup, stack creation, operations, failure recovery, and cleanup.

## Setting Up

### Create a Tenant

Every stack belongs to a tenant. Start by creating one:

```
$ pulice tenant create --name dev
Tenant created: dev (id: 7a3b9c1e4f2d8a6b)
```

List existing tenants:

```
$ pulice tenant list
default  (id: default, created: 2026-01-01T00:00:00)
dev  (id: 7a3b9c1e4f2d8a6b, created: 2026-04-29T14:30:00)
```

## Creating a Stack

### With Inline Arguments

```
$ pulice website create --name my-blog --aws-region us-east-1 --tenant dev --passphrase secret
Stack reference: f4e2a1b8c9d0e3f5a7b6
Updating (7a3b9c1e-website-f4e2a1b8c9d0e3f5a7b6):

    pulumi:pulumi:Stack website-f4e2a1b8 creating...
 +  aws:s3:BucketV2 my-blog-bucket created (1s)
 +  aws:cloudfront:OriginAccessIdentity my-blog-oai created (2s)
 +  aws:s3:BucketPolicy my-blog-policy created (1s)
 +  aws:cloudfront:Distribution my-blog-cdn created (4m12s)
    pulumi:pulumi:Stack website-f4e2a1b8 created

Resources:
    + 4 created

Duration: 4m18s
```

### Interactive Mode

If you omit `--tenant` and `--passphrase`, pulice prompts interactively:

```
$ pulice website create --name my-blog --aws-region us-east-1
Select a tenant:
  [1] default
  [2] dev
Tenant number: 2
Passphrase: ********
Stack reference: a1b2c3d4e5f6g7h8i9j0
Updating (7a3b9c1e-website-a1b2c3d4e5f6g7h8i9j0):
...
```

## Listing Stacks

```
$ pulice website list --tenant dev
7a3b9c1e-website-f4e2a1b8c9d0e3f5a7b6  ref=f4e2a1b8c9d0e3f5a7b6
7a3b9c1e-website-a1b2c3d4e5f6g7h8i9j0  ref=a1b2c3d4e5f6g7h8i9j0
```

The `ref=` value is what you pass to `--stack-reference` in subsequent commands.

## Checking Status

```
$ pulice website status --stack-reference f4e2a1b8c9d0e3f5a7b6 --tenant dev --passphrase secret
stack_name: 7a3b9c1e-website-f4e2a1b8c9d0e3f5a7b6
resource_count: 4
last_update: 2026-04-29 14:35:22
url: None
```

## Updating a Stack

Modify resource properties by passing new values:

```
$ pulice website update \
    --name my-blog \
    --price-class PriceClass_200 \
    --stack-reference f4e2a1b8c9d0e3f5a7b6 \
    --tenant dev \
    --passphrase secret
Updating (7a3b9c1e-website-f4e2a1b8c9d0e3f5a7b6):

 ~  aws:cloudfront:Distribution my-blog-cdn updated (45s)

Resources:
    ~ 1 updated
    3 unchanged

Duration: 48s
```

## Handling Failures

### Create Fails Midway

If `create` fails, the stack reference is already saved:

```
$ pulice website create --name broken --aws-region us-east-1 --tenant dev --passphrase secret
Stack reference: dead0000beef1111cafe2222
Updating (7a3b9c1e-website-dead0000beef1111cafe2222):

 +  aws:s3:BucketV2 broken-bucket created (1s)
    error: aws:cloudfront:Distribution broken-cdn: AccessDenied: ...

Resources:
    + 1 created

Duration: 5s

The update failed.
```

You can still find and manage it:

```
$ pulice website list --tenant dev
7a3b9c1e-website-dead0000beef1111cafe2222  ref=dead0000beef1111cafe2222
```

### Retry After Fixing the Issue

Fix the underlying problem (e.g., IAM permissions) and retry with `update`:

```
$ pulice website update \
    --name broken \
    --stack-reference dead0000beef1111cafe2222 \
    --tenant dev \
    --passphrase secret
```

### Clean Up a Failed Stack

If you just want to destroy whatever was partially created:

```
$ pulice website delete --stack-reference dead0000beef1111cafe2222 --tenant dev --passphrase secret
Destroying (7a3b9c1e-website-dead0000beef1111cafe2222):

 -  aws:s3:BucketV2 broken-bucket deleted (1s)
    pulumi:pulumi:Stack website-dead0000 deleted

Resources:
    - 1 deleted

Duration: 3s

Stack dead0000beef1111cafe2222 destroyed and removed.
```

### Wrong Passphrase

```
$ pulice website status --stack-reference f4e2a1b8c9d0e3f5a7b6 --tenant dev --passphrase wrong
Error: Invalid passphrase for stack '7a3b9c1e-website-f4e2a1b8c9d0e3f5a7b6'.
```

### Unknown Tenant

```
$ pulice website list --tenant staging
Error: Tenant 'staging' not found.
```

## Exporting and Importing State

### Export for Backup

```
$ pulice website export \
    --stack-reference f4e2a1b8c9d0e3f5a7b6 \
    --tenant dev \
    --passphrase secret \
    --output backup.json
Exported to backup.json
```

### Import (Restore)

```
$ pulice website import \
    --stack-reference f4e2a1b8c9d0e3f5a7b6 \
    --tenant dev \
    --passphrase secret \
    --input backup.json
Import complete.
```

## Refreshing State

Reconcile Pulumi state with actual cloud resources (useful after manual changes):

```
$ pulice website refresh --stack-reference f4e2a1b8c9d0e3f5a7b6 --tenant dev --passphrase secret
Refreshing (7a3b9c1e-website-f4e2a1b8c9d0e3f5a7b6):

 ~  aws:s3:BucketV2 my-blog-bucket updated (drift detected)

Resources:
    ~ 1 updated
    3 unchanged

Duration: 8s
```

## Destroying a Stack

```
$ pulice website delete --stack-reference f4e2a1b8c9d0e3f5a7b6 --tenant dev --passphrase secret
Destroying (7a3b9c1e-website-f4e2a1b8c9d0e3f5a7b6):

 -  aws:cloudfront:Distribution my-blog-cdn deleted (3m45s)
 -  aws:s3:BucketPolicy my-blog-policy deleted (1s)
 -  aws:cloudfront:OriginAccessIdentity my-blog-oai deleted (1s)
 -  aws:s3:BucketV2 my-blog-bucket deleted (1s)
    pulumi:pulumi:Stack website-f4e2a1b8 deleted

Resources:
    - 4 deleted

Duration: 3m50s

Stack f4e2a1b8c9d0e3f5a7b6 destroyed and removed.
```

The stack no longer appears in `list`:

```
$ pulice website list --tenant dev
No stacks found.
```

## Deleting a Tenant

Tenants can only be deleted when they have no stacks:

```
$ pulice tenant delete --name dev
Tenant deleted: dev
```
