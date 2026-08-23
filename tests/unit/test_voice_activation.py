"""tests/unit/test_voice_activation.py — Phase 6: VoiceActivation unit tests."""

from __future__ import annotations

import pytest

from pluma.voice.activation import MOD_ALT, MOD_CONTROL, MOD_WIN, VoiceActivation, parse_hotkey_string


def test_parse_hotkey_string_variants() -> None:
    # ctrl+alt+v
    mods, vk = parse_hotkey_string("ctrl+alt+v")
    assert mods == (MOD_CONTROL | MOD_ALT)
    assert vk == ord("V")

    # win+alt+p
    mods, vk = parse_hotkey_string("win+alt+p")
    assert mods == (MOD_WIN | MOD_ALT)
    assert vk == ord("P")

    # space / escape
    mods, vk = parse_hotkey_string("alt+space")
    assert mods == MOD_ALT
    assert vk == 0x20


def test_voice_activation_press_and_release() -> None:
    press_called = []
    release_called = []

    def on_press() -> None:
        press_called.append(True)

    def on_release() -> None:
        release_called.append(True)

    act = VoiceActivation(on_press=on_press, on_release=on_release, hotkey="ctrl+alt+v")
    assert not act.is_active

    # Simulate key press
    act.trigger_press()
    assert act.is_active
    assert len(press_called) == 1

    # Idempotent press
    act.trigger_press()
    assert len(press_called) == 1

    # Simulate key release
    act.trigger_release()
    assert not act.is_active
    assert len(release_called) == 1

    # Idempotent release
    act.trigger_release()
    assert len(release_called) == 1
