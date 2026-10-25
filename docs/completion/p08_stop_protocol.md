# STOP receipt contract: pluma.stop.v1

P08, 2026-10-20. This defines the bounded backend STOP request/response payload.
It does not enable UI action entry or define P15 event subscriptions/reconnect.
Native dark UI, Windows message boundaries, per-user pipe restrictions, HMAC
challenge/proof/AUTH_OK, three-second client budget and 1 MiB transport bounds
are unchanged. A client disconnect/timeout does not abandon the cleanup owner.
[Implementation evidence](p08_evidence.md) identifies source and fixture limits.

## Requests

`{"command":"stop"}`, `{"command":"STOP"}` and `{"command":"stop_all"}`
select the supervisor's active nonterminal capsule snapshot. Every selected
latch is set before any cleanup/worker/grace/rollback starts. Requests preparing
across that global generation are rejected; new task admission stays closed
until that global cleanup owner exits. Empty selection is valid and proves
nothing about historical tasks. Completed/residual historical tasks are not
silently added to the active global snapshot.

`{"command":"stop_task","task_id":"<runtime ID>"}` selects one retained
capsule. ID must be a nonempty string containing a non-whitespace character,
at most 128 characters; it is not trimmed/reinterpreted. Invalid input is a
request error with no task/latch acknowledgement. A valid unknown/evicted ID
is a per-task TASK_NOT_FOUND error: runtime lookup is not a historical-ledger
query and does not assert that the task never existed.

Completed successes/failures/crash outcomes are observed without setting a new
STOP latch or rewriting their history. Repeated STOP shares an existing claim;
it never starts duplicate rollback. A client may explicitly repeat stop_task
to obtain a later snapshot for that retained ID. There is no automatic polling,
push API, event stream or receipt-to-future-completion promise introduced here.
P15 defines live events and complete cross-language version negotiation.

## Reply fields

The typed models live in `pluma/core/stop_protocol.py`. They reject unknown
fields, mistyped booleans, unknown outcomes/states and contradictory clean
STOP/count fields. The JSON payload contains:

| Field | Meaning |
|---|---|
| status | `ok` means a receipt was produced, including task pending/residual/error. `error` means invalid request input. Neither means clean cancellation. |
| stop_contract | Literal `pluma.stop.v1`; this versions only this STOP payload, not the whole transport. |
| message | Fixed human-readable copy: `STOP request processed.` or `A valid task ID is required.` Never infer task success from it. |
| error_code | Request error code or null. Per-task errors belong to tasks. |
| tasks | Strict per-task observations described below. |
| latch_acknowledged_count | Number of selected task latches observed set. Already-stopped tasks can contribute; unknown/uncancelled terminal tasks cannot. |
| stopped_count / stopped_tasks | Count/IDs of **verified clean stopped outcomes only**. They are derived and must agree with tasks. Candidates, pending, residual, failed, unknown and earlier successful tasks are excluded. |

Each task observation contains:

| Field | Meaning |
|---|---|
| task_id | Exact requested/selected runtime ID. |
| outcome | `pending`, `stopped`, `residual`, `error` or `terminal`. |
| latch_acknowledged | Actual cancellation token readback, not a transport success flag. |
| final_state | Actual supervisor state at observation, or null for unknown ID. Despite the compatibility name it can be STOPPING/ROLLING_BACK; completion_verified is required to treat it as terminal. |
| completion_verified | Terminal supervisor state **and** terminal-ready event observed. |
| terminal_persisted | True only after the supervisor's atomic history/journal write and readback. False is unverified persistence; null means unavailable/not established. |
| cleanup_in_progress | An active IPC cleanup owner or unfinished cleanup without a recorded exception is observed. False alone does not prove absence of owned tools/resources or successful cleanup. |
| cleanup_verified | Terminal cleanup evidence has no unresolved latest entries, no retained worker/job/snapshot/future/voice/persistent-job owner, and no active IPC cleanup for that task. This flag alone does not establish durable history. |
| has_residual | Unresolved cleanup/effect evidence, or retained terminal resource ownership. Irreversible commits remain residual. |
| rollback_performed / rollback_success | Existing deterministic supervisor evidence; nullable success is unknown/not attempted. No invented rollback promise. |
| cleanup_evidence | Detached, redacted typed cleanup entries, including identity and fixed errors. No raw exceptions, tool arguments, audio or credentials. |
| error_code | Fixed task error or null; no raw exception body. |

`stopped` requires actual STOPPED state, observed latch, terminal-ready,
terminal_persisted true, cleanup_verified true, no in-progress cleanup, no
residual/error, no failed rollback and no unresolved latest evidence. Only it
enters stopped_tasks. A terminal STOPPED_WITH_RESIDUAL or unresolved terminal
cleanup projects `residual`. A cleanup exception/start failure projects `error`
with the actual state and completion flags; unfinished cleanup is never a clean
STOP. A previously succeeded/crash-terminal task projects `terminal`; a failed
task projects `error` unless its unresolved cleanup already projects residual.

The resource/state lock is acquired without waiting when taking a receipt.
If another owner holds it, projection returns `pending`/EVIDENCE_BUSY and no
terminal/cleanup proof. A result is a point-in-time observation; later cleanup
can finish or fail. Clients must not convert a prior pending receipt to clean
success without a fresh verified outcome.

## Ownership and errors

IPC request_stop sets latches and claims through the existing supervisor
boundary, publishes one non-daemon StopOperation retaining its capsules before
thread startup, and runs the existing deterministic cleanup implementation.
The request waits at most 100 ms for that owner after publication, then returns
actual pending facts. This is a wait budget, not measured hardware p95 and not
a native driver termination deadline. Publication/start races retain the owner.
The snapshot never waits for resource/ledger locks to manufacture a result.

Completed cleanup owners are joined before removal. Capsules cannot be pruned
while that owner still holds them; runtime shutdown joins retained operations
before continuing task/outcome drain and closing storage. Hung device/rollback/
ledger work stays owned with an open store and pending/residual/error evidence.
No task worker can be force-killed beyond existing PLUMA ownership rules.

| Code | Meaning |
|---|---|
| INVALID_TASK_ID | Invalid targeted request, no fallback to global STOP. |
| TASK_NOT_FOUND | No retained runtime capsule for the requested ID. |
| EVIDENCE_BUSY | State/resource history could not be safely snapshotted without waiting. |
| STOP_CLEANUP_ERROR | Unexpected claim/cleanup failure; state is observed, not invented. Worker cleanup errors are recorded in the independent cleanup journal. |
| STOP_START_FAILED | Cleanup thread startup failed; latch/claim retained, no clean completion claimed. |
| TERMINAL_HISTORY_UNVERIFIED | Clean-looking terminal memory lacks verified persisted history. |
| TASK_FAILED | Actual FAILED outcome, not clean cancellation. |

Legacy internal stop_task/stop_all_active_tasks retain their synchronous return
contracts; candidate IDs returned by that internal global method are not a wire
success API. The IPC adapter no longer treats them as stopped_tasks. No native
framing/authentication change or credential repair is part of P08. Remaining
BA-09, combined P10 fixtures, real voice/model/device and UI/P15/P17 gates are
separate; no final acceptance limitation is waived.
