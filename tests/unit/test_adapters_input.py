"""tests.unit.test_adapters_input — Unit tests for InputAdapter."""

from unittest.mock import MagicMock, patch
import pytest

from pluma.adapters.base import (
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
