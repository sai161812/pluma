"""A-03: planner and executor reject the same registered argument violations."""
import json
import sys

import pytest
from pydantic import BaseModel, Field

from pluma.brain.schemas import Plan, RouteMode, ToolCall
from pluma.brain.validator import PlanValidationError, PlanValidator
from pluma.tools.base import RiskClass, ToolSpec
from pluma.tools.registry import ToolArgumentError, ToolRegistry


SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': ['count', 'options'],
    'properties': {
        'count': {'type': 'integer', 'minimum': 1, 'maximum': 3},
        'options': {'type': 'object', 'additionalProperties': False, 'required': ['mode'],
                    'properties': {'mode': {'enum': ['read']}}},
    },
}


class Options(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}
    mode: str = Field(pattern='^read$')


class Arguments(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}
    count: int = Field(ge=1, le=3)
    options: Options


@pytest.fixture
def registry():
    value = ToolRegistry()
    yield value
    value.close()


def register(registry, schema):
    def forbidden(*args, **kwargs):
        pytest.fail('Argument validation reached policy, capture, dispatch or readback.')
    from types import SimpleNamespace
    registry._policy_engine = SimpleNamespace(evaluate=forbidden)
    registry.register(ToolSpec(name='argument_probe', description='Inert argument boundary fixture',
        args_schema=schema, risk_class=RiskClass.LOW, timeout_s=1,
        executor=forbidden, verifier=forbidden, undo_builder=forbidden))


def plan(args):
    return Plan(route=RouteMode.SMART, steps=[ToolCall(tool='argument_probe', arguments=args,
                                                    purpose='Validate owned inert fixture')])


def validate(registry, args, entry):
    if entry == 'executor':
        return registry.execute('argument_probe', args)
    if entry == 'json_plan':
        return PlanValidator(registry).parse_and_validate_json(plan(args).model_dump_json())
    return PlanValidator(registry).validate_plan(plan(args))


@pytest.mark.parametrize('schema', [SCHEMA, Arguments], ids=['json-schema', 'pydantic'])
@pytest.mark.parametrize('entry', ['executor', 'plan', 'json_plan'])
@pytest.mark.parametrize('args', [
    {}, {'count': 1}, {'count': 0, 'options': {'mode': 'read'}},
    {'count': 4, 'options': {'mode': 'read'}},
    {'count': '1', 'options': {'mode': 'read'}},
    {'count': True, 'options': {'mode': 'read'}},
    {'count': 1, 'options': {}},
    {'count': 1, 'options': {'mode': 'write'}},
    {'count': 1, 'options': {'mode': 'read', 'secret': 'private-schema-fixture'}},
    {'count': 1, 'options': {'mode': 'read'}, 'secret': 'private-schema-fixture'},
])
def test_registered_constraints_reject_before_policy_or_execution(registry, schema, entry, args):
    register(registry, schema)
    with pytest.raises(ToolArgumentError if entry == 'executor' else PlanValidationError) as error:
        validate(registry, args, entry)
    assert 'private-schema-fixture' not in str(error.value)
    assert not registry._worker_controllers


@pytest.mark.parametrize('entry', ['executor', 'plan', 'json_plan'])
def test_absent_json_schema_validator_refuses_even_otherwise_valid_arguments(registry, monkeypatch, entry):
    register(registry, SCHEMA)
    monkeypatch.setitem(sys.modules, 'jsonschema', None)
    with pytest.raises(ToolArgumentError if entry == 'executor' else PlanValidationError):
        validate(registry, {'count': 1, 'options': {'mode': 'read'}}, entry)
    assert not registry._worker_controllers


@pytest.mark.parametrize('entry', ['executor', 'plan', 'json_plan'])
def test_unsupported_registered_schema_refuses_before_policy(registry, entry):
    register(registry, object())
    with pytest.raises(ToolArgumentError if entry == 'executor' else PlanValidationError):
        validate(registry, {}, entry)


@pytest.mark.parametrize('schema', [SCHEMA, Arguments], ids=['json-schema', 'pydantic'])
def test_valid_registered_arguments_have_matching_planner_and_executor_admission(registry, schema):
    if isinstance(schema, dict):
        pytest.importorskip('jsonschema')
    register(registry, schema)
    args = {'count': 2, 'options': {'mode': 'read'}}
    original = json.dumps(args, sort_keys=True)
    assert registry.validate_call('argument_probe', args) == args
    assert PlanValidator(registry).validate_plan(plan(args)).steps[0].arguments == args
    assert PlanValidator(registry).parse_and_validate_json(plan(args).model_dump_json()).steps[0].arguments == args
    assert json.dumps(args, sort_keys=True) == original
