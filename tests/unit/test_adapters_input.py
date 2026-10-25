"""tests.unit.test_adapters_input — Unit tests for InputAdapter."""

from unittest.mock import MagicMock, patch
import pytest

from pluma.adapters.base import (
    AdapterError,
    InputOutOfBoundsError,
    Rect,
)
from pluma.adapters.input import InputAdapter


def test_input_adapter_key_resolution() -> None:
    """Verify virtual key code resolution handles names and single characters."""
    adapter = InputAdapter()
    assert adapter._resolve_vk("enter") == 0x0D
    assert adapter._resolve_vk("ctrl") == 0x11
    assert adapter._resolve_vk("shift") == 0x10
    assert adapter._resolve_vk("esc") == 0x1B
    assert adapter._resolve_vk("a") == ord("A")
    assert adapter._resolve_vk("Z") == ord("Z")
    assert adapter._resolve_vk(0x20) == 0x20

    with pytest.raises(ValueError):
        adapter._resolve_vk("invalid_key_name_12345")


def test_input_adapter_mouse_bounds() -> None:
    """Verify mouse operations check bounding rectangle when provided."""
    adapter = InputAdapter()
    bounds = Rect(left=100, top=100, right=500, bottom=500)

    # Out of bounds coordinates must raise InputOutOfBoundsError
    with pytest.raises(InputOutOfBoundsError):
        adapter.mouse_move(50, 50, bounding_rect=bounds)

    with pytest.raises(InputOutOfBoundsError):
        adapter.mouse_click(600, 600, bounding_rect=bounds)


def test_input_adapter_hotkey_safe_release() -> None:
    """Verify modifier keys are released even if main key fails."""
    adapter = InputAdapter()
    sent_inputs = []

    def mock_send(inputs):
        sent_inputs.extend(inputs)
        return len(inputs)

    with patch.object(adapter, "_send_inputs", side_effect=mock_send):
        adapter.send_hotkey(["ctrl", "shift"], "s", duration_s=0.0)

        # Expected:
        # 1. Ctrl down
        # 2. Shift down
        # 3. 's' down
        # 4. 's' up
        # 5. Shift up
        # 6. Ctrl up
        assert len(sent_inputs) == 6


def test_input_adapter_send_text() -> None:
    """Verify send_text creates unicode keyboard inputs."""
    adapter = InputAdapter()
    sent_inputs = []

    def mock_send(inputs):
        sent_inputs.extend(inputs)
        return len(inputs)

    with patch.object(adapter, "_send_inputs", side_effect=mock_send):
        adapter.send_text("Hello")
        # 5 characters * 2 (down + up) = 10 inputs
        assert len(sent_inputs) == 10


def test_sendinput_zero_or_partial_submission_is_failure():
    from types import SimpleNamespace
    from pluma.adapters.input import _INPUT
    for count in (0, 1):
        adapter = InputAdapter()
        adapter._user32 = SimpleNamespace(SendInput=lambda *args: count)
        with pytest.raises(AdapterError, match="input was not completed"):
            adapter._send_inputs([_INPUT(), _INPUT()])


def test_failed_key_release_does_not_skip_remaining_modifiers():
    from pluma.adapters.input import KEYEVENTF_KEYUP
    adapter = InputAdapter()
    releases = []
    def send(inputs):
        key = inputs[0].u.ki
        if key.dwFlags & KEYEVENTF_KEYUP:
            releases.append(key.wVk)
            if key.wVk == ord("S"):
                raise AdapterError("release denied")
        return len(inputs)
    with patch.object(adapter, "_send_inputs", side_effect=send):
        with pytest.raises(AdapterError):
            adapter.send_hotkey(["ctrl", "shift"], "s", duration_s=0)
    assert releases == [ord("S"), 0x10, 0x11]


def test_unicode_supplementary_characters_use_utf16_surrogates():
    adapter = InputAdapter()
    sent = []
    with patch.object(adapter, "_send_inputs", side_effect=lambda inputs: sent.extend(inputs) or len(inputs)):
        adapter.send_text("\U0001f600")
    assert [event.u.ki.wScan for event in sent] == [0xD83D, 0xD83D, 0xDE00, 0xDE00]


def test_partial_unicode_input_attempts_release_and_preserves_failure():
    from pluma.adapters.input import KEYEVENTF_KEYUP
    adapter = InputAdapter()
    calls = []
    def send(inputs):
        calls.append(inputs)
        if len(calls) == 1:
            raise AdapterError("partial input")
        return len(inputs)
    with patch.object(adapter, "_send_inputs", side_effect=send):
        with pytest.raises(AdapterError, match="partial input"):
            adapter.send_text("ab")
    assert len(calls) == 2
    assert all(event.u.ki.dwFlags & KEYEVENTF_KEYUP for event in calls[1])
