"""Focused task ownership and native-result tests for local voice STT."""

from __future__ import annotations

import sys
import types
import weakref
from types import SimpleNamespace

import pytest

from pluma.core.cancellation import StopReason, TaskCancelledError
from pluma.tools.registry import WorkerResponse
from pluma.voice.stt_adapter import WhisperSttAdapter


class _Capsule:
    task_id = "voice-native-fixture"
    job_object = None
    worker_controller = None
    tool_registry = None


class _Token:
    def __init__(self, capsule: _Capsule) -> None:
        self.task_id = capsule.task_id
        self._capsule = weakref.ref(capsule)
        self.is_cancelled = False
        self.reason = None

    def raise_if_cancelled(self, _message: str = "") -> None:
        if self.is_cancelled:
            raise TaskCancelledError("fixture stopped", reason=self.reason)

    def cancel(self, reason=None) -> None:
        self.is_cancelled = True
        self.reason = reason


class _Controller:
    def __init__(self, status="ok", *, cancel_reason=None) -> None:
        self.status = status
        self.cancel_reason = cancel_reason
        self.cleanup_verified = True
        self.request = None
        self.execution_args = None
        self.execution_token = None

    def execute_call(self, executor, args, request, **kwargs):
        self.request = request
        self.execution_args = args
        self.execution_token = kwargs["cancellation_token"]
        if self.cancel_reason is not None:
            self.execution_token.cancel(self.cancel_reason)
        if self.status == "ok":
            parent_token = self.execution_token
            class WorkerToken:
                @property
                def is_cancelled(self):
                    return parent_token.is_cancelled

                def raise_if_cancelled(self):
                    parent_token.raise_if_cancelled()

            worker_token = WorkerToken()
            worker_context = SimpleNamespace(cancellation_token=worker_token)
            return "ok", WorkerResponse(result=executor(args, worker_context))
        return self.status, "fixture worker ended"

    def verify_cleanup(self):
        return self.cleanup_verified


class _Registry:
    def __init__(self, controller: _Controller) -> None:
        self.controller = controller
        self.requested_task_ids = []

    def get_worker(self, task_id):
        self.requested_task_ids.append(task_id)
        return self.controller


def _fake_whisper_modules(monkeypatch, segments):
    class Samples:
        def astype(self, _dtype):
            return self

        def __truediv__(self, _value):
            return self

    numpy = types.ModuleType("numpy")
    numpy.int16 = object()
    numpy.float32 = object()
    numpy.frombuffer = lambda *_args, **_kwargs: Samples()

    package = types.ModuleType("pywhispercpp")
    package.__path__ = []
    model_module = types.ModuleType("pywhispercpp.model")

    class Model:
        def __init__(self, model_path, **kwargs):
            self.model_path = model_path
            self.model_kwargs = kwargs

        def transcribe(self, samples, **kwargs):
            assert isinstance(samples, Samples)
            assert kwargs["extract_probability"] is True
            assert kwargs["abort_callback"]() is False
            assert "n_processors" not in kwargs
            return segments

    model_module.Model = Model
    monkeypatch.setitem(sys.modules, "numpy", numpy)
    monkeypatch.setitem(sys.modules, "pywhispercpp", package)
    monkeypatch.setitem(sys.modules, "pywhispercpp.model", model_module)


def test_native_stt_is_dispatched_to_matching_capsule_and_confidence_is_real(
    tmp_path, monkeypatch
):
    model_path = tmp_path / "fixture.ggml"
    model_path.write_bytes(b"fixture model path only")
    _fake_whisper_modules(monkeypatch, [
        SimpleNamespace(text="delete private.txt", probability=0.9, t0=0, t1=8),
        SimpleNamespace(text="", t0=8, t1=9),  # missing probability must not imply 1.0
    ])
    capsule = _Capsule()
    token = _Token(capsule)
    controller = _Controller()
    registry = _Registry(controller)
    adapter = WhisperSttAdapter(registry=registry)
    adapter.load(str(model_path))

    result = adapter.transcribe(b"\0" * 1600, cancellation_token=token)

    assert registry.requested_task_ids == [capsule.task_id]
    assert capsule.worker_controller is controller
    assert capsule.tool_registry is registry
    assert controller.request.tool_name == "voice_stt"
    assert controller.request.task_id == capsule.task_id
    assert controller.execution_token is token
    assert result.text == "delete private.txt"
    assert abs(result.confidence - 0.45) < 1e-9
    assert result.is_low_confidence
    assert controller.request.validated_args["audio"] == b"\0" * 1600
    assert not adapter.is_loaded


def test_native_stt_refuses_missing_capsule_before_worker_admission(tmp_path):
    model_path = tmp_path / "fixture.ggml"
    model_path.write_bytes(b"fixture model path only")
    controller = _Controller()
    registry = _Registry(controller)
    adapter = WhisperSttAdapter(registry=registry)
    adapter.load(str(model_path))

    with pytest.raises(RuntimeError, match="matching task capsule"):
        adapter.transcribe(b"\0" * 1600, cancellation_token=SimpleNamespace(
            task_id="no-capsule", _capsule=None, is_cancelled=False,
            raise_if_cancelled=lambda *_args: None,
        ))
    assert registry.requested_task_ids == []


@pytest.mark.parametrize(
    ("status", "reason", "exception"),
    [
        ("cancelled", StopReason.USER_STOP, TaskCancelledError),
        ("timeout", StopReason.TASK_TIMEOUT, TimeoutError),
    ],
)
def test_native_stt_requires_worker_absence_after_stop_or_timeout(
    tmp_path, status, reason, exception
):
    model_path = tmp_path / "fixture.ggml"
    model_path.write_bytes(b"fixture model path only")
    capsule = _Capsule()
    token = _Token(capsule)
    controller = _Controller(status, cancel_reason=reason)
    registry = _Registry(controller)
    adapter = WhisperSttAdapter(registry=registry)
    adapter.load(str(model_path))

    with pytest.raises(exception):
        adapter.transcribe(b"\0" * 1600, cancellation_token=token)
    assert controller.verify_cleanup()
    assert token.is_cancelled
    assert token.reason == reason


def test_native_stt_does_not_report_success_when_worker_cleanup_is_unknown(tmp_path):
    model_path = tmp_path / "fixture.ggml"
    model_path.write_bytes(b"fixture model path only")
    capsule = _Capsule()
    token = _Token(capsule)
    controller = _Controller("cancelled", cancel_reason=StopReason.USER_STOP)
    controller.cleanup_verified = False
    adapter = WhisperSttAdapter(registry=_Registry(controller))
    adapter.load(str(model_path))

    with pytest.raises(RuntimeError, match="cleanup could not be verified"):
        adapter.transcribe(b"\0" * 1600, cancellation_token=token)


def test_native_abort_callback_observes_the_task_stop_latch(tmp_path, monkeypatch):
    model_path = tmp_path / "fixture.ggml"
    model_path.write_bytes(b"fixture model path only")
    capsule = _Capsule()
    token = _Token(capsule)

    class CancellingModel:
        def __init__(self, _path, **_kwargs):
            pass

        def transcribe(self, _samples, **kwargs):
            assert kwargs["abort_callback"]() is False
            token.cancel(StopReason.USER_STOP)
            assert kwargs["abort_callback"]() is True
            return []

    class Samples:
        def astype(self, _dtype):
            return self

        def __truediv__(self, _value):
            return self

    numpy = types.ModuleType("numpy")
    numpy.int16 = object()
    numpy.float32 = object()
    numpy.frombuffer = lambda *_args, **_kwargs: Samples()
    package = types.ModuleType("pywhispercpp")
    package.__path__ = []
    model_module = types.ModuleType("pywhispercpp.model")
    model_module.Model = CancellingModel
    monkeypatch.setitem(sys.modules, "numpy", numpy)
    monkeypatch.setitem(sys.modules, "pywhispercpp", package)
    monkeypatch.setitem(sys.modules, "pywhispercpp.model", model_module)
    controller = _Controller()
    adapter = WhisperSttAdapter(registry=_Registry(controller))
    adapter.load(str(model_path))

    with pytest.raises(TaskCancelledError):
        adapter.transcribe(b"\0" * 1600, cancellation_token=token)
    assert token.is_cancelled
    assert token.reason == StopReason.USER_STOP
