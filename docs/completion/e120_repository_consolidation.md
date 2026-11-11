# E120 - Repository consolidation

2026-11-11. Owner-authorized maintenance: retain a safe development checkpoint,
consolidate to `main`, remove unnecessary branches/generated clutter and leave
a clear handoff. This does not implement or complete another milestone.

## Preservation and source selection

Started at `751fa87f589309f26afbfd5e2e495a40a3976dfa`, `p12-preparation`,
nine commits ahead of its fetched remote. Only root `uv.lock` was untracked.
Fetched `origin/main` is `0468a031238261bee5bc79bd04b16a3d1964a3a9`.
One registered worktree exists. Every local/remote ref, tags and stash was
preserved in a verified complete bundle inside PLUMA. See the handoff and
[branch inventory](../history/BRANCH_INVENTORY_20261111.md) for refs and hashes.
The untracked lockfile was moved into that recovery directory with a matching
backup. No new recovery branch was created.

The accepted production baseline is `caaec5b`. Nine subsequently modified
release/measurement/runtime files were restored explicitly to that baseline:
README, benchmark/idle_baseline.py, build_release.py, install.ps1,
uninstall.ps1, pluma/app.py, pluma/core/health_contracts.py,
pluma/core/host.py and pluma/core/ipc.py. README adds current status text only.
E113/E119 accepted tests and evidence are retained. Unfinished E114-E118 source
remains recoverable at `751fa87` and in the source ZIP; it is not claimed ready.
Production Python, WinUI and benchmark/release source must match caaec5b before
the candidate is accepted. Master specification and UI styling are unchanged.

## Evidence and current limits

E108/E109 native UI and scoped completion evidence applies by unchanged-source
identity; it is not presented as a fresh native run. P24 remains 25/140 and
P25-P33 release/physical/security/performance/installed gates remain open.
The app-launch prerequisite interrupted before this request has no pytest
result; it is not accepted. A privileged, read-only process query found no
PLUMA Python/UV process remaining before cleanup.

## Fresh candidate checks

Candidate commit: `d86ec3e` (full identity is retained in candidate-checks/tested-commit.txt).
The inspected selection covers settings storage/execution/lifecycle, health and
owned Core recovery, perception metadata/live delivery, STOP, worker ownership,
shutdown, policy, routing and all four accepted P24 fixture modules.

- First isolated run: **526 passed / 1 environment failure**, 113.89 seconds;
  the locked-destination settings test could not import `win32con` because the
  initial portable environment omitted the declared Windows dependency.
- With declared pywin32/comtypes/pycaw in the ignored workspace cache: the
  owned locked-file case and COM-helper failure-cleanup case both pass,
  **2 passed in 0.77 seconds**. The intermediate missing-pycaw setup failure
  remains retained; no product assertion or safety check was weakened.
- `git diff --exit-code caaec5b -- pluma PLUMA.UI benchmark build_release.py
  install.ps1 uninstall.ps1`: exact active production-source identity.
- `git diff --check origin/main`: clean. The restored historical builder has
  two existing whitespace-only lines relative to the source-only preparation;
  they are unchanged from the accepted/main baseline, not a new code edit.

Commands use Python 3.12.10, pytest 9.2.0, timeout 2.4.0, Pydantic 2.14.3 and
PyYAML 6.0.3, with isolated APPDATA/LOCALAPPDATA/TEMP and short owned basetemp.
One BelowNormal runner executes sequentially. No personal clipboard/window,
browser, microphone, model or power operation is used.
Logs/JUnit and expanded module selection are under
`output/repository-consolidation-20261111-01/candidate-checks/`,
`candidate-windows-deps/` and `windows-dependency-check/`.

## Merged-source result

Local merge: `aa1a77b2d2aec61ed09052ce68e4c8e863bf74f2` (parents: the fetched
main and reviewed `ec3949c` consolidation candidate). Its tree exactly equals
the reviewed candidate. The complete inspected selection, now with declared
Windows dependencies and the COM-helper regression, passes **528/528 in
102.19 seconds**, zero failures/errors/skips/xfails. Two pytest warnings concern
JUnit record_property metadata and do not suppress any test.

Evidence: `output/repository-consolidation-20261111-01/merged-checks/` contains
`results.log`, `results.xml`, `selection.txt` and `tested-commit.txt`.
Command: the candidate's recorded uv prefix plus `--with 'pywin32>=306'
--with 'comtypes>=1.4.0' --with 'pycaw>=20240210'`, then `python -m pytest`
with every selector in selection.txt, `--runxfail --timeout=90 --basetemp
D:\Workspace\DEVEL\PLUMA\output\cons-tmp-04 -p no:cacheprovider -q
--junitxml <merged-checks>/results.xml`. Runs stayed sequential/BelowNormal.

Compared with accepted native E108 source, production source differs only by
E111's bounded router-purpose fix (fresh router tests pass); two UI wiring
documents differ, while WinUI executable source and styling are identical.
No new native/physical UI/model/installation acceptance is claimed.

## Generated-file cleanup

The reviewed cleanup removed **37 regenerable directories and three empty
scratch folders**, reclaiming **1,121,046,124 bytes**. These include WinUI
bin/obj, Python bytecode, build/pytest/egg metadata and the two disposable UV
caches. Source, models, private notes, historical evidence, tags, stash and the
verified recovery bundle remain. The exact path/count/byte inventory is in
`output/repository-consolidation-20261111-01/cleanup-result.json`.
The four owned test-fixture roots were subsequently removed under their
creating user contexts. Inspection/deletion explicitly unlinked 292 links
without traversing their targets, and reclaimed another 46,781,277 bytes.
No ACL or Windows policy was changed. Total cleanup: **1,167,827,401 bytes**
across 37 generated directories, three empty folders and four test roots.
The detailed fixture plans/results are retained alongside the cleanup report.

## GitHub and local consolidation

The verified development merge and evidence were pushed normally to GitHub
`main` (`0468a03` to `44cf263`; later changes are documentation only). Remote
readback matched the pushed main identity before branch cleanup.
All other remote heads were compared against the archived exact SHA inventory,
then **23 remote branches were deleted atomically**. **24 local branches** were
removed only after confirming they were merged or exactly preserved in the
verified bundle. The divergent old demo/sai/UI/integration lines were archived,
not indiscriminately merged into the accepted product tree.

Final structure: one worktree, one local branch `main`, one GitHub branch
`main`; existing tags and stash retained. No reset, git clean, force-push, new
milestone, release tag or branch with a new status name was introduced.
Original refs are in the committed branch inventory and the complete local
bundle. The final documentation commit is pushed normally and checked against
GitHub; exact final refs are retained under the ignored recovery directory.

This is a verified development checkpoint, not P24 completion, P32 release
acceptance, independent Sol approval or product-release readiness. Further
milestone work stops until the owner gives new instructions.
