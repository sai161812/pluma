# E99 — P20 Shell readback repair and guarded main integration

2026-11-03, Asia/Calcutta. Owner authorized the P20 hang repair and integration
only after verification. No P21+ implementation, visual redesign, reset, clean,
force-push or Windows security-policy change is included.

## Reproduction and cause

E98's three native timeout failures remain recorded. A longer deadline did not
resolve them and is excluded from this integration. The original five-second
ToolSpec budget and six-second native UI assertion are retained.

Worker stack capture identified the expensive readback call after `Explore`:
`ShellWindows.Item` returns an IDispatch, then pywin32's automatic wrapper calls
`__WrapDispatch -> GetTypeInfo` before PLUMA can inspect its actual location.
Two consecutive native stack samples are inside that metadata RPC at
`folder_view.py:33`. Another sample is inside dynamic property dispatch during
the independent verifier. This metadata/generation path is unnecessary for the
fixed operations PLUMA performs and can exhaust the shared tool deadline.

The retained fault reproduction makes the returned window's type-information
call unresponsive. The old adapter fails at `windows.Item(index)` with that
specific error; the repaired adapter reads the actual properties without asking
for type information. This is a COM fault fixture, not native Explorer evidence.

Relevant primary API contracts:
[PyIDispatch.GetIDsOfNames](https://mhammond.github.io/pywin32/PyIDispatch__GetIDsOfNames_meth.html),
[PyIDispatch.Invoke](https://mhammond.github.io/pywin32/PyIDispatch__Invoke_meth.html),
[pywin32 automatic wrapping](https://github.com/mhammond/pywin32/blob/main/com/win32com/client/__init__.py),
[COM teardown](https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-couninitialize).
The internal Explorer/server reason for a slow metadata response is not claimed
as diagnosed; the unnecessary client dependency on that response is removed.

## Bounded fix and preserved guarantees

- `pluma/adapters/folder_view.py` uses raw IDispatch name resolution/invocation
  for the fixed Explore, Windows, Count, Item, LocationURL and Visible operations.
  No automatic type-information lookup or generated wrapper is required.
- The requested literal folder URI and actual visibility are still read back;
  verification obtains a fresh Shell collection independently of execution.
  A successful API return or cached executor flag is never sufficient.
- COM references are released before apartment teardown, including failure and
  cancellation paths. Enumeration remains bounded to 256 windows and the
  three-second observation loop is unchanged.
- The typed registered tool, policy-before-dispatch, task/Job ownership,
  cancellation latch, five-second hard budget and non-undoable intent remain.
  STOP terminates only the owned tool worker, never Explorer. Uncertain external
  effects remain factual ledger residuals.
- `tests/unit/test_folder_view.py` covers blocked metadata, fresh verifier
  rejection of hidden/moved/unavailable views, bounded enumeration, activation
  failure, cancellation before dispatch/during readback and reference cleanup.
- `test_p20_detail_undo.py` retains a real owned-worker blocked-launch STOP
  regression with original PID/creation-time absence, no late effect, preserved
  uncertain intent and independent ledger readback.

Investigation fix commit: `2d11f8e`; verified development fix: `71c174d`.
The owned STOP regression is `cd18a44`. Only the adapter and these regression
files are carried to development. Diagnostic callbacks, startup tracing,
repeat-run switches and the failed ten-second experiment remain on the
separate `integration/verified-p00-p20-20261103` branch.

## Native investigation evidence

Unique ignored investigation directory:
`D:/Workspace/DEVEL/PLUMA-verified-integration-20261103/output/p20-shell-e99-20261103-114525/`.
All downloaded artifacts were compared with GitHub's SHA-256 digest before use.

| Exact run / source | Result and boundary |
|---|---|
| Baseline focused selection on `b4cfd49` | **73 passed**; fixture/policy/worker evidence only |
| `41588929449` / `d7aada3` | Full native gate passed with a wrapped diagnostic executor; not used to claim the unchanged path was repaired |
| `41590556126` / `93321c2` | Full gate passed with the original executor; concurrent-file sharing prevented useful stack extraction |
| `41591322862` / `4d5942c` | Normal native gate passed **214 UI**; stack capture identifies the metadata RPC. An extra whole-flow diagnostic repeat failed earlier in STOP/connection readback, so no five-cycle pass is claimed for it. Capture was running inside the IPC server as well as workers; subsequent capture is restricted to owned tool workers |
| Fault fixture before adapter change | **1 failed**, exact blocked type-information reproduction retained |
| Focused after adapter change | **81 passed**, no skips/xfails |
| Affected P20 plus folder tests on `e6ceb6a` | **640 passed**, no skips/xfails |
| `41592784530` / `e6ceb6a` | Full **285 IPC / 214 native UI / 663 native popup / 195 formatting**, layout/surface/audio/copy gates pass; **five further P20 cycles / 130 checks** pass at the original deadlines |

The repaired native run proves actual folder location/visibility, saved verifier
readback, and graceful closure of only the newly observed owned window. Initial
folder execution/readback is 3,829 ms; the five additional independent owned
folder trials are 920 / 894 / 884 / 891 / 944 ms. These are individual fixture
measurements, not a product latency percentile or target-laptop benchmark.
The same Windows image/runner and Windows adapter library versions were used in
the compared failed and passing runs. E98's missing JSON-Schema dependency is
present as declared; it is not presented as proof of a COM cause.

Native artifact `13210962377`, SHA-256:
`dbef1921b7128304f843b7f17b1bed228a5b8d3d28649c1c9661f7637b3cb601`.
Unsigned test-preview executable SHA-256:
`FC26D6F0A640438522A01E82EFF0150E26610E6B5068CFEB0265EF07BA78EDC6`.
This is not a signed release/install artifact.

## Merge and current-source verification

After fetching origin, main was `26dc2799e758dc971e05315d8b97f2b376731240`.
Development head `cd18a44` adds the verified repair to the reviewed P12–P20
range. No P21+ feature, unrelated UI branch, master/build/acceptance/prompt
changes or dark theme resource changes are selected. Original P17 interruption
commits/reverts retain their prior zero net delta before authorized P17 work.

Local merge `8dfb87c32fa83234deb18e37dfa51766f1e0f0a8` was conflict-free.
Its tree exactly equals development tree
`3ae72efc57e91391e6003ed602d66240d434cff8`. P00–P11 already belong to main.
The final candidate worktree is `D:/Workspace/DEVEL/PLUMA-main-merge-e99`,
branch `integration/main-p00-p20-e99`. The investigation branch is not merged.

Merged native run `41593732409` passes the full normal gate without diagnostic
hooks on exact merge `8dfb87c`. Merged Python selections pass **500 prerequisites
/ 352 contracts / 244 P12 / 16 P13 unit checks**; actual C#/Python IPC passes
**285 checks**. The affected selection records **1 failed / 639 passed** because
a shutdown test assumed a 30 ms call always reached the model stage. Under
concurrent load it legitimately returned from an earlier stage instead.

That test-only defect is deterministically reproduced by holding the real
capture stage. `f870509ef38136e9b5a74145f8300d9448061e96` adds both immediate and
delayed-stage cases and observes actual model-stage entry before asserting
runtime timer retention. The 30 ms call, storage-open, retained timer,
cleared-lifecycle-reference, joined timer and verified final-close assertions
remain. No runtime code changes. **50 shutdown tests pass** after repair.

The next sequential affected run records **1 failed / 640 passed**: a real
inverse fixture published an empty marker filename before writing its task ID.
`d922c8dc84df04bd770a5dff88dfc5e25eede1c2` fixes only that fixture by closing a
private pending file before atomically renaming it to the final marker. The
original exact task-ID, real claim, STOP/timeout, worker absence, unchanged
preference and retained unknown-effect assertions remain. **15 inverse tests**
and the final **641 affected P20/folder tests** pass after the fixture repair.
Both failed local reports are retained; no failed result is relabelled a pass.

Final native gate and sequential checks on `d922c8d` are recorded below before
any main push. Product and UI implementation are unchanged from the already
native-tested merge; only those two test/fixture corrections follow the merge.
Final test logs use the unique ignored directory:
`D:/Workspace/DEVEL/PLUMA-main-merge-e99/output/e99-merged-20261103-123344/`.
Commands, source IDs, JUnit and failures are retained there; no historical report
is overwritten. P13 units are fixtures, not a new native model pass.

### Final accepted results

Exact final tested source/test commit:
`d922c8dc84df04bd770a5dff88dfc5e25eede1c2`. All following documentation changes
leave product, UI, tests, dependency declarations and workflow source unchanged.

| Check | Final result |
|---|---|
| Manifest prerequisites after test synchronization repair | **501 passed in 72.10 s**, no failures/errors/skips/xfails |
| Manifest contracts on exact merge | **352 passed**, no failures/errors/skips/xfails; unchanged by the two test-fixture repairs |
| Manifest P12 on exact merge | **244 passed**, no failures/errors/skips/xfails; unchanged by the two test-fixture repairs |
| Manifest P13 unit selection on exact merge | **16 passed**, no failures/errors/skips/xfails; native-model evidence remains E72/E94 |
| Final P19 affected selection | **332 passed in 45.83 s**, no failures/errors/skips/xfails |
| Final P20 selection plus `test_folder_view.py` | **641 passed in 145.09 s**, no failures/errors/skips/xfails |
| Actual local merged C#/Python IPC | **285 passed** |
| [Final Windows gate 41595595184](https://github.com/sai161812/pluma/actions/runs/41595595184) on exact `d922c8d` | **285 IPC / 214 native UI / 663 popup / 195 formatting**, **64,537 layout / 30 surface** checks, audio visualization and copy gates pass; zero build warnings/errors |

The final Windows run uses the normal checked-in workflow and unchanged native
assertions, with no injected executor, stack collector, repeat switch, skipped
folder operation or longer timeout. Actual conflict-folder visibility, saved
verification, new owned-window closure, selected inverse approval/denial/STOP,
retained conflicts, Activity entry and joined shell shutdown all execute.

Artifact `13212786014`, downloaded and API SHA-256 verified:
`be1aeeed0abaae1a27a210df60a2ab0c265bd327c12da53f4950fe6e2f8de9dd`.
Unsigned test-preview executable SHA-256:
`36CD7A916ED7C4B347D43ACE4C7DAB7008278959D4222A37E6635D25523DFF41`.

Exact commands are stored in `p20-verified.json`, `p19-verified.json`, and the
manifest runner `*-final.json` reports. They reproduce E96's final affected
P20 command plus `tests/unit/test_folder_view.py`, E94's P19 command, and:

```powershell
python docs/completion/run_p01_p13_checks.py prerequisites --output-dir <fresh ignored directory>
python docs/completion/run_p01_p13_checks.py contracts --output-dir <fresh ignored directory>
python docs/completion/run_p01_p13_checks.py p12 --output-dir <fresh ignored directory>
python docs/completion/run_p01_p13_checks.py p13 --output-dir <fresh ignored directory>
dotnet run --project PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj --verbosity quiet -p:UseSharedCompilation=false
./PLUMA.UI/verify-ui.ps1
python docs/completion/verify_requirements_matrix.py
git diff --check
```

The Python interpreter is the declared clean environment at
`D:/Workspace/DEVEL/PLUMA-verified-integration-20261103/output/integration-checks-e98/test-env/Scripts/python.exe`.
The actual package path was printed as the merged worktree's `pluma/__init__.py`;
tests did not accidentally exercise the investigation copy. APPDATA,
LOCALAPPDATA, TEMP and TMP were isolated in the affected runners. FAST desktop
routes use the documented inert isolation plugin; native CI uses owned fixtures
on the disposable host. No personal window, clipboard, profile, audio, file or
power state is used. Existing E98 catalog/clipboard/browser evidence remains
applicable to unchanged paths and is not relabelled as a fresh E99 run.

Review confirms the immutable master Git blob remains
`01b693dbf898b662aa4cd67736c1a0e8a21cf3e3`; no source requirements, dark theme
resources, hidden success fallback, detached branch or unrelated work is added.
The isolated failed investigation history is excluded from the main candidate.
Matrix validation and whitespace checks are required again on the final
documentation checkpoint. The owner authorized normal main integration after
these gates; independent approval is not invented.

## Recovery and remaining work

Pushed recovery references:
`recovery/main-before-p12-p20-20261103` (`26dc279`),
`recovery/pre-p20-repair-20261103-be8410d` (`be8410d`), and
`recovery/pre-p20-shell-fix-20261103-b4cfd49` (`b4cfd49`). Earlier recovery
branches remain. Recover through reviewed new reverts, using the correct
mainline for the merge; never reset/clean/force-push, delete uncertain undo
claims, or repeat a captured inverse to make recovery appear successful.

P21+ implementation is separate and has not started. E94's owner-approved
physical C-02 timing retest deferral to P25 is retained. Physical focus/audio,
broader UI/DPI/accessibility, full unit execution, installed recovery,
performance/quality/security and release gates keep their recorded scopes.
No full-product readiness or independent Sol approval is inferred.
