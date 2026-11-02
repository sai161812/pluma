# E98 — audit repairs and guarded integration

2026-11-03, Asia/Calcutta. Owner-authorized audit repairs and integration of
verified completed milestones only. P21 and later milestones are not started.
The immutable master and approved dark UI resources are unchanged.

## Scope and recovery

- Starting development head: `67ad1c1938f3f4653de61fdbf706b879025ea52e` on
  `p12-preparation`, clean and synchronized with origin.
- Remote main before integration: `26dc2799e758dc971e05315d8b97f2b376731240`.
  The separately checked-out local main worktree is preserved without updating it.
- Both recovery branches were created and pushed before integration:
  `recovery/pre-integration-20261103-67ad1c1` and
  `recovery/main-before-p12-p20-20261103`.
- Source/test repair commit: `c1b49c3ef5764bede78655aa0ea34482627d177c`.
- Isolated integration worktree:
  `D:/Workspace/DEVEL/PLUMA-verified-integration-20261103`, branch
  `integration/verified-p00-p20-20261103`.
- Merge candidate `81abc3cb824c616d63fcd13a435e23dac60c621f` has parents
  `26dc279` and `c1b49c3`. No conflicts occurred. Its Git tree is exactly the
  development tree `0d881819149ab97341e56f9b25f3efd4e7304b03`.
- P00–P11 already belong to main. The selected range adds P12–P20 and E97/E98
  test repairs. The interrupted P17 commits and their reverts have no net delta
  before the authorized P17 implementation. No Settings, Setup Wizard,
  capture-flash, OCR-indicator, critical-error or theme implementation is added.

Preserve these branches and SQLite data. Recovery uses reviewed reverts, newest
first, with the correct mainline for the integration merge, or a new worktree
from the recovery branch. Never reset/clean/force-push, discard uncertain undo
claims or redo an inverse merely to make a test pass.

## Reproduced causes and repairs

The direct clipboard fixture still reproduces `WinError 183` at station
creation. This is a logon-derived station collision, before clipboard access.
The already-documented same-permission fresh-logon mechanism succeeds without
reusing a station, elevation, real credentials, network authentication, profile
loading or changing Windows security. The original same-user/same-integrity,
new AuthenticationId, Job ownership, process-absence and interactive clipboard
sequence assertions are retained.

`tests/fixtures/clipboard_logon.py` previously depended on an ignored
`output/p11_power_actions/run_checks.py`. It now invokes its own checked-in
closed selection, isolates storage, preserves the actual pytest/JUnit outcome,
and rejects skipped, empty or inconsistent acceptance. Each run reserves a new
ignored evidence directory; stale reports cannot be reused or overwritten.

`docs/completion/run_p01_p13_checks.py` also previously truncated fixed report
names. It now defaults to a unique timestamp/UUID directory and accepts a fresh
`--output-dir` under ignored output; existing directories are refused. The old
overwritten `catalog-final.txt` remains unavailable and is not reconstructed.

Regression coverage in `tests/unit/test_clipboard_logon_evidence.py` verifies
preservation of existing reports, refusal of non-output locations and honest
acceptance of test results. No product policy or ownership assertion is relaxed.

A new environment installed only from `.[dev,windows]` then reproduced
**15 failures / 617 passes** in the affected P20 selection. JSON-Schema tools
correctly refused admission because `jsonschema` was missing; policy/worker
fixtures consequently never entered. The global interpreter had masked this
undeclared dependency. `b28c2ecd8cb6ec0507d34c100ba8909b959d8cde` declares
`jsonschema>=4.22.0,<5` in the core project and both requirements files. The
valid-schema admission regression no longer silently skips a required library.
Reinstalling from the declarations and checking dependencies succeeds; focused
schema/policy/multi-step/shutdown/STOP coverage passes **209 checks**. The
intentional absent-validator fail-closed regressions remain unchanged.

New browser-native runs use fresh profiles on never-switched owned desktops.
The old process of unestablished ownership is not touched; it does not prevent
testing a new independently owned session. Native browsing, exact tab undo,
STOP, PDF and authoritative download readback all pass.

## Fresh Python, dependency and IPC verification

Original-worktree reports: `output/integration-e98-20261103-002340/`.
Merged-worktree reports: `output/integration-checks-e98/` in the integration
worktree above. Full commands, source hashes, JUnit and failures remain ignored.
Windows 11 build 26300, Python 3.12.10. Normal Python suites use isolated
APPDATA/LOCALAPPDATA/TEMP/TMP where applicable; FAST desktop actions use the
documented inert adapter plugin. Fixtures do not use personal data, browser
profiles, clipboard contents, microphone or power effects.

| Selection / command | Result |
|---|---|
| Direct isolated clipboard read before using fresh-logon isolation | **1 failed**, `WinError 183`; retained |
| Evidence directory/result guards | **20 passed** |
| Native browser selection | **12 passed**, no skips/xfails |
| Tracked fresh-logon clipboard focused selection | **25 passed**, same permissions, no remaining owned process, interactive sequence unchanged |
| Tracked fresh-logon clipboard regression | **303 passed in 111.78 s**, no skips/xfails; both process/test exits zero, no remaining owned process, interactive sequence unchanged |
| `run_p01_p13_checks.py catalog --output-dir <fresh directory>` | **1,302 passed in 326.13 s**, no skips/xfails |
| Merged `prerequisites` / `contracts` / `p12` / `p13` manifest selections | **500 / 352 / 244 / 16 passed**, no skips/xfails |
| Merged P19 affected command from E94 | **331 passed in 36.18 s**, no skips/xfails |
| Merged P20 prerequisite command from E96 | **120 passed in 18.54 s**; separate from final selection |
| Merged final P20 affected command from E96 | **631 passed in 100.16 s**, no skips/xfails; two JUnit-family compatibility warnings, not worker failures |
| Merged fresh-logon clipboard focused selection, with no old ignored helper present | **25 passed**, zero owned processes, interactive sequence unchanged |
| Merged evidence guards | **20 passed** |
| `dotnet run --project PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj --verbosity quiet -p:UseSharedCompilation=false` | **285 IPC checks passed**, actual authenticated Python/C# pipes, no production desktop actions |
| `dotnet build PLUMA.UI/SurfaceControls.Tests/SurfaceControls.Tests.csproj --verbosity quiet -p:UseSharedCompilation=false` after diagnostic addition | **Passed**, zero warnings/errors |
| New venv; `python -m pip install -e ".[dev,windows]"`; `python -m pip check` | **Passed**, no broken requirements; global unrelated packages unchanged |
| Clean venv `pytest --collect-only -q tests/unit` | **2,426 collected**, no collection errors; full execution is not claimed |
| Clean venv evidence guards | **20 passed** |
| Clean venv affected P20 before declaring JSON-Schema dependency | **15 failed / 617 passed**, missing required validator; retained |
| Clean venv schema/policy/multi-step/shutdown/STOP after dependency repair | **209 passed in 8.70 s**, no skips/xfails |

Merged Python/IPC checks ran on `81abc3c`. The catalog started before committing
the already-applied test repair, so its metadata records parent `67ad1c1` plus
actual source hashes. All 313 captured Python source hashes match the original
tested files. Comparison with the merge worktree finds no content differences;
218 raw hash differences are solely Git checkout CRLF conversion. The Git trees
are identical. Scoped fixture-process readback found no process using the new
browser/catalog/merged test storage. This is not a blanket all-process orphan
or crash-recovery claim.

The P13 selection here is fixture coverage; the native model evidence remains
E72/E94. No fresh model/device pass is inferred. Physical microphone timing is
still owner-deferred to P25; installation, recovery, full performance/quality,
security and other later matrix gates remain open.

The immutable master Git blob is `01b693dbf898b662aa4cd67736c1a0e8a21cf3e3`
on both original main and the integration candidate. A new Windows checkout
normalizes line endings to CRLF; its raw file hash differs from the original
checkout without any Git content change. No master requirement was edited.

## Native integration gate

[Windows run 41506014340](https://github.com/sai161812/pluma/actions/runs/41506014340)
on exact merged source `81abc3c` **failed**. Builds, **285 IPC / 663 native
popup / 195 formatting**, layout and surface checks pass. Native selected undo,
denial, STOP and retained conflict checks execute, then the actual conflict
folder command is still `Stopping` when its existing six-second condition
expires at `NativeP20UndoChecks.cs:115`. No complete native UI pass is claimed.
E96's historical passing gate does not override this fresh failure.

Failed artifact `13172225164` was downloaded and its API SHA-256 verified:
`b68faec4a8814a41c51599d85e28f3bb86fe5017903a5af8f22182e051e3f690`.

Diagnostic commit `5a9f6a31994f5a56ce920e08dd1e80aff8efa067` adds owned
command/button/terminal/detail evidence around that failure; existing
assertions and deadlines are unchanged. Diagnostic native run
[41507711110](https://github.com/sai161812/pluma/actions/runs/41507711110)
also **failed**, now with independent evidence: the old conflict command was
terminal and the folder button enabled before invocation; a different request
and task were admitted. Its saved `open_folder` action reports `TOOL_TIMEOUT`
after 4.625 execution seconds / 5,081 ms total. Terminal state is FAILED with
`NON_UNDOABLE_EFFECT_REMAINS`, not successful folder opening. This rules out an
unadmitted click or the earlier command remaining pending. The report does not
separately measure COM activation versus Shell location observation.

Diagnostic artifact `13172975565`, API-verified SHA-256:
`ba8bdb0a9ebb7162e2275dc3d610140838dc8560dc9c6d0ba68d9852191f0fc3`.

Repair `d0e21600b395d59020ab7673ff975c4ba9ae02e3` gives only `open_folder` a
ten-second shared hard budget for cold native Shell work and verifier readback.
The matching native terminal wait is twelve seconds, including two seconds of
readback allowance; other six-second UI conditions and the overall native
runner bound are unchanged. The master specifies bounded calls and verified
readback, not a fixed five-second folder-opening budget. No success, visibility,
saved verifier, exact folder identity or owned-window closure assertion is
removed. STOP still cancels and kills only the PLUMA-owned worker; it never
force-kills Explorer or promises to undo the external view.

The added blocked-folder-launch regression passes with native worker identity
and absence readback, cancellation/terminal completion within four seconds,
no late operation, no fabricated verification, and retained uncertain external
intent. Focused P20/system/policy/worker checks: **73 passed in 16.63 s**, no
skips/xfails. The earlier catalog and merged prerequisite evidence cover their
unchanged paths; this bounded ToolSpec change requires a fresh affected P20 and
native UI gate before integration. Main remains unchanged pending that gate.

## Final gate and integration decision

[Windows run 41509078768](https://github.com/sai161812/pluma/actions/runs/41509078768)
on `d0e2160` **failed again**. The request/button admission is valid. Saved
`open_folder` execution reaches the new deadline: **9.625 execution seconds /
10,067 ms total**, `TOOL_TIMEOUT`, FAILED, verification false and uncertain
non-undoable effects. The visibility/verifier assertion fails; it is not
skipped. Increasing the budget did not resolve the native operation. No further
deadline increase or success fallback is made. Actual COM-stage diagnosis is
still required; cold-start budget exhaustion alone is not an established root
cause.

Final failed artifact `13172996724`, API-verified SHA-256:
`1d4161bd1820ff76bff37e9265efb757acdb6d84c8cb3a4250d7e156397ffe52`.
All three failed runs retain successful builds/285 IPC/663 popup/195 formatting
and their earlier native checks; none is a full native UI acceptance pass.

After the declared dependency repair, the clean environment passes **632 P20
checks in 66.25 s** and **500 prerequisite checks in 35.37 s**, no skips/xfails.
These run on candidate `b28c2ec`; they do not override the failed native gate.
The ten-second attempt and its STOP regression remain explicitly unverified
for native success on the isolated integration branch.

**Integration is stopped. No commit was pushed to main.** Remote main remains
`26dc2799e758dc971e05315d8b97f2b376731240`. The local candidate merge `81abc3c`
exists only on the pushed integration branch. Its diagnostic and failed-budget
follow-ups are preserved there, separate from verified development repairs.

The verified declaration-only dependency commit was separately cherry-picked
onto `p12-preparation` as `e1e0d845a0deee9c8f9f41fd90ea70589b016ff9`, alongside
runner repair `c1b49c3`. The unverified timeout change is not applied to that
development branch. Current handoff/matrix records supersede E96/E97's full
P20 gate claim while preserving those historical passing results. No P21 or
later implementation starts. Full unit execution, physical timing, install,
recovery, performance/quality and later security gates remain open.

Final verification on the actual development checkout `e1e0d84`, using the clean
declared environment: **229 passed in 17.75 s**, no skips/xfails, covering the
report guards, strict argument admission, policy, multi-step, shutdown and STOP.
The loaded package path was independently printed as
`D:/Workspace/DEVEL/PLUMA/pluma/__init__.py`, excluding accidental testing of the
integration copy. Matrix validation passes **298 source items / 334 rows** and
`git diff --check` passes. Only completion records change after this verification.

Next safe packet: instrument and isolate the real `folder_view.open_view`
COM activation, Explore and location-readback stages on a disposable Windows
host, resolve the reproduced cause, then pass the unchanged native visibility,
ledger, owned-window closure and affected STOP checks before retrying main
integration. No independent approval or product readiness is claimed.
