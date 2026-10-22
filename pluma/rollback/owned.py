"""Bounded, capsule-owned execution of registered native inverse phases.

Cleanup workers cannot plan or dispatch ordinary tools. They run only a closed
inverse on executor-captured evidence after the original executor has drained.
"""
from dataclasses import asdict
from typing import Any, Literal
import uuid

from pydantic import BaseModel

from pluma.core.cleanup import CleanupEvidence
from pluma.rollback.recipes import RollbackRecipes, RollbackStepResult
from pluma.tools.base import ToolResult


class InverseRequest(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}
    action: Literal['safe_delete', 'pending_mutation', 'set_volume', 'mute', 'unmute', 'set_default_audio_device',
                    'move_file', 'rename_file', 'copy_file', 'create_folder', 'window_geometry', 'window_state', 'window_focus', 'app_launch', 'clipboard_restore']
    state: dict[str, Any]


def execute_inverse(args, context):
    request = InverseRequest.model_validate(args)
    if request.action == 'pending_mutation' and request.state.get('tool') != 'safe_delete':
        return ToolResult.failure('undo_last', 'No registered recycle recovery phase.', 'INVERSE_UNSUPPORTED')
    outcome = RollbackRecipes().apply(request.action, request.state)
    return ToolResult(ok=outcome.ok, tool='undo_last', verified=outcome.ok,
        factual_message=outcome.message, data={'inverse': asdict(outcome)})


def apply_owned(action, state, capsule, *, timeout_s=10):
    from pluma.tools.registry import TaskWorkerController, WorkerRequest
    key = 'inverse-worker:' + str(uuid.uuid4())
    controller = TaskWorkerController(capsule.task_id)
    # Retain ownership before spawning; this is rollback after latch, not a new
    # ToolCall or a replan. It cannot reuse the cancelled action admission gate.
    with capsule.work_lock:
        capsule.inverse_workers[key] = controller
    outcome = RollbackStepResult(ok=False, action=action,
        message='Owned native inverse was not verified.', error='INVERSE_UNVERIFIED')
    errors = []
    try:
        args = InverseRequest(action=action, state=state).model_dump()
        import os
        request = WorkerRequest(capsule.task_id, 'undo_last', args, timeout_s,
            env_overrides={key: value for key, value in os.environ.items() if key.startswith('PLUMA_')})
        status, response = controller.execute_call(execute_inverse, args, request, timeout_s)
        if status == 'ok' and 'inverse' in response.result.data:
            candidate = RollbackStepResult(**response.result.data['inverse'])
            if candidate.ok == response.result.ok == response.result.verified:
                outcome = candidate
        else:
            errors.append('INVERSE_WORKER_RESPONSE_' + status.upper())
    except Exception:
        errors.append('INVERSE_EXECUTION_FAILED')
    finally:
        try:
            controller.dispose_owned_worker()
        except Exception:
            errors.append('INVERSE_DISPOSAL_FAILED')
        try:
            drained = controller.verify_cleanup() is True
        except Exception:
            drained = False
        identity = dict(controller.worker_identity or {}, command_class='rollback_worker')
        capsule.cleanup_evidence.append(CleanupEvidence(resource_id=key, kind='worker',
            identity=identity, verified=drained, errors=errors,
            code='INVERSE_WORKER_EXITED' if drained else 'INVERSE_WORKER_PENDING'))
        for check in controller.cleanup_evidence:
            capsule.cleanup_evidence.append(check.model_copy(update={'resource_id': key + ':' + check.resource_id}))
        if drained:
            with capsule.work_lock:
                capsule.inverse_workers.pop(key, None)
        else:
            outcome = RollbackStepResult(ok=False, action=action,
                message='Inverse worker cleanup remains unverified.', error='INVERSE_CLEANUP_UNVERIFIED')
    return outcome
