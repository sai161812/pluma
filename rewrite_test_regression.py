import os
import re

with open('tests/unit/test_phase13_5_regression.py', 'r', encoding='utf-8') as f:
    code = f.read()

replacement = '''    def test_invented_snapshot_id_is_rejected(self):
        """click_element with unknown snapshot_id must return ok=False, not continue."""
        from pluma.tools.registry import get_default_tool_registry
        
        ctx = self._make_task_context_with_registry(register_snapshot=False)
        reg = get_default_tool_registry()

        result = reg.execute(
            "click_element",
            {"name": "OK", "snapshot_id": "invented-id-does-not-exist", "target_ref": "invented-id-does-not-exist::elem_1"},
            task_id="test",
            task_context=ctx,
        )
        assert result.ok is False, "Invented snapshot_id must be rejected"
        assert result.verified is False
        assert "not registered" in result.error.lower() or "not found" in result.error.lower()

    def test_invented_snapshot_id_rejected_when_registry_absent(self):
        """click_element with snapshot_id but no registry on ctx must return ok=False."""
        from pluma.tools.registry import get_default_tool_registry
        
        ctx = MagicMock()
        ctx.snapshot_registry = None  # No registry
        ctx.cancellation_token = MagicMock()
        ctx.cancellation_token.is_cancelled = False

        reg = get_default_tool_registry()
        result = reg.execute(
            "click_element",
            {"name": "OK", "snapshot_id": "any-id", "target_ref": "any-id::elem_1"},
            task_id="test",
            task_context=ctx,
        )
        assert result.ok is False
        assert "Parent UI Grounding rejected" in (result.error or "")

    def test_expired_snapshot_is_rejected(self):
        """click_element with an expired snapshot must return ok=False — never continue."""
        from pluma.tools.registry import get_default_tool_registry
        
        ctx = self._make_task_context_with_registry(register_snapshot=True, expired=True)
        reg = get_default_tool_registry()

        result = reg.execute(
            "click_element",
            {"name": "OK", "snapshot_id": "snap-test-001", "target_ref": "snap-test-001::elem_1"},
            task_id="test",
            task_context=ctx,
        )
        assert result.ok is False, "Expired snapshot must be rejected"
        assert "expired" in (result.error or "").lower() or "stale" in (result.error or "").lower()

    def test_valid_registered_snapshot_id_does_not_error(self):
        """click_element with a valid snapshot_id proceeds past grounding (may fail for other reasons)."""
        from pluma.tools.registry import get_default_tool_registry
        from pluma.perception.element_refs import BoundingBox, ElementSource, ScreenElement

        ctx = self._make_task_context_with_registry(register_snapshot=True, expired=False)
        btn = ScreenElement(
            element_id="elem_1",
            snapshot_id="snap-test-001",
            source=ElementSource.UIA,
            label="SomeButton",
            control_type="Button",
            bounds=BoundingBox(left=10, top=10, right=100, bottom=40),
            confidence=1.0,
        )
        snap = ctx.snapshot_registry.resolve("snap-test-001")
        snap.controls.append(btn)

        reg = get_default_tool_registry()
        result = reg.execute(
            "click_element",
            {"name": "SomeButton", "snapshot_id": "snap-test-001", "target_ref": "snap-test-001::elem_1"},
            task_id="test",
            task_context=ctx,
        )
        grounding_errors = {"no_snapshot_registry", "not registered", "expired", "stale", "Parent UI Grounding failed"}
        if result.error:
            assert not any(ge in result.error.lower() for ge in grounding_errors), \\
                f"Valid snapshot should not cause grounding error: {result.error}"'''

code = re.sub(
    r'    def test_invented_snapshot_id_is_rejected\(self\):.*?        if result\.error:\n            assert not any.*?f"Valid snapshot should not cause grounding error: \{result\.error\}"\n',
    replacement + '\n',
    code,
    flags=re.DOTALL
)

with open('tests/unit/test_phase13_5_regression.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('UI test update done')
