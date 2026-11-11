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

Fresh consolidation checks, exact tested commit, merge/push and cleanup
results: pending. No branch is deleted before its history is preserved and
main integration is verified. Existing tags and stash remain untouched.
