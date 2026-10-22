# Workspace cleanup and recovery

Requested 2026-10-19 before preparing the completion prompts. This cleanup
does not fix backend findings, enable actions, redesign the UI or complete a
product phase. Existing runtime sources, tests and immutable requirements remain.

## Current folder layout

Active folder: `D:\Workspace\DEVEL\PLUMA`, branch `ui-wiring`.

- Root: current specifications, agent contract, build/configuration entry
  points, live handoff, README and `PLUMA_COMPLETION_PROMPTS.md`.
- `pluma/`, `PLUMA.UI/`, `tests/`, `benchmark/`, `packaging/`: working source,
  verification and deployment inputs.
- `docs/history/`: nine retained historical reports/notes/prompts/logs, with
  their old claims clearly separated from current acceptance.
- `docs/local/`: ignored owner reference notes. The original untracked
  `PLUMA_BACKEND_DEVELOPER_CAPABILITY_MATRIX.md` was moved here unchanged and
  backed up locally; it was not published. Its protocol/push claims require
  checking against actual source and the current handoff.
- `output/`: ignored current audit/native evidence and future verification
  exports. Fresh full-test logs now go to `output/verification/`.
- `build/`, `dist/`, `release/`, WinUI `bin/obj` and Python caches regenerate
  as needed. Release bundles are ignored rather than committed as current code.

The former `D:\Workspace\DEVEL\PLUMA-ui-wiring` worktree remains detached at
`55b625c`, including its original evidence. The backend `main` and
`ui-polish-integration` worktrees and all original branch histories are retained.
`main` remains `6dbf589`; no merge was performed.

## What left the active folder

Thirty-six one-off root `fix_*.py` and `rewrite_*.py` patch scripts were inspected
as text and archived outside the project. They were not imported, executed or
treated as test evidence. They directly rewrite source/tests and are not runtime,
build or supported verification entry points. Their complete inventory and
SHA-256 readbacks are in the local archive manifest.

Historical files moved unchanged into `docs/history/`:

```text
ACCEPTANCE_TEST_RAW_LOG.txt
FINAL_RELEASE_REPORT.md
PHASE_13_5_COMPLETION_REPORT.md
PHASE_13_5_FINAL_TEST_RUN.txt
PHASE_13_6_COMPLETION_REPORT.md
PHASE_13_7_COMPLETION_REPORT.md
PLUMA_ANTIGRAVITY_PROMPT.md
PLUMA_PHASE_13_5_ANTIGRAVITY_HANDOFF.txt
fix13.6.txt
```

Old `output` exports, Python/WinUI build output, IDE state, release bundles,
root run logs, 24 additional generated cache directories and three empty
fixture folders were moved to the local archive. The original output alone
contained about 1.56 GiB. The final backend audit run
`20261019-113604-da2f4a6f` and native UI run `39243181549` were copied into
the active folder's ignored output with per-file SHA-256 readback.

Active verification helpers remain at the root. Their only execution change
in this cleanup is writing logs under `output/verification`. The release
builder's document paths follow the moved historical files and include their
history disclaimer. Neither verification helper nor the full release builder
was used as proof of product acceptance during cleanup.

## Preserved local state

Archive directory:

```text
D:\Workspace\DEVEL\PLUMA-local-archive\20261019-pre-completion-cleanup
```

Its `archive-manifest.json`, `obsolete-script-manifest.json` and
`cache-manifest.json` map original locations to archived locations. All
archival path targets were checked within the explicitly named workspace and
archive roots; file moves/copies used native PowerShell literal paths.
Archival was used after automatic approval review rejected the bulk deletion
command with only "blocked by policy". No irreversible bulk deletion was run.

The original primary checkout had 342 tracked generated-file changes confined
to WinUI `bin/obj`. They are preserved in local Git stash commit:

```text
4c72146410a14352d0b33165e8910b6ae1a53b28
Preserve original ui-polish generated state before requested cleanup 2026-10-19
```

The stash is local, not uploaded as a GitHub source commit, and was not popped.
The pre-existing capability reference is preserved locally, not silently added
to the repository. Archived builds and evidence are retained for inspection.

## Source recovery

Pushed annotated checkpoints:

| Tag | Source state |
|---|---|
| `pre-project-cleanup-2026-10-19` | Audited `55b625c74d769de1219378a16d4621f4f49b3d10`, before this cleanup |
| `pre-ui-wiring-2026-10-19` | `04bc1fb7d1efa1744b1027a51ce10e3b3ef7eccc`, before UI wiring |

To inspect pre-cleanup source without overwriting current work:

```powershell
git -C D:\Workspace\DEVEL\PLUMA fetch origin --tags
git -C D:\Workspace\DEVEL\PLUMA worktree add --detach D:\Workspace\DEVEL\PLUMA-before-cleanup pre-project-cleanup-2026-10-19
git -C D:\Workspace\DEVEL\PLUMA-before-cleanup status --short
```

Choose a new destination if it exists. This restores the tracked source layout,
including removed patch scripts and old tracked release files, in a separate
checkout. Source recovery does not undo any runtime external action.

To inspect original local generated edits, first create a separate checkout
based on original `ui-polish` commit `9150e81`, inspect `git stash show --stat`
for the exact stash above, then apply it only in that separate checkout. Use
`apply`, not `pop`, so the backup stays available. Do not apply generated binary
state over the current wiring branch or run old patch scripts against it.

Local archived files can be copied to a separate inspection directory. Check
the manifests and exact destination first; never overwrite newer source or
user data indiscriminately. Shared changes should be undone with reviewed
revert commits and regression checks, without reset/clean/force-push.

## Verification of this cleanup

On Windows with Python 3.12.10 and pytest 8.3.3:

- `python output/cleanup-verification/verify_cleanup.py`: eight housekeeping
  checks passed. All three edited Python helpers parsed; 46 active-document
  local links resolved; the guide contained 34 ordered milestones covering
  all 72 numbered A-H cases and all 26 surface IDs. Archive hashes/source
  comparisons passed for 36 scripts and nine historical records.
- The same check exercised log placement with pytest mocked, and packaged the
  relocated documents/disclaimer with PyInstaller mocked and inert fixture
  binaries. These establish path compatibility only, not a working release,
  executed product suite or installed-app acceptance. Fixture outputs and
  `result.json` are under ignored `output/cleanup-verification/`.
- `python -m pytest tests/unit/test_phase13_5_stage_i_packaging.py -q -p no:cacheprovider`:
  **2 passed in 0.41s**. These check configuration defaults and entry-point
  importability; they do not build or install the product.
- `./PLUMA.UI/check-surface-copy.ps1`: **33 compiled XAML files passed** the
  visible-string underscore/em-dash check. This is a source scan, not a new
  native render or physical taskbar/motion check.
- `git diff --check` passed. Runtime backend, tests, WinUI C#/XAML, master
  specification, agent contract, build plan and acceptance definitions are
  unchanged from `55b625c`.

The nine backend findings remain open. No product-phase completion, new UI
runtime verification or owner-approved acceptance limitation is claimed.
