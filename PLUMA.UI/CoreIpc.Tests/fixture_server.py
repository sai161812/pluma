"""Owned authenticated IPC fixture using the production transport/handler."""
def main():
    from pathlib import Path
    import json
    import os
    import sys
    import threading
    from types import SimpleNamespace

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    os.environ["LOCALAPPDATA"] = sys.argv[2]
    mode = sys.argv[3] if len(sys.argv) > 3 else "status"
    saturate_status = len(sys.argv) > 4 and sys.argv[4] == "saturate"

    from pluma.core.ipc import IpcServer


    def status(request):
        if request != {"command": "status"}:
            raise ValueError("Only the read-only status fixture is registered.")
        return {"status": "ok", "running": True, "active_tasks": 2, "voice_enabled": True,
                "padding": "x" * 24000}


    db = None
    owned_db = None
    registry = None
    owned_read = None
    release_status = threading.Event()
    paused_events = threading.Event()
    event_lock = threading.Lock()
    executed_calls = []
    approved_calls = set()
    command_calls = []
    command_resources = []


    def report_event(value):
        with event_lock:
            sys.stdout.write(value + "\n")
            sys.stdout.flush()


    voice_threads = []
    voice_release = threading.Event()
    voice_entered = threading.Event()
    voice_paused = threading.Event()
    if mode in {"versioned", "commands", "voice"}:
        from pluma.core.resident import ResidentCore
        from pluma.core.task_supervisor import TaskState, TaskSupervisor
        from pluma.config.loader import load_config
        from pluma.memory.activity import ActivityLedger
        from pluma.memory.db import DbConnection
        from pluma.policy.engine import PolicyEngine
        from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult
        from pluma.tools.registry import ToolRegistry
        from pluma.ui.ipc_confirmations import IpcConfirmationBroker
        from pydantic import BaseModel, ConfigDict, StrictStr

        class FixtureReadArgs(BaseModel):
            model_config = ConfigDict(extra="forbid", strict=True)
            path: StrictStr

        owned_db = Path(sys.argv[2]) / f"p15-ledger-{os.getpid()}.db"
        if owned_db.exists():
            raise RuntimeError("Owned fixture database already exists.")
        db = DbConnection(str(owned_db))
        db.open()
        ledger = ActivityLedger(db)
        supervisor = TaskSupervisor(ledger=ledger)
        broker = IpcConfirmationBroker(supervisor.get_task, timeout_s=3)
        registry = ToolRegistry(policy_engine=PolicyEngine(confirmation_contract=broker))
        owned_read = Path(sys.argv[2]) / f"p16_budget_预算_{os.getpid()}.txt"
        with owned_read.open("x", encoding="utf-8") as fixture_file:
            fixture_file.write("PLUMA owned P15 fixture")

        def read_owned_fixture(args, context):
            if args != {"path": str(owned_read)}:
                raise RuntimeError("Only the exact owned fixture path is permitted.")
            executed_calls.append(context.task_id)
            return ToolResult.success("fixture_read", {"length": len(owned_read.read_text(encoding="utf-8"))},
                                      "Read owned fixture.", verified=False)

        registry.register(ToolSpec(name="fixture_read", description="Read an owned fixture after material approval",
            args_schema=FixtureReadArgs, risk_class=RiskClass.HIGH, timeout_s=5,
            # This inert read fixture deliberately uses the owned thread path so
            # parent-side entry counters can prove that denied calls never enter.
            executor=lambda args, context: read_owned_fixture(args, context),
            verifier=lambda result: VerifyResult(ok=result.data["length"] == len(owned_read.read_text(encoding="utf-8")),
                method="file_readback", detail="Owned fixture length read back.")))

        class FixtureOrchestrator:
            def execute(self, request, capsule):
                supervisor.start_task(capsule.task_id)
                if request.text == "fixture:hold":
                    report_event("TASK_ENTERED")
                    if not capsule.cancellation_token.wait_for_cancel(8):
                        raise TimeoutError("Owned fixture wait expired.")
                    capsule.cancellation_token.raise_if_cancelled()
                success = True
                if request.text == "fixture:approval":
                    result = registry.execute("fixture_read", {"path": str(owned_read)}, task_context=capsule, ledger=ledger)
                    success = result.ok and result.verified
                final = TaskState.SUCCEEDED if success else TaskState.FAILED
                supervisor.finalize_task(capsule.task_id, final)
                return SimpleNamespace(
                    final_state=final, completion_verified=success,
                    terminal_persisted=True, has_residual=False,
                    route=SimpleNamespace(value="FAST"),
                    user_message="Fixture result verified.", duration_ms=1.0,
                )

        core = ResidentCore.__new__(ResidentCore)
        core.ledger = ledger
        core.supervisor = supervisor
        core.orchestrator = FixtureOrchestrator()
        core.confirmation_broker = broker
        core.config = load_config(Path(sys.argv[2]) / "no-user-settings.json")
        core.config["brain"]["model_path"] = r"C:\fixture\planner.gguf"
        core.config["voice"]["model_path"] = r"C:\fixture\whisper.ggml"

        if mode in {"commands", "voice"}:
            # Actual production orchestration/policy/registry/verification/SQLite.
            # Only routing and planner waiting are fixed inert fixture adapters.
            from typing import Literal
            from pluma.core.orchestrator import Orchestrator
            from pluma.core.router import RouteResult
            from pluma.core.task_supervisor import ResourceOwnership
            from pluma.brain.schemas import Plan, PlanMode, RouteMode, ToolCall

            class CommandArgs(BaseModel):
                model_config = ConfigDict(extra="forbid", strict=True)
                operation: Literal["read", "fail", "hold", "residual", "verify", "process", "rollback"]

            def command_executor(args, context):
                command_calls.append(context.task_id)
                operation = args["operation"]
                if operation == "rollback":
                    original = Path(sys.argv[2]) / ("p17-conflict-original-" + context.task_id + ".txt")
                    moved = Path(sys.argv[2]) / ("p17-conflict-moved-" + context.task_id + ".txt")
                    with original.open("x", encoding="utf-8") as stream:
                        stream.write("Owned rollback fixture")
                    command_resources.extend([original, moved])
                    context.undo_stack.append({"action": "move_file", "source": str(original), "destination": str(moved)})
                    original.rename(moved)
                if operation == "residual":
                    conflict = Path(sys.argv[2]) / ("p17-conflict-" + context.task_id + ".txt")
                    with conflict.open("x", encoding="utf-8") as stream:
                        stream.write("original fixture")
                    command_resources.append(conflict)
                    context.register_owned_resource("temp_file", ResourceOwnership.PLUMA_CREATED, str(conflict))
                    conflict.write_text("changed owned fixture; cleanup must refuse", encoding="utf-8")
                if operation in {"hold", "residual", "rollback"}:
                    report_event("COMMAND_ENTERED")
                    if not context.cancellation_token.wait_for_cancel(8):
                        raise TimeoutError("Owned command fixture was not stopped.")
                    context.cancellation_token.raise_if_cancelled()
                if operation == "fail":
                    return ToolResult.failure("fixture_command", "Owned fixture failure.", "FIXTURE_FAILED")
                return ToolResult.success("invoke_control" if operation == "verify" else "fixture_command", {"length": len(owned_read.read_text(encoding="utf-8"))},
                                          "Read owned fixture.", verified=False)

            registry.register(ToolSpec(name="fixture_command", description="Read only an owned fixture", args_schema=CommandArgs,
                risk_class=RiskClass.READ, timeout_s=10, executor=command_executor,
                verifier=lambda result: VerifyResult(ok=result.data.get("length") == len(owned_read.read_text(encoding="utf-8")),
                    method="owned_file_readback", detail="Owned file length independently read back.")))
            registry.register(ToolSpec(name="fixture_denied", description="Inert policy refusal", args_schema=CommandArgs,
                risk_class=RiskClass.DENY, timeout_s=2,
                executor=lambda args, context: (_ for _ in ()).throw(RuntimeError("Denied executor must never run.")),
                verifier=lambda result: VerifyResult(ok=False, method="denied")))

            # UI projection fixture only: this name is registered against an owned
            # read adapter here, never the native UIA executor or a personal window.
            registry.register(ToolSpec(name="invoke_control", description="Owned verifier projection fixture", args_schema=CommandArgs,
                risk_class=RiskClass.READ, timeout_s=5, executor=command_executor,
                verifier=lambda result: VerifyResult(ok=result.data.get("length") == len(owned_read.read_text(encoding="utf-8")),
                    method="owned_file_readback", detail="Owned fixture length independently read back.")))
            from tests.fixtures.runtime_worker import execute as process_execute, verify as process_verify
            registry.register(ToolSpec(name="fixture_process", description="Owned process-isolated wait", args_schema=CommandArgs,
                risk_class=RiskClass.READ, timeout_s=10, process_isolated=True, executor=process_execute, verifier=process_verify))
            registry.register(ToolSpec(name="fixture_rollback", description="Move only a newly owned test file", args_schema=CommandArgs,
                risk_class=RiskClass.LOW, timeout_s=10, executor=command_executor,
                verifier=lambda result: VerifyResult(ok=False, method="stopped")))
            from pluma.rollback.engine import RollbackEngine
            import time
            class ObservableRollback(RollbackEngine):
                def _apply(self, task_id, action, state):
                    # Delay selection, never replace the production owned inverse.
                    if action == "move_file":
                        time.sleep(.65)
                    result = super()._apply(task_id, action, state)
                    if action == "move_file":
                        if not result.ok or Path(state["destination"]).exists() or Path(state["source"]).read_text(encoding="utf-8") != "Owned rollback fixture":
                            raise RuntimeError("Owned inverse readback failed.")
                        report_event("ROLLBACK_READBACK_OK")
                    return result
            inverse = ObservableRollback()

            class CommandRouter:
                def route(self, request):
                    operation = request.text.removeprefix("fixture:")
                    if operation == "planning":
                        return RouteResult(RouteMode.SMART, "Owned planner cancellation fixture")
                    if operation not in {"read", "fail", "hold", "residual", "denied", "verify", "process", "rollback"}:
                        raise ValueError("Unknown fixture command.")
                    return RouteResult(RouteMode.FAST, "Owned safe fixture", Plan(route=RouteMode.FAST, mode=PlanMode.DIRECT,
                        steps=[ToolCall(tool="fixture_denied" if operation == "denied" else "invoke_control" if operation == "verify" else "fixture_process" if operation == "process" else "fixture_rollback" if operation == "rollback" else "fixture_command",
                            arguments={"operation": "read" if operation == "denied" else operation}, purpose="Owned fixture")]))

            class WaitingPlanner:
                def plan(self, *, cancellation_token, **kwargs):
                    report_event("PLANNING_ENTERED")
                    if not cancellation_token.wait_for_cancel(8):
                        raise TimeoutError("Owned planner fixture was not stopped.")
                    cancellation_token.raise_if_cancelled()

            core.orchestrator = Orchestrator(registry=registry, supervisor=supervisor, ledger=ledger,
                router=CommandRouter(), llm_manager=WaitingPlanner(), rollback_engine=inverse)

        if mode == "voice":
            from pluma.voice.capture import AudioCapture
            from pluma.voice.vad import EnergyVAD
            from pluma.voice.recognition import RecognitionProgress
            from pluma.voice.pipeline import VoiceClarificationRequired
            from pluma.core.request import InputMode, PlumaRequest
            import math
            import struct

            class InertCapture(AudioCapture):
                denied = False
                def start(self):
                    if self.denied:
                        raise PermissionError("Private fixture driver details")
                    with self._lock:
                        self._buffer.clear(); self._vad_pending.clear()
                        self._utterance_complete.clear()
                        self._boundary_detector.reset()
                        self._meter_sequence = 0
                        self._is_recording = True

            class FixtureVoicePipeline:
                outcome = "hold"
                def process_audio(self, audio, cancellation_token):
                    if self.outcome == "clarify":
                        return VoiceClarificationRequired(.1)
                    if self.outcome == "empty":
                        return None
                    cap = core._current_voice_capsule
                    cap.recognition_progress = RecognitionProgress(cap.task_id, cancellation_token)
                    cap.recognition_progress.accept(1, "Read file_name.md " + "owned transcript " * 120)
                    voice_entered.set()
                    while not voice_release.wait(.01):
                        cancellation_token.raise_if_cancelled()
                    cancellation_token.raise_if_cancelled()
                    return PlumaRequest(input_mode=InputMode.VOICE, text="fixture:read", original_transcript="fixture:read")

            core.audio_capture = InertCapture(vad=EnergyVAD())
            core.voice_pipeline = FixtureVoicePipeline()
            voice_tone = struct.pack('<16000h', *(int(8000*math.sin(2*math.pi*440*i/16000)) for i in range(16000)))

            def begin_voice():
                old = getattr(core, "_voice_session", None)
                if old is not None and old.capsule.cancellation_token.is_cancelled:
                    core._on_voice_release()
                core._on_voice_press()
                if not core._current_voice_capsule.cancellation_token.is_cancelled:
                    core.audio_capture.feed(voice_tone)

            def voice_control(command):
                if command == "voice_begin":
                    voice_release.clear(); voice_entered.clear()
                    core.voice_pipeline.outcome = "hold"; begin_voice()
                elif command == "voice_silence":
                    core.audio_capture.feed(bytes(3200))
                elif command == "voice_decode":
                    thread = threading.Thread(target=core._on_voice_release, name="OwnedVoiceFixture")
                    voice_threads.append(thread); thread.start()
                    if not voice_entered.wait(3):
                        raise RuntimeError("Fixture decoding was not observed.")
                elif command == "voice_more":
                    progress = core._current_voice_capsule.recognition_progress
                    progress.accept(progress.snapshot().sequence + 1, "additional owned speech " * 100)
                elif command == "voice_commit":
                    voice_release.set()
                    for thread in voice_threads:
                        thread.join(3)
                        if thread.is_alive():
                            raise RuntimeError("Owned voice caller remains active.")
                elif command in {"voice_clarify", "voice_empty"}:
                    core.voice_pipeline.outcome = "clarify" if command == "voice_clarify" else "empty"
                    begin_voice(); core._on_voice_release()
                elif command == "voice_deny":
                    core.audio_capture.denied = True
                    begin_voice()
                    core.audio_capture.denied = False
                elif command == "voice_timeout":
                    from pluma.core.cancellation import StopReason
                    begin_voice()
                    core._current_voice_capsule.cancellation_token.cancel(StopReason.TASK_TIMEOUT)
                    core._on_voice_release()
                elif command == "voice_pause":
                    voice_paused.set()
                elif command == "voice_resume":
                    voice_paused.clear()
                else:
                    raise RuntimeError("Unknown owned voice fixture command.")
                report_event(command.upper())

        def handler(request):
            if request.get("message_type") == "voice_query" and voice_paused.is_set():
                return {"protocol_version": 1, "message_type": "protocol_error", "error_code": "FIXTURE_PAUSED",
                        "message": "Owned fixture voice connection is unavailable."}
            if request.get("message_type") == "events_query" and paused_events.is_set():
                return {"protocol_version": 1, "message_type": "protocol_error", "error_code": "FIXTURE_PAUSED",
                        "message": "Owned fixture event connection is unavailable."}
            if request == {"command": "status"}:
                if saturate_status:
                    report_event("STATUS_ENTERED")
                    release_status.wait(8)
                return status(request)
            if request.get("message_type") == "stop":
                release_status.set()
            reply = core.handle_ipc_command(request)
            if (request.get("message_type") == "confirmation_decision" and request.get("approved") is True
                    and reply.get("accepted") is True):
                approved_calls.add(request["task_id"])
            return reply
    elif mode == "status":
        handler = status
    else:
        raise ValueError("Unsupported owned IPC fixture mode.")

    server = IpcServer(handler, address="\\\\.\\pipe\\" + sys.argv[1], require_auth=True)
    try:
        server.start()
        if not server._running:
            raise RuntimeError("Fixture pipe did not start.")
        if any(name in sys.modules for name in ("torch", "whisper", "llama_cpp", "paddleocr")):
            raise RuntimeError("An IPC fixture imported a heavy inference runtime.")
        print("READY", flush=True)
        for line in sys.stdin:
            if line.strip() == "stop":
                break
            if mode == "voice" and line.strip().startswith("voice_"):
                voice_control(line.strip())
            if line.strip() == "pause_events":
                paused_events.set(); report_event("EVENTS_PAUSED")
            if line.strip() == "resume_events":
                paused_events.clear(); report_event("EVENTS_RESUMED")
    finally:
        # Release any test-only blocking handler before asking the production IPC
        # server to drain its owned client threads.
        release_status.set()
        try:
            server.stop(timeout_s=4.0)
        except Exception:
            with server._clients_lock:
                remaining = [(thread.name, thread.is_alive(), type(conn).__name__)
                             for thread, conn in server._clients.items()]
            print(f"IPC_FIXTURE_REMAINING_OWNERS {remaining!r}", flush=True)
            raise
        if db is not None:
            broker.close()
            supervisor.stop_all_active_tasks()
            voice_release.set()
            for thread in voice_threads:
                thread.join(3)
                if thread.is_alive():
                    raise RuntimeError("Owned voice fixture did not exit.")
            for thread in list(getattr(core, "_submission_threads", {}).values()):
                thread.join(timeout=2)
                if thread.is_alive():
                    raise RuntimeError("Owned fixture task did not exit.")
            registry.close()
            if set(executed_calls) - approved_calls or len(executed_calls) != len(set(executed_calls)):
                raise RuntimeError("Unapproved or duplicate fixture executor entry.")
            if len(command_calls) != len(set(command_calls)):
                raise RuntimeError("Duplicate command fixture executor entry.")
            if mode in {"commands", "voice"}:
                import sqlite3
                from contextlib import closing
                with closing(sqlite3.connect("file:" + owned_db.as_posix() + "?mode=ro", uri=True)) as readback:
                    rows = readback.execute("SELECT task_id, final_state FROM tasks").fetchall()
                    if not rows or any(state not in {"SUCCEEDED", "FAILED", "STOPPED", "STOPPED_WITH_RESIDUAL"} for _, state in rows):
                        raise RuntimeError("Independent fixture SQLite terminal readback failed.")
                    report_event("COMMAND_LEDGER_READBACK_OK")
            db.close()
        for conflict in command_resources:
            if conflict.parent != Path(sys.argv[2]) or not conflict.name.startswith("p17-conflict-"):
                raise RuntimeError("Owned conflict cleanup path was not verified.")
            conflict.unlink(missing_ok=True)
        if owned_read is not None:
            owned_read.unlink()
        if owned_db is not None:
            for suffix in ("", "-wal", "-shm"):
                Path(str(owned_db) + suffix).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
