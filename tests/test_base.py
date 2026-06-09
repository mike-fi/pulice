"""Tests for pulice.base — ComponentArgs and ManagedComponent."""

import pytest
from pydantic import Field, ValidationError
from pulice.core.base import ComponentArgs, ManagedComponent

# ---------------------------------------------------------------------------
# ComponentArgs
# ---------------------------------------------------------------------------


class TestComponentArgs:
    """Validate the shared base model behaviour."""

    def test_name_is_required(self):
        with pytest.raises(ValidationError) as exc_info:
            ComponentArgs()  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        assert any(e['loc'] == ('name',) for e in errors)

    def test_name_accepted(self):
        args = ComponentArgs(name='my-resource')
        assert args.name == 'my-resource'

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            ComponentArgs(name='x', unknown_field='bad')  # type: ignore[call-arg]

    def test_subclass_adds_field(self):
        class MyArgs(ComponentArgs):
            region: str = Field('us-east-1', description='AWS region')

        args = MyArgs(name='r')
        assert args.region == 'us-east-1'

        args_overridden = MyArgs(name='r', region='eu-west-1')
        assert args_overridden.region == 'eu-west-1'

    def test_subclass_required_field_missing(self):
        class StrictArgs(ComponentArgs):
            account_id: str = Field(..., description='Account ID')

        with pytest.raises(ValidationError) as exc_info:
            StrictArgs(name='x')  # type: ignore[call-arg]
        assert any(e['loc'] == ('account_id',) for e in exc_info.value.errors())

    def test_subclass_extra_fields_still_forbidden(self):
        class MyArgs(ComponentArgs):
            region: str = Field('us-east-1')

        with pytest.raises(ValidationError):
            MyArgs(name='x', region='eu-west-1', bad='nope')  # type: ignore[call-arg]

    def test_model_roundtrip(self):
        class MyArgs(ComponentArgs):
            count: int = Field(3, description='Count')

        args = MyArgs(name='test', count=5)
        assert args.model_dump() == {'name': 'test', 'count': 5}


# ---------------------------------------------------------------------------
# ManagedComponent class variable contract
# ---------------------------------------------------------------------------


class TestManagedComponent:
    """Ensure ManagedComponent declares the args_model ClassVar correctly."""

    def test_args_model_classvar_present(self):
        class MyArgs(ComponentArgs):
            pass

        class MyResource(ManagedComponent):
            args_model = MyArgs

        assert MyResource.args_model is MyArgs

    def test_args_model_not_set_raises_on_access(self):
        """A ManagedComponent subclass without args_model has no attribute."""

        class Bare(ManagedComponent):
            pass

        assert not hasattr(Bare, 'args_model')

    def test_args_model_inherits_from_component_args(self):
        class RichArgs(ComponentArgs):
            tier: str = Field('free')

        class RichResource(ManagedComponent):
            args_model = RichArgs

        assert issubclass(RichResource.args_model, ComponentArgs)
