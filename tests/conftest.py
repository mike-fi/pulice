"""Pytest configuration and fixtures for pulice tests."""

import pytest
from typing import Any


@pytest.fixture
def mock_pulumi_set_mocks():
    """Set up Pulumi mocks for testing.

    This fixture configures Pulumi to run in test mode with mocked resources.
    """
    import pulumi

    class PuliceMocks(pulumi.runtime.Mocks):
        """Mock implementation for Pulumi resources."""

        def new_resource(self, args: pulumi.runtime.MockResourceArgs) -> tuple[str, dict[str, Any]]:
            outputs = args.inputs
            if args.typ == 'aws:iam/role:Role':
                outputs['arn'] = f'arn:aws:iam::123456789012:role/{args.name}'
                outputs['id'] = f'{args.name}-id'
                outputs['name'] = args.name
            elif args.typ == 'aws:cloudwatch/logGroup:LogGroup':
                outputs['arn'] = f'arn:aws:logs:us-east-1:123456789012:log-group:{args.name}'
                outputs['id'] = args.name
                outputs['name'] = args.inputs.get('name', args.name)
            return f'{args.name}_id', outputs

        def call(self, args: pulumi.runtime.MockCallArgs) -> dict[str, Any]:
            return {}

    pulumi.runtime.set_mocks(PuliceMocks())
