"""Owned settings Save with minimum field pre-state and guarded semantic undo."""
from copy import deepcopy
import json
from pathlib import Path
import re
import tempfile

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


def stage_settings(context, ledger, path):
    """Parent publishes exact directory identity before any settings bytes exist."""
    from pluma.core.task_supervisor import ResourceOwnership
    from pluma.memory.activity import ResourceRecord
    if context is None or ledger is None or path is None:
        raise SettingsError("SETTINGS_OWNERSHIP_UNAVAILABLE")
    store = SettingsStore(path)
    with context.work_lock:
        context.cancellation_token.raise_if_cancelled()
        store.path.parent.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix=".pluma-settings-" + context.task_id + "-", dir=store.path.parent))
        resource = context.register_owned_resource("temp_dir", ResourceOwnership.PLUMA_CREATED, str(directory),
                                                    metadata={"persisted_resource": True})
        identity = resource.metadata.get("cleanup_identity")
        if not identity:
            raise SettingsError("SETTINGS_OWNERSHIP_UNAVAILABLE")
        ledger.insert_resource(ResourceRecord(id=resource.resource_id, task_id=context.task_id,
            resource_type="temp_dir", ownership="PLUMA_CREATED", external_id=str(directory), metadata=resource.metadata))
        row = ledger._db.execute_read_one("SELECT external_id,metadata_json FROM resources WHERE id=?", (resource.resource_id,))
        if row is None or row["external_id"] != str(directory) or json.loads(row["metadata_json"]) != resource.metadata:
            raise SettingsError("SETTINGS_OWNERSHIP_UNVERIFIED")
        context.cancellation_token.raise_if_cancelled()
        return {"path": str(directory), "identity": identity}


def peek_settings(args, context):
    from pluma.memory.tool_store import connect
    from pluma.memory.undo import _latest_available
    with connect(context.storage_path) as connection:
        latest = _latest_available(connection, args.get("selection"))
    state = latest[1] if latest else {}
    return {"action": "settings_lookup", "path": state.get("path") if state.get("action") == "settings_write" else None}


def scratch(state):
    from pluma.core.ownership import capture_temp_identity
    directory = Path(state["staging"]["path"])
    observed = capture_temp_identity(directory)
    expected = state["staging"]["identity"]
    if (directory.parent != Path(state["path"]).parent or not directory.is_dir()
            or any(observed[key] != expected[key] for key in ("device", "inode"))):
        raise SettingsError("SETTINGS_SCRATCH_IDENTITY_CHANGED")
    return directory


def restored_values(overrides, state):
    result = deepcopy(overrides)
    sections = state.get("sections_present", {"agent": state.get("agent_present", True)})
    for field, old in state["before"].items():
        section, key = field.split(".")
        values = result.setdefault(section, {})
        if old["present"]:
            values[key] = old["value"]
        else:
            values.pop(key, None)
        if not values and not sections.get(section, True):
            result.pop(section, None)
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
    from pluma.config.settings import _hotkey
    from pluma.config.loader import _load_yaml, _DEFAULTS_FILE, _merge, get
    current = _merge(_load_yaml(_DEFAULTS_FILE), observed.overrides)
    changed_bindings = [value for field,value in changes.items() if field.endswith("_hotkey")
                        and _hotkey(value) != _hotkey(get(current, *field.split("."), default="ctrl+alt+v"))]
    if changed_bindings:
        from pluma.adapters.hotkeys import probe_changed
        probe_changed(changed_bindings)
    before = {field: {"present": field.split(".")[1] in observed.overrides.get(field.split(".")[0], {}),
                      "value": observed.overrides.get(field.split(".")[0], {}).get(field.split(".")[1])} for field in changes}
    state = {"action": "settings_write", "guard_version": 1, "path": str(store.path),
             "before_revision": proof_revision(observed.revision), "after_revision": proof_revision(_revision(encoded(updated))),
             "changes": changes, "before": before, "agent_present": "agent" in observed.overrides,
             "sections_present": {field.split(".")[0]: field.split(".")[0] in observed.overrides for field in changes}}
    reverse = restored_values(updated, state)
    state["restored_revision"] = proof_revision(_revision(None) if observed.revision == "absent"
                                               else _revision(encoded(reverse)))
    return state


def execute_settings(args, context):
    try:
        state = next(item["pre_state"] for item in reversed(context.undo_stack)
                     if item.get("action") == "pending_mutation" and item.get("tool") == "save_settings")
        if (state["path"] != context.settings_path or state["changes"] != patch(args)
                or raw_revision(state["before_revision"]) != args["expected_revision"]
                or state["staging"] != context.execution_binding["settings_staging"]):
            raise SettingsError("SETTINGS_BINDING_CHANGED")
        context.cancellation_token.raise_if_cancelled()
        result = SettingsStore(state["path"]).save(state["changes"], expected_revision=raw_revision(state["before_revision"]),
                                                  scratch_dir=scratch(state))
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
        directory = scratch(state)
        with _exclusive(store.path.with_name(store.path.name + ".lock")):
            observed = store.snapshot()
            if observed.revision != raw_revision(state["after_revision"]) or state.get("guard_version") != 1:
                raise SettingsError("SETTINGS_UNDO_CONFLICT")
            # Only the captured public agent fields can be restored, never a
            # policy/path value smuggled in through a stored inverse.
            from pluma.config.settings_contract import FIELD_PATHS
            if not state["before"] or set(state["before"]) - set(FIELD_PATHS.values()):
                raise SettingsError("SETTINGS_UNDO_INVALID")
            if state["before_revision"] == "absent":
                store.path.unlink()
            else:
                raw = encoded(restored_values(observed.overrides, state))
                if _revision(raw) != raw_revision(state["restored_revision"]):
                    raise SettingsError("SETTINGS_UNDO_INVALID")
                _replace(store.path, raw, directory=directory)
            if not verify_restored(state):
                raise SettingsError("SETTINGS_UNDO_UNVERIFIED")
        return RollbackStepResult(ok=True, action="settings_write",
                                  message="Restored captured settings. Restart Core to apply them.")
    except Exception:
        return RollbackStepResult(ok=False, action="settings_write",
                                  message="Settings undo conflicts or is unverified.", error="ROLLBACK_CONFLICT")


def recover_pending_settings(pending):
    from pluma.rollback.recipes import RollbackStepResult
    try:
        state = pending["pre_state"]
        if state.get("guard_version") != 1 or state.get("action") != "settings_write":
            raise SettingsError("SETTINGS_INVALID_PROOF")
        observed = SettingsStore(state["path"]).snapshot()
        if observed.revision == raw_revision(state["before_revision"]):
            return RollbackStepResult(ok=True, action="pending_mutation",
                message="Settings source independently matches captured pre-state.")
        if observed.revision == raw_revision(state["after_revision"]):
            return restore_settings(state)
    except Exception:
        pass
    return RollbackStepResult(ok=False, action="pending_mutation",
        message="Settings source differs from both captured states. Evidence retained.", error="ROLLBACK_CONFLICT")


SETTINGS_TOOL_SPECS = [ToolSpec(name="save_settings", description="Save explicitly selected PLUMA settings; restart required.",
    args_schema=SettingsSaveArgs, risk_class=RiskClass.MEDIUM, timeout_s=10, process_isolated=True,
    executor=execute_settings, verifier=verify_settings, undo_builder=capture_settings)]


def capture_recovery(args, context):
    store = SettingsStore(context.settings_path)
    current, previous = store.recovery_state()
    if current != args["expected_revision"] or previous.revision != args["previous_revision"]:
        raise SettingsError("SETTINGS_CONFLICT")
    return {"action":"non_undoable", "non_undoable":True, "operation":"recover_settings", "path":str(store.path),
            "before_revision":proof_revision(current), "after_revision":proof_revision(previous.revision),
            "reason":"Restore the last valid source; preserve the rejected source separately. No automatic undo."}


def execute_recovery(args, context):
    try:
        state=next(item["pre_state"] for item in reversed(context.undo_stack)
                   if item.get("action")=="pending_mutation" and item.get("tool")=="recover_settings")
        if (state["path"]!=context.settings_path or raw_revision(state["before_revision"])!=args["expected_revision"]
                or raw_revision(state["after_revision"])!=args["previous_revision"]):
            raise SettingsError("SETTINGS_BINDING_CHANGED")
        context.cancellation_token.raise_if_cancelled()
        SettingsStore(context.settings_path).restore_previous(expected_revision=args["expected_revision"],
            previous_revision=args["previous_revision"],scratch_dir=scratch(state))
        return ToolResult.success("recover_settings", data={"recovered":True,"restart_required":True},
            factual_message="Restored previous valid settings. Rejected source preserved. Restart Core to apply.").model_copy(
                update={"private_context":{"settings_recovery":state}})
    except Exception:
        return ToolResult.failure("recover_settings","Recovery was not verified. Source evidence retained.","SETTINGS_RECOVERY_FAILED")


def verify_recovery(result):
    try:
        state=result.private_context["settings_recovery"]
        store=SettingsStore(state["path"])
        from pluma.config.settings import _read
        rejected=store.path.with_name(store.path.name+".rejected."+raw_revision(state["before_revision"]))
        ok=(result.ok and store.snapshot().revision==raw_revision(state["after_revision"])
            and _revision(_read(rejected))==raw_revision(state["before_revision"]))
    except Exception:
        ok=False
    return VerifyResult(ok=ok,method="independent_settings_recovery_readback",detail="Recovery source and retained original checked.")


from pluma.config.settings_contract import SettingsRecoveryArgs
SETTINGS_TOOL_SPECS.append(ToolSpec(name="recover_settings",description="Restore last valid local settings, preserving rejected source; no automatic undo.",
    args_schema=SettingsRecoveryArgs,risk_class=RiskClass.MEDIUM,timeout_s=10,process_isolated=True,non_undoable=True,
    executor=execute_recovery,verifier=verify_recovery,undo_builder=capture_recovery))
