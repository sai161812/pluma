"""Clipboard declaration and refusal checks; real positive paths use native fixtures."""
import pytest
from pluma.tools.clipboard import CLIPBOARD_TOOL_SPECS, execute_clear_clipboard, execute_set_clipboard_text
from pluma.tools.registry import ToolRegistry, ToolArgumentError, register_default_tools


@pytest.mark.parametrize('call,args', [(execute_clear_clipboard, {}), (execute_set_clipboard_text, {'text': 'private fixture'})])
def test_direct_mutation_without_captured_undo_refuses(call, args):
    result = call(args)
    assert not result.ok and not result.verified and result.error_code == 'CLIPBOARD_WRITE_UNVERIFIED'


def test_plain_text_specs_are_registered_with_real_readback_and_owned_workers():
    names = {spec.name for spec in CLIPBOARD_TOOL_SPECS}
    assert names == {'clipboard_get', 'clipboard_set', 'clipboard_clear', 'clear_clipboard', 'get_clipboard_text', 'set_clipboard_text'}
    for spec in CLIPBOARD_TOOL_SPECS:
        assert spec.process_isolated and callable(spec.executor) and callable(spec.verifier)
        if spec.name not in ('clipboard_get', 'get_clipboard_text'):
            assert callable(spec.undo_builder)


def test_non_text_format_is_not_a_planner_argument():
    registry = ToolRegistry()
    try:
        register_default_tools(registry)
        with pytest.raises(ToolArgumentError):
            registry.validate_call('clipboard_set', {'text': 'fixture', 'format': 'bitmap'})
    finally:
        registry.close()
