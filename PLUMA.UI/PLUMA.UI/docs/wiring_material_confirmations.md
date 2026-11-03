# P16 material approval connection

The existing native dark `RiskApprovalDialog` is connected to P15's typed
confirmation contract. `MainWindow` owns one `ConfirmationController` and
`NativeConfirmationPresenter` for the window lifetime. The dashboard's command
entry is now connected by [P17's submission/STOP owner](wiring_command_submission.md).

## Delivery and ownership

- On the shell's loaded root, one serialized async loop queries pending
  confirmations every 250 ms. This is an explicit window-owned approval
  connection, separate from dashboard status refresh. It starts no model,
  microphone, capture loop, core process or system operation.
- Only one modal dialog is open at a time. Queries continue while it is open
  so STOP, task termination, expiry and changed/removed calls dismiss it.
- The exact task/call/binding and redacted material view are retained. After a
  user decision the controller reads pending state again, checks the same
  displayed material and expiry, and sends one typed decision. It never sends
  edited display text as tool arguments.
- A bounded set of displayed IDs prevents repeated dialogs/decisions. No
  approval is remembered for another call. Timeout/uncertain acknowledgement
  is not retried; task/history readback remains authoritative.
- Connection loss cancels the dialog, attempts a bounded logical disconnect,
  and retries with a fresh client UUID after one second. The broker retains
  exact ownership and expiry if delivery is unavailable. An old call cannot
  transfer approval to the new client.
- Window close cancels the loop and dialog, awaits them and sends a disconnect
  before disposing the shared IPC client. Dialog timers, registrations and
  async work are owned and disposed. A failure to contact the backend is not
  reported as completed backend cleanup; its own lease/task deadline denies
  unanswered work.

The existing independent STOP transport and backend latch/admission check are
unchanged. UI polling uses ordinary capacity; it cannot occupy the reserved
STOP slot. Backend policy still binds validated tool arguments and fails
closed without an exact current decision.

## Native presentation

The dialog shows the deterministic material-effect prompt and target summary,
tool/risk labels, and redacted arguments. Deny remains the default button.
Approve disables its button against duplicate invocation. Dismissal is denial;
programmatic cancellation produces no approval and disconnects the lease.

Argument field names are made readable, while literal values retain Unicode,
underscores, punctuation and internal whitespace. `PopupMessageText` has a
scoped `PreserveLiteralText` option for material/argument data; ordinary popup
copy retains its established formatter. Labels and raw execution identities
are not exchanged. The existing native theme, typography, fixed body width,
bounded wrapping and scrolling remain in use. Gallery-only plain argument
samples still render as literal text and cannot execute actions.

`LastFailure` contains fixed factual controller diagnostics, never raw server
exceptions or private arguments. P18 owns the broader visible result/error
notification connection. Closing an approval dialog never claims that an
operation succeeded or that its effects were undone.

## Acceptance and boundaries

`CoreIpc.Tests/ConfirmationControllerChecks.cs` covers approval, denial,
changed/stale views, expiry, STOP/removal, connection loss, window-lifetime
cancellation, presenter failure, duplicate suppression and uncertain writes.
Its native IPC checks run the actual policy/registry and verify ledger results.

`SurfaceControls.Tests/NativeConfirmationChecks.cs` uses only its own window,
dialogs, private credential, temporary Unicode-named file, authenticated Python
pipe and WAL ledger. It invokes real native Approve/Deny buttons and checks
STOP, expiry and lifetime close through the actual controller/presenter/backend.
Display strings alone are insufficient: terminal, action verification,
decision count, drained dialog/client and fixture executor-entry ownership are
also checked. No power/destructive operation is used as a demonstration.

Elevation remains the unchanged fixed one-operation broker. Fresh inert/owned
native tests cover dispatch, journal, admission and cleanup; the permitted
actual DNS-only UAC result is recorded separately in E59. No new UAC mutation,
administrator privilege or unrestricted shell is introduced by this bridge.

See [E85](../../../docs/completion/p16_material_approval.md) for exact source,
commands, results, hosted verification and remaining later-milestone limits.
