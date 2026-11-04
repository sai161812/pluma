# P22 health, setup and recovery wire

The default shell still opens the existing Dashboard. Its Setup and Recovery
buttons attach the existing dark surfaces to one shell-owned HealthController.
No wizard fixture or gallery result changes production readiness. Historical
surface inventory notes saying these surfaces are unwired are superseded here
and by [E104](../../../docs/completion/e104_p22_completion.md).

## Authenticated messages

All requests use the existing current-user private named-pipe authentication,
protocol_version=1 and canonical request UUID. Unknown fields, null material,
boolean integers, malformed identities and stale targets are rejected.

- health_query: read only. Returns exact instance UUID, PID, creation time,
  current host state/code, can_restart, config fingerprint, five capability
  receipts, hotkey evidence, native_verified, setup_ready and recovered-task count.
- setup_check: exact current instance_id and explicit include_microphone bool.
  Returns the ordinary submission acknowledgement/task identity. It executes
  registered READ check_setup, never an arbitrary command. No consent means
  MICROPHONE_CONSENT_REQUIRED; unavailable libraries/models are FAILED.
- core_restart: exact instance_id, pid and creation_time. Returns the ordinary
  submission acknowledgement. Registered MEDIUM restart_core requires the exact
  existing material-confirmation contract. It queues only its owned graph's
  restart, after terminal verification, then drains all owned work before replacement.

The capsule's nonserialized health_authorization binds the tool and arguments
only at the trusted selected typed-plan boundary. Ordinary planner/routine
output cannot manufacture microphone consent or restart authorization.
Mutation requests are not automatically replayed after uncertain writes.
Setup and recovery share the CommandController request fence and priority STOP.
Restart's saved result proves queued intent only, not successful recovery.
The supervisor's global STOP generation also fences queued replacement after
the intent task becomes terminal. STOP before replacement withdraws that queue;
it does not rewrite a completed task into a fabricated STOP outcome.

## Real capabilities and freshness

Explicit setup uses a process-owned 30-second budget and verified worker/Job
absence. It opens the configured local llama.cpp GGUF in vocabulary-only mode,
opens/releases the local whisper.cpp model, opens local PaddleOCR ONNX sessions,
reads the native UIA root and, only with consent, opens/starts/closes the microphone.
It does not perform inference, enumerate personal UI, download models, save
screenshots or retain audio samples. Errors expose bounded codes, not exception
strings, model paths, device contents or sensitive arguments. Hotkey proof comes
from the actual live registration owner, not configured chord strings.

Model imports occur only in the setup worker, never at shell/resident startup.
A successful check task means observations completed, not all capabilities passed.
Continue needs all five PASSED native receipts, actual hotkeys and a READY Core,
matching current config fingerprint, verified worker absence and fresh identity.
Core proof expires in 60 seconds; UI proof in 45 seconds. Duplicate submissions
cannot renew age. Continue re-reads authenticated health. Runtime disconnect,
not-ready or instance changes invalidate proof using the existing observer.
There is no extra background health poller. Explicit reads are bounded to three
seconds with limited pre-write busy retries; recovery waits at most 20 seconds
for new-instance health. Timeout/disconnect never means successful recovery.

## Ownership and recovery

CoreHost holds exclusive profile and endpoint leases before opening/reconciling
storage. Different profiles cannot create duplicate owners of the same endpoint.
The control host retains authenticated IPC while it replaces only its own
runtime graph. Its PID/creation time stay fixed and graph UUID changes. This is
an owned runtime restart, not process respawning. There is no arbitrary kill or
spawn API. Dead/unverified hosts require manual startup; Recovery is disabled.
Every authenticated health handler enters the current graph's existing drain
gate. Storage cannot close underneath a retained health read or submission.

Configuration or hotkey failures leave a control-only graph: normal execution
and setup remain blocked. Safe settings read/recovery, confirmations, history
and STOP remain available. No default source is written over corrupt settings.
Startup reconciles stale tasks before readiness; no previous PID is killed from
unverified persisted identity. Unexpected hotkey loss drains before publishing
new control identity and discards references to the old supervisor's queued work.

The recovery dialog yields its modal root to the existing material-approval
dialog. The Dashboard continues to show factual status; failed recovery reopens
the critical dialog. Same-PID/creation-time, new-instance authenticated READY and
live hotkeys are required before reporting verified recovery. Setup proof must
be reacquired. Close cancels and joins health operations, approval/recovery dialogs
and existing shell observers before disposing the IPC client.
If drain interrupted terminal readback, the shell reconciles the original
request/task from the new graph's persisted history before releasing pending
command ownership. It never resubmits restart or invents detailed verification
that is unavailable after graph replacement.

Native access checks establish availability only. They are not model accuracy,
installed reboot/recovery, physical appearance or microphone boundary-timing
acceptance. E104 and the matrix retain those separately owned gates and failures.
