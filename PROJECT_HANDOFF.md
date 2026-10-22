# PROJECT HANDOFF & TECHNICAL CONTINUITY RECORD

## Current checkpoint: 2026-10-22, P11 shared tool deadline

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Continue remaining P11 gates only.

- [E49](docs/completion/p11_shared_tool_deadline.md) fixes a concrete D-09
  defect: policy time and action time previously had separate `ToolSpec` budgets.
  Lookup/argument validation now starts one wall-clock budget shared by policy,
  pre-state, execution and readback. A regression proves the combined policy and
  executor duration cannot exceed that budget and owned work drains.
- Verification: `verification-tools-focused` passed **79 tests in 49.91s**;
  the direct shared-deadline, expired-journal and blocked-verifier tests passed
  **3/3**. D-09
  remains DEFECTIVE because native legacy/rollback/catalog cleanup and complete
  task-outcome evidence remain open.
- No P12 work was started. Working changes are limited to the registry deadline,
  its regression test and this evidence/matrix update.

## Previous checkpoint: 2026-10-22, P11 owned browser tools

## Current checkpoint: 2026-10-22, P11 owned browser tools

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Continue remaining P11 acceptance gates only.

- [E48](docs/completion/p11_browser_tools.md) implements and registers the six
  remaining missing names: `open_file`, `open_url`, `list_tabs`, `focus_tab`,
  `close_tab`, `download_status`. Native Edge/Chrome tests use separate PLUMA
  profiles, a private desktop and a loopback site; personal profiles and tabs
  are never attached. Live locked History DBs report unavailable; remote website
  effects and confirmed closed tabs are non-undoable.
- Native browser focused **12 passed (18.25s)**. Browser affected regression
  reached **204 passed / 1 failed (69.19s)**: an existing app-launch test hit
  intermittent private desktop teardown (`SetThreadDesktop`, WinError 0). The
  exact failed case passed on retry (**1 passed, 2.19s**); that fixture flake
  remains recorded rather than claiming the whole regression was green.
- The P11 acceptance-map refresh marks D-01/D-04/D-05/D-06/D-07/D-08 from
  their later native evidence. Catalog now has **57 registered / 16 unregistered;
  46 IMPLEMENTED / 16 MISSING / 1 DEFECTIVE / 10 UNVERIFIED**. No exact P11
  catalog name remains missing.
- Remaining gates are `undo_last` catalog-wide evidence; D-02 focus and D-03
  physical audio; D-09 whole-call timeout/cleanup; D-10 declared adapter retry;
  A-07 factual-copy coverage; and applicable H-01/H-02/H-04/H-05/H-06/H-07
  portions. Ten exact tools stay UNVERIFIED: focus_app/focus_window, four audio
  changes and lock/sleep/restart/shutdown. H-04 exact-operation backend approval
  and H-05 allowlisted elevation dispatch remain open in P11; native confirmation
  and UAC UI wiring/evidence belongs to P16. No waiver exists; P11 is incomplete.
- Owner clarification: open_terminal only opens PowerShell; commands are entered
  manually. Empty typed arguments, no terminal typing/client automation, cwd
  control or elevation. Fixed native new-console launch uses existing Job/STOP
  ownership and original process readback. See [E47](docs/completion/p11_terminal_open.md).
- Native focused **7 passed (2.45s)**; affected regression **364 passed (44.60s)**.
  Process success persistence, STOP drain and schema-before-policy are covered.
  Obsolete terminal routes now resolve to open_terminal. Live terminal inverse
  refuses when no safely attributable GUI-close target exists; no force fallback.
- At E47 the catalog was **51 registered / 22 unregistered; 40 IMPLEMENTED /
  22 MISSING / 1 DEFECTIVE / 10 UNVERIFIED**. E48 is the current count above.
- E47 source parent `99255f9`; E48 is pushed as `250827b`. Continue only the
  remaining P11 acceptance gaps above; no personal profiles/settings, UI redesign,
  action-entry enabling, P12, or repeated completed audits.

## Previous checkpoint: 2026-10-22, P11 owned persistent application launch

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Continue every remaining P11 tool.

- [E46](docs/completion/p11_app_launch.md): open_app uses closed System32 aliases,
  parent-owned suspended creation and a separate kill-on-close Job, with native
  process/image/window readback. Only verified success promotes/preserves the app;
  STOP/failure drains owned trees. Manual undo closes only its matching instance,
  with no force fallback. Broker handoff/early exit retains unknown effects rather
  than claiming a personal instance. No arbitrary argv/path/cwd/admin/test-mode API.
- Affected regression **261 passed (101.42s)**; final focused **16 passed (8.08s)**;
  raw audit **15 (0.74s)**, containment **3 (3.62s)**, recovery **5 (0.79s)**.
  Failed promotion/containment, original-handle drain, true process exit after Job
  empty, text/voice, native persistence/undo and factual residuals are covered.
  E46 retains diagnostic failures/corrections and exact fixture cleanup evidence.
- Catalog **50 registered / 23 unregistered; 39 IMPLEMENTED / 23 MISSING /
  1 DEFECTIVE / 10 UNVERIFIED**. Seven P11 names missing: open_file;
  open_terminal; open_url/list_tabs/focus_tab/close_tab/download_status. Physical
  focus2/audio4/system4, full undo_last and remaining A/D/H evidence stay open.
- Source parent `b6aea5b` (pushed E45). Commit/push and CONTINUE, no partial final.
  Next open_terminal reuses this parent launcher; then owned Edge/Chrome CDP and
  browser-backed PDF/file viewing close all missing exact names. Scope decisions
  already delegated; no questions, no P12, no personal profiles/settings, no UI
  redesign/action enabling. Existing ignored output/p11_power_actions/
  CONTINUATION_PLAN.txt records implementation choices/API checks for resumption;
  it is a draft work plan, not acceptance evidence. Do not restart completed audits.


## Previous checkpoint: 2026-10-22, P11 guarded native focus implementation

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Continue remaining P11 only.

- [E45](docs/completion/p11_window_focus.md): focus_window/focus_app now use exact
  or uniquely resolved targets, native foreground/placement guards, required owned
  workers, durable minimum pre-state, independent readback and conflict-safe undo.
  Legacy title-first matching, unconditional restore and non-Windows success are
  removed. Windows foreground restrictions are respected without input bypass.
- Explicitly inert focus fixture **15 passed (1.11s)**; affected regression
  **158 passed (84.70s)** including native window-state/geometry/app-close and
  shared policy/undo checks. Actual exits/fixture keys zero; source hashes match.
  Native private-desktop probe was refused by Windows; original interactive
  foreground stayed unchanged and owned cleanup completed. No physical focus
  success is claimed, no restriction is weakened and no further owner question
  is needed. Native permitted active-desktop acceptance remains UNVERIFIED.
- Catalog unchanged: **50 registered / 23 unregistered; 38 IMPLEMENTED /
  23 MISSING / 1 DEFECTIVE / 11 UNVERIFIED**. Seven P11 names missing: open_file;
  open_terminal; browser five. Remaining open_app implementation/ownership must
  be repaired next, then all missing exact tools. Physical audio/system/focus,
  full undo_last and A/D/H evidence stay open; no acceptance waiver inferred.
- Source parent `ff75cfe` (pushed E44). Commit/push this checkpoint and continue
  P11 owned persistent launch implementation. Use docs/prior commits, no more
  questions, no tool omissions, no P12, no UI redesign/action-entry enabling.


## Previous checkpoint: 2026-10-22, P11 native application close

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Continue all remaining P11 tools.

- [E44](docs/completion/p11_app_close.md): close_app now uses the existing exact
  native process-close adapter, strict PID/creation time or unique executable
  name, policy, non-undoable durable intent and independent exit readback.
  Refusal/unsaved dialogs/timeouts never force-close anything. Legacy taskkill
  and broad name termination are removed. No reconstructive undo is promised.
- Focused **13 passed (12.13s)**; affected regression **204 passed (93.03s)**,
  including native close/refusal, unrelated process preservation, denied/schema,
  text/voice, existing process controls, policy/journal and raw audit assertions.
  Actual exits/fixture keys zero, source hashes match. No user app was closed.
- Catalog **50 registered / 23 unregistered; 38 IMPLEMENTED / 23 MISSING /
  1 DEFECTIVE / 11 UNVERIFIED**. Seven P11 names missing: open_file;
  open_terminal; browser five. open_app/focus_app/focus_window, physical audio/
  system, full undo_last and remaining A/D/H evidence remain open.
- Source parent `ccbfd6c` (pushed E43). Commit/push this checkpoint, then continue
  P11 focus and owned persistent launches, followed by all missing exact tools.
  Owner delegated choices, requires no questions and no P11 tool omissions.
  Preserve personal resources, immutable specs, other worktrees and disabled
  action entry. No P12 work or premature overall completion claim.


## Previous checkpoint: 2026-10-22, P11 native cross-volume move

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Continue every remaining P11 tool.

- [E43](docs/completion/p11_cross_volume_move.md): move_file now supports bounded
  cross-volume regular files using verified copy followed by Recycle Bin recovery.
  Source is never permanently deleted; streams and exact created destination are
  verified. Manual and owned STOP undo preserve newer content and original paths.
  Cross-volume folders refuse before copying; same-volume folders still work.
- Native C:/D: focused **8 passed (11.18s)**; final affected regression **151 passed
  (92.58s)** including 10 final cross-volume/stream-guard tests. E43 records the
  preserved receipt-immutability failure and repaired alternate-stream copy-undo
  sharing defect, plus exact recovery of its four initial fixture originals.
  All source hashes/exits/fixture keys match; no personal files were mutated.
- Catalog **50 registered / 23 unregistered; 37 IMPLEMENTED / 23 MISSING /
  1 DEFECTIVE / 12 UNVERIFIED**. Seven P11 names missing: open_file;
  open_terminal; browser five. App lifecycle/focus, physical audio/system, full
  undo_last and remaining A/D/H evidence remain open. E42 is pushed in `b90b71b`.
- Source parent `b90b71b`. Commit/push this checkpoint and continue remaining P11
  app/focus and launch ownership, followed by open_file/open_terminal/browser.
  Owner requires no more questions, docs/prior commits for choices, every tool
  implemented, no P12 and no overengineering. Preserve personal data/settings,
  immutable master, other worktrees and disabled action entry.


## Previous checkpoint: 2026-10-22, P11 guarded window state

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Continue all remaining P11 tools.

- [E42](docs/completion/p11_window_state.md): minimize/maximize/restore now use
  exact native identity, captured placement, stable independent readback and
  conflict-safe manual/owned STOP undo. No ambiguous title-first match, no-op
  verifier or non-Windows success. Active target is rechecked before commit;
  mutation requires an owned journal. Native windows stay on a never-visible
  test desktop; fixture processes are contained before resume and drained.
- Final affected regression **171 passed (100.79s)**; commit-focused **19 passed
  (29.29s)**; raw audit **15 passed (0.73s)**. Retained initial failures/repairs
  and final source provenance are in E42. Clipboard E41 is pushed in `b92a438`.
- Catalog **50 registered / 23 unregistered; 36 IMPLEMENTED / 23 MISSING /
  1 DEFECTIVE / 13 UNVERIFIED**. Seven P11 names missing: open_file;
  open_terminal; browser five. Focus/app lifecycle, cross-volume move, physical
  audio/system, full undo_last and remaining A/D/H evidence remain open.
- Source parent `b92a438`. Commit/push this checkpoint and continue P11. The owner
  explicitly requires no questions and no P11 tools left out. Use docs/prior
  commits for choices. Next bounded gap: native cross-volume file move using the
  existing verified copy and Recycle Bin recovery adapters. No permanent source
  deletion, user-data tests, P12, design changes or action-entry enabling.


## Previous checkpoint: 2026-10-22, P11 plain-text copy/paste completed

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Continue remaining P11 only.

- [E41](docs/completion/p11_clipboard_text.md): clipboard_set/clear and their
  compatibility names now copy/clear Unicode text with native readback, minimum
  volatile RAM undo, newer-copy conflict refusal and redacted factual history.
  Actual paste into an owned EDIT control succeeds after the tool worker exits.
  Plain-text only, as the owner requested; no image/file-list expansion.
- Final native focused **26 passed (60.83s)**; affected regression **274 passed
  (139.59s)**; corrected legacy FAST journal fixture **1 passed (1.42s)**.
  Raw audit **15 passed (0.80s)**, containment **3 passed (3.40s)**, recovery
  **5 passed (0.70s)**. Original clipboard sequence unchanged; same user/integrity,
  no profile loading; owned Job zero; actual exits/fixture keys zero.
  No completed audit was restarted. E41 records the single fixture correction.
- Catalog **50 registered / 23 unregistered; 33 IMPLEMENTED / 23 MISSING /
  1 DEFECTIVE / 16 UNVERIFIED**. Seven P11 names missing: open_file;
  open_terminal; open_url/list_tabs/focus_tab/close_tab/download_status.
  Full undo_last, app/window lifecycle, cross-volume move, physical audio/system
  and remaining A/D/H gates stay open. Clipboard undo expires on process restart
  or bounded cache eviction; missing private proof refuses before claiming undo.
- Source parent `049c0e9`. Commit/push this verified checkpoint, then continue
  bounded remaining P11 work. Do not declare P11 finished, begin P12, enable action
  entry, redesign UI, change immutable specs or mutate personal resources in tests.


## Previous checkpoint: 2026-10-22, P11 plain-text clipboard read

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Continue remaining P11 only.

- Owner correction: **plain-text copy/paste only**; file-list/bitmap/rich-format
  expansion is removed. [Scope decision](docs/completion/p11_scope_decisions.md).
  The owner delegated implementation choices and asked for no more questions.
  Required readback/privacy/safe undo remain; no locked master requirement changed.
- [E40](docs/completion/p11_clipboard_read.md) implements clipboard_get and its
  READ compatibility name in owned native workers with sequence/owner/content
  readback. Payloads are private to the caller, redacted from SQLite and prompts.
  Prior-result prompt redaction is fixed. No production image/file-list feature.
- Final focused **25 passed (10.69s)**, affected regression **179 passed (31.81s)**,
  raw --runxfail **15 passed (0.78s)**. Final exits/hashes match, keys zero;
  matrix 298/324 PASS, diff check PASS. Native text/voice and blocked-worker checks.
- Native isolation is resolved: fixture-only fresh same-user/same-integrity local
  logon, private create-only window station, no elevation/profile/account/network
  operations. Original WinSta0 sequence unchanged; owned Job processes zero.
  No need to ask for a VM/sign-in again. Earlier fixture failures remain in E40.
- Catalog **49 registered / 24 unregistered; 31 IMPLEMENTED / 24 MISSING /
  2 DEFECTIVE / 16 UNVERIFIED**. Eight P11 missing names: open_file;
  clipboard_set; open_terminal; browser five. Clipboard clear/undo and remaining
  app/window/cross-volume/audio/system/A/D/H checks remain open.
- Source parent `12d11f9`. Commit/push this verified recovery point, then finish
  plain-text write/clear with minimum volatile undo and conflict checks. No format
  expansion, P12 work, new visual design, action-entry enabling or acceptance waiver.


## Previous checkpoint: 2026-10-22, P11 shared argument validation

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Continue remaining P11 only.

- [E39](docs/completion/p11_argument_validation.md) makes PlanValidator use the
  registry's complete registered-schema validation. Dictionary arguments no longer
  pass with only required-key checks; unavailable/unsupported validators refuse.
  Argument failures omit private Pydantic input values. A-03 bounded invariant is
  implemented; actual model/configured-step-limit gates remain P13, untouched.
- Before: **24 failures / 89 passes**. After: focused **113 passed (1.41s)**;
  affected regression **161 passed / 1 elevation deselected (9.40s)**; raw
  --runxfail **15 passed (0.72s)**. Actual final exits/hashes match, fixture keys
  zero, matrix 298/324 PASS, diff check PASS. No device/model mutation performed.
- Power implementation and missing-policy guard are committed/pushed in
  `791853d` ([E38](docs/completion/p11_power_actions.md)): 477 affected passes,
  native read-only/inert transition evidence. Physical power effects remain U.
- Catalog unchanged: **48 registered / 25 unregistered; 30 IMPLEMENTED /
  25 MISSING / 2 DEFECTIVE / 16 UNVERIFIED**. Nine P11 missing names:
  open_file; clipboard_get/set; open_terminal; open_url/list_tabs/focus_tab/
  close_tab/download_status. App/window mutations, cross-volume move, physical
  audio/system, clipboard clear/full undo and remaining A/D/H gates stay open.
- Source parent `791853d`. Commit/push this verified recovery point. Next safe
  bounded P11 milestone: private in-memory clipboard capture/undo and isolated
  native clipboard fixtures, followed by its three typed tools. Do not mutate
  the user's clipboard for tests or infer a format/undo acceptance waiver.
  Preserve other worktrees, personal data/settings, immutable specs and disabled
  action entry. No P12 eligibility or full P11 completion claim.


## Previous checkpoint: 2026-10-22, P11 confirmed native system requests

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Continue remaining P11 only.

- [E38](docs/completion/p11_power_actions.md) registers lock/sleep/restart/shutdown
  with strict HIGH material confirmation, owned bounded native execution,
  non-undoable durable intent and separate native readback. No forced app closing,
  remote target, unrestricted command, UAC or global policy changes. Accepted OS
  effects cannot be promised reversed. Missing-policy dispatch now refuses before
  capture; the four-case inert bypass reproduction and repair are retained.
- Focused **154 passed (47.56s)**; final affected regression **477 passed / 1
  elevation deselected (145.68s)**, including combined P10 native owned fixtures.
  Raw --runxfail 15 (0.49s), containment 3 (3.39s), recovery 5 (0.57s).
  Final source hashes/exits match, fixture keys zero; matrix 298/324 PASS.
  Fixture setup failures/corrections are retained in E38; assertions preserved.
- Native system probes were read-only; transition tests use explicitly inert
  interfaces. No active-session power action was performed. Actual physical
  effects, shutdown event timing and long-sleep acceptance remain UNVERIFIED.
  The owner's commit-behavior decision is resolved, not an acceptance waiver.
- Catalog **48 registered / 25 unregistered; 30 IMPLEMENTED / 25 MISSING /
  2 DEFECTIVE / 16 UNVERIFIED**. Four system rows move MISSING -> UNVERIFIED.
  Sixteen P12 names untouched; **nine P11 names missing**: open_file;
  clipboard_get/set; open_terminal; browser five. App/window mutations,
  cross-volume move, physical audio/system, clipboard clear/full undo and A/D/H
  gates remain open. No P12 eligibility or full-product completion claim.
- Source parent `a7e4f7d` (pushed E37). Commit/push this verified checkpoint.
  Next safe bounded P11 work: shared argument validation before policy/planning,
  then remaining native tool/undo gaps. Preserve other worktrees, personal data,
  disabled action entry, immutable specs and recovery points.


## Previous checkpoint: 2026-10-22, P11 native app/window reads

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Continue remaining P11 only.

- [E37](docs/completion/p11_app_window_reads.md) implements bounded owned native
  list_apps/app_status/list_windows, exact PID/creation-time status, distinct
  same-name instances, explicit unavailable entries and independent readback.
  No dummy/tasklist/no-op READ paths. Caption errors/undecidable truncation refuse;
  native snapshots/limits are factual, not complete immutable-desktop claims.
- Focused **108 passed (34.63s)**; final regression **415 passed / 1 elevation
  deselected (79.58s)**, including the final caption-error case. Raw --runxfail
  15 (0.39s), containment 3 (2.78s), recovery 5 (0.43s). Final hashes/exits/keys
  and corrected native helper-window test assumptions are recorded in E37.
- Catalog **44 registered / 29 unregistered; 30 IMPLEMENTED / 29 MISSING /
  2 DEFECTIVE / 12 UNVERIFIED**. Sixteen missing P12 names untouched; **13 P11
  names missing**: open_file; system four; clipboard get/set; open_terminal;
  browser five. App/window mutations, cross-volume move, physical audio and
  clipboard/undo/A/D/H acceptance stay open.
- Power behavior is RESOLVED: owner selected native initiation after material
  confirmation, without forcing apps closed, with irreversible/uncertain effects
  recorded. [Decision](docs/completion/p11_scope_decisions.md). Do not re-ask.
  Next bounded P11 work: native system actions with real readback and inert
  transition fixtures. Do not disrupt the active user session for automation.
- Source parent `f29c0fc` (pushed E36). Commit/push this verified checkpoint.
  Preserve other worktrees, personal data/settings, disabled action entry and
  immutable specs. No completion waiver or P12 eligibility is inferred.

## Previous checkpoint: 2026-10-22, P11 native stream conflicts and inverse ownership

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Continue remaining P11 only.

- [E36](docs/completion/p11_move_stream_guards.md) fixes four reproduced native
  move/rename undo failures after alternate-stream edits with restored primary
  timestamps. Snapshots now cover all bounded data streams and attributes;
  directory ADS refuse before mutation. The original DELETE guard remains;
  secondary stream sharing and outside-rename refusal have native evidence.
- Guarded file/folder/window-geometry automatic inverses now use the same closed
  bounded capsule-owned cleanup worker as audio/recycle. Newer edits/legacy
  inadequate receipts refuse; unknown effects remain residual. rename_file is
  bounded IMPLEMENTED; cross-volume move_file semantics remain UNVERIFIED.
- Focused **141 passed (38.92s)** plus boundary **2 passed (1.53s)**; final
  affected regression **463 passed (92.61s)**, including both new boundary tests.
  Raw --runxfail 15 (0.42s), containment 3 (2.73s), recovery 5 (0.43s).
  Final source hashes/exits/fixture keys and retained failures are recorded in E36.
- Catalog **44 registered / 29 unregistered; 27 IMPLEMENTED / 29 MISSING /
  2 DEFECTIVE / 15 UNVERIFIED**. Sixteen missing P12 names untouched; **13 P11
  names missing**: open_file; system four; clipboard get/set; open_terminal;
  browser five. Remaining app/window/file/audio, clipboard/undo and A/D/H gates open.
- Owner decision pending: after exact material confirmation, should sleep/
  restart/shutdown requests initiate native operations without force-closing
  apps (recommended), or open Windows power UI for the owner to complete?
  AGENTS ambiguity rule applies. Do independent remaining P11 work while waiting;
  do not implement a guessed power commit behavior or infer an acceptance waiver.
- Source parent `10b39eb` (pushed E35). Commit/push this verified recovery point;
  continue remaining P11 only. Preserve other worktrees, disabled action entry,
  personal data/settings, immutable specifications and all recovery points.

## Previous checkpoint: 2026-10-22, P11 bounded native file search

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Continue remaining P11 only.

- [E35](docs/completion/p11_file_search.md) replaces find_file's implicit root
  and no-op verifier with strict explicit-root/basename/type/time criteria,
  owned bounded native enumeration, candidate/directory identities and independent
  readback. Duplicates remain distinct; limited results cannot claim uniqueness.
  Missing/access/reparse/replacement conflicts fail closed. No automatic action.
- Focused **82 passed (20.74s)**; affected regression **424 passed /
  1 elevation deselected (72.63s)**. Raw --runxfail 15 (0.40s), containment 3
  (2.79s), recovery 5 (0.45s). Actual exits zero; hashes match; fixture keys zero.
  Real owned native text/voice/SQLite, junction and STOP/timeout evidence is in E35.
- Catalog **44 registered / 29 unregistered; 26 IMPLEMENTED / 29 MISSING /
  2 DEFECTIVE / 16 UNVERIFIED**. Sixteen missing P12 names untouched; **13 P11
  names missing**: open_file; system four; clipboard get/set; open_terminal;
  browser five. Remaining legacy app/window/file/audio, clipboard/undo and
  A/D/H gates stay open. Full §26.3 planner/file-story acceptance is not inferred.
- Source parent `b524b04` (pushed E34). Commit/push this verified checkpoint;
  continue remaining P11 guarded native inverse/file gaps. Preserve other
  worktrees, personal settings, disabled action entry and immutable specifications.

## Previous checkpoint: 2026-10-22, P11 guarded audio and default-device tool

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Continue remaining P11 only.

- [E34](docs/completion/p11_audio_guards.md) guards volume/mute/unmute with
  captured endpoint and exact before/after state, independent current readback,
  newer-edit conflict refusal and unrounded-scalar undo. Legacy unsafe receipts
  are refused. Automatic inverses run in bounded capsule-owned cleanup workers;
  durable manual undo remains at-most-once with native/SQLite readback.
- set_default_audio_device is now registered: exact endpoint/direction/role,
  MEDIUM approval, active-target check, native default readback and guarded undo.
  Real current-endpoint selection does not change settings. Isolated transition
  fixtures are not physical evidence: all four audio mutation rows remain
  UNVERIFIED pending actual physical changes. No acceptance waiver is inferred.
- Focused **118 passed (27.14s)**; final affected regression **450 passed /
  1 elevation deselected (123.39s)**. Raw --runxfail 15 (0.51s), containment 3
  (3.26s), recovery 5 (0.55s). Exact commands/hashes/limits are recorded in E34.
- Catalog **44 registered / 29 unregistered; 25 IMPLEMENTED / 29 MISSING /
  2 DEFECTIVE / 17 UNVERIFIED**. Sixteen missing P12 names are untouched;
  **13 P11 names missing**: open_file; system four; clipboard get/set;
  open_terminal; browser five. Legacy native/inverse/A/D/H gates remain.
- Source parent `8fc1d02` (pushed E33). Commit/push this verified checkpoint;
  then continue P11's find_file bounded native candidates/readback gap. Preserve
  all worktrees, disabled action entry, personal settings and immutable specs.

## Previous checkpoint: 2026-10-22, P11 controlled command tools

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Continue remaining P11 only.

- [E33](docs/completion/p11_terminal_commands.md) implements run_command and
  run_powershell as closed read-only diagnostic IDs, plus a separate typed
  run_project_command for private owner configuration and exact HIGH approval.
  No planner command strings, profiles, policy bypass or elevation. Native
  suspended creation, ownership/Job before resume, bounded pipes/deadlines,
  native exit/tree/output readback and factual non-undoable intents are covered.
- Raw command output is redacted from history/model prompts; durable intents
  store IDs/digest only. Safe process adoption checks exact live handles and
  original task Job membership; no raw PID taskkill fallback. Legacy app
  lifetime/inverse acceptance remains open. Shared fixture readiness is atomic.
- Final focused **49 passed (33.19s)**; affected regression **405 passed /
  1 elevation deselected (158.04s)**. Raw --runxfail 15 (0.85s), native
  containment 3 (3.18s), recovery 5 (0.64s). Exact commands, retained failures,
  source hashes and isolated-storage provenance are in E33/output.
- Catalog **43 registered / 30 unregistered; 25 IMPLEMENTED / 30 MISSING /
  2 DEFECTIVE / 16 UNVERIFIED**. Sixteen untouched P12 names; **14 P11 names
  missing**: open_file; default audio device; system four; clipboard get/set;
  open_terminal; browser five. Legacy native/inverse and A/D/H gates remain.
- Source parent `0f2fd87`; commit/push this verified recovery point on ui-wiring.
  Preserve other worktrees, UI/action-entry boundaries and immutable documents.
  Next safe work is a remaining P11 tool plus its guarded inverse/native proof,
  not P12. No full milestone completion or owner waiver is claimed.

## Previous checkpoint: 2026-10-21, P11 folder and interrupted recycle recovery

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Owner requested all remaining P11.
Use PLUMA_COMPLETION_PROMPTS.md and its shared contract; no completion waiver.

- [E32](docs/completion/p11_recycle_recovery.md) closes safe_delete's bounded
  folder and interrupted-receipt recovery gaps with native identity/stream/tree
  evidence. Recycle Bin only; no permanent fallback. Directory data streams,
  reparse/offline/encrypted/hard-linked files, unsupported volumes and bounds
  fail closed. Stable content and separate revision digests preserve conflicts.
- STOP drains the original executor, then a bounded capsule-owned inverse
  worker recovers only the exact captured identity. Worker timeout/failed
  cleanup retains ownership and factual residuals. Manual pending recovery
  refuses a live/unverified original executor. Initial durable action IDs now
  prevent the observed STOP read/claim race; no weakened claim or undo checks.
- Final focused **33 passed (14.32s)**; affected regression **466 passed /
  1 elevation deselected (146.21s)**. Raw --runxfail 15 (1.44s), native
  containment 3 (5.64s), recovery 5 (1.41s). Actual exits zero, source hashes
  match, fixture keys/Bin residues zero. Matrix 298 source items / 324 rows PASS.
  E32 retains initial failures, recovery, exact commands and provenance.
- Catalog **41 registered / 32 unregistered; 23 IMPLEMENTED / 32 MISSING /
  2 DEFECTIVE / 16 UNVERIFIED**. Sixteen untouched P12 gaps; **16 P11 names
  still missing**, plus remaining legacy/native inverse and A/D/H acceptance.
  Remaining: open_file; default audio device; system four; clipboard get/set;
  terminal three; browser five. Full undo/clipboard clear remain defective.
- E32 source parent: pushed `f584823`. Commit containing this checkpoint is
  the next recovery point on ui-wiring; commit/push verified coherent changes.
  Preserve all other worktrees/main/integration/recovery points/draft PRs.
- Continue remaining P11 tools and their actual native/policy/undo evidence.
  This checkpoint does not authorize P12 or action entry. No personal data,
  clipboard/audio/power/security settings, dependency, UI or immutable spec change.

## Previous checkpoint: 2026-10-21, P11 recycle-only regular files

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Owner authorized remaining P11.
PLUMA_COMPLETION_GUIDE.md is absent; use PLUMA_COMPLETION_PROMPTS.md and its
shared contract. This is the next bounded P11 gap, not full milestone completion.

- Owner answered **"Windows Recycle Bin only (recommended)"**. Refuse
  unrecyclable targets; no permanent-delete fallback or PLUMA quarantine.
  [Decision](docs/completion/p11_scope_decisions.md) is resolved, not pending.
- [E31](docs/completion/p11_recycle_bin.md) adds typed HIGH exact-call approval,
  owned native RecycleItem, captured parent/file/all-stream identity, exact Bin
  receipt readback and guarded durable manual/automatic restore. Newer original
  path/parent/Bin content conflicts are preserved, including native refusal of
  a destination created after precheck. No shell/admin/elevation/global Bin undo.
- Supported regular files on fixed NTFS, single-link/non-reparse/online/
  unencrypted, bounded streams. Folders/other targets remain refused. An
  interruption after Shell commit but before final receipt retains uncertain
  pending intent; no guessed inverse/clean STOP. These remaining gaps are not
  owner-approved exemptions. safe_delete stays UNVERIFIED in the matrix.
- Final focused **22 passed (7.43s)**, wall 8.478s. Affected regression
  **343 passed / 1 elevation deselected (118.25s)**, wall 119.322s. Raw audit
  --runxfail 15 (0.53s), native containment 3 (3.67s), recovery 5 (0.56s).
  Actual exits zero; isolated keys zero; runtime/test hashes match; matrix
  298 source items / 324 rows PASS. No elevation/physical/global gate waiver.
  Exact commands, failures/recovery and provenance are recorded in E31/output.
- Catalog **41 registered / 32 unregistered; 22 IMPLEMENTED / 32 MISSING /
  2 DEFECTIVE / 17 UNVERIFIED**. Sixteen untouched P12 missing names;
  **16 P11 names missing**, plus partial safe_delete, legacy/native inverse and
  A/D/H gates. Remaining names: open_file; default audio device; system four;
  clipboard get/set; terminal three; browser five. No full completion waiver.
- Source parent is pushed `a654ebd`; commit/push this bounded E31 on ui-wiring.
  The next commit containing this checkpoint is the E31 recovery point.
  Preserve other worktrees/main/integration/recovery/draft PRs. Owned temporary
  files only; all eight initial failed/probe fixture Bin residues were restored.
  No personal files, clipboard/device/power/security/UI/dependency/spec change.
- Next safe milestone is remaining **P11** safe_delete target and interrupted
  receipt recovery coverage, then other listed required tool/inverse gates.
  Do not begin P12 or enable action entry.

## Previous checkpoint: 2026-10-21, P11 native window geometry

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Owner authorized remaining P11.
PLUMA_COMPLETION_GUIDE.md is absent; use PLUMA_COMPLETION_PROMPTS.md, which
contains the established shared contract. Do not misstate the whole milestone.

**Next bounded gap paused for an owner requirement decision:** safe_delete's
recovery policy is undefined in the master. Per AGENTS.md ambiguity rule, asked
Recycle Bin only (recommended, refuse unrecyclable/no permanent fallback) versus
PLUMA-managed private quarantine. Answer pending; a preselected option is not
approval. [Decision record](docs/completion/p11_scope_decisions.md). Completed
E28-E30 work is verified and pushed, latest code `b177440`; tree was clean.
P11 still has 17 missing names and open inverse/A/D/H checks; no completion waiver.

- [E30](docs/completion/p11_window_geometry.md) adds exact typed move_window and
  resize_window: HWND/PID/creation identity, normal top-level window, captured
  bounds/class/thread/DPI, required owned worker, exact readback and guarded
  manual/automatic undo. Newer geometry/identity/DPI refuses inverse. No focus,
  z-order, child-window or title-substring fallback. Coordinate_space=window_dpi
  explicitly denotes native target-DPI units, not fabricated physical pixels.
- Reviewed affected regression **348 passed (137.21s)**, wall 138.223s, includes
  all 18 final native geometry cases. Raw --runxfail 15 (0.54s), native
  containment 3 (3.63s), recovery 5 (0.56s). Actual exits zero, isolated keys
  zero, recorded runtime/test hashes match. Matrix source/link check passes.
  Initial worker DPI-rounding failures/diagnostics are retained in E30; exact
  success/undo assertions were preserved. No all-scale/multi-monitor, physical
  UI/device/elevation/model/performance/release certification inferred.
- Catalog **40 registered / 33 unregistered; 22 IMPLEMENTED / 33 MISSING /
  2 DEFECTIVE / 16 UNVERIFIED**. Sixteen untouched P12 names; **17 P11 names
  remain missing**, plus required legacy/native inverse and A/D/H checks.
  Remaining missing: file open/safe-delete; default audio device; system
  lock/sleep/restart/shutdown; clipboard get/set; terminal three; browser five.
  Clipboard clear/full undo catalog remain defective; sixteen native rows unverified.
- All mutations use owned hidden-window/process/file/SQLite fixtures. No UI
  appearance, disabled action entry, dependency, immutable specification,
  user window/input, clipboard/device/power/security or P12 change.
- E28 `f7a6833` and E29 `27bee2c` are pushed; E30 starts at `27bee2c`. Commit/push
  reviewed E30 on ui-wiring. Preserve other worktrees/main/integration/recovery
  points and draft PRs. Next safe milestone is remaining P11, never P12.

## Previous checkpoint: 2026-10-21, P11 native process control

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Continue remaining P11 only.
The referenced PLUMA_COMPLETION_GUIDE.md is absent; the established P11 contract
is PLUMA_COMPLETION_PROMPTS.md. The owner authorized finishing remaining P11.

- [E29](docs/completion/p11_process_control.md) adds exact typed same-user native
  graceful_close_process / terminate_process. Strict PID/creation time, exact
  MEDIUM approval, explicit force/data-loss acknowledgement, critical/session/
  resident/worker protection; native original-handle exit and independent readback.
  Graceful refusal/save prompts never trigger forced fallback. No shell/admin.
- ToolSpec.non_undoable journals durable intent before dispatch using existing
  action/intent storage with available=0, so it never offers an inverse. Parent
  capsule retains committed/unknown effect evidence for truthful STOP residuals.
  Missing journal/ledger/capture prevents dispatch. Internal supervisor identity
  crosses worker IPC, never a planner argument. No schema migration or UI change.
- Focused **20 passed (15.99s)**. Reviewed existing/new regression **427 passed /
  1 deselected (130.92s)**, wall 131.968s. Raw --runxfail 15 (0.48s), native
  containment 3 (3.12s), recovery 5 (0.52s). Actual exits zero, fixture keys zero,
  recorded runtime/test hashes match. Matrix source/link validation passes.
  Elevation deselection is not a pass/waiver. E29 records failed initial native
  fixture PID/window identity diagnostic and correction without weakened success
  assertions. Registered suspended fixture processes/native Jobs and hidden
  windows only; no personal application, window, clipboard or device/power mutation.
- Final schema review rejects integer 1/0 for force acknowledgement/copy
  overwrite despite Pydantic Literal coercion; both are covered before policy.
- Catalog: **38 registered / 35 unregistered; 20 IMPLEMENTED / 35 MISSING /
  2 DEFECTIVE / 16 UNVERIFIED**. Sixteen untouched P12 entries; 19 P11 names
  still missing. Remaining native/legacy inverse, ownership and A/D/H gates stay
  mandatory. No full P11, physical/elevation/UI/model/performance/release claim.
- E28 native copy/list/folder work is pushed as `f7a6833`; E29 starts there.
  Commit/push reviewed E29 on ui-wiring, preserving other worktrees, main,
  integration/recovery points and draft PR boundaries. Do not begin P12.
- Next safe P11 work: bounded native move_window/resize_window with exact target
  identity, geometry readback and conflict-safe undo on owned hidden fixtures.

## Previous checkpoint: 2026-10-21, P11 native file operations

**P11 IS NOT COMPLETE. P12 MUST NOT START.** Continue remaining P11 only.
The owner said PLUMA_COMPLETION_GUIDE.md; no such file exists here. The existing
PLUMA_COMPLETION_PROMPTS.md is the shared P11 execution contract.

- [E28](docs/completion/p11_file_operations.md) adds exact typed copy_file and
  list_folder with required owned native execution and independent readback.
  Copy is bounded/new-destination only, exact approval, preserved alternate
  streams and captured output identity. Guarded inverse preserves newer file,
  stream, directory and parent conflicts. No private stream names/content logged.
- create_folder now captures its existing anchor and all missing paths, creates
  exclusively with original returned native handles, records exact new IDs and
  reverses only empty captured directories. Existing folder is a verified no-op.
  Strict paths/bools and depth bounds precede effects; reparse/private path refusal.
- Registry accepts creation receipt additions without replacing any captured
  pre-state. Changed/omitted fields retain the pending journal and fail verified
  success; final backup-field edge case is covered. Automatic recipes/manual
  durable-claim undo include the new guarded file/folder receipts. Legacy full
  inverse/rollback bounds remain open; do not infer whole-catalog completion.
- Reviewed affected regression: **186 passed in 71.25s**, wall 72.053s.
  Raw --runxfail 15 (0.47s), native containment 3 (3.10s), recovery 5 (0.58s).
  Actual exits zero, fixture keys zero, all recorded source hashes match.
  Traceability 298 source items / 324 rows PASS. Earlier failed/preceding runs,
  fixes and exact provenance are retained in E28; E27 broad baseline is not an
  E28 whole-project run. No fabricated physical/device/elevation/release claim.
- Catalog: **36 registered / 37 unregistered; 18 IMPLEMENTED / 37 MISSING /
  2 DEFECTIVE / 16 UNVERIFIED**. Sixteen untouched P12 entries; P11-relevant
  missing count 21. Missing tools include process control, windows geometry,
  file open/safe-delete, audio default device, power, clipboard, terminal and
  browser; legacy native inverses/ownership and backend A/D/H gates still open.
- No UI appearance, disabled action entry, dependencies, immutable specification,
  user files/windows/clipboard/device/power/security settings or P12 changes.
  All mutations use owned temporary fixtures. Cross-volume/network/readonly-copy
  inverse acceptance remains open. Unknown interrupted effects stay residual.
- Started at pushed ui-wiring `17d17d2`; commit/push reviewed E28 on this branch.
  Preserve all other worktrees/main/integration/recovery points and draft PRs.
  Next safe work stays P11: bounded PID+creation-time process control with exact
  policy, original-handle exit readback and non-undoable commit evidence.

## Previous checkpoint: 2026-10-21, P11 storage/routines/global STOP implementation

**P11 IS NOT COMPLETE. P12 MUST NOT START.** The owner authorized completing
remaining P11 work and asked why the work packets are large. Continue actual
capability implementation in coherent batches; do not substitute repeated
whole-project audits for closing tools. P11 covers most of the action backend.
P12-P15 are likewise broad backend packets; P24-P29 are substantial integration,
physical/security/performance/packaging work. No later milestone is authorized.

- [E27](docs/completion/p11_storage_tools.md): Activity reads the actual ledger
  with bounded, redacted SQLite snapshots and fixed read failures. Registered
  STOP uses the real priority global latch-all service, also bound by standalone
  orchestrator composition. It distinguishes pending/residual from clean stop.
- Four missing memory tools implemented: save_preference, get_preference,
  create_routine, run_routine. Exact-call approval, required owned SQLite workers,
  journaled capture/CAS/readback/conflict-safe inverse; routines revalidate every
  saved call and share the capsule, policy, cancellation, budget and ledger.
  Completion checks actual child action rows. No nested/stored screen routines.
- Durable undo claims prevent duplicate or uncertain replays. Guarded memory
  and native file/folder move/rename inverses work; unsupported older pre-state
  stays refused/preserved. Native move uses captured file IDs/content/tree hash
  and parent binding; original usable-undo assertions remain. Same-volume,
  non-overwrite mode only; remaining file modes/catalog inverse gaps stay open.
  file_info now explicitly requires killable owned isolation without fallback.
- Counts: 34 exact names registered / 39 unregistered; all 73 catalog rows:
  15 IMPLEMENTED / 39 MISSING / 2 DEFECTIVE / 17 UNVERIFIED. Sixteen missing
  P12 entries untouched. Non-P12 missing count 23; clipboard_clear and the full
  catalog reach of undo_last remain defective. Native file rows retain UNVERIFIED
  despite tested guarded same-volume cases. No blanket waiver or full P11 claim.
- Focused final batch 151 passed (52.88s); native compatibility 23 (18.23s).
  First broad focused run: 827 passed / 1 failed / 1 excluded; usable-undo fixture
  and native identity support corrected without weakening assertions. First full
  regression: 1156 passed / 3 failed / 3 skipped / 1 excluded (215.39s). Explicit
  query / real-ledger Activity compatibility corrected; 21 targeted passes (3.40s).
  One original owned-worker cleanup failure is retained and not hidden: diagnostic
  original-case replay passed (0.99s), native job 3 members to 0 and original
  process handle signaled in about 63ms. No cleanup deadline/test relaxation;
  initial timing cause not established. Next broad run: 1158 passes / one FAST
  mute-emulation failure. Routing audio fixture now per-case inert memory; native
  audio/cleanup requirements remain unchanged. Broad regression **1159 passed / 3 skipped / 1 excluded in 219.60s**.
  Final review then made failed routines fatal to outer replanning: new proof
  verifies no prefix replay and rollback. Only multi_step.py/new memory test
  differ from the broad run; final affected memory/multi-step/journal suites
  **43 passed in 24.30s**. Current-source raw 15 (0.56s), containment 3 (3.36s),
  recovery 5 (0.55s), native IPC 39 (7.486s). Actual exits zero; final affected
  hashes match and broad differences are explicit; keys zero, 115 FAST isolated. Prior failures are
  retained, not counted as passes. Skips/excluded elevation remain separate.
- No UI appearance, immutable specification, dependency, physical desktop/device
  setting, unrestricted shell/admin or P12 change. Tests use isolated SQLite and
  owned fixtures; remaining native/physical gates remain explicit.
- Started pushed ui-wiring 5f1b1d9. Commit/push this reviewed batch only after
  checking actual exits/source hashes/keys/diff; then continue remaining P11.
  Migration adds claims only; older undo code must not open claim-bearing data.
  Preserve other worktrees/main/integration/recovery data and draft PR boundaries.

## Previous checkpoint: 2026-10-20, P00-P11 audit R01 repair

**P11 IS NOT COMPLETE. P12 MUST NOT START.** The renewed overall audit is
[here](docs/completion/p00_p11_audit.md). P00-P10 original bounded gates retain
supporting evidence; do not turn that statement into full-product certification.
Earlier P11 completion claims remain superseded.

- [E26](docs/completion/p11_worker_disposal.md) repairs audit R01: native owned
  worker disposal seals admission and verifies cleanup without recording a fake
  user STOP. Both FAST/SMART worker crashes finalize FAILED / internal_error;
  successful disposal retains SUCCEEDED / NULL in reopened SQLite. Genuine STOP
  and deadline preserve their first causes. No latch reset or cleanup waiver.
- Runtime scope: registry, TaskCapsule, both orchestrators and cancellation
  docstrings. New native disposal/history tests; existing cleanup Worker fixture
  gains the disposal interface and BA runtime-close Mock aliases it to its
  existing termination mock. Failure/readback and original BA assertions unchanged.
- Corrected pre-edit reproduction: 5 failed / 4 passed. Initial test setup had
  wrong PlanMode/ownership spellings (7 failed / 2 passed), transparently retained.
  After repair 9 passed. First broad run: 791 passed / 1 failed / 1 excluded;
  failure was the cleanup fixture's missing disposal method, now corrected.
- First full regression: 1109 passed / 1 failed / 3 skipped / 1 excluded; bare
  BA Mock interface wiring corrected, raw --runxfail then 15 passed.
- Final focused 792 passed / 1 excluded (105.68s); isolated regression 1110
  passed / 3 skipped / 1 excluded (161.90s); raw audit 15 (0.39s), containment
  3 (3.95s), recovery 5 (0.60s), native Python/C# IPC 39 (7.057s wall). Actual
  exits zero; final regression hashes match; focused runtime hashes match with
  the documented later test alias. All 115 FAST cases isolated, fixture keys
  zero. Independent reopened SQLite: 2 SUCCEEDED/NULL, 4 FAILED/internal_error.
  Matrix 298 source items / 324 rows PASS. Skips/excluded elevation are not passes.
- Catalog unchanged: 9 bounded READs / 27 missing non-P12 tools / 4 defective /
  17 unverified. Sixteen P12 perception/input tools remain untouched. Backend
  inverse/irreversible/ownership/privacy/elevation gates remain open. No waiver.
- No native UI, immutable specification, dependencies or user/device settings
  changed. Dark UI/action-entry boundary remains preserved. No P12 implementation.
- Started at pushed ui-wiring `0c2e8e6`; commit/push this reviewed repair on
  ui-wiring only. PRs 1/2 freshly checked draft/open/unmerged. Preserve
  main/integration, all four worktrees and recovery data.
  Recovery point: `0c2e8e6` in a separate detached worktree. Do not reset this one.
- Next safe milestone remains P11. A concrete bounded next step is repairing
  show_activity to use the task's actual ledger and fail closed on read errors,
  with isolated SQLite evidence. Do not begin that block automatically and do
  not start P12 without the owner's instruction.

## Previous checkpoint: 2026-10-20, overall P00-P11 audit and owned verification

**P11 IS NOT COMPLETE. P12 MUST NOT START.** The owner's renewed request is an
honest overall P00-P11 audit, completion of remaining P11 work and tested commits.
An earlier claim that P11 was finished was inaccurate; do not repeat it.

- [Overall audit](docs/completion/p00_p11_audit.md) reconciles prompts, source,
  registry, matrix and evidence. P00-P10 original bounded gates remain supported
  by fresh regression/raw/native evidence; this is not product certification.
- Exact catalog: 73 names, 30 registered / 43 unregistered. Sixteen missing
  perception/input entries belong to P12 and remain untouched. Other 57:
  **9 IMPLEMENTED / 27 MISSING / 4 DEFECTIVE / 17 UNVERIFIED**. Browser/terminal,
  clipboard, file/process/power and memory tools still require work. No waiver.
- [E25](docs/completion/p11_verification_ownership.md) repairs synchronous
  unbounded verifier/caller waits, late proof success, unsafe discard during an
  admission-observation race, SMART retry of uncertain effects, timeout cause
  after history failure, and unhandled private exceptions. Required verification
  uses the same native owned worker; legacy Futures stay owned until actual exit.
- Reproductions: blocked verifier 1 failed; private/false-timeout errors 4 failed.
  Expanded fixtures initially had 6 post-cleanup timing assumptions and then
  3 missing-observer wiring errors; preserved and corrected without xfail/skip or
  deadline relaxation. Final boundary **77 passed in 50.94s**, including 22 new
  cases. P01 admitted-body test is strengthened to interrupt caller before body
  exit, drain it explicitly, block late verification and retain unknown pre-state.
- Final-source focused **783 passed / 1 excluded in 103.29s**; isolated regression
  **1101 passed / 3 skipped / 1 excluded in 126.22s**; raw audit **15 in 0.38s**,
  containment **3 in 2.65s**, recovery **5 in 0.40s**. Native Python/C# IPC **39
  passed in 7.183s**. Actual exits zero, final hashes match, fixture keys zero,
  all 115 FAST cases isolated. Skips/elevation exclusion are not passes.
- **Audit R01 is open:** successful owned native fixture's reopened SQLite says
  SUCCEEDED / user_stop without user STOP. Normal worker disposal cancels its
  parent token. Separate admission closure from factual cancellation cause and
  verify fresh memory/result/history before closing the audit's next safety gap.
- Three runtime files (registry, two orchestrators), new verification tests and
  equivalent serializable existing fixtures. No user/device/settings mutation,
  native UI/immutable-spec/dependency change or P12 work. Docs record limitations.
- Terminal/browser/clipboard choices are already resolved in scope decisions.
  Existing A/D/H backend/catalog gaps remain; later native UI/planner/device
  assignments are recorded separately and not silently waived or implemented.
- Started pushed ui-wiring `2c5abf5`. Commit/push ui-wiring only; preserve other
  worktrees/main/integration/archives/stash/tags. Recovery: separate detached
  worktree at `2c5abf5`. Next safe work is P11 R01, then defective catalog and
  remaining typed tool/inverse/irreversible gates. P12 remains forbidden.

## Previous checkpoint: 2026-10-20, remaining P11: native system/network reads

P11 remains authorized and incomplete. **P12 is forbidden** until instructed.
No action enabling, merge or requirement waiver.

- Started clean/pushed ui-wiring `1a4137c` after 699 focused / 1017 isolated
  regression / 15 raw / 3 containment / 5 recovery passes. [E24](docs/completion/p11_system_status.md)
  reproduces CPU-read failure becoming verified zero and missing network_status:
  2 failures in 0.85s. Failed artifacts retained.
- New native system adapter reads a bounded CPU sample, available RAM and actual
  Windows system-volume bytes. get_system_status and compatibility system_status
  require owned killable workers, strict snapshots and correct result identity.
  No unavailable-data substitution. New network_status is typed/registered and
  available in SMART/DEEP schemas; bounded native link/MTU/speed/count snapshot,
  no addresses/SSID/credentials or outbound probes. Internet remains unknown.
- Initial repair 2 passed; expanded 52 passed / 1 failed when an immediate fake
  CPU sampler produced zero elapsed time, correctly rejected. Fixture now waits
  its requested interval without weakening assertions/deadlines; reviewed 62 pass.
- Final source: focused **761 passed / 1 excluded in 141.69s**; isolated regression
  **1079 passed / 3 skipped / 1 excluded in 174.22s**; raw audit **15 in 0.79s**,
  containment **3 in 3.58s**, recovery **5 in 0.74s**. Actual exits zero, final
  source hashes match, fixture keys zero, all 115 FAST cases isolated. Enlarged
  orchestration command bound 240s; per-test 20s and tool 5s deadlines unchanged.
  Skips/excluded elevation are not passes. No performance/soak/release claim.
- Native text/voice-mode requests, original Windows Job-worker identities/exit,
  actual SQLite and reopened history are verified. Alias/network SMART planner
  is explicitly inert; no physical STT/LLM claim. Fault/interface packets and
  blocking workers are disclosed fixtures. All native operations are read-only;
  no user/device/configuration mutation. UI and immutable contracts untouched.
- Runtime: new system adapter, system READ tools and schema subset only; one new
  62-case test module. Catalog **9 IMPLEMENTED / 43 MISSING / 4 DEFECTIVE /
  17 UNVERIFIED**. Other catalog actions, parent verifier bounds, identity/conflict-
  safe inverse, irreversible evidence and remaining A/D/H gates keep P11 open.
- Terminal scope remains fixed read-only diagnostics plus explicitly configured,
  confirmed project commands; no unrestricted planner shell. Browser/clipboard
  decisions remain recorded; dependent implementations are not claimed.
- PRs 1/2 freshly checked draft/open/unmerged. Commit/push ui-wiring only;
  preserve main/integration, other worktrees and archives/stash/tags. Recovery
  before this block: separate detached worktree at `1a4137c`. Next safe milestone
  is another bounded P11 verification/irreversible/inverse/catalog gap, with no
  new instruction needed between P11 blocks. P12 is not eligible or authorized.

## Previous checkpoint: 2026-10-20, remaining P11: native battery read

P11 remains authorized and incomplete. **P12 is forbidden** until instructed.
No action enabling, merge or requirement waiver.

- Starting clean/pushed ui-wiring `19b3ad3`; its 661 focused / 979 isolated
  regression / 15 raw / 3 containment / 5 recovery checks passed before edits.
  [E23](docs/completion/p11_battery_status.md) reproduces three battery failures:
  AC falsely implies charging, signed unknowns misreported, native failure returns
  verified success (3 failed in 0.43s). Failed artifacts preserved.
- New lazy native power adapter uses unsigned Windows fields and return-code
  checks. Typed battery_status READ now requires a killable owned worker and
  native snapshot verification. Charging is independent of AC; unknown states
  stay null; invalid/failed/unsupported native observations fail closed.
- Initial repaired test hit 3 fixture import errors from its fake DLL; importing
  the adapter before installing the read fixture fixes setup without weakening
  assertions. Corrected 3 passed, expanded 34 passed in 4.71s. Native text and
  voice-mode FAST requests, native Jobs/original identity/exit, actual SQLite and
  reopened history pass. Unknown/no-battery/errors/blocked calls are disclosed
  fixtures. No power transition, settings or user state is changed; no microphone
  or real STT claim.
- Final-source focused **699 passed / 1 excluded in 106.74s**; isolated regression
  **1017 passed / 3 skipped / 1 excluded in 130.30s**; raw audit **15 in 0.74s**,
  containment **3 in 3.08s**, recovery **5 in 0.59s**. Actual exits zero, final
  hashes match, fixture keys zero and all 115 FAST cases isolated. Skips and
  elevation exclusion are not passes. No performance/soak/release claim.
- Runtime changes: new power adapter and battery portion of system tools only.
  New 34-case battery module. Removed the EOF blank line flagged by E22's staged
  diff check; that earlier shell sequence incorrectly continued to commit after
  the check. Formatting is corrected and freshly checked, with no history rewrite.
- Catalog: **7 IMPLEMENTED / 44 MISSING / 4 DEFECTIVE / 18 UNVERIFIED**. Battery
  bounded READ row is implemented, not the whole gate. System/network reads,
  power requests, clipboard/browser/terminal, safe identities/inverses, verifier
  bounds, irreversible evidence and remaining A/D/H requirements remain P11.
- Terminal decision remains resolved: fixed read-only Windows diagnostics plus
  explicitly configured, confirmed project commands. No unrestricted planner shell.
- Commit/push ui-wiring only; preserve other worktrees/main/integration and all
  recovery archives/stash/tags. PRs 1/2 last checked draft/open/unmerged in E22.
  Recovery before this block: separate detached worktree at `19b3ad3`. Next safe
  work: bounded native system/network read gap, then remaining P11. No fresh
  instruction needed between P11 blocks. P12 is neither eligible nor authorized.

## Previous checkpoint: 2026-10-20, remaining P11: owned bounded pre-state

P11 remains authorized and incomplete. **P12 is forbidden** until instructed.
Do not enable action entry, merge or waive requirements.

- Started clean/pushed ui-wiring at `f4eea7b`. [E22](docs/completion/p11_prestate_ownership.md)
  reproduces caller-blocking pre-state outside the tool timer: corrected inert
  fixture 1 failed in 1.71s. Initial fixture/result setup error and runner-name
  mismatch are recorded, not counted as product evidence. Existing unchanged
  regression subset passed 822 / 3 skipped / 1 excluded before runtime edits.
- Capture now runs under capsule admission and owned lifetime. Required isolated
  tools use their existing killable worker/Jobs; serialization failure refuses
  without fallback. Legacy threads are tracked, bounded at the caller and retained
  until actual exit. STOP cannot dispatch late capture results. Capture and
  execution share the tool budget; policy/journal/cleanup waits remain separately
  bounded. Known no-execution history now has a two-second acknowledgement budget.
- Initial boundary 90 passed / 1 failed: privacy fixture local closure could not
  serialize. Equivalent module-level partial preserves all redaction assertions.
  Expanded 100 passed; reviewed boundary 101 passed. Thirteen new cases cover
  actual native capture STOP/deadline/exit, same-PID capture/execution, retained
  thread/storage ownership, no fallback, invalid/private errors and shared budget.
- Final-source focused **661 passed / 1 excluded in 97.83s**; isolated regression
  **979 passed / 3 skipped / 1 excluded in 125.54s**; raw audit **15 in 0.55s**,
  containment **3 in 3.10s**, recovery **5 in 0.56s**. Actual exits zero, final
  source hashes match, fixture keys zero, all 115 FAST cases isolated. Skips and
  excluded elevation are not passes or native acceptance. No performance claim.
- Only registry runtime changes; new tests plus serializable prior privacy fixture.
  No UI/dependency/immutable-contract or user device/state changes. Real Jobs and
  owned marker I/O are exercised; thread/error/history barriers are explicit.
- Owner terminal decision is resolved: fixed read-only Windows diagnostics plus
  explicitly configured, confirmed project commands. [Scope decisions](docs/completion/p11_scope_decisions.md)
  records the answer. No unrestricted planner shell or planner-created permission.
- Catalog remains **6 IMPLEMENTED / 44 MISSING / 4 DEFECTIVE / 19 UNVERIFIED**.
  Parent verifier ownership/bounds, identities/conflict-safe inverse, irreversible
  evidence and remaining catalog/A/D/H gates are still P11 work. D-09 remains open.
- PRs 1/2 freshly rechecked draft/open/unmerged. Commit/push ui-wiring only;
  main/integration, other worktrees, archives/stash/tags preserved. Recovery before
  this block: separate detached worktree at `f4eea7b`. Next safe work remains P11,
  bounded verification and native typed-tool/inverse gaps; no new instruction
  needed between authorized P11 blocks. P12 is not eligible or authorized.

## Previous checkpoint: 2026-10-20, remaining P11 in progress: mutation journal

P11 remains authorized and incomplete. **P12 is forbidden** until the owner's
instruction. Do not enable action entry, merge or waive missing requirements.

- Started clean/pushed ui-wiring at `2f5e87c`. The preceding 631 focused / 949
  regression / 15 raw / 3 containment / 5 recovery checks passed before edits.
  [Mutation journal E21](docs/completion/p11_mutation_journal.md) reproduces an
  actual owned rename left after STOP with zero undo records and persisted
  STOPPED (1 failure in 1.76s). Failed artifacts preserved; owned worker drained.
- Minimum pre-state now publishes/persists/readbacks before executor dispatch.
  Verified success atomically upgrades the same action/inverse. Unknown partial
  effects retain a non-executable pending recipe and residual outcome; no blind
  inverse. History failure cannot report success or trigger SMART replan/next
  step. Rejected admission consumes unused pre-state; thread deadlines latch
  TASK_TIMEOUT. Failed verifier copy is factual; worker snapshots cannot erase
  parent journals. Verified DB inverse can consume its exact pending memory row.
- Five runtime files change (registry, activity, rollback engine/recipes,
  multi-step); new 16-case journal tests and one existing cleanup fixture change.
  No migration, dependency, UI or immutable contract change.
- Expanded fixture run had 2 plan-schema setup failures / 12 passes; corrected
  DIRECT to MULTI_STEP without changing product schema/assertions. Boundary set
  passed 74. Initial focused: 644 passed / 1 failed / 1 excluded in 106.91s.
  Existing native cleanup could not verify worker exit within budget: SQLite
  correctly retained STOPPED_WITH_RESIDUAL, no matching queried standby events;
  original identity absent on later read. Same case passed unchanged in 1.53s.
- That fixture's finally skipped remaining cleanup after registry.close raised.
  Nested finally now attempts every owned owner; injected-close ordering test
  added. All original assertions/deadlines unchanged. Corrected focused 646
  passed; final reopened-prestate/refusal assertions strengthened afterwards.
- Before the last ordering review, 647 focused / 965 regression checks passed.
  Review then deferred worker undo removal until final verification/history;
  its added fixture required explicit MEDIUM host approval, not a risk downgrade.
  Reviewed boundary 76 passed. Final-source focused **648 passed / 1 excluded
  in 131.43s**; isolated regressions **966 passed / 3 skipped / 1 excluded in
  114.77s**; raw audit **15 in 0.46s**, containment **3 in 3.17s**, recovery
  **5 in 0.63s**. Final hashes match, pytest
  exits zero, fixture keys zero, all 115 FAST cases isolated. Skips/exclusion are
  not passes; initial failures remain documented. No performance/soak claim.
- Real Windows Jobs/workers, owned file effects, actual inverse and reopened
  SQLite prove the bounded boundary. Failure/SQL-trigger/planner seams explicit;
  no user file/window/browser/clipboard/audio state changed. Temporary test-only
  execution request restores in finally; no power/security policy change.
- Catalog totals remain 6 IMPLEMENTED / 44 MISSING / 4 DEFECTIVE / 19 UNVERIFIED.
  This is not full P11. Continue already authorized P11: bounded owned pre-state
  capture, tool-specific identity/conflict-safe inverse, irreversible evidence and
  remaining typed catalog/A/D/H gates. A pending partial effect with insufficient
  identity evidence stays residual, not a promised rollback.
- Terminal scope is resolved by the owner's response: fixed read-only Windows
  diagnostics plus explicitly configured, confirmed project commands. See
  [scope decisions](docs/completion/p11_scope_decisions.md). No unrestricted
  planner shell or planner-created command permission; implementation remains P11.
- Next safe milestone: P11 bounded pre-state execution only, then remaining P11
  gaps. No fresh instruction needed between authorized P11 blocks; do not start
  P12. Recovery before this block: `2f5e87c` in a separate detached worktree.
  Commit/push ui-wiring only; other worktrees/archive/stash/tags preserved.

## Previous checkpoint: 2026-10-20, remaining P11 in progress: native audio

The owner's instruction to finish remaining P11 is active. **P12 is forbidden.**
No action enabling, appearance work, merge or waiver is authorized.

- Started clean/pushed ui-wiring at `f19f261`; its 560 focused / 878 regression /
  15 raw / 3 containment / 5 recovery checks passed immediately before edits.
  [Audio evidence E20](docs/completion/p11_audio_readback.md) records native
  get_volume/list_audio_devices and compatible get_volume_status, strict schemas,
  bounded owned workers, endpoint identity, factual unknown properties, COM cleanup.
- Reproduced obsolete native adapter read failure and all three mutators claiming
  verified success on missing readback. Fixed native interfaces and fail-closed
  state/mode/endpoint readback; no requested-value substitute or test-mode fallback.
  Fixture output/proof now explicitly says fixture/emulated. Native writes are
  not exercised; set_volume/mute/unmute and undo remain UNVERIFIED.
- First focused run: 621 passed / 1 failed / 1 excluded in 328.99s. SQLite records
  verified device read followed by unverified worker cleanup, not a false clean
  success. Kernel-Power events show Modern Standby 18:13:22..18:17:28 overlapping
  the case. Failed artifacts preserved. Same case passed unchanged in 1.75s;
  combined 622 passed in 98.75s before final nine added review checks.
- Final focused **631 passed / 1 excluded in 94.13s**; isolated regressions
  **949 passed / 3 skipped / 1 excluded in 126.04s** (runner wall 272.908s);
  raw audit **15 in 0.77s**, containment **3 in 3.47s**, recovery **5 in 0.84s**.
  Final source hashes match; pytest exits zero, fixture keys zero, 115 FAST
  cases isolated. Skips/exclusion are not passes. No performance claim.
- Ignored test runner requests temporary system execution only during commands
  and restores its prior state in finally. No display/away mode, persistent
  policy/security change or resident PLUMA feature. This does not guarantee
  against Modern Standby or certify suspend/recovery. Native physical tests are
  reads only; voice/STT/planner and write/error/COM fault seams are disclosed.
- Catalog totals: 6 IMPLEMENTED / 44 MISSING / 4 DEFECTIVE / 19 UNVERIFIED.
  All 73 remain mandatory. Continue already authorized P11: pending mutation
  journal/partial effects, bounded pre-state, endpoint/file identity-safe inverse,
  remaining catalog and A/D/H evidence. P11 is not complete, P12 not eligible.
- Three runtime files and one new test; Windows dependencies installed only in
  ignored native venv. Other branches/worktrees/archive/stash/tags preserved.
  Commit/push ui-wiring only. Recovery before this block: `f19f261` in a separate
  detached worktree. Next safe milestone: P11 mutation evidence/undo, no new
  instruction needed between P11 blocks.

## Previous checkpoint: 2026-10-20, remaining P11 in progress: process inspection

P11 remains authorized; **P12 is forbidden** until the owner instructs otherwise.
This checkpoint does not finish P11 or enable command entry.

- Started clean at `0e64caa03eaf03f74952722a2341566a63a69506`, local/remote
  ui-wiring. Four worktrees, main/integration, archive/stash/tags preserved.
  GitHub connector rechecked PRs 1/2: draft/open/unmerged. gh is unavailable.
- Before edits: **368 prerequisite passes in 49.25s** using the isolated native
  environment. [Process evidence E19](docs/completion/p11_process_inspection.md)
  implements list_processes/process_info/process_usage: strict bounded READ tools,
  original native process handle and creation-time checks around observations,
  no command lines/environments, actual unavailable entries and truncation,
  required killable owned worker with fail-closed serialization, factual history.
- Five runtime files and one new test file; no UI, P12, dependency or immutable
  requirement change. Native Windows workers/Jobs/SQLite and reopened history
  cover text/voice requests; voice/STT/planner are inert seams, not device evidence.
- New checks **57 passed in 21.06s**; final focused **560 passed / 1 excluded
  in 79.64s**; regressions **878 passed / 3 skipped / 1 excluded in 89.02s**;
  raw audit **15 passed in 0.43s**; containment **3 passed in 3.24s**; recovery
  **5 passed in 0.66s**. Final source hashes match, fixture key counts zero;
  all 115 FAST cases are isolated. Skips/excluded elevation are not acceptance.
- Only three catalog rows close: totals 4 IMPLEMENTED / 46 MISSING / 4 DEFECTIVE /
  19 UNVERIFIED. Native access denial/PID reuse are injected, not forced OS events.
  No inspected process is changed or killed. Process control remains missing.
- Continue P11 under the existing instruction: pending mutation/effect journal,
  safe inverse/conflicts, remaining file/app/window/process/audio/system/clipboard/
  browser/terminal/memory/control catalog gaps and A/D/H evidence. No blanket waiver.
  Next safe milestone remains a bounded P11 gap; do not start P12 or ask for a
  new instruction between already authorized P11 blocks. No merge/action enabling.
- Recovery before this block: `0e64caa03eaf03f74952722a2341566a63a69506` in a
  separate detached worktree. Commit/push ui-wiring only.

## Previous checkpoint: 2026-10-20, remaining P11 in progress: policy boundary

The owner has explicitly authorized **finishing all remaining P11 work**, while
forbidding P12. This overrides earlier requests for a separate instruction before
each P11 slice. Continue coherent P11 blocks with verification and commits;
P11 is not complete, P12 remains ineligible and action entry remains disabled.

- Clean starting source: 87634db93efe5e01c4c64e16dcf50cc7d404b372. Fresh Git/PR/
  worktree checks preserve main/integration and draft/open/unmerged PRs 1/2.
- Initial prerequisite: 367 passed / 1 failed; one-second metadata fixture expired
  during cold import before its marker. Same owned worker is now prewarmed and
  identity checked, retaining the one-second blocked execution deadline. SMART
  actual timeout copy no longer says user request. Corrected prerequisites:
  **368 passed in 51.99s** before policy feature edits.
- [Policy evidence E18](docs/completion/p11_policy_boundary.md): MEDIUM requires
  exact-call explicit host approval, strict scope/response validation, no session
  blanket grant, and no lower-risk override bypass. Policy waits are bounded,
  admitted/retained on the same capsule; late approval cannot dispatch after STOP.
  Denials/failed pre-state now have sanitized executed=false action records;
  successful action risk/approval fields reflect actual policy. Failed pre-state
  no longer proceeds into a reversible mutation. Raw policy arguments are not logged.
- Focused **503 passed / 1 excluded in 65.24s**; regressions **821 passed /
  3 skipped / 1 excluded in 73.63s**; raw audit **15 passed in 0.64s**; containment
  **3 passed in 3.56s**; recovery **5 passed in 0.70s**. Final hashes match, keys
  zero, all 115 FAST cases tagged isolated. Skips/elevation exclusion are not passes.
- New fault-injection fixture initially leaked a shared ToolSpec mutation;
  scoped monkeypatch now restores it. Existing global STOP assertions unchanged.
  Real approved owned-file move/rollback/reopened history pass; approval UI,
  physical devices, browser and clipboard operations are not certified by this block.
- Owner delegated browser and clipboard choices. [Scope decisions](docs/completion/p11_scope_decisions.md)
  select native Edge/Chrome managed profiles/target IDs, preserving personal
  profiles, and (historically) multi-format clipboard with in-memory undo.
  Clipboard format scope was superseded by the owner on 2026-10-22: plain-text
  copy/paste only, as recorded in the current scope decisions.
  These adapters still require implementation and native verification. Missing
  declared Windows packages are being prepared only in ignored output/p11-native-env.
- Continue remaining P11: mutation/partial-effect journaling and inverse/conflict
  integrity, catalog implementations/adapters and A/D/H evidence. Do not treat
  this safety checkpoint as completion or require another instruction for already
  authorized P11 work. Do not start P12, enable command entry, merge or waive gaps.
- Recovery before this block: 87634db93efe5e01c4c64e16dcf50cc7d404b372 in a new
  detached worktree. Origin ui-wiring only; preserve other worktrees/archive/stash/tags.

## Previous checkpoint: 2026-10-20, P11 slice 1: typed file metadata

**This bounded P11 slice passes; P11 as a whole remains incomplete.** P01-P10
bounded gates remain green. No P12 eligibility, automatic next slice, UI enabling
or merge is authorized by this checkpoint.

- Started clean on local/remote `ui-wiring` at
  `29fa6eb59f2aaa0b3322aaa966e28de97bce63bc`. Git/worktrees/origin and PRs 1/2
  rechecked, draft/open/unmerged. Before tracked edits, P01-P10 prerequisites
  **318 passed in 36.75s**, matrix **298 source items / 324 rows**.
- Reviewed all 73 section-21 catalog rows across 13 categories and source ASTs
  for 13 tool modules. Selected missing exact `file_info`, one required P11 gap.
  H-03 explicit MEDIUM intent remains a recorded candidate, not waived or fixed.
- `file_info` now has a strict absolute Windows path schema, READ policy tier,
  five-second owned process budget, native metadata queries and deterministic
  verified result. No file contents or directory listings are read/returned.
  Unknown/relative/pattern/device/stream/reserved targets fail validation; missing,
  denied, unsupported/reparse and changed observations cannot fabricate metadata.
  SMART/DEEP file schema subsets expose it; FAST/screen-only subsets do not.
- Actual process deadlines now latch task_timeout before disposal. FAST and
  multi-step failure owners finalize actual TOOL_TIMEOUT as FAILED, retaining
  the first cancellation reason and evidence. Explicit STOP semantics remain;
  the inherited global timeout-reason STOP assertion is unchanged and passes.
  Broader ordinary in-process timeout/catalog gaps remain open under D-09.
- Final focused **481 passed, 1 deselected in 58.00s**; isolated regressions
  **799 passed, 3 skipped, 1 deselected in 74.56s**; raw audit `--runxfail`
  **15 passed in 0.76s**; native containment **3 passed in 3.60s**; recovery
  **5 passed in 0.79s**. All 50 new file_info checks pass in final suites;
  all 115 FAST cases have isolation tags, final source hashes match and fixture
  key counts are zero. Excluded elevation/corpus skips are not acceptance.
- [P11 file_info contract/evidence (E17)](docs/completion/p11_file_info.md)
  records native file/directory/Unicode/junction/process/SQLite evidence, inert
  voice/model/policy/error seams, intermediate timeout failures and the narrowed
  repair. Six runtime files, one test and four evidence/handoff documents change.
  Existing tests, immutable requirements, production UI and dependencies unchanged.
- Metadata reads produce no undo record or persistent side effect. Native tests
  read back unchanged files, real owned worker/job exit and reopened history;
  blocked FAST/SMART deadline versus STOP agrees with task memory/result/ledger/
  typed STOP receipts. Permission/I/O faults are injected, not claimed as actual
  denied-token/native ACL acceptance. No real user app, capture, model or system
  elevation operation was used. P10/other physical acceptance limits remain.
- Only CAT-file_info moves from MISSING to bounded IMPLEMENTED. The full catalog
  still has 49 MISSING, 4 DEFECTIVE and 19 UNVERIFIED entries across P11/P12/etc.
  No locked requirement or limitation is waived. Detailed denied action logging,
  original mutating catalog contracts, actual inference/device/UI, performance,
  security/install/package and release gates remain mandatory.
- Commit/push confined to `ui-wiring`; main `6dbf589`, integration `9544752`,
  other worktrees/archive/stash/tags retained. Recovery before this slice:
  `29fa6eb59f2aaa0b3322aaa966e28de97bce63bc` in a new detached worktree.
- **Next safe milestone remains P11**, one separately instructed bounded gap;
  H-03 explicit user intent for MEDIUM operations is still a priority candidate.
  Do not advance to P12 or enable command entry. No next slice has started.

## Previous checkpoint: 2026-10-20, P10 owned Windows safety revalidated

**P10 bounded gate passed after the owner authorized diagnosis and continuation.**
Action entry remains disabled. P11 has not started; no automatic progression.

- Started clean on local/remote `ui-wiring` at
  `792e13a24cd47c7a7ba677ad48c77d460233e5e9` (blocked evidence checkpoint).
  The original failing case passed unchanged in isolation (1 in 1.27s), then
  P01-P09 prerequisites passed **313 in 36.16s**, before tracked edits.
- Read-only failed-fixture SQLite identifies TOOL_TIMEOUT. Windows System
  Kernel-Power events show Modern Standby entering at 08:12:46 UTC and exiting
  at 08:17:40 UTC, overlapping the original run and ending near its failure.
  Host suspension is supported as an explanation for the elapsed-time anomaly;
  the exact worker state is not reconstructed. No power/security setting changed.
  The original failed evidence remains intact, not retroactively declared passed.
- Fixed the fixture's demonstrable cleanup ordering weakness: startup assertion
  failure now cancels/drains the original owned worker before joining its thread
  pool. A new native assertion-failure test verifies exit and no late effect.
  Existing startup/STOP/verification/ledger assertions and deadlines are retained.
  No production runtime or immutable requirement changed.
- Four combined real Windows cases cover FAST/SMART, successful file inverse
  and preserved conflict; registered typed execution, native Jobs/root/descendant
  handles/creation identity, authenticated STOP, no next action/replan, actual
  rollback and retained undo/residual data, memory/result/SQLite/resource mirror/
  IPC agreement, reopened history and verified storage-last runtime shutdown.
  A separate pre-existing fixture process/file survives STOP and runtime close.
- Final focused **413 passed in 46.34s**; isolated regressions **739 passed,
  3 skipped, 1 deselected in 63.38s**; raw audit `--runxfail` **15 passed in
  0.65s**; native containment **3 passed in 3.60s**; recovery **5 passed in 0.71s**.
  All 115 FAST cases carry isolation tags; all final source hashes match and
  fixture key counts are zero. Skips/excluded elevation are not acceptance.
- [P10 revalidation evidence (E16)](docs/completion/p10_revalidation.md) records
  commands, source identities, separate latch/reply/terminal observations and
  fixture limits, including one corrected new-fixture schema/setup error.
  Matrix **298 source items / 324 rows** and diff/link/scope review pass.
- No unresolved BA expected failure or newly reproduced safety blocker remains
  in the covered paths. Device/model/UI/browser-tab/reboot, complete tool-policy,
  performance/soak, packaging/install and release acceptance remain mandatory.
  Fixture policy/router/model seams are disclosed; no real user app, physical
  audio/screen capture, unrestricted shell or system-changing elevation ran.
- Commit/push remains confined to `ui-wiring`, PRs 1/2 draft/open/unmerged;
  main `6dbf589`, integration `9544752`, other worktrees/archive/stash/tags retained.
  Pre-follow-up recovery: `792e13a24cd47c7a7ba677ad48c77d460233e5e9`;
  pre-P10 runtime recovery: `b0e486a0ce323da66be630ac55048b756f9f6182`.
- **Next safe milestone: P11 only after a separate instruction.** Select one
  bounded mandatory catalog/policy/verification/undo gap using the matrix;
  H-03 explicit intent for MEDIUM policy is a recorded candidate. Do not enable
  command entry, merge or start P11 automatically. No requirement is waived.

## Previous checkpoint: 2026-10-20, P10 blocked at prerequisites

**P10 is incomplete. Do not advance to P11 or enable action entry.** Its explicit
failure rule, "Record failures as blockers and stop", was applied before any
runtime/test edits or new combined acceptance fixtures.

- Started clean on local/remote `ui-wiring` at
  `b0e486a0ce323da66be630ac55048b756f9f6182` (P09). Main `6dbf589`, integration
  `9544752`, all four worktrees and draft/open/unmerged PRs 1/2 were rechecked.
- Prerequisites: **1 failed, 312 passed in 294.55s**, real pytest exit 1.
  `test_registry_cancellation_is_unverified_and_persisted` failed waiting for
  the owned worker's `entered` marker, before the test issued cancellation.
  JUnit case duration **267.168s**, wrapper wall **300.364s**. The cause of the
  missing marker and unexpectedly long duration is unverified; neither a STOP
  defect nor harmless scheduling delay is established. No rerun/waiver applied.
- Raw audit independently **15 passed in 0.46s**, using `--runxfail` to bypass
  expected-failure handling. It does not override the failed prerequisite.
  Matrix before/after documentation: **298 source items / 324 rows**.
- [P10 blocked evidence (E15)](docs/completion/p10_evidence.md) records commands,
  source identities, isolation, the exact failure, read-only fixture SQLite
  observation and limitations. Both isolated runs left zero fixture key files.
  Runtime/test sources, immutable requirements and native dark UI are unchanged.
- Combined memory/result/ledger/IPC reconciliation, separate latch/cleanup
  latency and additional owned Windows acceptance were **not completed**.
  Earlier passing native cases in this run remain bounded evidence, not a pass
  for the missing combined gate. No real user application, device, model or
  system-changing elevation operation was intentionally exercised.
- This documentation checkpoint is committed/pushed on `ui-wiring`; no merge.
  Pre-P10 recovery is `b0e486a0ce323da66be630ac55048b756f9f6182`; inspect it in
  a separate detached worktree. Existing archive/stash/tags/worktrees remain.
- **Next safe milestone remains P10:** diagnose the failed owned-worker startup
  and timing boundary in a bounded follow-up, preserve its assertions, then
  re-establish P01-P09 prerequisites before combined acceptance. P11 is ineligible.
  No owner-approved limitation exists. All later tool, device, inference,
  screen, UI, performance, packaging and release gates remain mandatory.

## Previous checkpoint: 2026-10-20, P09 private Windows IPC credentials

This checkpoint supersedes earlier next-step/count statements. Locked source
and native dark UI are unchanged. This bounded security/interoperability gate
is not combined Windows safety, physical device/UI or release acceptance.

- **P09 bounded gate passed: BA-09 repaired; P01-P08 preserved.** Started clean
  on local/remote `ui-wiring` at `5853572842cd4706e9729e13fb483b7cae4639ff`.
  Matrix passed before edits; prerequisites **285 passed in 30.97s**; original
  BA-09 assertion reproduced **1 failed in 0.48s**. Original audit fixture/body/
  assertion and Windows skip condition are unchanged; only its xfail is removed.
- [P09 evidence and credential contract](docs/completion/p09_evidence.md) records
  exact commands, tested blobs, native handle/ACL facts, C# interoperability,
  fixture limitations, intermediate wrapper failure and recovery. Two runtime,
  three test and five handoff/evidence files change. No dependencies installed.
- Windows CREATE_NEW applies an explicit current-user owner and protected DACL
  at creation, with exclusive sharing through write/flush/verified readback.
  Existing reads validate that same opened handle, owner, allow-rule SIDs, disk
  file/type/link and exact 32-byte size. Broad/null/unsupported ACLs, wrong owner,
  corrupt files, denied access and unresolved contention fail closed. Reader
  handles block data writes/replacement. File/token handles and security buffers
  have explicit cleanup; tests cover repeated native handle counts.
- The user/SYSTEM/Administrators allow boundary matches the unchanged C# reader.
  Contention retries are bounded to 500 ms; losers reuse a verified winner or
  refuse. Existing invalid credentials are never truncated, repaired or rotated.
  Failed private first writes may retain their exact file for controlled recovery.
  No production credential was touched for testing and no secret is logged.
- Final focused **408 passed in 43.02s**, including **27 new credential cases**
  and ordinary BA-09. Isolated regressions **734 passed, 3 skipped, 1 deselected
  in 57.27s**; prerequisites rechecked **285 passed in 28.13s**; owned containment
  **3 passed in 2.90s**; recovery **5 passed in 0.63s**. Raw audit **15 passed
  in 0.68s**, no xfails. Matrix **298 source items / 324 rows**. All 115 FAST
  cases have desktop-isolation tags; preserve P02's correction. Fixture key
  files remaining zero, including cleanup of the initial failed report wrapper.
- **39 C# IPC checks passed in 11.358s**, including all 37 prior assertions,
  null-DACL refusal and fresh Python creation without a seeded key. The factory
  creates the key beneath inherited Users-read permissions; the unchanged C#
  opened-handle reader accepts it and authenticates twice for multi-buffer
  status. Native framing/HMAC, C# production reader and read-only UI remain
  unchanged. No production resident, device, model, hotkey or tools were started.
- Tests use exact owned temporary files/ACLs and native processes/pipes/SQLite.
  No Windows policy/elevation/security bypass or production key repair occurred.
  Corrupt/insecure/busy keys are refused, not silently recovered. Owner-mismatch
  injection is distinguished from real different-user/elevated-token acceptance.
  Thread exceptions are errors; corpus skips/exclusion are not acceptance.
- **No original BA finding/expected failure remains.** All nine bounded repairs
  pass, but P10 combined owned Windows safety and all remaining tool, inference,
  screen/voice/device/UI, recovery/security/performance/package/release gates
  remain mandatory. No requirement/limitation is waived. Action entry stays
  disabled; no automatic transition into combined acceptance or UI wiring.
- P09 is committed/pushed on `ui-wiring`; PRs 1/2 remain draft/open/unmerged.
  Main `6dbf589`, integration `9544752`, existing worktrees/archive/stash/tags
  remain unchanged. Pre-P09 recovery: `5853572842cd4706e9729e13fb483b7cae4639ff`;
  inspect in a new detached worktree. No merge or automatic progression.
- **Next safe milestone: P10 only**, after its shared contract, P01-P09 and
  fresh Git/PR prerequisite checks. P10 has not started.

## Previous checkpoint: 2026-10-20, P08 truthful STOP receipts

This checkpoint supersedes earlier next-step/count statements. Locked source
and native dark UI are unchanged. This is a bounded backend gate, not full
STOP, native-device/UI, installed-artifact or release acceptance.

- **P08 bounded gate passed: both BA-08 regressions repaired; P01-P07 preserved.**
  Started clean on local/remote `ui-wiring` at
  `7cee32faa2e1bc1b363ecb2dfedf46bf5ec116d6`. Matrix passed before edits;
  prerequisites **235 passed in 29.85s**; original BA-08 assertions reproduced
  **2 failed in 0.54s**. Only those two strict markers are removed. All original
  audit setup/bodies/assertions and inherited shutdown/voice tests are unchanged.
- [P08 evidence](docs/completion/p08_evidence.md) records exact commands, tested
  blobs, environment, intermediate failures, fixture readback, limits and recovery.
  [STOP protocol contract](docs/completion/p08_stop_protocol.md) defines the
  bounded `pluma.stop.v1` payload. Three runtime files, two test files and five
  handoff/evidence documents change. P15 live events remain separate.
- STOP aliases return typed per-task pending/stopped/residual/error/earlier-terminal
  observations. Transport ok, latch acknowledgement, terminal-ready, persisted
  history, retained cleanup owners and rollback/residual facts are distinct.
  stopped_count/stopped_tasks now contain verified clean cancellations only;
  unknown, unfinished, failed, residual and prior successful tasks are excluded.
  Strict schema/proof/count validation rejects fabricated clean STOP payloads.
- Global latches/claims precede cleanup; existing admission generation remains.
  IPC publishes one retained non-daemon cleanup owner before thread startup,
  waits at most 100 ms for it and returns actual pending facts. No resource/ledger
  lock wait can fabricate proof. Pending operations/capsules stay owned through
  pruning and P06 shutdown joins, before storage closure. A slow/error stage
  retains ownership/store. The wait budget is not hardware p95 or termination proof.
- Missing/invalid/terminal IDs, duplicate/concurrent/reentrant STOP, partial rollback,
  irreversible effects, absent/failed persistence and cleanup exceptions have
  explicit outcomes. No duplicate inverse or self-join occurs; completed success
  is not rewritten as cancellation. Unexpected cleanup failure records a fixed
  journal error and actual unfinished state; no automatic recovery is promised.
- Final focused **380 passed in 34.51s**, including **48 new STOP cases** and
  both ordinary BA-08 audit cases. Isolated regressions **706 passed, 3 skipped,
  1 deselected, 1 xfailed in 54.44s**; prerequisites rechecked **235 passed in
  21.29s**; owned containment **3 passed in 2.97s**; recovery **5 passed in
  0.46s**. Raw audit **1 failed, 14 passed in 0.75s**. Matrix **298 source
  items / 324 rows**. Fixture keys zero; 115 FAST cases have desktop-isolation
  tags. Preserve the P02 correction. Thread exceptions are errors; skips,
  exclusion and xfail are not accepted requirements.
- Real SQLite readback and a test-owned HMAC-authenticated Windows native pipe
  verify STOP while execute is blocked. Other failure seams are injected and
  device/STT adapters remain inert. Native framing/authentication/credential
  source, internal synchronous STOP bodies, owned-process admission/controller,
  rollback recipes and native UI are unchanged. No production device/desktop/
  hotkey/model, settings, elevation or security-policy bypass was activated.
- **One original finding remains: BA-09, one raw failure.** Private atomic first
  credential creation/validation is P09. Combined Windows P10, model/device,
  full tools/screen/ledger/UI, recovery/security/performance and release gates
  remain. No owner-approved requirement limitation is waived. Action entry stays
  disabled; physical voice and P15/P17 integration are not counted as done.
- P08 is committed/pushed on `ui-wiring`; PRs 1/2 remain draft/open/unmerged.
  Main `6dbf589`, integration `9544752` and existing worktrees/archive/stash/tags
  remain unchanged. Pre-P08 recovery: `7cee32faa2e1bc1b363ecb2dfedf46bf5ec116d6`;
  inspect in a new detached worktree. No merge or automatic progression.
- **Next safe milestone: P09 only**, after its shared contract, P01-P08
  prerequisites and fresh Git/PR checks. P09 has not started.

## Previous checkpoint: 2026-10-20, P07 voice capture ownership

This checkpoint supersedes earlier next-step/count statements. Locked source
requirements and native dark UI are unchanged. This bounded gate does not
certify physical voice, the full backend, installed artifacts or release.

- **P07 bounded gate passed: both BA-07 failures repaired; P01-P06 preserved.**
  Started clean on local/remote `ui-wiring` at
  `e5643210d2795ac9d542021ef7adf06df736bef4`. Matrix passed before edits;
  prerequisites **204 passed in 22.30s**; original BA-07 raw reproductions
  **2 failed in 0.57s**. Only those two expected-failure markers are removed;
  original audit setup/assertions and inherited shutdown tests are unchanged.
- [P07 evidence and capture contract](docs/completion/p07_evidence.md) records
  exact commands, tested blobs, environment, verification, limits and recovery.
  Four runtime files, three test files and four handoff/evidence files change.
- Push-to-talk attaches one VoiceSession to its capsule before capture admission.
  STOP closes/discards through that owner without key release. All global latches
  still precede cleanup. Device operations serialize independently of STOP;
  pending/failed capture or STT retains ownership and factual residual evidence,
  blocks pruning/new capture and prevents complete shutdown/storage closure.
  One retained cleanup worker bounds the STOP caller's wait; it cannot falsely
  prove a hung native driver exited. P06 shutdown/entry ownership remains.
- Empty, unavailable, denied/low-confidence, failed and cancelled paths finalize.
  No transcript produces independent pre-execution journal facts without fake
  command text/tasks rows. STT and ordinary registered execution use the same
  capsule/token, with actual SQLite readback. Missing orchestration fails closed
  instead of invoking a capsule-free voice callback. Text dispatch is unchanged.
- Capture requires positive stream-close readback; failed closure retains its
  handle, discards audio and supports verified retry. Stale callbacks cannot feed
  another utterance. Missing device dependencies fail closed. Raw audio remains
  transient, device/model imports lazy, driver exception details omitted. Explicit
  inert fixtures replace reliance on an absent library to avoid a microphone.
- Final focused **328 passed in 32.44s**, including **29 new voice cases**.
  Isolated regressions **656 passed, 3 skipped, 1 deselected, 3 xfailed in
  47.91s**; prerequisites rechecked **204 passed in 19.25s**; owned containment
  **3 passed in 2.86s**; recovery **5 passed in 0.50s**. Raw audit **3 failed,
  12 passed in 0.56s**. Matrix **298 source items / 324 rows**. Fixture keys zero;
  all 115 FAST cases have desktop-isolation properties. Retain P02's historical
  isolation correction. Thread exceptions are errors; skips/xfails are not passes.
- Inert device/STT fixtures prove lifecycle races, actual registered voice/text
  routing, no post-STOP executor start, 55 empty cycles and SQLite journal/history
  facts. Inherited native owned process/descendant/pipe/recovery evidence passes.
  This is not physical microphone/whisper.cpp/hotkey/overlay, full idle soak,
  loaded p95, product/install or release acceptance; P14/P19 remain mandatory.
  No requirement or acceptance limitation is waived. Action entry stays disabled.
- **Two findings remain: BA-08 and BA-09, three raw failures.** Truthful typed
  STOP acknowledgements and initial credential privacy remain. Broader tools,
  native inference, screen, device/UI, security, performance and release gates
  stay open. A pending/residual result is never a clean STOP claim.
- P07 is committed/pushed on `ui-wiring`; PRs 1/2 remain draft/open/unmerged.
  Main `6dbf589`, integration `9544752` and existing worktrees/tags/archive/stash
  remain unchanged. Pre-P07 recovery: `e5643210d2795ac9d542021ef7adf06df736bef4`;
  inspect in a new detached worktree. No merge or automatic progression.
- **Next safe milestone: P08 only**, after its shared contract, P01-P07
  prerequisites and fresh Git/PR checks. P08 has not started.

## Previous checkpoint: 2026-10-20, P06 owned shutdown before storage

This checkpoint supersedes earlier next-step/count statements. Locked source
requirements and native dark UI are unchanged. This is a bounded gate, not full
STOP, backend, device, installed-artifact, recovery or release acceptance.

- **P06 bounded gate passed: BA-06 repaired; P01-P05 preserved.** Started clean
  on local/remote `ui-wiring` at `3d56551e12058a1e8ce969d337108529389284ce`.
  Matrix passed before editing. Prerequisites freshly passed **157 checks in
  16.32s**. Original BA-06 reproduced **1 failed in 0.52s**, task RUNNING,
  latch unset, worker/job/registry undrained. Original assertion is unchanged;
  only its strict marker is removed. Work crossed midnight from October 19.
- [P06 evidence and shutdown contract](docs/completion/p06_evidence.md) records
  exact commands, blobs, environment, real native/SQLite facts, failed fixtures,
  remaining gaps and recovery. Fourteen runtime files, two test files and four
  handoff/evidence documents change; no inherited P01-P05 test assertion changes.
- Shutdown rejects all entry and latches tasks/preparations first. It owns one
  serialized stage worker across bounded close calls, drains capture/tasks/
  handlers/registry/futures, reads retained ownership and terminal history back,
  verifies model/timer unload, then closes storage. A slow/unverified stage
  retains its worker/store and returns incomplete; repeated/concurrent close
  shares/resumes the same owner. The host waits for verified close before
  claiming clean shutdown. The five-second default is an acknowledgement
  budget, not forced termination of arbitrary Python/device work.
- Tool/planner futures remain tracked after result timeout and retain capsules
  through pruning. Unknown absence defers rollback/temp deletion; verified
  shutdown records remaining pre-state/residuals without silently repeating
  inverses. Futures stay with the capsule until supervisor readback; callbacks
  do not change terminal evidence after persistence. Existing P01/P02 latch,
  executor admission and original process-handle ownership remain.
- Native IPC retains and joins client/accept owners. Shutdown wakes only its
  own pending named listener and serializes native connection closure. Capture
  cancellation discards audio and retains a failed native stream; an admitted
  late press is cancelled after handler drain. Activation/hotkey/model timers
  require exit readback. No microphone/model/user desktop action was started.
- Cancelled capture with no transcript stores actual terminal/STOP facts in the
  independent cleanup journal without fabricating command text or a tasks row.
  Normal execution still requires P05 task-history readback. SQLite queues one
  close sentinel behind admitted writes, refuses later writes, and keeps
  connection ownership on writer timeout. Persistence failure blocks closure.
- Final focused **286 passed in 21.02s**, including **46 new shutdown cases**
  and inherited lifecycle/capture checks. Isolated regressions **612 passed,
  3 skipped, 1 deselected, 5 xfailed in 34.39s**. Prerequisites rechecked
  **157 passed in 12.70s**; owned containment **3 passed in 2.97s**; startup/
  recovery fixtures **5 passed in 0.46s**. Raw audit **5 failed, 10 passed in
  0.57s**. Matrix **298 source items / 324 rows**. Windows 11 build 26200 /
  Python 3.12.10 / pytest 8.3.3. Fixture keys remaining zero; all 115 FAST
  cases have desktop-isolation properties. Keep the P02 isolation correction;
  skips/exclusion/xfails are not acceptance. Thread exceptions fail final tests.
- Real runtime shutdown verifies owned root/descendant exit, unrelated fixture
  survival, absent late effects, released jobs, native pipe handler/accept exit
  and reopened SQLite outcomes. Capture/model adapters are inert; the process
  fixture uses inert policy, not policy acceptance. No full unit/product/device/
  install, physical voice/GPU/hotkey, fifty-cycle soak or p95 claim is made.
- **Three findings remain: BA-07 through BA-09, five raw failures.** Ordinary
  voice STOP/empty capture, typed truthful STOP acknowledgements and initial
  credential privacy remain. Broader mandatory tools, model/screen/STT/device/
  UI/recovery/security/performance/release gates stay open. No requirement or
  acceptance limitation is waived. Action entry remains disabled.
- P06 is committed/pushed on `ui-wiring`; PR 1/2 remain draft/open/unmerged.
  Main remains `6dbf589`, integration `9544752`. Pre-P06 recovery is
  `3d56551e12058a1e8ce969d337108529389284ce`; inspect in a new detached
  worktree. Existing worktrees/tags/archive/stash remain; no merge, worktree
  switch, destructive cleanup, force push or security bypass.
- **Next safe milestone: P07 only, BA-07 voice capture/capsule lifetime.**
  Reproduce both original assertions first; connect cancellation, finalize all
  empty/denied/failed/cancelled paths and serialize press/release/STOP/shutdown.
  Preserve the capsule into STT/execution, transient audio and cold models.
  Inert tests are not P14/P19 physical voice acceptance. P10 later combines all
  nine audit repairs and native failure/ledger/handle paths. P07 was not started.
  Do not advance automatically or enable actions.

## Previous checkpoint: 2026-10-19, P05 authoritative terminal outcomes

This checkpoint supersedes earlier next-step/count statements. Locked source
requirements and the native dark UI are unchanged. This is a bounded gate,
not full STOP, backend, device, installed-artifact or release acceptance.

- **P05 bounded gate passed: BA-05 repaired; P01-P04 preserved.** Started clean
  on local/remote `ui-wiring` at `8956cb7ec669df89b79e98c411e4c90f63016be0`.
  Coverage passed before editing. Prerequisites freshly passed **111 checks in
  13.72s**. Original BA-05 reproduced: **1 failed in 0.63s**, supervisor residual
  overwritten by returned/history STOPPED. Original assertion is unchanged;
  only its strict marker is removed.
- [P05 evidence and terminal contract](docs/completion/p05_evidence.md) records
  exact commands, source blobs, reports, SQLite/Windows facts, failure fixtures,
  remaining gaps and recovery. Five runtime files, three test files and four
  handoff/evidence documents change. All inherited P01-P04 assertions remain;
  FAST's old mock call-count check now asserts authoritative atomic terminal
  state/evidence. Intermediate failures/corrections are recorded.
- All routes project the supervisor's state, finished/pending finalization,
  persistence flag, residual and redacted rollback/cleanup facts. FAST failure
  and multi-step STOP/failure share its existing cleanup owner. No independent
  route terminal write or second rollback overwrites residual truth. Last-step
  STOP and terminal commitment share the short admission boundary; repeated
  finalization preserves outcome, timestamp and evidence. Incomplete cleanup
  remains nonterminal with pending copy; no stopped/success claim is fabricated.
- Terminal state, cleanup journal and resource mirror persist atomically and
  are read back. Failure makes success FAILED or clean STOP residual, records
  fixed persistence evidence and queues a conservative retry after the original
  write. Real blocked-writer tests prove late writes cannot be the last stale
  success. Unavailable storage reports `terminal_persisted=false`; explicit
  later reconciliation preserves state without repeating cleanup/rollback.
- Execute IPC adds factual completion/persistence/residual/rollback fields;
  authenticated native pipe and recent-history readback pass. Existing STOP
  acknowledgements remain BA-08 for P08. No runtime shutdown/voice/protocol/UI
  milestone was started. Action entry stays disabled.
- Final focused: **228 passed in 22.34s**, including **45 new outcome cases**.
  Relevant isolated regressions: **553 passed, 3 skipped, 1 deselected,
  6 xfailed in 36.87s**. Prerequisites rechecked **111 passed in 10.89s**;
  owned-worker containment **3 passed in 2.95s**. Raw audit: **6 failed,
  9 passed in 0.64s**. Matrix: **298 source items / 324 rows**. Windows 11
  build 26200 / Python 3.12.10 / pytest 8.3.3. Fixture keys remaining: zero;
  all 115 FAST cases have explicit desktop-isolation properties. Retain the
  P02 isolation correction. Skips/exclusion/xfails are not acceptance.
- Real file conflicts/partial rollback, reopened SQLite, aborted transactions,
  delayed queued commits and authenticated owned native pipes are verified.
  Planner/perception/device adapters are inert, audio emulated; existing real
  P03/P04 worker/descendant/unrelated-process checks pass unchanged. No physical
  microphone/model/OCR/hotkey, full unit/product/install or p95 claim is made.
- **Four findings remain: BA-06 through BA-09, six raw failures.** Runtime
  shutdown, capture/empty voice capsule, typed truthful STOP acknowledgements
  and conditional initial credential privacy remain. Full tool/model/screen/
  voice/UI/recovery/security/release gates remain in the matrix. No requirement
  or acceptance limitation is waived.
- P05 is committed/pushed on `ui-wiring`. PR 1/2 remain draft/open/unmerged;
  main remains `6dbf589`, integration `9544752`. Pre-P05 recovery is
  `8956cb7ec669df89b79e98c411e4c90f63016be0`; inspect in a new detached
  worktree. Existing tags/worktrees/archive/stash are preserved; no merge,
  worktree switch, destructive cleanup, force push or security bypass.
- **Next safe milestone: P06 only, BA-06 bounded runtime shutdown/drain.**
  Reproduce its original assertion before editing; reject work, latch/cancel,
  drain handlers and retained terminal/unpublished-preparation owners, verify
  cleanup, persist outcomes, close registry before storage, and test repeated
  bounded close. P10 combines real descendant/failure/ledger paths after all
  nine audit repairs. P06 was not started. Do not advance or enable actions.

## Previous checkpoint: 2026-10-19, P04 verified cleanup and residual ownership

This checkpoint supersedes earlier next-step/count statements. Locked source
requirements and the native dark UI are unchanged. This is a bounded gate,
not full STOP, backend, device, installed-artifact or release acceptance.

- **P04 bounded gate passed: BA-04 repaired; P01-P03 preserved.** Started clean
  on local/remote `ui-wiring` at `f6543d1a1df622e8f7d2a64131cd49d32343a298`.
  Coverage passed before editing. Prerequisites freshly passed **72 checks in
  12.67s**. Original BA-04 reproduced first: **1 failed in 0.42s**, clean
  STOPPED despite termination failure and lost worker reference. The original
  assertion is unchanged; its strict marker is removed.
- [P04 evidence and cleanup contract](docs/completion/p04_evidence.md) records
  exact commands, tested blobs, reports, verified Windows/SQLite facts, failure
  injections, limits, recovery and next gate. Typed cleanup evidence combines
  worker/root, Job Object, temporary resource, snapshot, rollback, irreversible
  effect and persistence readback. Errors use fixed factual codes, not raw
  exception bodies or tool arguments. Unresolved handles/identity survive
  terminal cleanup, registry close/acquisition and pruning.
- Native jobs read active-process count before handle closure; failures remain
  owned. A termination exception can resolve only through positive fallback
  absence/closure readback. Worker cleanup retains P03's original process
  handles, task/PID/creation/class identity, bounded I/O and shared latch.
  No new detached helper, model/capture workload or name/PID killer is added.
- Unknown worker/job absence defers rollback and temporary deletion. Partial
  rollback preserves remaining pre-state. Registered temps capture identity,
  reject changed/missing/reparse identity, and read absence before release;
  pre-existing resources and unregistered computed task paths are untouched.
  Existing file/audio rollback recipes read postconditions; database undo
  consumes only matching restored memory pre-state. Deferred resource identity
  is retained in reports for later inspection.
- Clean STOP requires resolved evidence; otherwise core state is
  STOPPED_WITH_RESIDUAL. Ordinary successful-terminal cleanup failures become
  FAILED. Failed unpublished preparations remain tracked without publishing a
  stale task. Migration 0002 journals redacted reports independently of task
  history insertion, atomically mirrors existing task resources and reads the
  journal back. This stores no fabricated command/input mode. Queue writes have
  two-second acknowledgement bounds; storage failure retains evidence and
  prevents clean core completion. Returned/history reconciliation remains P05.
- Final focused: **183 passed in 20.10s**, including 38 new cleanup cases and
  seven existing database migration/WAL/writer cases. Relevant regressions with
  explicit desktop isolation: **507 passed, 3 skipped, 1 deselected, 7 xfailed
  in 36.94s**. Additional owned-worker containment: **3 passed in 3.60s**.
  Raw audit: **7 failed, 8 passed in 0.88s**. Matrix: **298 source items /
  324 rows**. Windows 11 build 26200 / Python 3.12.10 / pytest 8.3.3; isolated
  storage, owned processes/jobs/files/pipes, SQLite and inert/audio emulation.
  Fixture keys remaining: zero. All 115 FAST cases have desktop-isolation tags;
  retain P02's isolation correction. Skips/exclusion/xfails are not acceptance.
- Real supervisor cleanup reads root/descendant exit, unrelated fixture
  survival, empty/closed jobs, absent late effects and SQLite cleanup/state
  back. Failures cover unknown worker exit, live/query/close failures, no-op
  deletion/rollback, conflicts, pre-existing ownership, pruning, repeated STOP,
  snapshot failure, unpublished preparation, persistence/redaction and bounded
  acknowledgement. No full unit/product/device/install or hotkey/p95 claim.
- P02/P03 inert doubles now expose explicit readback. P02's former expected
  ROLLING_BACK after resource error now requires factual residual state; latch
  and ordering assertions remain. BA-08's old resource-error setup ceased to
  be nonterminal after P04, so its injection now fails after the actual
  ROLLING_BACK boundary; original guard/assertion/strict marker remain. P08 is
  still defective. An initial new test's missing verifier was corrected; all
  intermediate reports are retained under ignored output/p04.
- **Five findings remain: BA-05 through BA-09, seven raw failures.** FAST
  returned/history residual truth, runtime drain, voice capture/empty-capsule,
  IPC outcome truth and initial credential privacy remain. Full tool/model/
  voice/screen/native-device/recovery and release gates remain in the matrix.
  UI action entry stays disabled. Core evidence alone does not repair results.
- P04 is committed/pushed on `ui-wiring`. PR 1/2 remain draft/open/unmerged;
  main remains `6dbf589`, integration `9544752`. Pre-P04 recovery is
  `f6543d1a1df622e8f7d2a64131cd49d32343a298`; inspect in a new detached
  worktree. Existing tags/worktrees/archive/stash are preserved; no merge,
  worktree switch, destructive cleanup, force push or security bypass.
- **Next safe milestone: P05 only, BA-05 authoritative terminal projection.**
  Reproduce `test_fast_stop_preserves_supervisor_residual_outcome` with
  `--runxfail`; align returned results/history with supervisor state and residual
  details, test racing STOP, partial/non-undoable effects and storage failures.
  P06 must include retained terminal/preparation owners in shutdown drain;
  P10 reruns combined P01-P09 Windows/failure/ledger paths and handle lifecycles.
  P05 was not started. Do not advance automatically or enable actions.

## Previous checkpoint: 2026-10-19, P03 interruptible owned workers

This checkpoint supersedes earlier next-step/count statements below. The master
specification is unchanged. This is a bounded gate, not complete STOP, backend,
UI, device, installed-artifact or release acceptance.

- **P03 bounded gate passed: BA-02 repaired; P01/P02 preserved.** Started clean
  on local/remote `ui-wiring` at `f303f231b825cad151fcf0846b3966e6ccc4a2a2`.
  Coverage passed before editing; prerequisites freshly passed **45 checks in
  3.21s**. Original BA-02 reproduced first: **1 failed in 0.50s**, STOP unable
  to acquire the controller during the outstanding response wait.
- [P03 evidence and worker lifetime contract](docs/completion/p03_evidence.md)
  records exact commands, tested blobs, isolated reports, real Windows readback,
  review, limitations and recovery. Request serialization is separate from
  short lifetime state and bounded cleanup locks. STOP latches before waiting;
  parent overlapped message-pipe sends/reads check deadline/cancellation, with
  bounded drain/close. No detached I/O or cleanup helper thread is introduced.
- Workers receive a cooperative view of the shared task latch. Explicit
  disposal wakes parent cancellation waiters. Startup and cleanup failures
  retain controller ownership for retry; a pending synchronous OS launch
  reports a bounded failure until its original caller can finish cleanup.
  No ToolCall is sent before identity and both Job Object assignments succeed.
  Root exit is read back; the original Process/creation identity is retained.
- Identity/readback and Job Object assignment use the original native process
  handle, avoiding a PID lookup/reuse race. Worker-only jobs contain descendants;
  shared capsule jobs are preserved. Idle pool acquisition uses a new controller
  rather than retagging one an earlier task could still reference. Force
  termination targets owned handles/jobs only. Same-task disposed restart is
  rejected; repeated/concurrent disposal remains bounded.
- Twenty-six new cases cover actual Windows pending writes/reads and hung/
  cooperative workers, full request pipes and response timeouts, owned descendant
  exit with an unrelated fixture surviving, startup races, PID substitution,
  failure/retry, pool ownership, repeated disposal and SQLite cancellation
  readback. BA-02's original 150ms assertion is unchanged; its process double
  now records killed exit for readback, and its strict marker is removed.
  Review caught/fixed an intermediate parent-cancel regression without changing
  P01's assertion. P01 cancellation/tests and P02 supervisor/tests are unchanged.
- Final focused: **126 passed in 14.48s**. Relevant regressions with explicit
  `-p tests.fixtures.desktop_isolation`: **468 passed, 3 skipped, 1 deselected,
  8 xfailed in 28.50s**. Additional owned-worker containment: **3 passed in
  2.89s**. Raw audit: **8 failed, 7 passed in 0.67s**. Matrix: **298 source
  items / 324 rows**. Windows 11 build 26200 / Python 3.12.10 / pytest 8.3.3;
  isolated user-local storage, test/audio emulation, owned fixtures; zero
  fixture keys remaining. All 115 FAST cases carry the isolation property.
  Skips, elevation exclusion, emulation and expected failures are not acceptance
  passes or approved limitations. Retain P02's inherited isolation correction.
- Actual controller cancellation-to-disposal observations were 63ms hung / 78ms
  cooperative against 30-second tool deadlines. Root/descendant exit, cooperative
  marker/exit code, absent late effects and unrelated fixture liveness were read
  back. These are single fixture observations, not hotkey/loaded-device p95 or
  whole-supervisor latency. P10 must rerun them through combined P01-P09 task,
  rollback, cleanup, ledger/IPC and runtime/voice paths; P26 measures performance.
- **Six findings remain: BA-04 through BA-09 (eight raw failures).** In
  particular supervisor/registry reference loss and aggregate cleanup readback
  remain defective; controller exceptions do not establish clean STOPPED.
  FAST residual truth, runtime/voice drain, IPC truth and initial credential
  privacy remain open. Action entry remains disabled; native dark UI unchanged.
- P03 is committed/pushed on `ui-wiring`; PR 1 and PR 2 remain draft/open and
  unmerged. Main remains `6dbf589`; UI integration remains `9544752`. No
  worktree switch, merge, force push, destructive cleanup or security bypass.
  Pre-P03 recovery: `f303f231b825cad151fcf0846b3966e6ccc4a2a2`; inspect in a
  new detached worktree. Existing recovery tags/archive/stash/worktrees remain.
- **Next safe milestone: P04 only, BA-04 cleanup readback and retention.**
  Reproduce `test_failed_worker_cleanup_requires_residual_state` with
  `--runxfail`; preserve failure/identity until verified absence, combine
  worker/job/resource/rollback evidence and persist factual residual state.
  Use P03's retained identity and pending-cleanup failure paths. P04 was not
  started. Do not advance automatically or enable UI actions.

## Previous checkpoint: 2026-10-19, P02 global latch-all

This checkpoint supersedes earlier next-step/count/isolation statements below.
The master specification is unchanged; this is a bounded milestone, not full
STOP, backend, UI or release completion.

- **P02 bounded gate passed: BA-01 repaired; P01 preserved.** Started clean on
  local/remote `ui-wiring` at `eab9d8d70ce2abbf45e0171501678a3c41736299`.
  Coverage passed before editing, and P01 prerequisites freshly passed
  **22 checks in 2.68s**. BA-01 reproduced first: **1 failed in 0.58s**, first
  cleanup observed `[(True, False), (True, True)]`.
- [P02 evidence and latch/request contract](docs/completion/p02_evidence.md)
  records exact commands, tested blobs, isolated reports, timings, limitations,
  recovery and the next gate. Global STOP now latches every affected
  nonterminal capsule before state claims or cleanup. A short state/publication
  lock is never held for resource construction, grace, worker I/O, rollback or
  cleanup. Existing cleanup remains owned by its single STOPPING claim, including
  overlapping STOP calls and repeated STOP during ROLLING_BACK.
- Requests published before STOP are included. Creation during global STOP is
  rejected before allocation; preparation crossing a STOP generation is rejected
  before publication and its prepared resources closed. Fresh explicit commands
  can proceed after all global callers return. No queued retry, detached cleanup
  branch or second cancellation tree is introduced. Terminal tasks are preserved.
- Twenty-two new controlled ordering cases cover blocked cleanup phases,
  later-task registry admission, native worker events, simultaneous/global/task
  STOP, terminal states, preparation/publication/start/success races, failure,
  empty/repeated STOP and real SQLite readback. P01's execution source/tests
  remain unchanged. BA-01's original assertion remains; only its marker is removed.
- Final focused checks: **100 passed in 7.45s**. Final relevant regressions,
  explicitly loading the desktop-isolation plugin: **441 passed, 3 skipped,
  1 deselected, 9 xfailed in 21.94s**. Raw audit: **9 failed, 6 passed in 0.84s**.
  Windows 11 build 26200 / Python 3.12.10 / pytest 8.3.3; isolated user-local
  storage, test/audio emulation and owned fixtures. Existing skips/unexecuted
  elevation and expected failures are not acceptance or approved limitations.
  No complete product/device/install suite is claimed. Fixture keys remaining: zero.
- **Test-isolation correction:** an earlier inherited FAST regression run was
  executed before review found its clipboard/window/app-close helpers could
  reach the real desktop. Prior desktop state was not captured; no no-impact
  or restoration claim is made. P01 used the same inherited sub-suite; its
  evidence now carries a correction. The final P02 run loads
  `-p tests.fixtures.desktop_isolation`, with in-memory clipboard, no target
  window and blocked desktop termination for FAST cases. This is fixture
  route/orchestration evidence, not native desktop acceptance. Use that plugin
  for future bounded runs of this suite; retain the original logs as disclosed.
- Controlled latch acknowledgement was recorded separately from cleanup in
  JUnit (0.196-2.381 ms to first cleanup boundary across four single fixture
  observations). These are not real hotkey/p95 or loaded-device measurements.
  Actual combined Windows descendant/cleanup and latency gates remain P10/P26.
- The [matrix](docs/completion/requirements_matrix.md) remains complete:
  **298 source items / 324 rows**. BA-01 and BA-03 pass bounded gates; seven
  findings remain (BA-02, BA-04 through BA-09), with nine raw failures. Typed
  acknowledgement/terminal truth remains P08; candidate IDs are not clean STOP
  proof. Action entry stays disabled; native dark UI and locked requirements
  are unchanged.
- Active folder/branch remain `D:\Workspace\DEVEL\PLUMA` / `ui-wiring`.
  P02 changes are committed/pushed there; PR 1 and PR 2 stay draft/unmerged,
  `main` stays `6dbf589`. Recovery point before P02:
  `eab9d8d70ce2abbf45e0171501678a3c41736299`; inspect in a new detached
  worktree as documented. Existing tags/archive/stash/worktrees are preserved.
- **Next safe milestone: P03 only, BA-02 interruptible owned-worker waits.**
  Reproduce `test_worker_stop_interrupts_outstanding_response_wait` using
  `--runxfail`, then separate execution serialization from cancellation and
  termination ownership. Preserve P01/P02 and bounded, verified owned cleanup.
  P03 was not started; do not advance automatically or enable UI actions.

## Previous checkpoint: 2026-10-19, P01 executor admission

This checkpoint supersedes the P00 next-step/count statements below. The master
specification remains immutable; this is a bounded work packet, not completion
of the STOP system, backend, UI or release.

- **P01 bounded gate passed: BA-03 repaired.** Before editing, P00 coverage
  passed and the clean local/remote `ui-wiring` checkout was
  `81cd450e8991f549f7605bebfb9231cf1e063452`. The raw reproduction failed with
  `Executor started after the latch was set: [True]` (**1 failed in 0.54s**).
- [P01 evidence and admission contract](docs/completion/p01_evidence.md) records
  exact commands, tested runtime/test blob hashes, environment, outputs,
  verification/SQLite/undo evidence, recovery and next gate. Reports, JUnit and
  working-file SHA-256 hashes remain ignored under `output/p01/`.
- `pluma/tools/registry.py` now invokes registered executors through the same
  worker-side admission wrapper for thread and process paths. Parent checks
  after policy/pre-state/controller waits do not grant a stale queued permit.
  Noncancellable metadata cannot bypass the latch. Rejected entry returns
  unverified cancellation, without inventing an effect or undo record.
- `CancellationToken` serializes thread admission with cancel and lazily
  publishes a native manual-reset Windows event for owned process workers.
  The zero-time worker kernel read is ordered against SetEvent without a
  child-held lock. Native handles are inherited during spawn and finalized
  with their lifetime. A call admitted before the latch is already in flight;
  no lock is held through its body. P03 still owns interrupting active waits.
- The original BA-03 assertion is unchanged and its xfail marker is removed.
  Twenty-one new admission cases cover policy/pre-state waits, queued thread
  cancellation/timeout, late worker preparation/startup/receive, task ownership,
  successful verification/undo/SQLite, failure readback and handle lifetime.
  Actual Job Object-contained spawned workers prove live gate inheritance,
  cancellation before marker creation, controller rebinding and latch safety
  after owned worker crash. Their exit is read back after fixture cleanup.
- Focused suite: **78 passed in 6.90s**. Relevant regressions: **418 passed,
  3 skipped, 1 deselected, 10 xfailed in 22.10s**. Raw audit: **10 failed,
  5 passed in 0.79s**. Windows 11 build 26200 / Python 3.12.10 / pytest 8.3.3;
  isolated user-local storage, owned inert fixtures, test/audio emulation.
  Existing corpus skips and the unexecuted elevation operation are recorded,
  not acceptance passes or approved limitations. No full unit/product/device/
  install suite or hotkey p95 is claimed. Remaining fixture keys: zero.
- [Live requirements matrix](docs/completion/requirements_matrix.md) still
  validates **298 source items / 324 rows**. BA-03 is implemented for its
  bounded gate; full F-08/G-02 and P10 integration remain open. Eight backend
  findings remain: BA-01/02/04/05/06/07/08/09, with ten failing assertions.
  No remaining assertion was weakened or defect marker removed.
- Active folder remains `D:\Workspace\DEVEL\PLUMA`, branch `ui-wiring`.
  Meaningful P01 changes are committed/pushed there. PR 1 and PR 2 remain
  draft/open and unmerged; `main` stays `6dbf589`. UI source/design and disabled
  action entry are unchanged. No automatic progression or worktree switch.
- Pre-P01 recovery: `81cd450e8991f549f7605bebfb9231cf1e063452`; use a new
  detached worktree as documented in P01 evidence. Existing recovery tags,
  archive/stash and detached audit worktree are preserved. No reset/clean/
  force push or security-policy bypass.
- **Next safe milestone: P02 only, BA-01 latch-all ordering.** Reproduce
  `test_global_stop_latches_every_task_before_first_grace` with `--runxfail`.
  Latch every affected CREATED/RUNNING task before any cleanup/grace wait;
  cover simultaneous STOP/racing requests and preserve P01 admission evidence.
  Keep action entry disabled. P02 must pass before P03; neither was started.

## Previous checkpoint: 2026-10-19, P00 requirements/evidence map

This dated checkpoint supersedes historical completion claims, test counts and
next-phase instructions below. The master specification remains authoritative.

- **P00 documentation gate passed.** The
  [live requirements matrix](docs/completion/requirements_matrix.md) contains
  324 traceable rows covering 298 extracted source items plus 26 cross-cutting
  contracts/optional items: all 72 A-H cases, seven I metrics, 17 J bullets,
  18 section-28 checkboxes, 73 section-21 tool names, 26 UI surfaces, nine BA
  findings, eight locked capabilities, 14 engineering laws, 39 build-plan gate
  bullets and 15 owner placement cases. No product phase or release is marked
  complete. All requirement definitions remain unchanged.
- [P00 evidence and recovery](docs/completion/p00_evidence.md) records the
  inspected source `88078bb3c625f0a741b329144f747bbb3fa1dd69`, actual GitHub
  state, source/test/build hashes, commands/results, historical-claim review,
  source findings and the prioritized bounded P01 packet. The documentation
  checker imports no PLUMA runtime; seven inert negative probes reject omitted
  requirements, altered wording, invalid status/owner/evidence, duplicate IDs
  and malformed rows. Coverage is documentation evidence, not runtime acceptance.
- Active development folder: `D:\Workspace\DEVEL\PLUMA`, branch `ui-wiring`.
  The former `PLUMA-ui-wiring` checkout remains detached at audited `55b625c`;
  the `main` and UI integration worktrees are retained separately.
- Dark native UI and authenticated read-only dashboard status are implemented.
  Command entry remains disabled; action/voice/event/settings/history wiring
  and physical/release acceptance are unfinished.
- [Backend audit](PLUMA.UI/PLUMA.UI/docs/backend_wiring_audit.md): nine open
  findings (eight P1, one conditional P2), reproduced by eleven assertions.
  Fresh P00 audit: **4 passed, 11 xfailed in 1.03s**; raw `--runxfail`:
  **11 failed, 4 passed in 0.90s**. Relevant bounded regressions:
  **277 passed, 1 deselected, 11 xfailed in 9.06s**. Windows 11 build 26200,
  Python 3.12.10 / pytest 8.3.3, isolated user-local storage; audio/test mode
  fixtures, one unexecuted elevation operation. Reports/command vectors/JUnit
  are ignored under `output/p00/`; remaining fixture credentials: zero.
  These are open defects, not backend/device/full-suite certification.
- Fresh source inspection identifies additional required gaps, mapped to their
  later packets: absent catalog ToolSpecs and placeholder browser/process/
  terminal modules; configured step limit not propagated; MEDIUM explicit
  intent and material approval/elevation wiring; clipboard readback and undo
  evidence; real model/STT/OCR cancellation/ONNX/device evidence; effective
  configuration and missing UI events/settings/history. Inspection findings
  require bounded reproduction before repairs and are not extra reproduced BA
  findings. Optional output/wake modes do not make voice input optional.
- Current GitHub query: `main` remains `6dbf589`; PR 1 is draft/open into
  `main`, PR 2 is draft/open from `ui-wiring` into `ui-polish-integration`.
  P00 changes are committed/pushed on the existing `ui-wiring` branch; no merge,
  retarget, force push or worktree switch. Hosted native run `39243181549`
  remains source-specific evidence (head `64559bd`, tested merge `b333e746`),
  not a fresh P00 physical UI test. See the evidence record for its build hash.
- [Completion prompts](PLUMA_COMPLETION_PROMPTS.md) define the remaining work
  against the existing specification/build/acceptance documents. **Next safe
  step: execute P01 only**, first reproducing BA-03 with `--runxfail`, then
  repair actual thread/process executor admission versus STOP during pre-state
  capture/queued work. Keep action entry disabled. P01 must pass its bounded
  gate before P02; P00 did not begin that repair.
  Execute one bounded prompt per task; do not start later milestones automatically.
- Requested workspace cleanup archives obsolete root patch scripts and generated
  output, retains historical records under `docs/history`, and keeps the owner's
  previously untracked capability note in ignored `docs/local`.
  [Cleanup/recovery record](docs/workspace_cleanup.md) names the backups and stash.
- GitHub recovery tags: `pre-ui-wiring-2026-10-19` at `04bc1fb` and
  `pre-project-cleanup-2026-10-19` at `55b625c`. Original branch histories and
  local generated-file state are preserved. No PR is merged by this preparation.
- Pre-P00 recovery source: `88078bb3c625f0a741b329144f747bbb3fa1dd69`.
  Inspect it in a new detached worktree as described in P00 evidence; do not
  reset the active branch or apply archived generated state over current source.
- P00 verification: `python docs/completion/verify_requirements_matrix.py`
  reports **298 source items, 324 traceable rows**, all required wording,
  ownership/status/evidence cells and local links valid; ignored
  `python output/p00/check_matrix.py` passes **seven negative probes**.
  `git diff --check` passes. A separate final diff review checks scope, secrets,
  fabricated success, misleading test claims and preservation of production
  sources/locked documents. No full product suite, device/performance/install
  gate or owner-approved limitation is claimed.
- Cleanup/guide verification: eight housekeeping checks passed (including 46
  resolved local links, 34 ordered prompts, 72 numbered acceptance IDs and 26
  surface IDs); packaging regressions **2 passed in 0.41s**; visible-copy source
  scan **33 compiled XAML files passed**. Helper output/package checks used
  mocked execution and inert binaries, not real acceptance or a distributable.
  Details and commands are in the cleanup record. Backend/tests/UI runtime and
  locked requirement documents remain unchanged from audited `55b625c`.

The sections below are retained historical engineering records. Their older
"COMPLETED", "Certified Stable" and "next Phase 11" statements do not override
this checkpoint or the current audit.

> **CRITICAL PERMANENT DIRECTIVE FOR ALL AGENTS**
>
> `PROJECT_HANDOFF.md` is the **authoritative, permanent live save-state** for PLUMA.
>
> Whenever you finish any phase, before considering that phase complete:
> 1. Verify the work you implemented (run full test suite and phase gate checks).
> 2. Update `PROJECT_HANDOFF.md` to reflect the new verified project state.
> 3. Record the completed phase, new modules, and important changes.
> 4. Record any unresolved issues or known limitations.
> 5. Record any important architectural decisions introduced.
> 6. Record the next phase / current objective.
> 7. Record the **exact next action** another agent should take.
> 8. Remove or correct information that is no longer true.
>
> Assume that at any moment the current model, conversation, session, or account may disappear permanently. A incoming agent must be able to resume development safely using only:
> 1. The existing repository,
> 2. The specification files (`PLUMA_MASTER_SPEC.md`, `AGENTS.md`, `PLUMA_BUILD_PLAN.md`, `PLUMA_ACCEPTANCE_TESTS.md`, `PLUMA_TECH_STACK.md`),
> 3. This `PROJECT_HANDOFF.md` file.

---

## 1. Project Overview & Mission

**PLUMA** is a fully local, voice-first Windows 11 AI desktop assistant engineered with safety, bounded execution, and zero unnecessary runtime overhead at its core.

### Core Immutable Principles
1. **Lightweight Resident Core**: The background process starts and idles without loading LLM, STT, OCR, screen capture loops, or GPU inference.
2. **Unified Voice & Text Pipeline**: Voice is mandatory and enters the identical `PlumaRequest` pipeline, router, policy, tool execution, verification, and ledger path as text (`InputMode` enum only records source).
3. **Deterministic Typed Tools as Execution API**: Natural language is never an execution API. Every action is a registered, typed `ToolSpec`.
4. **Hierarchical Automation Priority**: Native/Application APIs $\rightarrow$ Controlled PowerShell/CLI $\rightarrow$ UI Automation (UIA) $\rightarrow$ Stable Keyboard/Input $\rightarrow$ Targeted OCR $\rightarrow$ Raw coordinates (strictly last resort).
5. **Postcondition Verification**: Every state-changing action has an explicit postcondition and must read it back before reporting success.
6. **Reversibility & Undo Evidence**: Every reversible action captures safe pre-state into an `UndoRecord` before executing.
7. **Task Capsule & Job Object Containment**: Every command is one `TaskCapsule` owned by one `TaskSupervisor`. Spawned subprocesses are assigned to Windows Job Objects (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`).
8. **Global STOP Precedence**: Setting the atomic stop latch immediately rejects all new tool steps, replans, or worker starts. Cleanup strictly avoids touching pre-existing user resources.
9. **Factual Activity Ledger**: All audit history in SQLite is deterministic, template-generated factual data, never LLM hallucination.
10. **Zero Invented UI**: UI is functional contract-based until the project owner provides visual styling direction.

---

## 2. Specification & Reference Documents

| Document | Authority & Scope |
|----------|-------------------|
| [`PLUMA_MASTER_SPEC.md`](file:///D:/Workspace/DEVEL/PLUMA/PLUMA_MASTER_SPEC.md) | **Authoritative product and engineering specification.** Read before making architectural changes. |
| [`AGENTS.md`](file:///D:/Workspace/DEVEL/PLUMA/AGENTS.md) | **Mandatory safety and architecture contract** binding all coding agents. |
| [`PLUMA_BUILD_PLAN.md`](file:///D:/Workspace/DEVEL/PLUMA/PLUMA_BUILD_PLAN.md) | Ordered implementation phases (Phase 0 through Phase 14). |
| [`PLUMA_ACCEPTANCE_TESTS.md`](file:///D:/Workspace/DEVEL/PLUMA/PLUMA_ACCEPTANCE_TESTS.md) | Objective release gates and verification criteria. |
| [`PLUMA_TECH_STACK.md`](file:///D:/Workspace/DEVEL/PLUMA/PLUMA_TECH_STACK.md) | Approved runtime libraries, adapters, and technology stack. |

---

## 3. Technology Stack & Constraints

- **Language & Runtime**: Python 3.12+ (64-bit Windows 11).
- **Core Frameworks**: `pydantic` (v2 schemas), `ctypes` (Win32 API integration), `sqlite3` (WAL mode, async worker thread), `multiprocessing.connection` (local IPC named pipes).
- **Automation Adapters**:
  - Native Win32: `ctypes` `user32`/`kernel32`/`gdi32` (window management, process info, display rects).
  - Shell: `subprocess` with Windows Job Objects and bounded timeouts (`PowerShellAdapter`).
  - UIA: `pywinauto` (UIA backend, lazy import inside methods).
  - Input: `SendInput` ctypes with modifier safety & coordinate bounds checking (`InputAdapter`).
  - Screen: targeted window/rect GDI capture with headless fallback (`ScreenAdapter`).
- **Perception & Models** (lazy/on-demand only in later phases):
  - Audio/STT: `whisper.cpp` / `pywhispercpp` (Phase 6).
  - OCR: `PaddleOCR` / ONNX Runtime (Phase 8).
  - Local Planner: `llama.cpp` (Phase 9).
- **Testing**: `pytest`, `pytest-timeout`, `pyyaml`.

---

## 4. Phase Roadmap & Completion Status

| Phase | Description | Status | Test Count |
|---|---|---|---|
| **Phase 0** | Freeze contracts, schemas, SQLite baseline, benchmarks, golden corpus | **COMPLETED** | 65 |
| **Phase 1** | Resident Core, Task Capsule, Windows Job Objects, atomic STOP sequence | **COMPLETED** | 82 (cumul.) |
| **Phase 2** | Typed tool framework, initial 19 tools, postcondition verifiers, ledger integration | **COMPLETED** | 101 (cumul.) |
| **Phase 3** | Deterministic FAST route, Router, Fast Orchestrator, clipboard & window tools | **COMPLETED** | 220 (cumul.) |
| **Phase 4** | Windows Automation Adapters (Native Win32, PowerShell, UIA, Input, Screen capture) | **COMPLETED** | 246 (cumul.) |
| **Phase 5** | Activity Ledger completion, redaction engine, reverse-order rollback | **COMPLETED** | 266 (cumul.) |
| **Phase 6** | Mandatory voice path (push-to-talk, VAD, whisper.cpp on-demand) | **COMPLETED** | 294 (cumul.) |
| **Phase 7** | UIA perception worker (ScreenElement semantic grounding, snapshot TTL) | **COMPLETED** | 314 (cumul.) |
| **Phase 8** | Targeted OCR fallback (PaddleOCR/ONNX region-only) | **COMPLETED** | 339 (cumul.) |
| **Phase 9** | Replaceable local planner (llama.cpp on-demand manager, grammar constraints) | **COMPLETED** | 365 (cumul.) |
| **Phase 10** | Bounded multi-step orchestration (execute-observe-replan loop, replan limits) | **COMPLETED** | 384 (cumul.) |
| **Phase 11** | Policy engine, risk classifications, single-operation elevation broker | **COMPLETED** | 399 (cumul.) |
| **Phase 12** | Latency and quality benchmark tuning, leak testing | **COMPLETED** | 405 (cumul.) |
| **Phase 13** | Packaging, `%LOCALAPPDATA%` isolation, crash recovery | **COMPLETED** | **430 (cumul.)** |
| **Phase 14** | Owner-directed UI implementation | Blocked on Owner Design | Pending |

---

## 5. Current Verified Implementation Details (Phases 0–11)

### Phase 0: Schema Contracts & Storage Foundation
- [`pluma/brain/schemas.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/schemas.py): `RouteMode` (`FAST`, `SCREEN`, `SMART`, `DEEP`), `PlanMode`, `ToolCall`, `Plan` with hard cap step validation ($N \le 20$).
- [`pluma/core/request.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/request.py): `PlumaRequest`, `InputMode` (`TEXT`, `VOICE`), `RequestID` validation.
- [`pluma/core/cancellation.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/cancellation.py): `CancellationToken`, `StopReason`, `TaskCancelledError`.
- [`pluma/memory/db.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/db.py): SQLite with WAL mode, busy timeout, queued async background writer loop for crash resiliency.

### Phase 1: Resident Core & Process Containment
- [`pluma/core/job_object.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/job_object.py): Win32 `CreateJobObjectW`, `SetInformationJobObject` setting `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, `AssignProcessToJobObject`.
- [`pluma/core/ownership.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/ownership.py): `OwnershipRegistry` tracking PID creation timestamps via `GetProcessTimes` to protect against PID reuse.
- [`pluma/core/task_supervisor.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/task_supervisor.py): Complete task state machine with reverse rollback and Job Object termination.
- [`pluma/core/ipc.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/ipc.py): Local-only Windows named pipe `IpcServer` / `IpcClient`.
- [`pluma/core/resident.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/resident.py): Resident daemon with Win32 `RegisterHotKey` loop and push-to-talk integration.

### Phase 2: Typed Tool Framework & Initial Tools
- [`pluma/tools/base.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/base.py): `ToolSpec`, `ToolResult`, `VerifyResult`, `RiskClass`, `AdapterPriority`.
- [`pluma/tools/registry.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/registry.py): `ToolRegistry` with validation, cancellation checks, policy evaluations, pre-state capture, execution, verification, and ledger writes.
- Deterministic Tool Suites: `files.py`, `apps.py`, `windows.py`, `audio.py`, `system.py`, `clipboard.py`.

### Phase 3: Deterministic FAST Route & Orchestration
- [`pluma/core/router.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/router.py): Regex/pattern classifier routing all golden FAST commands directly without LLM/OCR.
- [`pluma/core/orchestrator.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/orchestrator.py): Command lifecycle coordinator.

### Phase 4: Windows Automation Adapters
- [`pluma/adapters/base.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/base.py): Common error hierarchy and immutable data models.
- [`pluma/adapters/win32.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/win32.py): Native Win32 window and process management.
- [`pluma/adapters/powershell.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/powershell.py): Bounded PowerShell adapter with Job Object containment, timeout limits, and instant cancellation polling loop.
- [`pluma/adapters/uia.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/uia.py): Lazy-loading UI Automation adapter with HWND pre-validation.
- [`pluma/adapters/input.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/input.py): `SendInput` ctypes with modifier safe release.
- [`pluma/adapters/screen.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/screen.py): Targeted window/rect GDI screen capture with headless fallback.

### Phase 5: Activity Ledger, Redaction & Rollback Engine
- [`pluma/memory/activity.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/activity.py): Complete `ActivityLedger` write path and `ActivityQuery` read path.
- [`pluma/memory/redaction.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/redaction.py): Deterministic sensitive-value redaction.
- [`pluma/memory/preferences.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/preferences.py): `PreferencesStore` for user settings.
- [`pluma/memory/aliases.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/aliases.py): `AliasStore` for command aliases.
- [`pluma/memory/routines.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/routines.py): `RoutineStore` for multi-step routines.
- [`pluma/rollback/recipes.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/rollback/recipes.py): `RollbackRecipes` inverse operations.
- [`pluma/rollback/engine.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/rollback/engine.py): `RollbackEngine` reverse-order execution.

### Phase 6: Mandatory Voice Path
- [`pluma/voice/vad.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/vad.py): Lightweight `EnergyVAD` calculation of RMS energy for 16-bit 16kHz PCM audio.
- [`pluma/voice/capture.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/capture.py): `AudioCapture` managing microphone recording with lazy-loaded `sounddevice`.
- [`pluma/voice/stt_adapter.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/stt_adapter.py): `WhisperSttAdapter` for on-demand `whisper.cpp` inference.
- [`pluma/voice/lifecycle.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/lifecycle.py): `VoiceLifecycleManager` managing on-demand loading and idle unload timer.
- [`pluma/voice/pipeline.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/pipeline.py): `VoicePipeline` orchestrating VAD trimming, STT transcription, and material target safety.
- [`pluma/voice/activation.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/activation.py): `VoiceActivation` managing configurable push-to-talk keybindings.

### Phase 7: UIA Perception Worker
- [`pluma/perception/context.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/context.py): `ActiveWindowContext` inspecting active foreground window identity, PID, executable name, geometry, and DPI scale.
- [`pluma/perception/element_refs.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/element_refs.py): `ScreenElement`, `ScreenSnapshot`, `BoundingBox`, and `SnapshotFreshness` models.
- [`pluma/perception/uia_snapshot.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/uia_snapshot.py): `UiaSnapshotBuilder` capturing semantic control trees with window-relative bounding boxes and TTL expiration.
- [`pluma/perception/freshness.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/freshness.py): `FreshnessChecker` asserting TTL expiration and active window focus matching.
- [`pluma/tools/ui.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/ui.py): `inspect_active_window`, `click_element`, and `type_into_element` registered ToolSpecs.
- [`pluma/verify/screen.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/verify/screen.py): `ScreenVerifier` validating control text, invocation accessibility, and window active states.

### Phase 8: Targeted OCR Fallback
- [`pluma/perception/capture.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/capture.py): `WindowCapture` delivering ephemeral in-memory target window and region screen captures.
- [`pluma/perception/ocr_adapter.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/ocr_adapter.py): `OcrAdapter`, `OcrWord`, `OcrResult` with lazy PaddleOCR import, cancellation support, and dependency injection.
- [`pluma/perception/ocr_lifecycle.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/ocr_lifecycle.py): `OcrLifecycleManager` on-demand warm/cold state machine with automatic 10s idle unload timer.
- [`pluma/tools/ui.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/ui.py): `click_ocr_text` tool grounding clicks on visible text, rejecting ambiguous duplicates, and clearing image bytes.
- [`pluma/verify/screen.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/verify/screen.py): `verify_ocr_text_present` and `verify_ocr_text_absent` postcondition verifiers.

### Phase 9: Replaceable Local Planner
- [`pluma/brain/interface.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/interface.py): `PlannerInterface` abstract contract and error hierarchy.
- [`pluma/brain/tool_subset.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/tool_subset.py): `ToolSubsetSelector` selecting route-specific tool schemas (`SMART`, `SCREEN`, `DEEP`) to prevent token bloat and hallucination.
- [`pluma/brain/prompt_builder.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/prompt_builder.py): `PromptBuilder` constructing sanitized prompts with credential redaction.
- [`pluma/brain/validator.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/validator.py): `PlanValidator` strict 2nd-pass validation enforcing tool existence, argument schemas, and hard step limits ($N \le 20$).
- [`pluma/brain/llama_cpp_adapter.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/llama_cpp_adapter.py): `LlamaCppAdapter` pluggable local LLM worker using `llama.cpp` with zero module-level imports.
- [`pluma/brain/lifecycle.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/lifecycle.py): `LlmLifecycleManager` state machine with 30s idle unload timer (`runtime.model_idle_unload_seconds`).

### Phase 10: Bounded Multi-Step Orchestration
- [`pluma/core/multi_step.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/multi_step.py): `MultiStepOrchestrator` coordinating the **Execute $\rightarrow$ Observe $\rightarrow$ Replan** loop with per-step stop-latch checks and reverse rollback.
- [`pluma/core/orchestrator.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/orchestrator.py): Unified 4-route dispatcher (`FAST`, `SMART`, `SCREEN`, `DEEP`).
- [`pluma/core/router.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/router.py): Pattern classifiers for `DEEP` route commands.
- [`pluma/core/task_supervisor.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/task_supervisor.py): State machine transitions with rollback failure handling.

### Phase 11: Policy Engine, Risk Classes & Elevation Broker
- [`pluma/policy/rules.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/policy/rules.py): `PolicyRules` risk classifier (`READ`, `LOW`, `HIGH`, `RESTRICTED`) with protected system path and command detection.
- [`pluma/policy/engine.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/policy/engine.py): `PolicyEngine` evaluating tool calls before execution against confirmation boundaries.
- [`pluma/policy/elevation_broker.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/policy/elevation_broker.py): `ElevationBroker` executing single-operation elevated subprocesses without elevating the resident core.
- [`pluma/ui/confirmations.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/ui/confirmations.py): `ConfirmationContract` functional confirmation interfaces.

---

## 6. Test Suite & Verification Baseline

Run the complete test suite with:
```powershell
python -m pytest tests/unit/ -v
```

**Current status: 393 passed, 0 failed, 0 warnings (Execution time ~11.2s)**

### Test Coverage Summary by File
- `tests/unit/test_policy_engine.py` (9 tests): `READ`/`LOW` auto-approval, `HIGH` confirmation, `RESTRICTED` paths, restricted command patterns, approval/denial callbacks, YAML overrides, ElevationBroker, ToolRegistry integration.
- `tests/unit/test_multi_step_orchestrator.py` (7 tests): Sequential execution, stop-latch checks, replan bounds, rollback on abort, SMART/SCREEN/DEEP e2e routes.
- `tests/unit/test_comprehensive_cross_check.py` (7 tests): Cross-subsystem call contracts, message determinism, activity ledger persistence, 4-route orchestration.
- `tests/unit/test_deep_audit_verification.py` (5 tests): End-to-end multi-subsystem integrity, TTL enforcement, OCR ambiguity, VAD safety, string redaction.
- `tests/unit/test_brain_tool_subset.py` (6 tests): Route-specific tool selection, prompt schema formatting.
- `tests/unit/test_brain_prompt_builder.py` (4 tests): System/user prompt formatting, context injection, credential redaction.
- `tests/unit/test_brain_validator.py` (6 tests): Valid plan acceptance, invented tool rejection, schema mismatch rejection, step count cap.
- `tests/unit/test_brain_lifecycle.py` (5 tests): COLD/WARM state transitions, 30s idle unload timer, cancellation, shutdown.
- `tests/unit/test_brain_llama_cpp_adapter.py` (5 tests): Structured plan generation, complex file decomposition, cancellation, zero module-level imports.
- All existing tests (339 tests across Phases 0–8) fully passing.

---

## 7. Known Architectural Decisions & Technical Nuances

1. **Zero ML at Idle (Spec §4)**: `llama_cpp`, `paddleocr`, and `whisper` are never imported at the module level.
2. **Zero Resident Elevation (Spec §15)**: The PLUMA resident core process NEVER runs elevated. Any action requiring elevation is dispatched as an isolated, single-operation out-of-process execution.
3. **Execute-Observe-Replan Loop (Spec §6)**: Step outputs are verified immediately; failures trigger bounded replanning up to `max_replans = 3`.
4. **Stop-Latch Pre-Check (Spec §12)**: Checked before every tool execution and before every replan invocation; halts immediately if cancelled.
5. **Reverse Rollback on Abort (Spec §13)**: Reversible prior actions are rolled back in reverse order via `RollbackEngine`.
6. **Layering Compliance**: Low-level `pluma.core` does not import high-level `pluma.brain` or `pluma.perception` at module level.

---

## 8. Current Objective & Exact Next Steps

### Next Phase: **Phase 14 — Creator-Directed UI Implementation**
Reference: `PLUMA_BUILD_PLAN.md` Phase 14 & `PLUMA_MASTER_SPEC.md` §16, §17, §18, §19.

### Notes for Phase 14:
- All non-visual functional UI contracts (`ConfirmationContract`, `ActivityViewContract`, `SettingsContract`) are in place.
- Per `PLUMA_BUILD_PLAN.md` §Phase 14 and `AGENTS.md`, Phase 14 is **blocked on user/owner direction** for visual styling.
- Do not invent colors, typography, cards, gradients, waveforms, or AI dashboard aesthetics until the user specifies the UI design.

### Summary of Completed Work (Phases 0–13):
- **414 automated unit and benchmark tests passing with 0 failures and 0 warnings**.
- Standalone packaging configuration in `packaging/pluma.spec`.
- Full production entry point in `pluma/app.py`.
- Windows storage hierarchy under `%LOCALAPPDATA%\Pluma\` and `%APPDATA%\Pluma\`.
- Automatic crash recovery and state reconciliation in `pluma/core/recovery.py`.

### Phase 0: Schema Contracts & Storage Foundation
- [`pluma/brain/schemas.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/schemas.py): `RouteMode` (`FAST`, `SCREEN`, `SMART`, `DEEP`), `PlanMode`, `ToolCall`, `Plan` with hard cap step validation ($N \le 20$).
- [`pluma/core/request.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/request.py): `PlumaRequest`, `InputMode` (`TEXT`, `VOICE`), `RequestID` validation.
- [`pluma/core/cancellation.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/cancellation.py): `CancellationToken`, `StopReason`, `TaskCancelledError`.
- [`pluma/memory/db.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/db.py): SQLite with WAL mode, busy timeout, queued async background writer loop for crash resiliency.

### Phase 1: Resident Core & Process Containment
- [`pluma/core/job_object.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/job_object.py): Win32 `CreateJobObjectW`, `SetInformationJobObject` setting `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, `AssignProcessToJobObject`.
- [`pluma/core/ownership.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/ownership.py): `OwnershipRegistry` tracking PID creation timestamps via `GetProcessTimes` to protect against PID reuse.
- [`pluma/core/task_supervisor.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/task_supervisor.py): Complete task state machine with reverse rollback and Job Object termination.
- [`pluma/core/ipc.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/ipc.py): Local-only Windows named pipe `IpcServer` / `IpcClient`.
- [`pluma/core/resident.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/resident.py): Resident daemon with Win32 `RegisterHotKey` loop and push-to-talk integration.

### Phase 2: Typed Tool Framework & Initial Tools
- [`pluma/tools/base.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/base.py): `ToolSpec`, `ToolResult`, `VerifyResult`, `RiskClass`, `AdapterPriority`.
- [`pluma/tools/registry.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/registry.py): `ToolRegistry` with validation, cancellation checks, pre-state capture, execution, verification, and ledger writes.
- Deterministic Tool Suites: `files.py`, `apps.py`, `windows.py`, `audio.py`, `system.py`, `clipboard.py`.

### Phase 3: Deterministic FAST Route & Orchestration
- [`pluma/core/router.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/router.py): Regex/pattern classifier routing all golden FAST commands directly without LLM/OCR.
- [`pluma/core/orchestrator.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/orchestrator.py): Command lifecycle coordinator.

### Phase 4: Windows Automation Adapters
- [`pluma/adapters/base.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/base.py): Common error hierarchy and immutable data models.
- [`pluma/adapters/win32.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/win32.py): Native Win32 window and process management.
- [`pluma/adapters/powershell.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/powershell.py): Bounded PowerShell adapter with Job Object containment and timeout limits.
- [`pluma/adapters/uia.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/uia.py): Lazy-loading UI Automation adapter with HWND pre-validation.
- [`pluma/adapters/input.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/input.py): `SendInput` ctypes with modifier safe release.
- [`pluma/adapters/screen.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/screen.py): Targeted window/rect GDI screen capture with headless fallback.

### Phase 5: Activity Ledger, Redaction & Rollback Engine
- [`pluma/memory/activity.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/activity.py): Complete `ActivityLedger` write path and `ActivityQuery` read path.
- [`pluma/memory/redaction.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/redaction.py): Deterministic sensitive-value redaction.
- [`pluma/memory/preferences.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/preferences.py): `PreferencesStore` for user settings.
- [`pluma/memory/aliases.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/aliases.py): `AliasStore` for command aliases.
- [`pluma/memory/routines.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/routines.py): `RoutineStore` for multi-step routines.
- [`pluma/rollback/recipes.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/rollback/recipes.py): `RollbackRecipes` inverse operations.
- [`pluma/rollback/engine.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/rollback/engine.py): `RollbackEngine` reverse-order execution.

### Phase 6: Mandatory Voice Path
- [`pluma/voice/vad.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/vad.py): Lightweight `EnergyVAD` calculation of RMS energy for 16-bit 16kHz PCM audio.
- [`pluma/voice/capture.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/capture.py): `AudioCapture` managing microphone recording with lazy-loaded `sounddevice`.
- [`pluma/voice/stt_adapter.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/stt_adapter.py): `WhisperSttAdapter` for on-demand `whisper.cpp` inference.
- [`pluma/voice/lifecycle.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/lifecycle.py): `VoiceLifecycleManager` managing on-demand loading and idle unload timer.
- [`pluma/voice/pipeline.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/pipeline.py): `VoicePipeline` orchestrating VAD trimming, STT transcription, and material target safety.
- [`pluma/voice/activation.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/activation.py): `VoiceActivation` managing configurable push-to-talk keybindings.

### Phase 7: UIA Perception Worker
- [`pluma/perception/context.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/context.py): `ActiveWindowContext` inspecting active foreground window identity, PID, executable name, geometry, and DPI scale.
- [`pluma/perception/element_refs.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/element_refs.py): `ScreenElement`, `ScreenSnapshot`, `BoundingBox`, and `SnapshotFreshness` models.
- [`pluma/perception/uia_snapshot.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/uia_snapshot.py): `UiaSnapshotBuilder` capturing semantic control trees with window-relative bounding boxes and TTL expiration.
- [`pluma/perception/freshness.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/freshness.py): `FreshnessChecker` asserting TTL expiration and active window focus matching.
- [`pluma/tools/ui.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/ui.py): `inspect_active_window`, `click_element`, and `type_into_element` registered ToolSpecs.
- [`pluma/verify/screen.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/verify/screen.py): `ScreenVerifier` validating control text, invocation accessibility, and window active states.

### Phase 8: Targeted OCR Fallback
- [`pluma/perception/capture.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/capture.py): `WindowCapture` delivering ephemeral in-memory target window and region screen captures.
- [`pluma/perception/ocr_adapter.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/ocr_adapter.py): `OcrAdapter`, `OcrWord`, `OcrResult` with lazy PaddleOCR import, cancellation support, and dependency injection.
- [`pluma/perception/ocr_lifecycle.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/ocr_lifecycle.py): `OcrLifecycleManager` on-demand warm/cold state machine with automatic 10s idle unload timer.
- [`pluma/tools/ui.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/ui.py): `click_ocr_text` tool grounding clicks on visible text, rejecting ambiguous duplicates, and clearing image bytes.
- [`pluma/verify/screen.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/verify/screen.py): `verify_ocr_text_present` and `verify_ocr_text_absent` postcondition verifiers.

### Phase 9: Replaceable Local Planner
- [`pluma/brain/interface.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/interface.py): `PlannerInterface` abstract contract and error hierarchy.
- [`pluma/brain/tool_subset.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/tool_subset.py): `ToolSubsetSelector` selecting route-specific tool schemas (`SMART`, `SCREEN`, `DEEP`) to prevent token bloat and hallucination.
- [`pluma/brain/prompt_builder.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/prompt_builder.py): `PromptBuilder` constructing sanitized prompts with credential redaction.
- [`pluma/brain/validator.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/validator.py): `PlanValidator` strict 2nd-pass validation enforcing tool existence, argument schemas, and hard step limits ($N \le 20$).
- [`pluma/brain/llama_cpp_adapter.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/llama_cpp_adapter.py): `LlamaCppAdapter` pluggable local LLM worker using `llama.cpp` with zero module-level imports.
- [`pluma/brain/lifecycle.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/lifecycle.py): `LlmLifecycleManager` state machine with 30s idle unload timer (`runtime.model_idle_unload_seconds`).

### Phase 10: Bounded Multi-Step Orchestration
- [`pluma/core/multi_step.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/multi_step.py): `MultiStepOrchestrator` coordinating the **Execute $\rightarrow$ Observe $\rightarrow$ Replan** loop with per-step stop-latch checks and reverse rollback.
- [`pluma/core/orchestrator.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/orchestrator.py): Unified 4-route dispatcher (`FAST`, `SMART`, `SCREEN`, `DEEP`).
- [`pluma/core/router.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/router.py): Pattern classifiers for `DEEP` route commands.
- [`pluma/core/task_supervisor.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/task_supervisor.py): State machine transitions with rollback failure handling.

---

## 6. Test Suite & Verification Baseline

Run the complete test suite with:
```powershell
python -m pytest tests/unit/ -v
```

**Current status: 377 passed, 0 failed, 0 warnings (Execution time ~11.0s)**

### Test Coverage Summary by File
- `tests/unit/test_multi_step_orchestrator.py` (7 tests): Sequential execution, stop-latch checks, replan bounds, rollback on abort, SMART/SCREEN/DEEP e2e routes.
- `tests/unit/test_deep_audit_verification.py` (5 tests): End-to-end multi-subsystem integrity, TTL enforcement, OCR ambiguity, VAD safety, string redaction.
- `tests/unit/test_brain_tool_subset.py` (6 tests): Route-specific tool selection, prompt schema formatting.
- `tests/unit/test_brain_prompt_builder.py` (4 tests): System/user prompt formatting, context injection, credential redaction.
- `tests/unit/test_brain_validator.py` (6 tests): Valid plan acceptance, invented tool rejection, schema mismatch rejection, step count cap.
- `tests/unit/test_brain_lifecycle.py` (5 tests): COLD/WARM state transitions, 30s idle unload timer, cancellation, shutdown.
- `tests/unit/test_brain_llama_cpp_adapter.py` (5 tests): Structured plan generation, complex file decomposition, cancellation, zero module-level imports.
- All existing tests (339 tests across Phases 0–8) fully passing.

---

## 7. Known Architectural Decisions & Technical Nuances

1. **Zero ML at Idle (Spec §4)**: `llama_cpp`, `paddleocr`, and `whisper` are never imported at the module level.
2. **Execute-Observe-Replan Loop (Spec §6)**: Step outputs are verified immediately; failures trigger bounded replanning up to `max_replans = 3`.
3. **Stop-Latch Pre-Check (Spec §12)**: Checked before every tool execution and before every replan invocation; halts immediately if cancelled.
4. **Reverse Rollback on Abort (Spec §13)**: Reversible prior actions are rolled back in reverse order via `RollbackEngine`.
5. **Layering Compliance**: Low-level `pluma.core` does not import high-level `pluma.brain` or `pluma.perception` at module level.

---

## 8. Current Objective & Exact Next Steps

### Next Phase: **Phase 11 — Policy Engine, Risk Classes & Elevation Broker**
Reference: `PLUMA_BUILD_PLAN.md` Phase 11 & `PLUMA_MASTER_SPEC.md` §14, §15.

### Objectives for Phase 11:
1. **Policy Engine (`pluma/policy/engine.py`, `pluma/policy/rules.py`)**:
   - Evaluates action against policy rules before execution.
   - Risk classifications: `READ`, `LOW`, `HIGH`, `RESTRICTED`.
   - Explicit user confirmations for `HIGH` risk operations (destructive deletes, system modifications).
2. **Single-Operation Elevation Broker (`pluma/policy/elevation_broker.py`)**:
   - Elevated operations run isolated single subprocesses via UAC elevation broker.
   - Resident core NEVER runs elevated; only isolated single tasks.
3. **Confirmation Contract (`pluma/ui/confirmations.py`)**:
   - Functional contract for user confirmation prompts.
4. **Write Unit & Integration Tests**:
   - Policy evaluation for `READ`, `LOW`, `HIGH`, `RESTRICTED` risk classes.
   - Confirmation prompts blocking execution until approved.
   - Elevation broker running single isolated operations.

### Exact Instructions for the Next Agent:
1. Review `PLUMA_BUILD_PLAN.md` (Phase 11 section) and `PLUMA_MASTER_SPEC.md` (§14, §15).
2. Prepare and present the Phase 11 Implementation Plan to the user for approval.
3. Upon approval, implement `pluma/policy/` components and unit tests.
4. Verify all tests pass (`pytest tests/unit/ -v`).
5. Update `PROJECT_HANDOFF.md` before proceeding to Phase 12.

