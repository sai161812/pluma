"""tests.unit.test_phase13_7_ui_verification — Verify failed UI verification cannot be overwritten."""

from pluma.tools.base import ToolResult, ToolSpec, RiskClass
from pluma.tools.registry import ToolRegistry
from pluma.verify.common import verify_noop

def test_ui_verification_failure_cannot_become_success():
    """Ensure verify_noop does not overwrite a failed executor verification."""
    registry = ToolRegistry()
    
    def mock_ui_click(args, ctx):
        return ToolResult(
            tool_name="click_element",
            ok=True,
            data={},
            factual_message="Clicked",
            verified=False,
            verify_detail=None,
        )
        
    spec = ToolSpec(
        name="click_element",
        description="test",
        version="1.0",
        args_schema={},
        risk_class=RiskClass.LOW,
        timeout_s=5.0,
        executor=mock_ui_click,
        verifier=verify_noop,
    )
    registry.register(spec)
    
    res = registry.execute("click_element", {})
    
    # It must propagate to ok=False because verified is False
    assert res.ok is False
    assert res.verified is False
