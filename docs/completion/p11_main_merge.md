# E61: P00-P11 main merge and P12 readiness

2026-10-25, Asia/Calcutta. The owner explicitly requested a safe GitHub main merge, proper documentation/messages, verification and preparation for P12. This supersedes E60's instruction to wait for merge authorization; its physical acceptance limitations remain in force.

## Actual GitHub merge record

| Change | Reviewed head | Main merge commit |
|---|---|---|
| [PR 1: dark WinUI foundation](https://github.com/sai161812/pluma/pull/1) | `9544752d1af4d675b50ff7aa8e99fb27da9c722f` | `3cb367d3a387987b6872c493521eeaab59651d68` |
| [PR 2: P00-P11 implementation](https://github.com/sai161812/pluma/pull/2) | `34a8471be6d159b245efe4e2f7fac1dd5c9d806f` | `812a8b9c05e7c7e8852be1841ae5e47677f6382f` |

Refreshed both PR descriptions with current implementation scope, validation, limitations and integration order. Marked them ready and used normal merge commits with GitHub expected-head guards; no squash/rebase, force push, branch deletion or protection override. PR 1 merged first. PR 2 was then retargeted from integration to main, rechecked for mergeability and merged. The PR/commit messages state the owner authorization, test evidence, deferred physical checks and absence of a release/P12 claim.

Fetched GitHub main after each merge. The PR 2 merge candidate and resulting main tree both equal the reviewed head's complete tree:

```text
34a8471 tree = 812a8b9 tree = c4fcb264c98d39fa4cdcc8fe9b2b593813de6542
pluma tree = 90bdbebb7c5b12b6f229cf213a7849ce14d69adb
PLUMA.UI tree = 9bb00e1477775092b8bb37a2d6da4d61d3c521bb
```

`git diff --exit-code origin/main HEAD` was empty before creating this documentation branch. No source or test conflict was resolved by hand. Other worktrees and their local main/integration pointers were preserved; GitHub's `origin/main` is the merged authority. The primary checkout was fast-forwarded to the merged revision, then a separate `docs/p11-main-handoff` branch was created for this documentation-only follow-up. This PR's documentation changes do not alter the code/test/UI trees above.

## Verification

Pre-merge [E60](p11_merge_readiness.md) records fresh **435 prerequisites, 1,274 catalog regressions, 319 routing/contracts and 283 clipboard checks**, each with zero failed/error/skipped cases, plus 39 IPC checks. No deferred physical effect was counted as passing.

GitHub Windows UI verification succeeded on both exact reviewed heads:

- [PR 1 run 39160052427](https://github.com/sai161812/pluma/actions/runs/39160052427).
- [PR 2 run 40199073748](https://github.com/sai161812/pluma/actions/runs/40199073748), current head `34a8471`, checked before merging. Its tested file tree is the resulting main file tree. This is tree-equivalent CI evidence, not an assertion that a new workflow ran on the main merge SHA.

Fresh post-merge checks run from actual merge revision `812a8b9`, Windows 11 build 26200, Python 3.12.10:

- `python output/p11-e61/run_checks.py prerequisites`: **435 passed in 56.63s**, zero failures/errors/skips, exit zero. The ignored runner copies E60's fixed 435-case safety/credential/voice-lifecycle/ownership/rollback/shutdown set, isolated storage, source hashes and actual exit/JUnit recording. Original BA assertions run with `--runxfail`; no exclusion is added.
- `dotnet run --project PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj --verbosity quiet -p:UseSharedCompilation=false`, with `PLUMA_TEST_PYTHON` pointing to the test interpreter: **39 IPC checks passed**, exit zero, including production Python/C# authenticated round trips.
- Requirements-matrix validation and diff checks are repeated for the documentation follow-up. No source change justifies rerunning the 1,274-case catalog or privileged DNS flush after the complete tree-equivalence check.

Local Application Control restrictions remain unchanged; the blocked unsigned UI-runner attempts are still not passes. Actual native UI fixture CI is the source of that verification. Physical focus/audio, taskbar/monitor/DPI/accessibility and later model/microphone/perception/end-to-end/device acceptance remain required at their recorded final/later gates. This merge is a tested development baseline, not a release.

## Ready for P12, not started

P12 must follow `PLUMA_COMPLETION_PROMPTS.md` and acceptance E-01 through E-10. Existing screen ToolSpecs/perception modules are partial implementations; their names alone are not acceptance. The 16 unregistered section-21 screen names remain MISSING, and the E rows remain UNVERIFIED.

First safe bounded work packet when the owner instructs P12:

1. Create a fresh development branch from updated GitHub main; do not reuse an old detached checkout or edit another worktree's local main.
2. Read the immutable master, agent contract, P12 prompt, UIA/OCR build gates, E acceptance rows, technology contract and current matrix. Inspect the existing context/UIA snapshot/ToolSpec/reference code and tests before selecting exact files.
3. Start with E-01/E-02 semantic target-window inspection and the exact registered capability needed for that bounded path. Use a deterministic owned Win32/WPF fixture. Demonstrate semantic control identity and that UIA avoids OCR when it can resolve the target.
4. Keep cancellation, window/process creation identity, short-lived references, geometry/DPI checks, independent transition readback and transient capture privacy. Test ambiguity, stale references, target closure and denial before broadening scope. Add further P12 catalog tools in separate bounded tasks.
5. Update the matrix and evidence, commit/push meaningful changes, then stop at that task's gate. Preserve the native dark design and disabled UI action entry; no unrequested wiring/planner/voice phase is authorized.

Only this plan was prepared. No P12 implementation or test acceptance is claimed.

## Recovery and continuation

Pre-merge main: `6dbf58925352d41a0196dda33044b18282cc6ddf`; reviewed P11 head: `34a8471`; merged implementation checkpoint: `812a8b9`. Development branches, recovery tags and worktrees were preserved. If a defect appears, create a bounded fix/revert PR against main using these exact commits; do not reset main or rewrite merged history. Record the exact failing behavior and run affected checks. The final handoff documentation is integrated separately so the verified implementation checkpoint stays identifiable.

Final documentation checks: matrix **PASS (298 source items / 324 rows)**; `git diff --check` **PASS**; source/test/UI diff against merged main **empty**. The follow-up PR contains documentation only. A successful documentation merge leaves the tested implementation tree identifiers unchanged.
