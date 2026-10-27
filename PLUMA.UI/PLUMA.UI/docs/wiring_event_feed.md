# P18 packet 1: factual live feed and task notices

This packet connects the committed P15 event journal to the dashboard live feed
and task-terminal notices (surface 24). It does not complete every P18 surface.
The broker remains bounded request/readback, not a push stream or heartbeat.

## Ownership and readback

MainWindow owns one EventFeedController loop under its existing window lifetime.
It starts only when the shell root is loaded, delays 250 ms between successful
polls and one second after failure, and drains before the shared IPC client is
disposed. It opens no model, capture, audio or execution worker. Each cycle has
a 30-second cancellation budget; transport requests retain their shorter bounds.
All calls use ordinary capacity; P17's separate STOP capacity remains reserved.

The consumer uses pages of at most 25 events. A forked cursor validates sequence
continuity before material readback. Events carry identities, not successful
outcomes: task-scoped history establishes correlation, then typed terminal
readback establishes persistence, verification and residual facts. No batch
cursor, partial display burst or notice is committed until every required
readback succeeds. Lost reads retain the cursor for retry; malformed/gapped
streams cause snapshot resynchronization in the owning loop.

Reset/stream change reads the 25 most recent task summaries and independent
outcomes. Historical snapshots replace stale state silently; they do not replay
old notices. Pending observations are rechecked, with fair rotation across
bounded batches. Persisted but unverified success gets at most three additional
readbacks to handle the race between ledger commit and cached verification.
If detailed proof remains unavailable, the display remains unverified.

## Display and notification semantics

Task bursts coalesce by task and are ordered by their latest event sequence.
The display holds at most 200 entries; observation/deduplication state holds at
most 512 task identities. Identities include stream/event and material outcome.
No command, transcript, arguments, result/error body or server-written message
is copied into this packet's display state or diagnostics. Copy consists of
fixed factual templates plus the actual task ID.

Completed requires persisted terminal SUCCEEDED, detailed completion verification
and no residual. Failure, STOP, missing persistence, unavailable verification and
remaining effects have separate messages. Material terminal updates replace the
same task's notice key. Unchanged/replayed facts do not repeat notices.

MainWindow routes notices through the existing native PopupStackHost using
surface 24. EventNoticePresentation constructs the shared ToastNotification;
severity reflects verified success, warning or informational evidence. Existing
class sizes, layout readiness, reading holds, newest-below ordering and taskbar
motion stay owned by the unchanged host. Dismissing a notice never issues STOP,
undo or any tool call.

The existing host can refuse a new card at its capacity. This packet does not
claim guaranteed toast delivery or add an unbounded queue; the bounded feed
retains its factual entry. Multi-surface burst arbitration remains P18 work.
Task-scoped history also retains P15's 100-action cap; unavailable/oversized
readback leaves the batch uncommitted and explicitly marks the connection stale.

Dashboard subscribes while loaded and restores the shell-owned buffer on return.
An observable collection is updated incrementally without forced scrolling or
rebinding on every poll. Empty polls do not publish unchanged views. The gallery
keeps explicit preview data; normal production navigation creates no samples.

## Remaining P18 work

Detailed task/step/route/tool/result/rollback projections, policy and perception
indicators, verified owned worker-termination feedback, and the remaining event
surfaces 4–9, 17, 19–23 need subsequent bounded packets. Where existing IPC lacks
required evidence, add a narrowly typed readback before presentation. A resource
event or dismissal never proves worker termination. Full event-driven desktop
host/backend acceptance across all surfaces remains part of P18, with physical
Windows/owner appearance acceptance still assigned to P25.

The next safe packet is typed action/state/cleanup evidence and its projection
contracts, then the affected remaining surfaces. Do not start P19 or merge.
See [E87](../../../docs/completion/p18_event_feed.md) for exact source, tests,
native-versus-fixture boundaries and recovery.
