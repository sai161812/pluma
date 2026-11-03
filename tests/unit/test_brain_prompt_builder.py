"""tests/unit/test_brain_prompt_builder.py — Phase 9: PromptBuilder unit tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest

from pluma.brain.prompt_builder import PromptBuilder
from pluma.perception.element_refs import (
    BoundingBox,
    ElementSource,
    ScreenElement,
    ScreenSnapshot,
)


def test_build_system_prompt() -> None:
    builder = PromptBuilder()
    schemas = [
        {
            "name": "create_folder",
            "description": "Create a directory.",
            "args_schema": {
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        }
    ]
    sys_prompt = builder.build_system_prompt(schemas)
    assert "PERMITTED TOOLS:" in sys_prompt
    assert "create_folder(path*: string)" in sys_prompt
    assert "Plan JSON schema" in sys_prompt


def test_build_user_prompt_with_context() -> None:
    builder = PromptBuilder()
    user_prompt = builder.build_user_prompt(
        command="Organize my downloads",
        context={"active_process": "explorer.exe", "active_window_title": "Downloads"},
    )
    assert "USER COMMAND: Organize my downloads" in user_prompt
    assert "explorer.exe" in user_prompt
    assert "Downloads" in user_prompt


def test_build_user_prompt_redaction() -> None:
    """Verify passwords/tokens in commands/context are redacted (Acceptance Test F-09)."""
    builder = PromptBuilder()
    secret_cmd = "Set password to secret_token_12345 and api_key=AIzaSy1234567890abcdef"
    user_prompt = builder.build_user_prompt(
        command=secret_cmd,
        context={"active_process": "notepad.exe"},
    )
    assert "AIzaSy" not in user_prompt, "API keys must be redacted in planner prompts"
    assert "[REDACTED" in user_prompt or "api_key" in user_prompt


def test_build_user_prompt_with_screen_snapshot() -> None:
    builder = PromptBuilder()
    now = datetime.now(timezone.utc)
    snapshot = ScreenSnapshot(
        snapshot_id="snap-1",
        created_at=now,
        expires_at=now + timedelta(seconds=5),
        active_process="app.exe",
        active_window_title="Settings",
        window_rect=BoundingBox(left=0, top=0, right=800, bottom=600),
        dpi_scale=1.0,
        controls=[
            ScreenElement(
                snapshot_id="snap-1",
                source=ElementSource.UIA,
                label="Save Settings",
                control_type="Button",
                bounds=BoundingBox(left=10, top=10, right=100, bottom=40),
                confidence=1.0,
            )
        ],
        ocr_words=[],
    )

    user_prompt = builder.build_user_prompt(
        command="Click Save",
        screen_snapshot=snapshot,
    )
    assert "VISIBLE SCREEN ELEMENTS:" in user_prompt
    assert "Save Settings" in user_prompt


@pytest.mark.parametrize('through_adapter', [False, True])
def test_screen_secrets_and_password_controls_are_excluded_without_mutating_refs(through_adapter) -> None:
    now = datetime.now(timezone.utc)
    box = BoundingBox(left=0, top=0, right=80, bottom=30)
    def element(label, **kwargs):
        return ScreenElement(snapshot_id='private-screen', source=ElementSource.UIA,
            label=label, bounds=box, confidence=1, **kwargs)
    secret = 'screen-private-fixture-872'
    password = element('password=' + secret, control_type='Edit', metadata={'is_password': True})
    unknown = element('unclassified-private-value', control_type='Edit')
    safe = element('api_key=' + secret, control_type='Button',
        uia_automation_id='token=' + secret)
    ocr = element('api_key=' + secret).model_copy(update={'source': ElementSource.OCR})
    snapshot = ScreenSnapshot(snapshot_id='private-screen', expires_at=now + timedelta(seconds=30),
        active_process='fixture.exe', active_window_title='Fixture', window_rect=box,
        dpi_scale=1, controls=[password, unknown, safe], ocr_words=[ocr])
    if through_adapter:
        from unittest.mock import MagicMock
        from pluma.brain.llama_cpp_adapter import LlamaCppAdapter
        from pluma.brain.schemas import RouteMode
        backend = MagicMock()
        backend.generate.return_value = ('{"route":"SCREEN","mode":"direct","steps":['
            '{"tool":"get_active_window_context","arguments":{},"purpose":"Inspect"}]}')
        adapter = LlamaCppAdapter(custom_backend=backend)
        plan = adapter.plan('inspect the screen', screen_snapshot=snapshot, route=RouteMode.SCREEN)
        assert plan.steps[0].tool == 'get_active_window_context'
        prompt = backend.generate.call_args.kwargs['prompt']
    else:
        prompt = PromptBuilder().build_user_prompt('inspect the screen', screen_snapshot=snapshot)
    assert secret not in prompt
    assert 'unclassified-private-value' not in prompt
    assert '[REDACTED]' in prompt
    assert safe.uia_automation_id == 'token=' + secret
    assert password in snapshot.controls and snapshot.find_element(safe.element_id) == safe
