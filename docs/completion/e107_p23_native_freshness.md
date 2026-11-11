# E107 - P23 packet 2: native presentation freshness boundary

P23 remains in progress. This bounded packet implements a read-only native
probe and revocable presentation lease; it does not enable surfaces 15/16.
P24 is ineligible. Base 3e4a03e, recovery/pre-p23-e107-20261104 pushed at that
source. E106's completed checks are now recorded by e9b263e. Main is unchanged.

The correct repository D:/Workspace/DEVEL/PLUMA was clean and matched the pushed
P23 checkpoint. A different IDE folder did not modify this checkout. Master
blob remains 01b693dbf898b662aa4cd67736c1a0e8a21cf3e3. The unchanged master,
shared contract, current handoff, build phase 14, E-01..10 and approved target
placement contracts were reused/refreshed before editing. Fresh prerequisites:
54 pass, no skips/xfails.

## Implementation and safety

See the [wire/freshness contract](../../PLUMA.UI/PLUMA.UI/docs/wiring_perception_feedback.md).
NativePerceptionTarget reads only an explicit target's current native identity,
caption hash, geometry, monitor, DPI, visibility and foreground status. It closes
its own query-only process handle and restores thread DPI context. It performs
no activation, capture, process launch, hook, app command or termination.

PerceptionPresentation requires strict actual observation metadata, the original
RUNNING task/request, connected ready runtime, priority STOP clear and fresh
native facts. Missing/ambiguous matches cannot create a lease. Any target/task/
STOP/disconnect/expiry change permanently revokes it. Original wall and monotonic
deadlines include native probe duration; repeats do not renew the lifetime.
ROI subtraction and negative desktop origins remain exact. This is presentation
eligibility only and never action authority or success evidence.

An initial native fixture exposed a mismatch in the new probe: forcing physical
DPI awareness read 225/200/750/500 while the backend's target-native window_dpi
contract reported 180/160/600/400. Existing backend behavior was correct for its
contract and was not changed. The probe now matches target awareness. Legacy
coordinates are identified and refused by the lease until the native host has
explicit conversion evidence. No ratio, assertion tolerance or fake success was
introduced. Initial failed native report is retained.

Same-process targets are refused because caption reads would synchronously
message the UI thread. This and legacy coordinate conversion remain host scope,
not an owner waiver. No XAML, dependency, master or personal desktop change.

## Evidence

Fresh ignored root: output/p23-e107-20261104-201225-d5ffdbf3/.

- Declared E98 test-env/Scripts/python.exe run_checks.py prerequisites:
  test_p23_perception_readback, test_p18_runtime, test_screen_control_catalog;
  54 pass (19.75s pytest), base 3e4a03e.
- dotnet build PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj -c Release --nologo:
  zero warnings/errors; corrected build 5.24s.
- PLUMA_TEST_PYTHON=<declared E98 interpreter> dotnet
  PLUMA.UI/CoreIpc.Tests/bin/Release/net8.0-windows/CoreIpc.Tests.dll:
  corrected local integration 393 checks pass. Includes 37 new deterministic
  lease checks; these are not native rendering/physical acceptance.
- run_checks.py native-target-final tests/windows/test_p23_native_presentation_probe.py
  -p tests.fixtures.desktop_isolation: 1 pass. Real query-only C# native reads
  match owned isolated Python window HWND/PID/creation/class/title hash/DPI and
  target-native bounds; owned movement/caption changes read back; hiding the
  owned HWND returns no target. No foreground activation or personal resource
  changes. Fixture teardown owns and verifies its process/window cleanup.
- E106's 1,118 required Python regressions remain applicable: no production
  Python/backend changes in E107. No need to repeat unrelated unchanged gates.

Exact source **a41e280ac4291f2be1ff2fc55298e1f90e99f598** passes the
committed-source owned native probe (1 pass, 2.084s pytest), with a zero-warning/
error Release rebuild (1.99s). Local test DLL SHA256:
1D4F05E3AD8A793B5BAD9F6A3D5D0F909CB8DF932E8FBC1367A0B96F3BB1B454.
An affected P20 folder/undo selection also passes 23 checks (15.873s pytest),
no skips/xfails, after the native gate failure described below.

Windows exact-source evidence (same unchanged source, normal full gate):

- [Run 41852074824](https://github.com/sai161812/pluma/actions/runs/41852074824): **failed**, stage native-controls. 393 IPC checks passed. No production resident, microphone or personal desktop actions were started. 663 native popup checks passed. 195 formatting checks passed. No backend or microphone was started. Error: native-controls failed with exit code 1. Artifact 13334739213, SHA256 ba75e46e300190f5148a35a3acd26da6b43c4cb3005722b0568286bb605290ec (verified against GitHub digest). Test executable SHA256 8E754AC34826D36884228A7171E4AFA97292D8642A464B4EA0551D72FEBA2B3A; NotSigned.

- [Run 41853104578](https://github.com/sai161812/pluma/actions/runs/41853104578): **passed**, stage complete. 393 IPC checks passed. No production resident, microphone or personal desktop actions were started. 663 native popup checks passed. 195 formatting checks passed. No backend or microphone was started. 237 UI checks passed. 15 UI checks passed. Artifact 13336751115, SHA256 da2b481d2738f588d72920a01adb647ec3d881836981df5199e47f8567eceaa3 (verified against GitHub digest). Test executable SHA256 8E754AC34826D36884228A7171E4AFA97292D8642A464B4EA0551D72FEBA2B3A; NotSigned.

The first native run times out at NativeP20UndoChecks.cs:115 waiting six seconds
for the existing conflict Open folder command to reach terminal UI state. The
reported state is Running. IPC/controller, popup/formatting and build stages pass.
The artifact has no corresponding worker stack or saved terminal/action trace,
so the precise Shell/worker/readback cause is **not established**. E107's new
classes are not called by that existing flow; no causal P23 regression is claimed.
The failure is retained and is not a pass. Neither deadlines, assertions, policy,
verification nor window ownership was changed. Mock/fault P20 checks do not
establish native folder completion. A same-source comparison alone does not
repair or explain the first failure.

The comparison full Windows gate passes, but repeatability of the native folder
completion remains an open reliability finding. No blanket whole-UI stability
or full P23 acceptance claim is made.


## Remaining P23 and recovery

Next safe step: diagnose the retained native P20 folder terminal-wait failure
with owned-worker/native evidence, preserving deadlines and cleanup. P23 host
work follows that prerequisite check. Remaining P23 packet: serialized live observation delivery plus owned nonactivating,
input-transparent native host for existing surfaces 15/16. Deduplicate original
observations, revoke on immediate STOP/terminal/disconnect and revalidate every
display update. Cover remaining capture paths, explicit legacy coordinate
conversion and real host DPI; keep image bytes transient. Combined moved/closed
window, monitor/DPI, stale/ambiguous-match and STOP acceptance must pass. Surface
17 continues to require saved actual verifier readback independently.

This boundary alone cannot establish full P23 or advance to P24. Existing
owner-approved C-02 physical timing deferral to P25 and later physical,
installation/recovery/security/performance/release gates remain unchanged.

Recovery: use reviewed dependent reverts on p12-preparation, preserving E106 and
unrelated work; recovery/pre-p23-e107-20261104 preserves the starting source.
No reset, clean, force push, merge or branch switch. No concurrent production
hosts on one profile/pipe. The new bounded implementation is ready for independent Sol review with the
recorded native regression finding; full acceptance is not approved or inferred.
