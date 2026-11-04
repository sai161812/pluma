# E108 - P23 live delivery and native target hosting

Implementation candidate; full native acceptance is pending. P23 is not yet
declared complete and P24 has not started. Base 3502e9e on p12-preparation;
recovery/pre-p23-e108-20261104 preserves the clean starting checkpoint and is
pushed. No merge, branch switch, reset/clean/force-push, XAML/style or master edit.
The unchanged complete master blob is 01b693dbf898b662aa4cd67736c1a0e8a21cf3e3.
AGENTS, shared P23 contract, handoff/E107, build phase 14, E-01..10 and approved
target/notification placement were reviewed/reused before editing.

## Implementation

- The existing task-owned worker pipe admits bounded private observation
  messages only from registered screen producers. Capture/refresh/read/find and
  the existing click_ocr_text fallback publish actual fresh capture/match facts.
  Capture facts can arrive before tool completion and history, so they confer
  neither success nor action authority. Private intermediate snapshots are not
  inserted into the planner registry; new action references still require normal
  verified tool-result registration and TTL admission. Cross-target/invalid
  receipts, flooding, STOP and late delivery fail closed. Final receipts cannot
  replay an observation or renew its lifetime.
- The existing serialized runtime observer queries feedback while tasks run,
  plus a bounded three-second metadata tail after recent activity/terminal events.
  No extra reader, idle image loop or heavy startup import is introduced.
  Missing/corrupt/disconnected replies clear presentation. Shell STOP revokes
  immediately; failure/expiry and native revalidation remove stale facts. Successful
  tails require actual terminal persistence and retain the original expiry only.
- A shell-owned nonactivating, input-transparent transparent window hosts the
  unchanged ScreenCaptureFlash and OcrMatchIndicator controls, outside the popup
  stack. It occupies only the actual capture ROI and has no non-client shadow.
  It is hidden until native bounds and root DPI/layout agree. Native identity,
  title hash, geometry, monitor, visibility/foreground and original wall/monotonic
  age are rechecked. Each capture flashes once; repeated IPC cannot resurrect a
  revoked observation. Only host-created windows are closed.
- Legacy/system/per-monitor coordinate mapping uses Windows'
  LogicalToPhysicalPointForPerMonitorDPI for ROI and match corners, followed by
  host-local DIP conversion. No guessed multiplication of legacy coordinates.
  The target is checked again after mapping. Actual confidence/bounds are used;
  no raw recognized text, caption, audio or image is added to the UI channel.
  Surface 17 remains independently driven by saved actual verifier evidence.

## Reproduced OCR prerequisite and bounded repair

New native cold-model checks reproduce the unchanged 12-second tool timeout.
Owned-worker stacks identify Paddle's cold dependency imports. Images were
captured before runtime loading, consuming their short evidence lifetime.
The fix prepares the on-demand worker first, then captures a fresh snapshot.
OCR uses installed local small ONNX weights with explicit paths; its lazy
vendor import does not probe network host availability. Missing weights refuse
without a download. Test/model provisioning is an explicit separate process;
the resident remains cold and all tool budgets, STOP and input TTL checks stay.

A fresh derived observation can outlive the admitted input snapshot while the
same task/known target remains owned, without reviving that expired action ref.
Snapshot removal, task state and STOP still clear feedback. Meaningful tests
exercise this distinction. No image timestamp is reset after recognition.

## Current evidence and limitations

Unique ignored root: output/p23-e108-20261104-230308-e366ce50/.
The E98 declared Python initially needed sandbox-authorized runtime access.
An old OCR environment lacks pytest; that failed setup attempt is retained.
A new private test-env installs only declared windows/dev/ocr extras. Historical
environments are unchanged. Native target windows never activate on the user's
desktop. Positive foreground/render tests run only on the disposable host.

Pre-edit affected prerequisites: 61 pass, no skips/xfails. First live selection:
43 pass. Initial focused selection: 108 pass. Final focused selection including
OCR grounding: 130 pass, no skips/xfails. C# IPC/controller selection: 400 pass.
Native controls build: zero warnings/errors. The actual owned native OCR check
passes after repair (5.289s pytest) under the original tool deadline, delivering
a unique real match and saved verified action with worker absence/no image file.
These initial checks run on base plus the implementation diff; committed-source
reruns and exact build identities will be recorded after final acceptance.

Failed cold/trace results remain under native-ocr-cold/ and native-ocr-trace/;
they are not acceptance passes. Native OCR uses an owned-HWND foreground seam
only; the combined disposable-host suite separately requires real foreground,
actual composed pixels, native hit testing, bounds, saved verification, moved/
hidden/closed targets, original expiry, STOP, disconnect/reconnect and shutdown.

E107's native P20 folder-terminal wait failure remains retained and unexplained;
its same-source comparison passed. Fresh full UI regression evidence is required,
not assumed. No deadline or assertion is relaxed to make that flow pass.

## Completion condition

### 2026-11-05 verification checkpoint (not closure)

Committed bc60b5f affected selection: 1210 passed, no failures/skips/xfails;
native conversion/capture/real OCR: 3 passed. Full results are retained under
required-regressions/ and native-committed/. CI 41886670901 failed the P22
missing-model fixture because OCR is now installed; 1be0b90 isolates that negative
fixture. CI 41888196449 failed P20 saved folder verification. Diagnostic run
41891397425 independently passed P22 but exposed a P18 STOP-finalization race
in its test and failed P23 WindowFromPoint input pass-through. These failures
are retained, not counted as passes. Its artifact SHA256 is
0e894f198a171e81fe94b00eec55b52080ac4e26ef37dada3f234b0f27169735.

Review also reproduced lost capture-only observations between UI polls
(short-capture-reproduction/: one failed regression). A bounded successful
metadata tail now uses the original deadline, releases snapshot/image state,
waits for terminal persistence, and is revoked by STOP/shutdown. Focused delivery,
readback and STOP: 80 passed (short-capture-regressions/); C# IPC: 403 passed
(short-capture-core-run.log), Release build zero warnings/errors. Native tests
add no-holding-step capture and actual region coverage. Combined acceptance is
still required; no completion claim or P24 eligibility is implied.

Normal run 41896683698 on 35d8800 passed 403 IPC, 663 native popup, 195 formatting
and 15 P22 UI checks. The independent native-controls suite crashed before the
folder scenario: the added diagnostic branch's local imports shadowed existing
history readback closure bindings. Removing those imports is verified by an
actual subprocess/control/SQLite regression (native-fixture-import-guard/).
This was an E108 fixture regression, not an undo product failure. Its P23 suite
still found another PLUMA HWND at the right-edge hit-test sample. The revised
fixture uses the target's empty left margin, asserts no overlap with the separate
notification lane, and requires real SendInput delivery to an owned WM_LBUTTONDOWN
counter while feedback is visible. Neither styles nor WindowFromPoint alone are
accepted as actual pointer-delivery proof. The capture-only native case checks
saved success and a separate late metadata query; it does not require a previously
displayed RUNNING frame to change phase in place or replay a completed flash.

Run 41896086286 was cancelled by workflow concurrency when the newer checkpoint
was dispatched; its partial artifact is retained and is not acceptance evidence.
Run 41896683698 artifact SHA256:
ae304cfdab6d5d092a882c12eae6b171d0a93d8e22256d544a1c794e8bd1efa4.
The final native-fixture selection on committed 02fd21e passes 4 checks: real
diagnostic control/storage plus native conversion, capture and PaddleOCR/ONNX.
Required affected backend regressions on 22a5b2d: 1213 passed, no skips/xfails,
11 existing JUnit record_property warnings. Later changes so far affect native
feedback input and test fixtures, not those backend paths. Full disposable-host
acceptance on 02fd21e is running, with optional owned-folder stack diagnostics.

Run 41898248106 on 02fd21e failed overall. The folder visibility/saved verifier/
new-window-only cleanup scenario passes, as do target identity, input styles,
uncovered-target hit testing and actual native ROI bounds. Remaining failures:
P21 fixture READY was not received within its original seven seconds; P22's
third recovery-dialog admission timed out; the P23 one-shot GetPixel brightness
assertion failed. These are retained as failures, not assumed repaired. Pixel
acceptance now uses a transient 1x1 BitBlt SRCCOPY|CAPTUREBLT sample to include
layered windows (Microsoft's documented capture flag), samples within the existing
220ms flash and logs exact colors/layout. Its brightness/outside-ROI assertions
remain mandatory; safe independent scenarios continue before an overall failure
is raised. Owned startup stacks/recovery state diagnostics retain their original
deadlines. No product restart/startup fix is inferred without those diagnostics.
The fixture/folder/undo selection passes 24 checks and native acceptance compiles
with zero warnings/errors. Run artifact SHA256:
a9b2759a76b36a5b5de0d8a111ecf0ce12f37fdfe4b280d2eb9d1f00437412a6.

Run 41900460308 on e8ec837 passed 403 IPC, 237 native UI (including P20 folder
visibility/verification/owned-window cleanup and P21), 663 popup and 195 formatting.
P22 reached its final shutdown assertion but did not drain within five seconds;
the next run records its exact awaited owner. No deadline was increased.
P23 proves real pointer delivery beneath the layer and exact outer ROI bounds,
but composed pixels expose an opaque #222222 matte and a 414x234 client in a
420x240 ROI; the flash starts at zero arranged size. The candidate removes the
native frame, reads back full client bounds, enables client alpha over an empty
DWM blur region, clears WM_ERASEBKGND to alpha-zero black, and arranges the
existing flash before its unchanged storyboard. No image-copy backdrop or new
dependency is introduced. These repairs still require native pixel acceptance.

The real short capture also exposed disposal-only fencing: worker disposal seals
native admission with no cancellation cause, so stop_latch_set alone wrongly
discarded successful metadata. Native regression disposal-tail-reproduction/
fails before repair; disposal-tail-fixed/ passes 42 checks afterward. The parent
permits only successful persisted metadata with no explicit cancellation cause;
executor admission remains sealed. Extended native conversion/capture/OCR checks
pass 3, including failed new admission and metadata-only STOP preserving success.
Required affected regressions after this change pass 1213, no skips/xfails
(required-regressions-disposal-tail/, base e8ec837 plus the reviewed source diff).
Release native acceptance build is warning/error-free. Diagnostic folder mode
adds three fresh owned fixture repetitions without changing the normal gate or
individual budgets. Run 41900460308 artifact SHA256:
ec3b9c42b1eb0bdbf7b33b66f1457424d8d9cf346c3a0727ad7c2b62f4729834.

Required affected regressions, native conversion/capture/OCR checks and the
combined native P23 suite must pass on the recorded committed source. Until
then UI-15/16 remain UNVERIFIED and P24 ineligible. Existing physical monitor/
scaling/accessibility, C-02 timing deferred to P25, and later quality/resource,
security/installation/release gates remain with their owning milestones.

Recovery uses reviewed dependent reverts preserving unrelated work and the
pushed recovery branch. Independent Sol approval is not assumed.
