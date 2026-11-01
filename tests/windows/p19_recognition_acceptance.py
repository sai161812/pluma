"""Actual whisper.cpp segment transport; owned runtime, no microphone/actions.

Reports contain counts, hashes and cleanup identities, never speech or PCM.
The optional callback barrier observes STOP before final result publication;
it does not represent physical microphone or mid-decode latency evidence.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

from pluma.core.cancellation import TaskCancelledError
from pluma.memory.activity import ActivityQuery
from pluma.memory.redaction import redact_command_text
from pluma.voice.recognition import RecognitionProgress
from tests.windows.p14_native_stt_acceptance import _runtime, _sample_audio, _cleanup_readback, _same_original_process as same_process


def run(model, sample, report_path):
    started = time.perf_counter()
    root = report_path.parent / "runtime"
    root.mkdir(parents=True, exist_ok=True)
    audio = _sample_audio(sample)
    runtime = _runtime(model, root)
    with model.open("rb") as model_file:
        model_hash = hashlib.file_digest(model_file, "sha256").hexdigest()
    report = dict(commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        pywhispercpp=importlib.metadata.version("pywhispercpp"),
        model_sha256=model_hash,
        sample_sha256=hashlib.sha256(audio).hexdigest(), microphone_used=False, cases={})
    original_accept = RecognitionProgress.accept
    try:
        assert "pywhispercpp" not in sys.modules and runtime.voice_lifecycle.state == "COLD"
        for stop in (False, True):
            case_started = time.perf_counter()
            cap = runtime.supervisor.create_task_capsule(history_expected=False)
            observed, resume, done = threading.Event(), threading.Event(), threading.Event()
            prefixes = []
            def observed_accept(progress, sequence, text):
                original_accept(progress, sequence, text)
                snap = progress.snapshot()
                assert progress.task_id == cap.task_id and snap.state == "DECODING" and not done.is_set()
                assert same_process(cap.worker_controller.worker_identity)
                prefixes.append(hashlib.sha256(snap.text.encode()).hexdigest())
                observed.set()
                if stop and sequence == 1:
                    assert resume.wait(5), "Owned acceptance barrier was not released."
            RecognitionProgress.accept = observed_accept
            def transcribe():
                try:
                    return runtime.voice_lifecycle.transcribe(audio, cancellation_token=cap.cancellation_token)
                finally:
                    done.set()
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(transcribe)
                try:
                    assert observed.wait(30), "No actual native callback arrived."
                    controller = cap.worker_controller
                    identity = dict(controller.worker_identity)
                    if stop:
                        runtime.supervisor.request_stop(cap.task_id)
                        snap = cap.recognition_progress.snapshot()
                        assert snap.state == "CANCELLED" and snap.text == ""
                        resume.set()
                        try:
                            future.result(10)
                            raise AssertionError("Stopped recognition returned a result.")
                        except TaskCancelledError:
                            pass
                    else:
                        result = future.result(45)
                        snap = cap.recognition_progress.snapshot()
                        assert snap.state == "RECOGNIZED" and snap.text == redact_command_text(result.text)
                        expected = []
                        parts = []
                        for segment in result.segments:
                            if segment["text"].strip():
                                parts.append(segment["text"].strip())
                                expected.append(hashlib.sha256(redact_command_text(" ".join(parts)).encode()).hexdigest())
                        assert prefixes == expected and prefixes
                        assert "ask not what your country can do for you" in result.text.lower()
                        assert cap.recognition_progress._raw == ""
                        runtime.supervisor.stop_task(cap.task_id, grace_s=0)
                    assert runtime.supervisor.join_stop_operations(5)
                    assert controller.verify_cleanup() and not same_process(identity)
                    from pluma.core.cancellation import StopReason
                    metadata = _cleanup_readback(runtime, cap, StopReason.USER_STOP.value)
                    assert ActivityQuery(runtime.db).task_by_id(cap.task_id) is None
                    report["cases"]["cancel_after_segment" if stop else "native_segments"] = dict(
                        actual_callback_count=len(prefixes), callback_before_result=True,
                        worker_identity=identity, worker_absent=True, cleanup_ledger_verified=bool(metadata),
                        transcript_persisted=False, callback_barrier_used=stop)
                    report["cases"]["cancel_after_segment" if stop else "native_segments"]["duration_seconds"] = round(time.perf_counter() - case_started, 4)
                finally:
                    resume.set()
                    if not future.done():
                        runtime.supervisor.request_stop(cap.task_id)
                        future.result(10)
            assert runtime.voice_lifecycle.state == "COLD" and "pywhispercpp" not in sys.modules
        assert not [p for p in root.rglob("*") if p.suffix.lower() in {".wav", ".raw", ".pcm"}]
        # This is a real owned deadline, potentially during startup/model load;
        # no mid-decode latency claim is inferred from it.
        RecognitionProgress.accept = original_accept
        timeout_cap = runtime.supervisor.create_task_capsule(history_expected=False)
        runtime.voice_lifecycle.adapter.inference_timeout_s = .1
        try:
            runtime.voice_lifecycle.transcribe(audio, cancellation_token=timeout_cap.cancellation_token)
            raise AssertionError("Native deadline returned a transcript.")
        except TimeoutError:
            pass
        timeout_controller = timeout_cap.worker_controller
        timeout_identity = dict(timeout_controller.worker_identity)
        snapshot = timeout_cap.recognition_progress.snapshot()
        assert snapshot.state == "TIMED_OUT" and snapshot.text == ""
        from pluma.core.cancellation import StopReason
        runtime.supervisor.stop_task(timeout_cap.task_id, reason=StopReason.TASK_TIMEOUT, grace_s=0)
        assert timeout_controller.verify_cleanup() and not same_process(timeout_identity)
        _cleanup_readback(runtime, timeout_cap, StopReason.TASK_TIMEOUT.value)
        report["cases"]["owned_deadline"] = dict(worker_absent=True, cleanup_ledger_verified=True,
            text_suppressed=True, stage="startup_or_decode", worker_identity=timeout_identity)
        assert runtime.voice_lifecycle.state == "COLD" and "pywhispercpp" not in sys.modules
        assert not [p for p in root.rglob("*") if p.suffix.lower() in {".wav", ".raw", ".pcm"}]
        assert not runtime.tool_registry._worker_controllers
        report["resident_native_bindings_loaded"] = False
        report["duration_seconds"] = round(time.perf_counter() - started, 4)
        report["status"] = "passed"
        return report
    finally:
        RecognitionProgress.accept = original_accept
        runtime.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--sample", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    result = run(args.model, args.sample, args.report)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
