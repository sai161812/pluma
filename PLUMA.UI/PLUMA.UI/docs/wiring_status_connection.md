# Wiring step 1: authenticated read-only core status

Owner authorized wiring on `ui-wiring` on 2026-10-19. The first bounded step
connects dashboard health to the existing resident status command. It does not
execute a command, start the resident core, activate the microphone or load a
model. This is not completion of all wiring, the backend audit or Phase 14.

The pushed recovery tag `pre-ui-wiring-2026-10-19` identifies pre-wiring source
`04bc1fb`. See [recovery commands](wiring_recovery.md) for a separate checkout
that preserves all subsequent work. [Draft PR 2](https://github.com/sai161812/pluma/pull/2)
targets `ui-polish-integration`; PR 1 and `main` remain unmerged/unchanged.

## Implemented behavior and files

- `CoreIpcClient.cs`: a read-only adapter using the per-user local Windows pipe,
  same-user/elevation restriction and the existing 32-byte HMAC-SHA256 challenge,
  proof and `AUTH_OK` acknowledgement. It reads the existing credential only,
  validates its actual opened-handle owner/ACL and never creates or repairs
  production credentials. User, SYSTEM and Administrators are the only allowed
  credential-file allow-rule identities; the owner must be the current user.
  Secret/proof buffers are cleared and are never logged or sent as a secret.
- Python's Windows `PipeConnection` uses native message boundaries. Each proof
  or JSON request is one native pipe message; no TCP length prefix or
  newline-delimited/JSON-RPC protocol is invented. The backend source is unchanged.
- `CoreStatus.cs`: typed status/result projection. Missing, mistyped, negative,
  duplicate, malformed or oversized fields cannot imply connected state. Only
  supplied running/active-count/voice flags are accepted; a reachable stopped
  core is displayed as stopped. Error copy is fixed human-readable text, never
  an unredacted exception, credential or server-supplied narrative.
- Requests have a three-second budget and a 1 MiB response bound, matching the
  backend's maximum payload. The client admits at most four concurrent checks.
  Cancellation interrupts pipe I/O; disposal cancels and awaits admitted work.
- `DashboardPage.xaml/.cs` and `MainWindow.xaml.cs`: one owned status query on
  normal dashboard load and an explicit native Refresh button. No heartbeat,
  polling, automatic core startup or untracked retry runs. The label describes
  a point-in-time check; its tooltip/accessibility help includes the check time
  and asks the user to refresh for current status. Failure clears prior connected
  and active-count display. Navigation/window close cancels owned checks.
- Production dashboard starts disconnected with empty activity/history/message
  lists and an unavailable route. Command input remains disabled until its real
  submission/STOP wiring is implemented. `SurfaceGalleryWindow.xaml.cs` invokes
  explicit dashboard fixture data; the gallery never attaches a core client.
- The existing dark brushes, typography, popup geometry and notification classes
  are retained. A native icon button supplies the necessary explicit refresh.
  Its two-row layout keeps the health value aligned with adjacent card values;
  a native control assertion verifies their vertical positions within one pixel.

## Verification

`CoreIpc.Tests` links the actual transport/projection source into a Windows
console runner. Its native fixtures use uniquely named owned pipes, private
test-owned credentials and bounded cleanup. A separately tracked Python fixture
uses the production `IpcServer` with authentication enabled and a status-only
handler. It never starts `ResidentCore` or tools. Fixture startup rejects loaded
torch/Whisper/llama.cpp/PaddleOCR modules; fixture keys are removed after use.
Explicit fixture-file ownership keeps the test deterministic on elevated CI
hosts without weakening production credential checks or changing Windows policy.

Local commands, Windows 11 / SDK 10.0.401 / .NET 8 target:

```powershell
dotnet run --project PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj -p:UseSharedCompilation=false
# 37 IPC checks passed; includes two real Python-server/C#-client round trips.

dotnet run --project PLUMA.UI/PopupStack.Tests/PopupStack.Tests.csproj --verbosity quiet -p:UseSharedCompilation=false
# 64,537 checks passed across 5,000 scenarios.
dotnet run --project PLUMA.UI/SurfaceContracts.Tests/SurfaceContracts.Tests.csproj --verbosity quiet -p:UseSharedCompilation=false
# 30 checks passed.
dotnet run --project PLUMA.UI/AudioVisualizer.Tests/AudioVisualizer.Tests.csproj --verbosity quiet -p:UseSharedCompilation=false
# 15 checks passed.
./PLUMA.UI/check-surface-copy.ps1
# PASS 33 compiled XAML files.

dotnet build PLUMA.UI/PLUMA.UI/PLUMA.UI.csproj -p:Platform=x64 -p:SurfaceGalleryPreview=true -p:OutDir=D:\Workspace\DEVEL\PLUMA-ui-wiring\output\wiring-preview\ -p:UseSharedCompilation=false -nr:false -v:minimal
dotnet build PLUMA.UI/SurfaceControls.Tests/SurfaceControls.Tests.csproj -p:Platform=x64 -p:UseSharedCompilation=false -nr:false -v:minimal
# Both builds: 0 warnings, 0 errors.
```

The IPC checks cover actual Python compatibility, multi-buffer native messages,
strict field types/duplicates, wrong secret/challenge/acknowledgement, broad key
permissions, unavailable server/credential, deadlines, caller cancellation,
concurrency, owned disposal and reconnect without cached health. No production
credential, task, UI window or resident instance is used by these tests.

The expanded native control suite checks default dashboard state, supplied
status/count projection, absence of polling, stale-state removal on timeout,
explicit reconnect and navigation cancellation. `verify-ui.ps1` now runs the
IPC suite and requires its pass footer before native popup/gallery/control
acceptance. The workflow installs Python 3.12 and the existing lightweight core
dependencies for the isolated fixture. No inference extras are installed.

Initial [hosted wiring run 10](https://github.com/sai161812/pluma/actions/runs/39240895888)
passed against source `2837939` (PR merge `a175e61`): 37 IPC checks, 661 native
popup checks, 195 formatting checks and 41 native control checks, with both
builds at zero warnings/errors. It exported 58 PNGs. Render review then found
the refresh button lowered the health value; `953f737` corrected that layout
and added the seventh dashboard assertion, bringing required control checks
to 42. Run 10 is evidence for the preceding source, not the later alignment fix.

[Run 11](https://github.com/sai161812/pluma/actions/runs/39241747830) passed IPC,
builds and popup checks but failed the surface 9 scroll-to-last-line audit.
That audit sampled asynchronous native `ChangeView` after a fixed 30 ms.
`SurfaceGalleryAudit.cs` now awaits actual native offset readback for up to two
seconds, retaining the same one-pixel end-position assertion and recording
offset/extent/wait diagnostics. Popup production code and thresholds are unchanged.
The complete pipeline must still pass; a retry or successful build is not a substitute.

The final current-head result and artifact link are recorded in
[PR 2](https://github.com/sai161812/pluma/pull/2), whose Windows UI verification
check must pass with 37 IPC, 661 popup, 195 formatting and 42 control checks,
alongside the pure checks and 58 render exports. This keeps the evidence tied
to the actual PR head instead of treating an earlier run as final verification.

Local Application Control still blocks the rebuilt unsigned WinUI executable;
no policy or alternative execution host is used to bypass that restriction.
The console IPC tests run through their normal .NET test-project command.

## Next bounded work

Text submission and priority STOP through the same TaskSupervisor pipeline are
next. They need separate owned cancellation/control requests so a long execute
response cannot block STOP or the WinUI dispatcher. Then define/test live typed
events before task/step/tool/voice projections. History/settings/confirmations,
remaining production fixtures, physical Windows 11 review and full end-to-end
acceptance remain open. Do not infer verified tool success from an IPC `ok`.
