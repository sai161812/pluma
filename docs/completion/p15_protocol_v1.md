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
| `submit_text` | `text` (1–4096 characters, nonblank) | `submission_ack`: accepted/refused, task identity |
| `terminal_readback` | originating `request_id`, `task_id` | `terminal_readback`: pending/terminal, verification, persistence, residual facts |
| `stop` | optional `task_id` (otherwise global); optional `submission_request_id` only for global STOP | `stop_ack`: existing evidence-bearing `pluma.stop.v1` receipt |
| `settings_query` | none | `settings_snapshot`: allowlisted effective configuration |
| `history_query` | optional `task_id`, `limit` (1–100, default 25) | `history_reply`: recent tasks or one task with ordered actions; over-limit task history is refused |
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
visible event consumer; this protocol creates no fabricated UI activity.
