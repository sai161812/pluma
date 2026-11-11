# PLUMA project handoff

Updated 2026-11-11 (Asia/Calcutta). The owner requested a safe development
checkpoint, one canonical `main` branch and repository cleanup. Further
milestone development is not authorized by this maintenance request.

## What is implemented

P00-P23 have recorded scoped implementation/acceptance evidence under the
documented owner limits. This includes typed Windows tools; task ownership,
STOP and guarded undo; privacy and factual history; voice/text routing;
UIA/OCR and bounded local planning; authenticated IPC; native text/voice,
confirmation, activity, settings, health and perception UI bindings.

[E109](docs/completion/e109_p00_p23_readiness.md) reconciles P00-P23.
[E108](docs/completion/e108_p23_live_hosting.md) records the accepted native
Windows/UI/STOP gate. UI source and styling are unchanged in this consolidation.
These scoped results do not establish a finished or production-ready product.

P24 is partial: **25/140 unique fixed-corpus cases accepted; 115 remain**.
E110-E113 cover owned file/list/history/status/mutation/undo flows; E119 adds
three emulated volume-status commands. [E113](docs/completion/e113_p24_owned_undo_prepared.md)
records 2 acceptance and 261 related regression passes. [E119](docs/completion/e119_p24_volume_status_readonly.md)
records 19 focused passes at `ca37ee3`, plus 257 selected regressions and seven
explicitly deselected physical/import-dependent checks. These are bounded
fixture results. A fresh E112 mutation rerun passed 2/2, while the original
cold failure's cause remains unknown. The interrupted private-desktop app
prerequisite produced no pytest acceptance report and adds no accepted case.

## Active source and unfinished work

Production source, WinUI, benchmark and release scripts are restored to the
accepted `caaec5b` baseline; the subsequent E113/E119 tests/evidence are retained.
Unverified E114-E118 release/measurement preparations were excluded from the
active source, preserving their complete content in Git history at `751fa87`
and the local recovery archive. They must be reviewed and verified before reuse.
Existing installer/build scripts are not a verified release or deployment path.

Still required: P24's remaining corpus and combined scenarios; P25 physical
display/accessibility/device checks; P26 laptop resource/latency/quality/soak;
P27 adversarial/privacy/crash review; P28 signed reproducible packaging;
P29 disposable install/upgrade/recovery/uninstall; P30 independent review;
P31 exact-build release acceptance; P32 release integration/tagging; P33 release
handover. The maintenance merge is not P32 release acceptance.

Owner-approved deferrals remain: fresh C-02 speech-boundary timing retest to
P25, live focus/audio mutations and disruptive power effects. Signing authority
and physical/installed evidence remain missing. Requirements are unchanged.

## Verification and integration

Consolidation verification and remote status are recorded in
[E120](docs/completion/e120_repository_consolidation.md). Fresh checks are
pending until that record has actual results. Existing native E108/E109 evidence
is reused only where source identity is unchanged. No physical acceptance is
inferred from fixtures, skipped/deselected cases or a successful merge.

The final intended state is `main` locally and on GitHub, with unnecessary
development/recovery branches removed after preservation and verification.
See [branch inventory](docs/history/BRANCH_INVENTORY_20261111.md).

## Recovery without keeping extra branches

All recovery files are inside `PLUMA/output/repository-consolidation-20261111-01/`:

- `all-refs-before-fetch.bundle`: verified complete Git bundle, including every
  former local/remote branch, tags and stash. SHA-256
  `4D429670B5DD59906C73DE8379D530F653AFD333908611FF962CA80848C03D08`.
- `refs-before-fetch.txt`, `remote-refs-fetched.txt`: exact original refs.
- `unfinished-and-evidence-source-751fa87.zip`: unfinished source/evidence
  snapshot, SHA-256 `E3F204D7264F23FB4780E4C69C33AC8E89F1D76A3AAD62D76BC9AA90C2FD119B`.
- `uv.lock` and `uv.lock.original`: preserved untracked dependency lock; excluded
  from the active root because it was not an accepted release lock.

`git bundle list-heads output/repository-consolidation-20261111-01/all-refs-before-fetch.bundle`
lists recoverable refs. `git show 751fa87:build_release.py` reads the unfinished
builder; the same command works for other archived paths. Restore only the
chosen work on a future explicitly authorized branch; no reset/clean is needed.
The bundle is local and ignored; retain it or copy it as a personal backup.

The full previous [handoff](docs/history/PROJECT_HANDOFF_20261111.md) and
[remaining-work record](docs/history/PLUMA_REMAINING_WORK_20261111.md) are retained
as historical snapshots. Current status here and E120 supersedes their cursors.

## When development resumes

Read AGENTS.md, the immutable master, completion prompts, this handoff and the
matrix. Start with P24's next owned-fixture acceptance packet after validating
its environment. Do not repeat completed milestones or run personal-desktop,
installer/power or model-load experiments merely to re-establish old evidence.
Keep one sequential test/build worker and bounded resource use. No development
or automatic startup was enabled by the repository consolidation.
