# PLUMA remaining work

Current checkpoint: 2026-11-11. [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md) is the
current handoff. The owner requested repository consolidation, with no further
milestone development until new instructions. `main` is the only local and
GitHub branch; this maintenance checkpoint is not a finished release.

## Recorded progress

- P00-P23: scoped implementation and acceptance under recorded owner limits;
  see [E109](docs/completion/e109_p00_p23_readiness.md) and
  [E108](docs/completion/e108_p23_live_hosting.md).
- P24: 25/140 unique corpus cases accepted, 115 remaining. E113/E119 fixture
  evidence remains; physical/native evidence is identified separately.
- E114-E118: unfinished release/benchmark source preparation archived at
  commit `751fa87` and in the local recovery bundle. It is excluded from the
  active `caaec5b` production baseline and must be reviewed before reuse.

## Remaining existing milestones

| ID | Required work |
| --- | --- |
| P24 | Remaining 115 corpus cases, voice/text/native planner and UIA/OCR paths, confirmations, STOP under load, undo/conflict, reconnect/failure and factual UI/ledger outcomes. Original E112 cold failure remains unexplained. |
| P25 | Physical Windows surfaces, monitor/DPI, accessibility/input, microphone boundary retest and deferred focus/audio checks. |
| P26 | Actual laptop idle/GPU/RAM, latency, STT/OCR/planner quality and 50-cycle evidence. |
| P27 | Adversarial IPC/privacy/ownership, partial failure, crash and recovery review. |
| P28 | Reproducible Core+WinUI package, offline rebuild/provenance and authorized signatures. |
| P29 | Disposable-profile clean installation, startup, upgrade/migration, interrupted recovery and uninstall. |
| P30 | Fresh independent review and repair review. |
| P31 | Exact-build final regression, native/physical/security/performance/installed acceptance. |
| P32 | Release integration/tagging after release gates; the maintenance consolidation is not that gate. |
| P33 | Verified usable release and setup/recovery/maintenance handover. |

Requirements remain in PLUMA_MASTER_SPEC.md, PLUMA_BUILD_PLAN.md,
PLUMA_ACCEPTANCE_TESTS.md and the detailed PLUMA_COMPLETION_PROMPTS.md contracts.
No acceptance gate was waived by stopping development or deleting old branches.

## Next authorized development step

None under the current cleanup request. A future request can select the next
bounded P24 acceptance packet, using owned fixtures and existing valid evidence.
Preserve the owner's C-02/P25 and other physical deferrals. Avoid uncontrolled
model loads, parallel builds or personal-desktop tests.

The full prior inventory, case IDs and source-only notes remain in
[the historical snapshot](docs/history/PLUMA_REMAINING_WORK_20261111.md).
Recovery and exact branch disposition are in PROJECT_HANDOFF.md and
[E120](docs/completion/e120_repository_consolidation.md).
