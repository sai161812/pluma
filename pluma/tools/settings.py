"""Owned settings Save with minimum field pre-state and guarded semantic undo."""
from copy import deepcopy
import json
import re

from pluma.config.settings import (SettingsError, SettingsStore, _apply, _exclusive,
                                   _replace, _revision, SCHEMA_VERSION)
from pluma.config.settings_contract import SettingsSaveArgs, patch
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult


def encoded(overrides):
    return json.dumps({"settings_schema_version": SCHEMA_VERSION, "overrides": overrides},
                      ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2).encode("utf-8")


def proof_revision(revision):
    # A namespaced non-secret digest survives generic hex-token redaction in
    # durable inverse recipes. Never exempt arbitrary values from redaction.
    return "absent" if revision == "absent" else "sha256:" + revision


def raw_revision(revision):
    if revision == "absent":
        return revision
    if not isinstance(revision, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", revision):
        raise SettingsError("SETTINGS_INVALID_PROOF")
    return revision[7:]


def restored_values(overrides, state):
    result = deepcopy(overrides)
    agent = result.setdefault("agent", {})
    for field, old in state["before"].items():
        key = field.split(".")[1]
        if old["present"]:
            agent[key] = old["value"]
        else:
            agent.pop(key, None)
    if not agent and not state["agent_present"]:
        result.pop("agent", None)
    return result


def capture_settings(args, context):
    if not getattr(context, "settings_path", None):
        raise SettingsError("SETTINGS_UNAVAILABLE")
    context.cancellation_token.raise_if_cancelled()
    store = SettingsStore(context.settings_path)
    observed = store.snapshot()
    if observed.revision != args["expected_revision"]:
        raise SettingsError("SETTINGS_CONFLICT")
    changes = patch(args)
    updated = _apply(observed.overrides, changes)
    agent = observed.overrides.get("agent", {})
    before = {field: {"present": field.split(".")[1] in agent,
                      "value": agent.get(field.split(".")[1])} for field in changes}
    state = {"action": "settings_write", "guard_version": 1, "path": str(store.path),
             "before_revision": proof_revision(observed.revision), "after_revision": proof_revision(_revision(encoded(updated))),
             "changes": changes, "before": before, "agent_present": "agent" in observed.overrides}
    reverse = restored_values(updated, state)
    state["restored_revision"] = proof_revision(_revision(None) if observed.revision == "absent"
                                               else _revision(encoded(reverse)))
    return state


def execute_settings(args, context):
    try:
        state = next(item["pre_state"] for item in reversed(context.undo_stack)
                     if item.get("action") == "pending_mutation" and item.get("tool") == "save_settings")
        if (state["path"] != context.settings_path or state["changes"] != patch(args)
                or raw_revision(state["before_revision"]) != args["expected_revision"]):
            raise SettingsError("SETTINGS_BINDING_CHANGED")
        context.cancellation_token.raise_if_cancelled()
        result = SettingsStore(state["path"]).save(state["changes"], expected_revision=raw_revision(state["before_revision"]))
        if result.revision != raw_revision(state["after_revision"]):
            raise SettingsError("SETTINGS_WRITE_UNVERIFIED")
        return ToolResult.success("save_settings", data={"revision": result.revision,
            "changed_fields": sorted(key.split(".")[1] for key in state["changes"]),
            "restart_required": True}, verified=False,
            factual_message="Saved settings. Restart PLUMA Core to apply them.", adapter_used="local_settings").model_copy(
                update={"private_context": {"settings_write": state}})
    except Exception:
        return ToolResult.failure("save_settings", "Settings were not verified. Previous evidence is retained.",
                                  "SETTINGS_SAVE_FAILED")


def verify_settings(result):
    try:
        state = result.private_context["settings_write"]
        observed = SettingsStore(state["path"]).snapshot()
        ok = (result.ok and result.tool == "save_settings" and observed.revision == raw_revision(state["after_revision"])
              and result.data == {"revision": raw_revision(state["after_revision"]), "restart_required": True,
                  "changed_fields": sorted(key.split(".")[1] for key in state["changes"])})
    except Exception:
        ok = False
    return VerifyResult(ok=ok, method="independent_settings_readback",
                        detail="Settings read back from the selected source." if ok else "Settings readback failed.")


def verify_restored(state):
    try:
        return SettingsStore(state["path"]).snapshot().revision == raw_revision(state["restored_revision"])
    except Exception:
        return False


def restore_settings(state):
    from pluma.rollback.recipes import RollbackStepResult
    try:
        store = SettingsStore(state["path"])
        with _exclusive(store.path.with_name(store.path.name + ".lock")):
            observed = store.snapshot()
            if observed.revision != raw_revision(state["after_revision"]) or state.get("guard_version") != 1:
                raise SettingsError("SETTINGS_UNDO_CONFLICT")
            # Only the captured public agent fields can be restored, never a
            # policy/path value smuggled in through a stored inverse.
            from pluma.config.settings_contract import FIELDS
            if not state["before"] or set(state["before"]) - {"agent." + key for key in FIELDS}:
                raise SettingsError("SETTINGS_UNDO_INVALID")
            if state["before_revision"] == "absent":
                store.path.unlink()
            else:
                raw = encoded(restored_values(observed.overrides, state))
                if _revision(raw) != raw_revision(state["restored_revision"]):
                    raise SettingsError("SETTINGS_UNDO_INVALID")
                _replace(store.path, raw)
            if not verify_restored(state):
                raise SettingsError("SETTINGS_UNDO_UNVERIFIED")
        return RollbackStepResult(ok=True, action="settings_write",
                                  message="Restored captured settings. Restart Core to apply them.")
    except Exception:
        return RollbackStepResult(ok=False, action="settings_write",
                                  message="Settings undo conflicts or is unverified.", error="ROLLBACK_CONFLICT")


SETTINGS_TOOL_SPECS = [ToolSpec(name="save_settings", description="Save explicitly selected PLUMA settings; restart required.",
    args_schema=SettingsSaveArgs, risk_class=RiskClass.MEDIUM, timeout_s=10, process_isolated=True,
    executor=execute_settings, verifier=verify_settings, undo_builder=capture_settings)]
