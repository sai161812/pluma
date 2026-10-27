# P17 dashboard command submission and priority STOP

`MainWindow` owns one `CommandController` and authenticated `CoreCommandClient`
across dashboard navigation. Enter and Run share the same submission method.
The existing native dark theme, controls and popup stack are retained.

## Admission and truthful results

- Verified core status enables entry. Before writing a command, the adapter
  requires the typed `submission_stop_fence` capability; legacy cores fail closed.
- The controller reserves one request identity before transport starts and blocks
  duplicate input until its outcome is resolved. Acknowledgement means admission,
  never execution success. Text still enters the shared resident request,
  TaskSupervisor, orchestrator, policy, registry, verification and ledger path.
- Readback retains the originating request/task identity. Only persisted,
  independently verified success displays Completed. Failure, missing verification,
  non-persisted terminal outcomes and residual effects have distinct factual states.
- Unknown writes are never replayed. Read-only history discovery and terminal
  reconciliation use the same request identity. An ambiguous/missing task remains
  blocked; Refresh checks again without another submission.
- Ordinary readback polls with a 250 ms delay between bounded transport calls.
  No model, capture, microphone or worker is started by opening the dashboard.

## Independent STOP and lifetime

- Stop requests global task cancellation using the reserved transport capacity.
  Its separately tracked operation runs independently of result observation,
  native dialog dispatch, cancellation layout and popup animation.
- The submission token is cancelled first. A pending submission's request ID is
  also sent as `submission_request_id`, fencing late admission after a lost reply.
  The resident orders this short fence against thread start without waiting for
  the ordinary submission/history lock. Backend STOP still latches before cleanup.
- At most 256 stopped request IDs are retained in memory. Durable terminal replay
  checks permit safe reclamation; saturation pauses new admission until core
  restart instead of evicting an unresolved stopped identity.
- A STOP receipt proves only the stated latch acknowledgement. Existing surface
  20 and dashboard copy distinguish pending cleanup from authoritative terminal
  readback; no animation implies successful rollback or worker absence.
- Navigation unsubscribes the page; the shell retains the command owner. Native
  view updates marshal to their captured dispatcher before accessing controls.
- Shell close cancels and drains observation, transport and approval leases
  before disposing the client. Closing the UI is not global STOP and never claims
  backend cancellation. Explicit Stop cancels accepted work.

The controller stores fixed factual status copy and correlation identities, not
tool arguments or generated narrative. Existing backend redaction, undo pre-state,
postconditions and ownership remain authoritative. Sample data is confined to
the explicit gallery preview; preview submission cannot execute commands.

## Evidence and boundaries

[E86](../../../docs/completion/p17_command_submission.md) records the fresh
authorized implementation, exact test commands, source/build identities and
recovery point. Native checks use owned windows, private credentials, temporary
files and a real SQLite WAL ledger. Routing/planner waits and lost replies are
explicitly injected fixtures; they do not establish native model/device behavior.
P18 owns the broader live feed/notification consumer. Voice, history/settings
surfaces and later physical, adversarial, performance and release gates retain
their assigned milestones. No automatic advancement or merge is authorized.
