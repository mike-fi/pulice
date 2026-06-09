"""AWS RDS PostgreSQL managed component.

Creates:
1. A VPC security group allowing inbound PostgreSQL traffic
2. A DB subnet group for VPC placement
3. An RDS PostgreSQL instance
"""

from __future__ import annotations
import pulumi
import pulumi_aws as aws
from pydantic import Field
from pulice import ComponentArgs, ManagedComponent


class PostgresDatabaseArgs(ComponentArgs):
    """Arguments for the PostgreSQL database component.

    Args:
        name: Logical name for the database instance.
        instance_class: RDS instance type.
        allocated_storage: Storage in GB.
        engine_version: PostgreSQL engine version.
        master_username: Master database username.
        vpc_id: VPC ID for the security group.
        subnet_ids: Comma-separated subnet IDs for the DB subnet group.
    """

    instance_class: str = Field(
        default='db.t3.micro',
        description='RDS instance type',
    )
    allocated_storage: int = Field(
        default=20,
        description='Allocated storage in GB',
    )
    engine_version: str = Field(
        default='16.4',
        description='PostgreSQL engine version',
    )
    master_username: str = Field(
        default='pulice_admin',
        description='Master database username',
    )
    vpc_id: str = Field(
        description='VPC ID for the security group',
    )
    subnet_ids: str = Field(
        description='Comma-separated subnet IDs for the DB subnet group',
    )


class PostgresDatabase(ManagedComponent):
    """AWS RDS PostgreSQL instance with networking.

    Provisions a security group, subnet group, and RDS instance
    configured for PostgreSQL.
    """

    args_model = PostgresDatabaseArgs

    def __init__(
        self,
        name: str,
        args: PostgresDatabaseArgs,
        opts: pulumi.ResourceOptions | None = None,
        **kwargs,
    ) -> None:
        super().__init__('pulice:example:PostgresDatabase', name, {}, opts)

        child_opts = pulumi.ResourceOptions(parent=self)
        subnet_list = [s.strip() for s in args.subnet_ids.split(',')]

        # --- Security Group ---
        sg = aws.ec2.SecurityGroup(
            f'{name}-sg',
            vpc_id=args.vpc_id,
            description=f'Allow PostgreSQL access for {name}',
            ingress=[
                aws.ec2.SecurityGroupIngressArgs(
                    protocol='tcp',
                    from_port=5432,
                    to_port=5432,
                    cidr_blocks=['10.0.0.0/8'],
                    description='PostgreSQL from private networks',
                ),
            ],
            egress=[
                aws.ec2.SecurityGroupEgressArgs(
                    protocol='-1',
                    from_port=0,
                    to_port=0,
                    cidr_blocks=['0.0.0.0/0'],
                ),
            ],
            opts=child_opts,
        )

        # --- DB Subnet Group ---
        subnet_group = aws.rds.SubnetGroup(
            f'{name}-subnet-group',
            subnet_ids=subnet_list,
            description=f'Subnet group for {name}',
            opts=child_opts,
        )

        # --- RDS Instance ---
        db = aws.rds.Instance(
            f'{name}-db',
            engine='postgres',
            engine_version=args.engine_version,
            instance_class=args.instance_class,
            allocated_storage=args.allocated_storage,
            db_name=name.replace('-', '_'),
            username=args.master_username,
            manage_master_user_password=True,
            db_subnet_group_name=subnet_group.name,
            vpc_security_group_ids=[sg.id],
            skip_final_snapshot=True,
            publicly_accessible=False,
            opts=child_opts,
        )

        # --- Outputs ---
        self.register_outputs(
            {
                'endpoint': db.endpoint,
                'address': db.address,
                'port': db.port,
                'db_name': db.db_name,
                'security_group_id': sg.id,
            }
        )
