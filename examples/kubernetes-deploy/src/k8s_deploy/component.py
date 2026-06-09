"""Kubernetes namespace with resource quotas and limit ranges.

Creates:
1. A Kubernetes Namespace with labels
2. A ResourceQuota with CPU and memory limits
3. A LimitRange with default container resource constraints
"""

from __future__ import annotations
import pulumi
import pulumi_kubernetes as k8s
from pydantic import Field
from pulice import ComponentArgs, ManagedComponent


class KubernetesNamespaceArgs(ComponentArgs):
    """Arguments for the Kubernetes namespace component.

    Args:
        name: Namespace name.
        labels: Comma-separated key=value label pairs.
        cpu_limit: Total CPU limit for the namespace.
        memory_limit: Total memory limit for the namespace.
        default_cpu: Default CPU request/limit per container.
        default_memory: Default memory request/limit per container.
    """

    labels: str = Field(
        default='',
        description='Comma-separated key=value label pairs (e.g. team=backend,env=dev)',
    )
    cpu_limit: str = Field(
        default='4',
        description='Total CPU limit for the namespace',
    )
    memory_limit: str = Field(
        default='8Gi',
        description='Total memory limit for the namespace',
    )
    default_cpu: str = Field(
        default='100m',
        description='Default CPU request/limit per container',
    )
    default_memory: str = Field(
        default='256Mi',
        description='Default memory request/limit per container',
    )


class KubernetesNamespace(ManagedComponent):
    """Kubernetes namespace with resource governance.

    Provisions a namespace with labels, a ResourceQuota to cap total
    resource usage, and a LimitRange to set default container limits.
    """

    args_model = KubernetesNamespaceArgs

    def __init__(
        self,
        name: str,
        args: KubernetesNamespaceArgs,
        opts: pulumi.ResourceOptions | None = None,
        **kwargs,
    ) -> None:
        super().__init__('pulice:example:KubernetesNamespace', name, {}, opts)

        child_opts = pulumi.ResourceOptions(parent=self)

        # Parse labels
        label_dict = {'managed-by': 'pulice'}
        if args.labels:
            for pair in args.labels.split(','):
                k, _, v = pair.strip().partition('=')
                if k:
                    label_dict[k] = v

        # --- Namespace ---
        namespace = k8s.core.v1.Namespace(
            f'{name}-ns',
            metadata=k8s.meta.v1.ObjectMetaArgs(
                name=args.name,
                labels=label_dict,
            ),
            opts=child_opts,
        )

        ns_name = namespace.metadata.name

        # --- ResourceQuota ---
        quota = k8s.core.v1.ResourceQuota(
            f'{name}-quota',
            metadata=k8s.meta.v1.ObjectMetaArgs(
                name=f'{args.name}-quota',
                namespace=ns_name,
            ),
            spec=k8s.core.v1.ResourceQuotaSpecArgs(
                hard={
                    'limits.cpu': args.cpu_limit,
                    'limits.memory': args.memory_limit,
                    'requests.cpu': args.cpu_limit,
                    'requests.memory': args.memory_limit,
                },
            ),
            opts=child_opts,
        )

        # --- LimitRange ---
        limit_range = k8s.core.v1.LimitRange(
            f'{name}-limits',
            metadata=k8s.meta.v1.ObjectMetaArgs(
                name=f'{args.name}-limits',
                namespace=ns_name,
            ),
            spec=k8s.core.v1.LimitRangeSpecArgs(
                limits=[
                    k8s.core.v1.LimitRangeItemArgs(
                        type='Container',
                        default={
                            'cpu': args.default_cpu,
                            'memory': args.default_memory,
                        },
                        default_request={
                            'cpu': args.default_cpu,
                            'memory': args.default_memory,
                        },
                    ),
                ],
            ),
            opts=child_opts,
        )

        # --- Outputs ---
        self.register_outputs(
            {
                'namespace_name': ns_name,
                'quota_name': quota.metadata.name,
                'limit_range_name': limit_range.metadata.name,
            }
        )
