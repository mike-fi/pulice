"""Static website hosting with S3 and CloudFront.

Creates:
1. An S3 bucket configured for static website hosting
2. A CloudFront Origin Access Identity
3. A bucket policy granting read access to the OAI
4. A CloudFront distribution serving the S3 content
"""

from __future__ import annotations
import json
import pulumi
import pulumi_aws as aws
from pydantic import Field
from pulice import ComponentArgs, ManagedComponent


class StaticWebsiteArgs(ComponentArgs):
    """Arguments for the static website component.

    Args:
        name: Logical name for the website.
        domain_name: Custom domain name for the CloudFront distribution.
        price_class: CloudFront price class (PriceClass_100, PriceClass_200, PriceClass_All).
        aws_region: AWS region for the S3 bucket.
    """

    domain_name: str = Field(
        default='',
        description='Custom domain name for CloudFront (optional)',
    )
    price_class: str = Field(
        default='PriceClass_100',
        description='CloudFront price class (PriceClass_100, PriceClass_200, PriceClass_All)',
    )
    aws_region: str = Field(
        default='us-east-1',
        description='AWS region for the S3 bucket',
    )


class StaticWebsite(ManagedComponent):
    """Static website hosting with S3 and CloudFront.

    Provisions an S3 bucket for content, a CloudFront distribution for
    global edge delivery, and the necessary access policies.
    """

    args_model = StaticWebsiteArgs

    def __init__(
        self,
        name: str,
        args: StaticWebsiteArgs,
        opts: pulumi.ResourceOptions | None = None,
        **kwargs,
    ) -> None:
        super().__init__('pulice:example:StaticWebsite', name, {}, opts)

        child_opts = pulumi.ResourceOptions(parent=self)

        # --- S3 Bucket ---
        bucket = aws.s3.BucketV2(
            f'{name}-bucket',
            bucket=f'{name}-{pulumi.get_stack()[:8]}',
            opts=child_opts,
        )

        aws.s3.BucketWebsiteConfigurationV2(
            f'{name}-website-config',
            bucket=bucket.id,
            index_document=aws.s3.BucketWebsiteConfigurationV2IndexDocumentArgs(
                suffix='index.html',
            ),
            error_document=aws.s3.BucketWebsiteConfigurationV2ErrorDocumentArgs(
                key='error.html',
            ),
            opts=child_opts,
        )

        # --- Origin Access Identity ---
        oai = aws.cloudfront.OriginAccessIdentity(
            f'{name}-oai',
            comment=f'OAI for {name} static website',
            opts=child_opts,
        )

        # --- Bucket Policy ---
        aws.s3.BucketPolicy(
            f'{name}-policy',
            bucket=bucket.id,
            policy=pulumi.Output.all(bucket.arn, oai.iam_arn).apply(
                lambda vals: json.dumps(
                    {
                        'Version': '2012-10-17',
                        'Statement': [
                            {
                                'Effect': 'Allow',
                                'Principal': {'AWS': vals[1]},
                                'Action': 's3:GetObject',
                                'Resource': f'{vals[0]}/*',
                            }
                        ],
                    }
                )
            ),
            opts=child_opts,
        )

        # --- CloudFront Distribution ---
        aliases = [args.domain_name] if args.domain_name else []

        distribution = aws.cloudfront.Distribution(
            f'{name}-cdn',
            enabled=True,
            is_ipv6_enabled=True,
            default_root_object='index.html',
            price_class=args.price_class,
            aliases=aliases if aliases else None,
            origins=[
                aws.cloudfront.DistributionOriginArgs(
                    domain_name=bucket.bucket_regional_domain_name,
                    origin_id=f'S3-{name}',
                    s3_origin_config=aws.cloudfront.DistributionOriginS3OriginConfigArgs(
                        origin_access_identity=oai.cloudfront_access_identity_path,
                    ),
                )
            ],
            default_cache_behavior=aws.cloudfront.DistributionDefaultCacheBehaviorArgs(
                allowed_methods=['GET', 'HEAD', 'OPTIONS'],
                cached_methods=['GET', 'HEAD'],
                target_origin_id=f'S3-{name}',
                forwarded_values=aws.cloudfront.DistributionDefaultCacheBehaviorForwardedValuesArgs(
                    query_string=False,
                    cookies=aws.cloudfront.DistributionDefaultCacheBehaviorForwardedValuesCookiesArgs(
                        forward='none',
                    ),
                ),
                viewer_protocol_policy='redirect-to-https',
                min_ttl=0,
                default_ttl=3600,
                max_ttl=86400,
            ),
            restrictions=aws.cloudfront.DistributionRestrictionsArgs(
                geo_restriction=aws.cloudfront.DistributionRestrictionsGeoRestrictionArgs(
                    restriction_type='none',
                ),
            ),
            viewer_certificate=aws.cloudfront.DistributionViewerCertificateArgs(
                cloudfront_default_certificate=True,
            ),
            opts=child_opts,
        )

        # --- Outputs ---
        self.register_outputs(
            {
                'bucket_name': bucket.bucket,
                'bucket_arn': bucket.arn,
                'distribution_id': distribution.id,
                'distribution_domain': distribution.domain_name,
                'cloudfront_url': distribution.domain_name.apply(lambda d: f'https://{d}'),
            }
        )
