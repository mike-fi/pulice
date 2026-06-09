"""Bootstrap usecase: GitHub repo + AWS CodeBuild self-hosted runners.

Creates:
1. A GitHub repository
2. An AWS CodeBuild project configured as a GitHub Actions self-hosted runner
3. A GitHub webhook that triggers CodeBuild on workflow_job events
"""

from __future__ import annotations
import json
import pulumi
import pulumi_aws as aws
import pulumi_github as github
from pydantic import Field
from pulice import ComponentArgs, ManagedComponent


class BootstrapUsecaseArgs(ComponentArgs):
    """Arguments for the bootstrap usecase component.

    Args:
        name: Logical name for the resource group.
        github_org: GitHub organization or user that owns the repository.
        github_base_url: GitHub Enterprise Server API URL (e.g. https://github.example.com/api/v3/).
        repo_description: Description for the GitHub repository.
        repo_visibility: Repository visibility (public or private).
        aws_region: AWS region for CodeBuild resources.
        compute_type: CodeBuild compute type.
        image: CodeBuild build environment image.
        runner_labels: Comma-separated labels for the self-hosted runner.
    """

    github_org: str = Field(description='GitHub organization or user')
    github_base_url: str = Field(
        description='GitHub Enterprise Server API URL (e.g. https://github.example.com/api/v3/)',
    )
    repo_description: str = Field(
        default='',
        description='Description for the GitHub repository',
    )
    repo_visibility: str = Field(
        default='private',
        description='Repository visibility (public or private)',
    )
    aws_region: str = Field(
        default='eu-central-1',
        description='AWS region for CodeBuild resources',
    )
    compute_type: str = Field(
        default='BUILD_GENERAL1_SMALL',
        description='CodeBuild compute type',
    )
    image: str = Field(
        default='aws/codebuild/amazonlinux2-x86_64-standard:5.0',
        description='CodeBuild build environment image',
    )
    runner_labels: str = Field(
        default='codebuild',
        description='Comma-separated labels for the self-hosted runner',
    )


class BootstrapUsecase(ManagedComponent):
    """Bootstrap a GitHub repository with AWS CodeBuild self-hosted Action runners.

    This component provisions:
    - A GitHub repository under the specified organization
    - An IAM role for CodeBuild with permissions to run builds
    - A CodeBuild project configured as a GitHub Actions runner
    - A GitHub webhook that notifies CodeBuild on workflow_job events
    """

    args_model = BootstrapUsecaseArgs

    def __init__(
        self,
        name: str,
        args: BootstrapUsecaseArgs,
        opts: pulumi.ResourceOptions | None = None,
        **kwargs,
    ) -> None:
        super().__init__('pulice:example:BootstrapUsecase', name, {}, opts)

        child_opts = pulumi.ResourceOptions(parent=self)

        # --- GitHub Enterprise Provider ---
        gh_provider = github.Provider(
            f'{name}-github-provider',
            base_url=args.github_base_url,
            owner=args.github_org,
            opts=child_opts,
        )

        gh_opts = pulumi.ResourceOptions(parent=self, provider=gh_provider)

        # --- GitHub Repository ---
        repo = github.Repository(
            f'{name}-repo',
            name=args.name,
            description=args.repo_description,
            visibility=args.repo_visibility,
            auto_init=True,
            opts=gh_opts,
        )

        # --- IAM Role for CodeBuild ---
        assume_role_policy = json.dumps(
            {
                'Version': '2012-10-17',
                'Statement': [
                    {
                        'Effect': 'Allow',
                        'Principal': {'Service': 'codebuild.amazonaws.com'},
                        'Action': 'sts:AssumeRole',
                    }
                ],
            }
        )

        codebuild_role = aws.iam.Role(
            f'{name}-codebuild-role',
            assume_role_policy=assume_role_policy,
            opts=child_opts,
        )

        aws.iam.RolePolicyAttachment(
            f'{name}-codebuild-policy',
            role=codebuild_role.name,
            policy_arn='arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly',
            opts=child_opts,
        )

        aws.iam.RolePolicy(
            f'{name}-codebuild-inline-policy',
            role=codebuild_role.id,
            policy=json.dumps(
                {
                    'Version': '2012-10-17',
                    'Statement': [
                        {
                            'Effect': 'Allow',
                            'Action': [
                                'logs:CreateLogGroup',
                                'logs:CreateLogStream',
                                'logs:PutLogEvents',
                            ],
                            'Resource': '*',
                        },
                        {
                            'Effect': 'Allow',
                            'Action': [
                                'codebuild:CreateReportGroup',
                                'codebuild:CreateReport',
                                'codebuild:UpdateReport',
                                'codebuild:BatchPutTestCases',
                                'codebuild:BatchPutCodeCoverages',
                            ],
                            'Resource': '*',
                        },
                    ],
                }
            ),
            opts=child_opts,
        )

        # --- CodeBuild Project (GitHub Actions Runner) ---
        codebuild_project = aws.codebuild.Project(
            f'{name}-codebuild',
            name=f'{args.name}-runner',
            description=f'Self-hosted GitHub Actions runner for {args.github_org}/{args.name}',
            service_role=codebuild_role.arn,
            source=aws.codebuild.ProjectSourceArgs(
                type='GITHUB_ENTERPRISE',
                location=repo.http_clone_url,
                buildspec='',
            ),
            environment=aws.codebuild.ProjectEnvironmentArgs(
                compute_type=args.compute_type,
                image=args.image,
                type='LINUX_CONTAINER',
                privileged_mode=True,
            ),
            artifacts=aws.codebuild.ProjectArtifactsArgs(type='NO_ARTIFACTS'),
            logs_config=aws.codebuild.ProjectLogsConfigArgs(
                cloudwatch_logs=aws.codebuild.ProjectLogsConfigCloudwatchLogsArgs(
                    group_name=f'/aws/codebuild/{args.name}-runner',
                    stream_name='build',
                ),
            ),
            opts=child_opts,
        )

        # --- GitHub Webhook for workflow_job events ---
        webhook = github.RepositoryWebhook(
            f'{name}-webhook',
            repository=repo.name,
            configuration=github.RepositoryWebhookConfigurationArgs(
                url=pulumi.Output.all(codebuild_project.arn, args.aws_region).apply(
                    lambda vals: f'https://codebuild.{vals[1]}.amazonaws.com/webhooks/trigger'
                ),
                content_type='json',
                insecure_ssl=False,
            ),
            events=['workflow_job'],
            opts=gh_opts,
        )

        # --- Outputs ---
        self.register_outputs(
            {
                'repository_url': repo.html_url,
                'repository_clone_url': repo.http_clone_url,
                'codebuild_project_name': codebuild_project.name,
                'codebuild_project_arn': codebuild_project.arn,
                'webhook_url': webhook.url,
            }
        )
