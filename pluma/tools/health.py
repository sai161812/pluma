"""P22 typed setup and self-owned restart requests, never arbitrary processes."""
from typing import Callable
from pydantic import BaseModel,ConfigDict,StrictBool,StrictInt,StrictStr,Field,field_validator
from pluma.tools.base import ToolSpec,ToolResult,VerifyResult,RiskClass


class SetupArgs(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    include_microphone:StrictBool=False


class RestartArgs(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    instance_id:StrictStr=Field(pattern=r"^[0-9a-f-]{36}$")
    pid:StrictInt=Field(gt=0)
    creation_time:StrictInt=Field(gt=0)

    @field_validator("instance_id")
    @classmethod
    def canonical_id(cls,value):
        from uuid import UUID
        if str(UUID(value))!=value:raise ValueError("Canonical Core identity required.")
        return value


def execute_setup(args,context):
    from pluma.adapters.capabilities import check_setup
    binding=context.execution_binding
    if not binding or "setup" not in binding:raise ValueError("No composed capability paths.")
    checks=check_setup(binding["setup"],args["include_microphone"],context.cancellation_token)
    return ToolResult.success("check_setup",data={"checks":checks,"fingerprint":binding["fingerprint"]},
        factual_message="Setup checks completed. Individual availability is reported separately.",adapter_used="native_setup").model_copy(
            update={"private_context":{"setup_config":binding["setup"]}})


def verify_setup(result):
    checks=result.data.get("checks",[])
    ok=(result.ok and result.adapter_used=="native_setup" and len(checks)==5
        and {c.get("id") for c in checks}=={"planner","speech","ocr","uia","microphone"}
        and all(c.get("origin")=="native" and c.get("state") in ("PASSED","FAILED","UNVERIFIED") for c in checks))
    if ok:
        try:
            from pluma.adapters.capabilities import probe
            config=result.private_context["setup_config"]
            for check in checks:
                if check["state"]=="PASSED" and check["id"]!="microphone":
                    ok=ok and probe(check["id"],config,False)[0]=="PASSED"
        except Exception:ok=False
    return VerifyResult(ok=ok,method="native_probe_receipts",detail="Bounded native access receipts; availability is not inferred from task success.")


def capture_restart(args,context):
    return {"action":"non_undoable","non_undoable":True,"operation":"restart_core",
            "reason":"Restart only this verified Core graph. Running tasks will be stopped; no automatic undo."}


def execute_restart(args,context):
    context.cancellation_token.raise_if_cancelled()
    receipt=context.request_core_restart(args,context.task_id)
    return ToolResult.success("restart_core",data={"requested":True},
        factual_message="Core restart requested. Recovery is not yet verified.").model_copy(update={"private_context":{"receipt":receipt}})


def verify_restart(result):
    receipt=result.private_context.get("receipt")
    ok=bool(result.ok and receipt is not None and receipt())
    return VerifyResult(ok=ok,method="owned_restart_queue_readback",detail="Only restart intent is queued; authenticated new-instance health must verify recovery.")


HEALTH_TOOL_SPECS=[ToolSpec(name="check_setup",description="User-initiated local dependency and consented microphone access checks.",
    args_schema=SetupArgs,risk_class=RiskClass.READ,timeout_s=30,process_isolated=True,
    executor=execute_setup,verifier=verify_setup),
    ToolSpec(name="restart_core",description="Request verified self-owned Core restart; stop active tasks. No automatic undo.",
    args_schema=RestartArgs,risk_class=RiskClass.MEDIUM,timeout_s=10,execution_scope="task_service",non_undoable=True,
    executor=execute_restart,verifier=verify_restart,undo_builder=capture_restart)]
