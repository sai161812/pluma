"""Single owned control host. Restarts replace only its graph, never another PID."""
import hashlib
import json
import math
import numbers
import os
from pathlib import Path
import threading
import time
from uuid import uuid4

from pluma.core.health_contracts import HealthRequest


class _GraphEndpoint:
    """Host retains the authenticated endpoint across verified graph drain."""
    def start(self):pass
    def stop(self):pass
    def begin_shutdown(self):pass


def request_owned_core_shutdown(
    target_pid: int,
    installation_root: str | Path,
    expected_executable: str | Path,
    timeout_s: float = 3.0,
    exit_timeout_s: float = 15.0,
) -> dict:
    """Ask the authenticated, exact installed Core to drain and exit gracefully."""
    if type(target_pid) is not int or target_pid <= 0:
        raise ValueError("A positive resident PID is required.")
    if (isinstance(timeout_s, bool) or not isinstance(timeout_s, numbers.Real)
            or not math.isfinite(timeout_s) or timeout_s <= 0 or timeout_s > 5.0):
        raise ValueError("Shutdown IPC timeout must be between 0 and 5 seconds.")
    if (isinstance(exit_timeout_s, bool) or not isinstance(exit_timeout_s, numbers.Real)
            or not math.isfinite(exit_timeout_s) or exit_timeout_s <= 0 or exit_timeout_s > 30.0):
        raise ValueError("Shutdown exit timeout must be between 0 and 30 seconds.")
    install_root = Path(installation_root).resolve()
    expected_executable = Path(expected_executable).resolve()
    try:
        common = os.path.commonpath((str(install_root), str(expected_executable)))
        if os.path.normcase(common) != os.path.normcase(str(install_root)):
            raise ValueError("Expected Core executable is outside the installation root.")
    except ValueError as exc:
        raise ValueError("Expected Core executable is outside the installation root.") from exc

    from pluma.core.ownership import get_process_creation_time
    import psutil

    creation_time = get_process_creation_time(target_pid)
    if creation_time is None:
        raise RuntimeError("Installed Core process identity is unavailable.")
    try:
        process = psutil.Process(target_pid)
        actual_executable = Path(process.exe()).resolve()
    except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
        raise RuntimeError("Installed Core executable could not be read safely.") from exc
    if os.path.normcase(str(actual_executable)) != os.path.normcase(str(expected_executable)):
        raise RuntimeError("Resident PID does not match the selected installation executable.")
    if get_process_creation_time(target_pid) != creation_time:
        raise RuntimeError("Core process identity changed during executable verification.")

    from pluma.core.ipc import IpcClient
    client = IpcClient(require_auth=True)
    health_id = str(uuid4())
    snapshot = client.send_command(
        {"protocol_version": 1, "message_type": "health_query", "request_id": health_id},
        timeout=timeout_s,
    )
    if (
        snapshot.get("message_type") != "health_snapshot"
        or snapshot.get("request_id") != health_id
        or snapshot.get("pid") != target_pid
        or snapshot.get("creation_time") != creation_time
        or not isinstance(snapshot.get("instance_id"), str)
    ):
        raise RuntimeError("Authenticated Core health identity did not match the selected process.")
    if get_process_creation_time(target_pid) != creation_time:
        raise RuntimeError("Core process identity changed before shutdown admission.")

    request_id = str(uuid4())
    request = HealthRequest(
        protocol_version=1,
        message_type="core_shutdown",
        request_id=request_id,
        instance_id=snapshot["instance_id"],
        pid=target_pid,
        creation_time=creation_time,
    )
    ack = client.send_command(request.model_dump(mode="json"), timeout=timeout_s)
    if (
        ack.get("message_type") != "shutdown_ack"
        or ack.get("request_id") != request_id
        or ack.get("pid") != target_pid
        or ack.get("creation_time") != creation_time
        or ack.get("instance_id") != snapshot["instance_id"]
        or ack.get("accepted") is not True
    ):
        raise RuntimeError("Core did not acknowledge the owned shutdown request.")
    try:
        exit_code = process.wait(timeout=float(exit_timeout_s))
    except psutil.TimeoutExpired as exc:
        raise RuntimeError("Core acknowledged shutdown but did not exit within the bounded drain period.") from exc
    except psutil.NoSuchProcess as exc:
        raise RuntimeError("Core exited before its process status could be read back.") from exc
    if exit_code != 0:
        raise RuntimeError(f"Core exited after shutdown with an unverified status: {exit_code!r}.")
    if get_process_creation_time(target_pid) == creation_time:
        raise RuntimeError("Core process identity remains after shutdown acknowledgement.")
    return {"pid": target_pid, "creation_time": creation_time, "exit_code": exit_code, "request_id": request_id}


class CoreHost:
    def __init__(self,paths,*,config_path=None,address=None,debug=False):
        from pluma.core.ipc import IpcServer
        from pluma.core.ownership import get_process_creation_time
        self.paths=paths
        self.config_path=str(Path(config_path or os.environ.get("PLUMA_CONFIG") or paths.user_settings_path).absolute())
        self.pid=os.getpid();self.creation_time=get_process_creation_time(self.pid)
        if not self.creation_time:raise RuntimeError("Core process identity unavailable.")
        self.debug=debug;self.runtime=None;self.instance_id=str(uuid4());self.state="STARTING"
        self.code="STARTING";self.recovery=None;self.setup_task=None;self.setup_time=0
        self._lease=None;self._lock=threading.RLock();self._restart=None;self._closing=False;self._recover_control=False
        self._shutdown_requested=False;self._shutdown_reply_sent=threading.Event();self._shutdown_reply_deadline=0.0
        self.server=IpcServer(self.handle,address=address,require_auth=True,
            response_sent_handler=self._response_sent)

    def _response_sent(self,request,response):
        if (request.get("message_type")=="core_shutdown" and response.get("message_type")=="shutdown_ack"
                and response.get("accepted") is True and response.get("pid")==self.pid
                and response.get("creation_time")==self.creation_time):
            self._shutdown_reply_sent.set()

    def _construct(self):
        from pluma.app import PlumaApplicationRuntime,setup_logging
        from pluma.config.loader import load_config,_load_yaml,_DEFAULTS_FILE
        from pluma.config.settings import _validate
        from pluma.core.recovery import CrashRecoveryManager
        self.instance_id=str(uuid4());self.setup_task=None;self.setup_time=0
        self.recovery=CrashRecoveryManager(paths=self.paths).reconcile_startup()
        try:
            config=load_config(self.config_path);_validate(config)
            valid=True
        except Exception:
            config=_load_yaml(_DEFAULTS_FILE);valid=False
        if self.debug:config.setdefault("logging",{})["debug"]=True
        setup_logging(self.paths.logs_dir,debug=bool(config.get("logging",{}).get("debug",False)))
        runtime=PlumaApplicationRuntime(self.paths,config=config,settings_path=self.config_path)
        self.runtime=runtime
        runtime.resident_core.ipc=_GraphEndpoint()
        runtime.tool_registry.core_restart_callback=self.schedule
        runtime.tool_registry.setup_binding={"setup":{"planner":runtime.resident_core.effective_model_path,
            "speech":runtime.resident_core.effective_stt_model_path,
            "ocr":str(Path(os.environ.get("PADDLEX_HOME",str(Path.home()/".paddlex")))/"official_models")},
            "fingerprint":self.fingerprint()}
        if not valid:
            self.state="CONFIGURATION_ERROR";self.code="SETTINGS_INVALID";return
        if not self.recovery.db_integrity_ok or self.recovery.errors:
            self.state="RECOVERY_ERROR";self.code="STARTUP_RECOVERY_UNVERIFIED";return
        try:
            runtime.resident_core.start()
            self.state="READY";self.code="CORE_READY"
        except Exception:
            if not runtime.close(3).complete:
                self._recover_control=True
                self.state="RECOVERY_ERROR";self.code="OWNED_DRAIN_PENDING";return
            self.runtime=PlumaApplicationRuntime(self.paths,config=config,settings_path=self.config_path)
            self.runtime.resident_core.ipc=_GraphEndpoint()
            self.runtime.tool_registry.core_restart_callback=self.schedule
            self.state="HOTKEY_ERROR";self.code="HOTKEY_UNAVAILABLE"

    def fingerprint(self):
        config=self.runtime.config if self.runtime else {}
        return "sha256:"+hashlib.sha256(json.dumps(config,sort_keys=True,ensure_ascii=True).encode()).hexdigest()

    def start(self):
        from pluma.config.settings import _exclusive
        self.paths.local_root.mkdir(parents=True,exist_ok=True)
        from contextlib import ExitStack
        if self._lease is not None:raise RuntimeError("Host already owns a lease.")
        self._lease=ExitStack()
        try:
            self._lease.enter_context(_exclusive(self.paths.local_root/"core.host.lock"))
            endpoint_root=Path(os.environ.get("LOCALAPPDATA") or Path.home())/"Pluma"
            endpoint_root.mkdir(parents=True,exist_ok=True)
            name=hashlib.sha256(self.server.address.encode()).hexdigest()
            self._lease.enter_context(_exclusive(endpoint_root/("core.endpoint."+name+".lock")))
            self._construct();self.server.start()
        except BaseException:
            self.close()
            raise

    def identity(self):
        return {"instance_id":self.instance_id,"pid":self.pid,"creation_time":self.creation_time}

    def schedule(self,args,task_id):
        from pluma.core.ownership import get_process_creation_time
        with self._lock:
            if self._closing or self._recover_control or self.state not in ("READY","CONFIGURATION_ERROR","HOTKEY_ERROR","RECOVERY_ERROR") or self._restart is not None or args!=self.identity() or get_process_creation_time(self.pid)!=self.creation_time:
                raise ValueError("Restart target is not the owned current Core.")
            pending=(self.instance_id,task_id,self.runtime.supervisor._stop_generation)
            self._restart=pending
        return lambda:self._restart==pending

    @staticmethod
    def _voice_available(core):
        if not core.voice_enabled:return True
        activation=core.voice_activation
        return bool(activation is not None and activation._running and activation._thread is not None
                    and activation._thread.is_alive())

    def _observe_liveness(self):
        core=self.runtime.resident_core if self.runtime else None
        if self.state=="READY" and core is not None and (not core._running or
                (core._hotkey_thread is not None and (not core._hotkey_thread.is_alive() or not self._voice_available(core)))):
            self._recover_control=True;self.state="RECOVERY_ERROR";self.code="OWNED_DRAIN_PENDING"

    def advance(self):
        if self._shutdown_requested:
            if not self._shutdown_reply_sent.is_set() and time.monotonic()<self._shutdown_reply_deadline:return
            self.server.begin_shutdown()
            self.close()
            return
        self._observe_liveness()
        if self._recover_control:
            if not self.runtime.close(3).complete:return
            from pluma.app import PlumaApplicationRuntime
            config=self.runtime.config
            with self._lock:self._restart=None
            self.instance_id=str(uuid4());self.setup_task=None;self.setup_time=0
            self.runtime=PlumaApplicationRuntime(self.paths,config=config,settings_path=self.config_path)
            self.runtime.resident_core.ipc=_GraphEndpoint()
            self.runtime.tool_registry.core_restart_callback=self.schedule
            self._recover_control=False;self.state="HOTKEY_ERROR";self.code="HOTKEY_UNAVAILABLE"
            return
        with self._lock:pending=self._restart
        if pending is None:return
        capsule=self.runtime.supervisor.get_task(pending[1])
        if not capsule.terminal_ready.is_set():return
        with self.runtime.supervisor._admission_lock:
            if capsule.stop_latch_set or capsule.state.value!="SUCCEEDED" or pending[2]!=self.runtime.supervisor._stop_generation:
                with self._lock:self._restart=None
                self.code="RESTART_CANCELLED"
                return
            self.state="RESTARTING";self.code="OWNED_DRAIN_PENDING"
        if not self.runtime.close(3).complete:return
        with self._lock:self._restart=None
        self._construct()

    def close(self):
        self._closing=True
        if self.runtime is not None and not self.runtime.close(3).complete:return False
        self.server.stop();self.state="STOPPED"
        if self._lease is not None:
            self._lease.__exit__(None,None,None);self._lease=None
        return True

    def health(self,request_id):
        checks=[];native=False
        if self.setup_task is not None and self.state=="READY":
            try:
                from pluma.memory.activity import ActivityQuery
                cap=self.runtime.supervisor.get_task(self.setup_task)
                rows=ActivityQuery(self.runtime.db).actions_for_task(self.setup_task)
                if cap.terminal_ready.is_set() and cap.state.value=="SUCCEEDED" and len(rows)==1 and rows[0]["verified"]:
                    data=json.loads(rows[0]["result_json"])
                    if "data" in data:data=data["data"]
                    if data.get("fingerprint")==self.fingerprint() and time.monotonic()-self.setup_time<60:
                        checks=data.get("checks",[])
                        from pluma.tools.health import execute_setup,verify_setup
                        spec=self.runtime.tool_registry.lookup("check_setup")
                        native=(spec.executor is execute_setup and spec.verifier is verify_setup
                            and len(checks)==5 and all(c.get("origin")=="native" for c in checks)
                            and any(e.kind=="worker" and e.verified and e.code=="WORKER_ABSENCE_VERIFIED" for e in cap.cleanup_evidence))
            except Exception:checks=[];native=False
        core=self.runtime.resident_core if self.runtime else None
        hotkeys=bool(core is not None and core._running and core._hotkey_thread is not None
            and core._hotkey_thread.is_alive() and getattr(core,"_hotkey_error",None) is None and self._voice_available(core))
        ready=(self.state=="READY" and native and hotkeys and {c.get("id") for c in checks}=={"planner","speech","ocr","uia","microphone"}
               and all(c.get("state")=="PASSED" for c in checks))
        return {"protocol_version":1,"message_type":"health_snapshot","request_id":request_id,
            **self.identity(),"state":self.state,"code":self.code,"can_restart":not self._closing and not self._recover_control and self._restart is None and self.state in ("READY","CONFIGURATION_ERROR","HOTKEY_ERROR","RECOVERY_ERROR"),
            "fingerprint":self.fingerprint(),"checks":checks,"native_verified":native,"hotkeys_registered":hotkeys,
            "setup_ready":ready,"stale_tasks_recovered":self.recovery.stale_tasks_recovered if self.recovery else 0}

    def handle(self,payload):
        runtime=self.runtime
        try:
            if runtime is None:raise ValueError("No Core graph.")
            with runtime.resident_core._entry_gate.enter():
                if runtime is not self.runtime:raise ValueError("Core graph changed.")
                return self._handle(payload)
        except Exception:
            return {"protocol_version":1,"message_type":"protocol_error","error_code":"HEALTH_REQUEST_UNAVAILABLE",
                    "message":"Core is unavailable or draining. No recovery was verified."}

    def _handle(self,payload):
        self._observe_liveness()
        kind=payload.get("message_type")
        try:
            if kind=="health_query":
                request=HealthRequest.model_validate(payload)
                return self.health(request.request_id)
            if kind in ("setup_check","core_restart"):
                request=HealthRequest.model_validate(payload)
                if request.instance_id!=self.instance_id or self._closing or self._restart is not None:
                    raise ValueError("Owned Core changed.")
                if kind=="setup_check" and self.state!="READY":raise ValueError("Core is unavailable.")
                if kind=="core_restart" and {"instance_id":request.instance_id,"pid":request.pid,"creation_time":request.creation_time}!=self.identity():
                    raise ValueError("Wrong Core identity.")
                selected={"health_tool":"check_setup" if kind=="setup_check" else "restart_core",
                    "arguments":{"include_microphone":request.include_microphone} if kind=="setup_check" else self.identity()}
                from pluma.core.ipc_contracts import SubmitTextV1,SubmissionAckV1
                ack=self.runtime.resident_core._submit_text_v1(SubmitTextV1(protocol_version=1,message_type="submit_text",
                    request_id=request.request_id,text="Check local setup availability." if kind=="setup_check" else "Restart this owned PLUMA Core."),SubmissionAckV1,selected=selected)
                if kind=="setup_check" and ack.get("accepted") and self.setup_task!=ack["task_id"]:
                    self.setup_task=ack["task_id"];self.setup_time=time.monotonic()
                return ack
            if kind=="core_shutdown":
                request=HealthRequest.model_validate(payload)
                from pluma.core.ownership import get_process_creation_time
                with self._lock:
                    if (self._closing or self._shutdown_requested or self.runtime is None
                            or request.instance_id!=self.instance_id or request.pid!=self.pid
                            or request.creation_time!=self.creation_time
                            or get_process_creation_time(self.pid)!=self.creation_time
                            or self._restart is not None):
                        raise ValueError("Shutdown target is not the owned current Core.")
                    runtime=self.runtime
                    self._closing=True;self._shutdown_requested=True
                    self._shutdown_reply_sent.clear();self._shutdown_reply_deadline=time.monotonic()+2.0
                    self.state="STOPPING";self.code="SHUTDOWN_REQUESTED"
                # Close every admission path before acknowledging the request.
                runtime.supervisor.begin_shutdown()
                runtime.resident_core.begin_shutdown()
                runtime.tool_registry.begin_shutdown()
                return {"protocol_version":1,"message_type":"shutdown_ack","request_id":request.request_id,
                    **self.identity(),"accepted":True}
            if self.state!="READY":
                allowed={"confirmation_query","confirmation_decision","confirmation_disconnect","terminal_readback","history_query",
                    "history_page_query","task_detail_query","settings_query","settings_edit_query","stop","runtime_query","events_query"}
                if kind=="settings_save" and (self.state=="HOTKEY_ERROR" or payload.get("changes")=={"recover_previous":True}):pass
                elif kind not in allowed:raise ValueError("Core is not ready.")
            if self.runtime is None:raise ValueError("No Core graph.")
            reply=self.runtime.resident_core.handle_ipc_command(payload)
            if kind=="runtime_query" and reply.get("message_type")=="runtime_snapshot":
                reply.update(core_instance_id=self.instance_id,core_ready=self.state=="READY" and self.runtime.resident_core._running)
            return reply
        except Exception:
            return {"protocol_version":1,"message_type":"protocol_error","error_code":"HEALTH_REQUEST_UNAVAILABLE",
                    "message":"The requested health or recovery operation is unavailable. No replacement Core was started."}
