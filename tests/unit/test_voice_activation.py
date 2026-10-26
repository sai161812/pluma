"""tests/unit/test_voice_activation.py — Phase 6: VoiceActivation unit tests."""

from __future__ import annotations

import ctypes

import pytest

import pluma.voice.activation as activation_module
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


def test_windows_polling_loop_dispatches_press_and_release(monkeypatch) -> None:
    press_called = []
    release_called = []
    activation = VoiceActivation(
        on_press=lambda: press_called.append("press"),
        on_release=lambda: release_called.append("release"),
        hotkey="ctrl+alt+v",
    )

    class FakeUser32:
        key_polls = 0

        def GetAsyncKeyState(self, virtual_key):
            if virtual_key == ord("V"):
                self.key_polls += 1
                if self.key_polls == 1:
                    return 0x8000
                activation._running = False
                return 0
            if virtual_key in (0x11, 0x12):
                return 0x8000
            return 0

    fake_user32 = FakeUser32()
    monkeypatch.setattr(activation_module.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: fake_user32, raising=False)
    monkeypatch.setattr(activation_module.time, "sleep", lambda _seconds: None)
    activation._running = True

    activation._monitor_loop()

    assert fake_user32.key_polls == 2
    assert press_called == ["press"]
    assert release_called == ["release"]
    assert not activation.is_active
