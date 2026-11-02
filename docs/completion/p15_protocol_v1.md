# P15 version 1 local UI/core contract

This contract is implemented by `ipc_contracts.py`, `ResidentCore`,
`IpcConfirmationBroker`, `ActivityQuery`, and the C# `CoreRequestProtocol` and
`CoreIpcClient`. It uses the existing same-user Windows message-mode pipe and
HMAC challenge/response. Each authenticated connection carries one request and
one reply. It is bounded JSON, not JSON-RPC. No heartbeat, push subscription or
automatic background polling is started by the transport itself. P16's
[window-owned approval connection](../../PLUMA.UI/PLUMA.UI/docs/wiring_material_confirmations.md)
explicitly queries while the shell is open and disposes its lifetime on close.

## Common rules

- Every request has integer `protocol_version: 1`, a defined `message_type`
  and canonical lowercase UUID `request_id`. Task/client/confirmation/stream
  identities use the same UUID format. Unknown/extra fields and wrong types
  are refused. Duplicate JSON properties at any depth and non-standard
  `NaN`/`Infinity` tokens are refused before dispatch.
- Messages have the existing 1 MiB native byte cap. C# typed JSON has depth 8.
  Requests have bounded transport deadlines and owned cancellation/disposal.
- Four ordinary C# calls leave a separate STOP call slot. Python retains its
  tested 31 ordinary handler slots plus reserved STOP dispatch capacity.
- Submissions and decisions are sent once. A timeout/cancellation after a
  write is `OutcomeUnknown`; never replay a side effect automatically.
  Read terminal/history/pending state before a new explicit decision.
- A transport acknowledgement never proves tool success or completed cleanup.
  Terminal readback and factual ledger verification remain authoritative.

## Message catalog

| Request | Additional fields | Reply |
| --- | --- | --- |
| `action_detail_query` | `task_id`, positive Int64 `action_id` | `action_detail`: exact task/request/action/tool identity and nullable bounded redacted factual message, error code and matched-policy reason (P18 E90) |
| `submit_text` | `text` (1–4096 characters, nonblank) | `submission_ack`: accepted/refused, task identity |
| `terminal_readback` | originating `request_id`, `task_id` | `terminal_readback`: pending/terminal, verification, persistence, residual facts |
| `stop` | optional `task_id` (otherwise global); optional `submission_request_id` only for global STOP | `stop_ack`: existing evidence-bearing `pluma.stop.v1` receipt |
| `settings_query` | none | `settings_snapshot`: allowlisted effective configuration |
| `history_query` | optional `task_id`, `limit` (1–100, default 25) | `history_reply`: recent tasks or one task with ordered actions; over-limit task history is refused |
| `activity_query` | required `task_id`, `after_action_id` (nonnegative Int64, default 0), `limit` (1–100, default 25) | `activity_page`: scoped saved state/route, minimal action/undo facts, continuation and optional validated cleanup summary |
| `confirmation_query` | `client_id` | `confirmation_list`: client identity and its pending material operations |
| `confirmation_decision` | `client_id`, `task_id`, `confirmation_id`, `binding`, boolean `approved` | `confirmation_ack`: accepted decision or concrete refusal; approval is nullable on refusal |
| `confirmation_disconnect` | `client_id` | `confirmation_disconnected`: count of pending calls denied during disconnect/pruning |
| `events_query` | optional `stream_id`, `after_sequence` (nonnegative Int64, default 0), `limit` (1–100) | `event_batch`: stream identity, retained bounds, cursor, reset/continuation flags, ordered events |

The wire models are the exact field/type definitions. A fixed
`protocol_error` is returned for invalid/unavailable requests without exposing
raw exceptions or sensitive arguments. The existing legacy envelopes remain
supported; new clients use the versioned catalog.

## Submission STOP fence

P17 adds a canonical `submission_request_id` fence to global STOP. It refuses
late admission of that exact originating request, independently of ordinary
submission/history I/O. Stopped IDs are bounded to 256; unresolved saturation
pauses admission until restart instead of evicting a cancellation. Durable
terminal replay checks permit safe reclamation. Settings advertise
`submission_stop_fence: true` only on a supporting resident; the C# dashboard
adapter refuses submission when it is absent/false. Existing clients may omit
the optional field. A fence cannot be combined with task-scoped STOP. See
[P17 E86](p17_command_submission.md) for admission-race and native UI evidence.

## P18 activity evidence extension

`activity_query` reads task/action/cleanup facts from one bounded SQLite SELECT.
It omits commands, transcripts, arguments, result/error bodies, inverse recipes
and resource/process identities. A page carries exact task/request correlation,
at most the requested number of actions in increasing action-ID order, the last
returned ID (or unchanged request cursor when empty), and `has_more` from one
extra row. This is row enumeration, not the journal change cursor. Pages are
individual snapshots: re-read on action/rollback changes; do not assume one
immutable snapshot across multiple calls.

Verification, recorded issues, explicit policy denial, undo availability and
rollback attempt/result are distinct flags. A saved state does not establish
live execution, and an issue can be pending mutation evidence. Optional cleanup
summary is recomputed from latest validated persisted checks; no report is null,
not proof of complete cleanup. Contradictory/corrupt/oversized reports refuse.
No worker-terminated claim is exposed. See [E88](p18_activity_evidence.md).

## P18 action presentation extension

P18 E90 adds scoped `action_detail_query` / `action_detail`, without adding fields
to the strict E88 activity-page wire record. Presentation is separate local UI
state. Both text fields are limited to 1,024 UTF-8 bytes after complete-value
redaction; error codes are uppercase ASCII identifiers of at most 64 characters, with
secret-shaped values withheld.
Historical missing values remain null; malformed/contradictory data refuses.
The query selects no private result/error body or inverse recipe and is read-only.
New UI detail bindings require the paired core endpoint; an older core refuses
the new query, leaving the consumer explicitly unavailable rather than fabricating
detail. See [E90](p18_action_details.md) for source-specific evidence and scope.

## Material confirmation lifetime


An explicit `confirmation_query` opens/renews a logical client lease for 30
seconds, bounded to 16 clients. It is independent of the short-lived pipe
connection. With no active client, policy retains `REQUIRE_CONFIRMATION` and
does not execute a HIGH/material operation. The normal unwired UI therefore
does not leave approval workers waiting at startup.

Each validated policy call gets a fresh `confirmation_id` and salted SHA-256
binding over the task, tool, exact arguments, risk and material prompt. This ID
is the identity of that particular call occurrence. The first client to read
the operation claims delivery; another client cannot approve it. The view
contains redacted arguments, factual material prompt/target, risk and expiry.
Clipboard arguments/summary are never exposed. Views are limited to 16 KiB,
with at most 32 pending calls.

A decision must match the delivery client, task, call identity and binding.
It is consumed atomically once; repeats, changed bindings, stale/unknown calls
and wrong identities refuse. An accepted denial is distinct from an invalid
decision. No session-wide approval is remembered. The original argument
snapshot and task cancellation are checked again before policy can allow the
call; the registry's existing STOP admission check still precedes execution.

Explicit disconnect, lease loss, STOP, task retirement, runtime shutdown or
the absolute confirmation deadline deny pending work. Waits last at most 30
seconds and remain inside the registry's shorter ToolSpec budget/cancellation
tree. The broker creates no worker or timer. Unanswered calls are never
approved. Restart loses pending confirmations; old decisions cannot revive
them. Native approval-dialog interaction is connected and verified in
[P16 E85](p16_material_approval.md).

## Factual event projection and reconnect

Migration 0005 writes events in the same SQLite transaction as the actual
ledger change. It retains the last 512 events and one durable stream UUID.
There is one global increasing sequence, ordered by the controlled writer;
rolled-back transactions leave no event. Bounds and the requested page are
read in one SQLite snapshot. There is no per-client queue or subscription.

| Event kind | Committed source | `record_id` |
| --- | --- | --- |
| `task_recorded`, `task_changed` | task insert/material field update | null; use task identity |
| `action_recorded`, `action_changed` | action insert/result-verification update | action row ID |
| `rollback_changed` | undo availability/rollback status insert or change | action row ID |
| `cleanup_recorded` | cleanup report | null; use task identity |
| `resource_changed` | resource insert/release | null; use task identity |
| `screen_recorded` | minimal screen-event metadata | screen-event row ID |

Each event contains only sequence, kind, UTC timestamp, task/request identities
and optional record ID. These are committed change facts, not completion
messages: an action record may be pre-mutation intent. Consumers fetch typed
history/terminal state before displaying verification, success or cleanup.
No command/transcript, arguments, result body, screen labels, external resource
identity, undo recipe or model reasoning is copied into the event buffer.

Start with `events_query` without a stream ID and cursor zero. The reply asks
for reset and supplies the current stream/high cursor. Read history/terminal
and pending-confirmation snapshots, then poll from that cursor. Changes during
snapshot readback remain available as later events; applying a snapshot again
is safe. Calls are serialized per consumer cursor.

For a matching stream and retained cursor, events are strictly increasing
after that cursor. `next_sequence` is the delivered tail, and `has_more` means
another bounded page is available. Repeating a cursor replays the same retained
immutable facts. `CoreEventCursor` ignores already-consumed sequences and
refuses a gap without partly changing its cursor.

Overflow, an impossible future cursor or a different database stream returns
`reset_required`, no events and the current high cursor. The C# cursor requires
fresh snapshots before accepting more events. A normal core restart preserves
the database stream and retained replay; replacement/restoration may require
reset. Disconnected consumers do not block execution or STOP. P18 owns the
remaining detailed event consumer. P18 E87 connects the bounded task feed and terminal notice bridge using independent readback; this protocol creates no fabricated UI activity.

## P18 live readback extensions (E91)

Both queries are authenticated read-only v1 requests with strict fields and a
canonical UUID `request_id`. They are observation APIs, never tool admission.

- `runtime_query`: no further arguments. `runtime_snapshot` returns the same
  request identity, up to 256 unique active `tasks` and the latest 256 retained
  identity-bound `terminations`. A busy/invalid snapshot returns fixed
  `RUNTIME_UNAVAILABLE`, not an empty successful snapshot.
- Each task contains `task_id`, `task_request_id`, active `state`, `elapsed_ms`,
  `plan_revision`, nullable `step`/`total`, `tool`/`risk`/`phase`,
  `tool_elapsed_ms`, redacted `arguments` (at most 1024 UTF-8 bytes), and nullable
  `rollback_step`/`rollback_total`/`rollback_recipe`. All fields must be present.
  States are CREATED/RUNNING/STOPPING/ROLLING_BACK. Phases distinguish DISPATCHING,
  EXECUTING, VERIFYING and RECORDING. Only observed executor entry provides
  EXECUTING and an elapsed value. Replanning starts a new validated revision;
  counts do not invent total future replans or completed inverses.
- A termination contains exact `task_id`, `task_request_id`, positive `pid` and
  `creation_time`, actual integer `exit_code`, and `command_class=tool_worker`.
  It is derived only from verified PLUMA-owned process-absence evidence.
  Initial connection seeds historical proofs silently; later unseen identities
  emit once, retaining a bounded 512-key reconnect cache. This is not a durable
  notification delivery guarantee; saved cleanup is authoritative.
- `action_verification_query`: exact `task_id` and positive `action_id`, with
  the same scoping rules as E90 detail. `action_verification` includes query and
  task/request identity, action/tool identity and nullable `verified`, `method`,
  `detail`. These last fields are all present or all null. Method is a bounded
  ASCII identifier, detail is redacted before the 1024-byte UTF-8 limit. Saved
  proof must agree with the saved verification flag. Missing legacy proof is
  unavailable; corruption/contradiction returns `VERIFICATION_UNAVAILABLE`.

Existing E88 activity and E90 detail DTOs are unchanged. The consumer commits
neither cursor nor callbacks before scoped proof readback succeeds. A runtime
snapshot cannot prove terminal success, undo completion or worker/model health.

## P19 internal recognition boundary (E92)

[E92](p19_recognition_segments.md) adds task-owned, bounded native STT segment
snapshots inside the backend. It adds no public v1 query, durable event or C# DTO.
Decoded RECOGNIZED text is not request commitment. Recognition previews must
remain transient and must not enter Activity/history or act as an execution API.
Typed lifecycle/readback, reconnect/reset and overlay integration remain P19 work.

## P19 transient voice readback (E93)

[E93](p19_voice_lifecycle.md) adds `voice_query` and `voice_snapshot`. This
supersedes E92's absence of a public voice query; overlay wiring remains open.

- Query: v1 envelope, canonical `request_id`, optional nullable `stream_id` and
  `voice_id`. A voice ID requires its stream. No audio, command or action fields.
- Reply: `request_id`, resident `stream_id`, `reset_required`, nullable `voice`.
  A different stream/generation or expired generation requires replacement of
  the prior view. Reconnect reads current state, never historical speech replay.
- Voice: `voice_id`, `task_id`, nullable `task_request_id`, `phase`, nullable
  `code`, nullable `capture_active`/`boundary_complete`, nullable `recognition_id`,
  integer `recognition_sequence` (0-128), and UTF-8 bounded `text` (16384 bytes).
  Every reply field must be present. Unknown fields/inconsistent facts fail.
- Phases: STARTING/LISTENING/DECODING/COMMITTED/CLARIFICATION/EMPTY/ERROR/CANCELLED/
  TIMED_OUT. Request identity exists only for COMMITTED, after real same-capsule
  orchestrator admission. It is not successful execution or verification.
  Text is permitted only during DECODING or COMMITTED and is redacted first.
- Capture metadata is only present in LISTENING and is read atomically from
  actual capture. A speech boundary is not a timeout. ERROR codes are limited
  to CAPTURE_DENIED/CAPTURE_UNAVAILABLE/VOICE_FAILED; CLARIFICATION uses
  LOW_CONFIDENCE_MATERIAL_TARGET and includes no transcript or guessed target.
- STOP/deadline clear active previews; failures cannot revive. Terminal views
  expire after 30 monotonic seconds, checked lazily on read. One latest voice
  reference is retained; no timer, model, capture or subscriber is started by
  queries. Busy/inconsistent reads return VOICE_UNAVAILABLE without old content.

Consumers must own/serialize reads, check query correlation, reset/clear old
state on null/failure/reset and cancel their lifetime on shutdown. Recognition
preview is not durable Activity/history/feed data or an execution API. Measured
waveform/silence-progress telemetry and actual overlay consumer remain later
P19 work; no synthetic waveform or countdown is authorized by this contract.

## P19 measured voice overlay binding (E94)

[E94](p19_overlay_acceptance.md) closes E93's remaining overlay/measurement work.
The unreleased P19 voice view adds nullable `meter`, emitted on every current
reply and accepted only in LISTENING. Its fields are `amplitude`, 32 `bands`,
`speech_active`, `silence_progress` and nonnegative `sample_sequence`. Levels
and progress must be finite 0..1 values. Unknown/inconsistent fields fail closed.
Current UI/core must use this matching P19 schema; older strict consumers reject
the extension instead of interpreting absent telemetry as measured values.

Capture copies one 1024-sample window and detector counters under a bounded lock,
then analyzes outside it. PCM never enters IPC. Silence progress comes from
actual frames after sufficient speech; reading/waiting cannot advance it. The
consumer refreshes spectrum freshness only when the sample sequence changes.
Outside capture, meter is null. No synthetic amplitude or countdown is used.

One shell-owned serialized observer starts after the initial dashboard status
read, preserving the four normal/one STOP slots. It owns cancellation, rejects
wrong correlation, regressing phases/sequences or changed ownership, clears on
failure and joins on close. One `voice` popup updates the same reader; generation
changes reset its viewport, earlier reading is preserved and only a reader at
the tail follows new speech. Actual admitted final text and the received banner
remain separate from task verification/success. P25 owns the explicitly approved
physical boundary-timing retest limitation; it is not a protocol pass or waiver.

## P20 bounded saved-task browsing (E95)

[E95](p20_saved_history.md) adds an independent read-only query; the original
`history_query` contract is unchanged. This endpoint cannot admit tools or undo.

- `history_page_query`: v1 envelope, canonical `request_id`, literal `search`
  (default empty, at most 256 Unicode characters), nullable canonical
  `before_task_id`, and `limit` (default 20, range 1-20). Extra fields fail.
- `history_page`: correlated `request_id`/`before_task_id`, `tasks` (at most 20),
  `has_more` and nullable `next_before_task_id`. Continuation is exactly the last
  returned task identity when more records exist. No guessed count is returned.
- Each task has `task_id`, `request_id`, `input_mode`, nullable `command_text`,
  `created_at`, nullable `started_at`/`completed_at`, nullable `final_state`,
  `route`, `stop_reason` and `error_code`. Every field must be present. Commands
  are canonically redacted before search/display and bounded to 8192 UTF-8 bytes;
  oversized whole values are unavailable, never exposed prefixes. Unknown legacy
  flags/codes are withheld. Timestamps require offsets; corrupt facts fail closed.
- A separate read-only SQLite snapshot anchors the cursor and page in descending
  stored `created_at`/`task_id` order. Literal casefold substring search covers
  redacted command, task identity, state, route and input mode. Wildcards/SQL
  syntax remain literal. No original transcript, action body or undo recipe is
  fetched. A 250 ms VM deadline and 50 ms lock timeout bound database work.
- Missing cursors return `HISTORY_CURSOR_UNAVAILABLE`; unavailable/corrupt
  storage returns `HISTORY_UNAVAILABLE`, never an invented empty page. Refresh
  restarts from newest; new inserts do not repeat records on an older page.
- The shell owns one read, a three-second linked deadline and at most two Busy
  retries. Only validated pages replace prior rows/cursors. Failure clears stale
  data; shell close cancels/joins. This is a bounded saved-task browser, not the
  remaining P20 detail/undo/conflict contract or a live event stream.
