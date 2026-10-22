"""Opt-in FAST orchestration fixture: never a native desktop acceptance backend.

Load explicitly with ``-p tests.fixtures.desktop_isolation``. Existing FAST
tests mock process verification but otherwise can clear the real clipboard,
operate the foreground window or close pre-existing apps by name. This fixture
keeps those route/orchestration checks confined to inert desktop adapters.
Other modules, including owned Job Object/spawn tests, retain their own fixtures.
"""
import ctypes
import subprocess
from functools import partial

import pytest


def _clipboard_capture(args, context):
    import uuid
    return {'action': 'clipboard_restore', 'guard_version': 1, 'volatile': True,
        'undo_ref': str(uuid.uuid4()), 'clipboard_private': {'clipboard_before': 'Fixture clipboard',
        'before_proof': {'sequence': 1, 'owner': 0, 'digest': '0' * 64}, 'after_proof': None}}


def _clipboard_execute(args, context, *, tool):
    from pluma.tools.base import ToolResult
    record = next(item['pre_state'] for item in reversed(context.undo_stack)
                  if item.get('action') == 'pending_mutation' and item.get('tool') == tool)
    text = args.get('text')
    return ToolResult.success(tool, data={'is_empty': text is None, 'char_count': len(text or '')},
        verified=True, undo_record=record, adapter_used='fixture_clipboard',
        factual_message='Explicit inert clipboard fixture; no native clipboard access.').model_copy(update={
            'private_context': {'clipboard_receipt': {'record': record, 'expected_text': text,
                'after_proof': {'sequence': 2, 'owner': 0, 'digest': '1' * 64}}}})


def _clipboard_verify(result):
    from pluma.tools.base import VerifyResult
    receipt = result.private_context['clipboard_receipt']
    text = receipt['expected_text']
    return VerifyResult(ok=result.ok and result.adapter_used == 'fixture_clipboard'
        and result.data == {'is_empty': text is None, 'char_count': len(text or '')},
        method='inert_fixture', detail='Explicit fixture clipboard observation; no native acceptance.')


class _NoTargetDesktop:
    def GetForegroundWindow(self):
        return 0

    def EnumWindows(self, callback, argument):
        return True  # no fixture windows, so no user window can become a target

    def IsWindow(self, handle):
        return False

    def IsWindowVisible(self, handle):
        return False

    def ShowWindow(self, *args):
        raise RuntimeError("Desktop input is unavailable in this fixture.")

    def SetForegroundWindow(self, *args):
        raise RuntimeError("Desktop input is unavailable in this fixture.")


@pytest.fixture(autouse=True)
def isolate_fast_orchestrator_desktop(request, monkeypatch):
    if not request.module.__name__.endswith("test_fast_orchestrator"):
        yield
        return

    from pluma.tools import clipboard
    from pluma.tools import audio
    sound = {"volume": 50, "muted": False}

    def read_audio():
        return dict(sound, is_mock=True, endpoint_id="fixture:default", scalar=sound["volume"] / 100.0)

    def write_audio(level=None, mute=None, expected_endpoint=None):
        if expected_endpoint not in (None, "fixture:default"):
            return False
        if level is not None:
            sound["volume"] = level
        if mute is not None:
            sound["muted"] = mute
        return True

    monkeypatch.setattr(audio, "_get_audio_endpoint_volume", read_audio)
    monkeypatch.setattr(audio, "_set_audio_endpoint_volume", write_audio)

    for spec in clipboard.CLIPBOARD_TOOL_SPECS:
        if spec.name in clipboard.MUTATION_NAMES:
            monkeypatch.setattr(spec, 'undo_builder', _clipboard_capture)
            monkeypatch.setattr(spec, 'executor', partial(_clipboard_execute, tool=spec.name))
            monkeypatch.setattr(spec, 'verifier', _clipboard_verify)

    real_load = getattr(ctypes, "WinDLL", None)
    desktop = _NoTargetDesktop()

    def load(name, *args, **kwargs):
        if str(name).casefold() in ("user32", "user32.dll"):
            return desktop
        return real_load(name, *args, **kwargs)

    if real_load is not None:
        monkeypatch.setattr(ctypes, "WinDLL", load)
    real_run = subprocess.run

    def run(command, *args, **kwargs):
        if isinstance(command, (tuple, list)) and command:
            executable = str(command[0]).replace("\\", "/").rsplit("/", 1)[-1].casefold()
            if executable in ("taskkill", "taskkill.exe", "pkill", "kill"):
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="Fixture target absent; desktop termination blocked.")
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    request.node.user_properties.append(("desktop_isolation", "inert clipboard/audio; no target window; desktop termination blocked"))
    yield
