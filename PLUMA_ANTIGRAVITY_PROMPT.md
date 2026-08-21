# Antigravity Handoff Prompt for PLUMA

Use this prompt after opening the PLUMA project directory. Attach or place these
files in the same project before sending it:

```text
PLUMA_MASTER_SPEC.md
AGENTS.md
PLUMA_BUILD_PLAN.md
PLUMA_ACCEPTANCE_TESTS.md
```

Keep `PLUMA_Final_Build_Guide.docx` as a reference copy if desired, but treat
the Markdown master specification as the searchable source of truth during
implementation.

## Initial prompt — paste this first

```text
You are the lead engineer for PLUMA.

The project directory contains:
- PLUMA_MASTER_SPEC.md — authoritative product and engineering specification
- AGENTS.md — mandatory safety, architecture and workflow contract
- PLUMA_BUILD_PLAN.md — ordered implementation phases
- PLUMA_ACCEPTANCE_TESTS.md — objective release and phase gates

Read all four files completely before modifying anything. Do not start coding
yet.

Your job is to build PLUMA exactly as specified:

- fully local Windows 11 agent;
- mandatory voice and text input through one pipeline;
- UI Automation first and targeted OCR fallback for screen-aware execution;
- deterministic typed tools as the execution API;
- local planner only when deterministic routing is insufficient;
- essential global STOP with an atomic stop latch, cancellation, owned-process
  termination, safe rollback and cleanup;
- verified postconditions for every state-changing action;
- SQLite Activity Ledger with factual deterministic text;
- heavy STT/OCR/planner components cold or unloaded while idle;
- owner-defined UI with no invented AI visual style or filler text.

Do not use paid APIs, remote browser agents, unrestricted shell execution,
permanent administrator privileges, continuous screen monitoring, raw pixel
clicking as the primary method, or any substitute architecture.

After reading the files, return only:

1. Your understanding of the locked requirements.
2. The proposed repository/module map.
3. The exact Phase 0 files you intend to create.
4. The acceptance tests that will prove Phase 0.
5. Risks or ambiguities that require owner approval.

Do not edit files until I approve this plan.
Do not continue beyond Phase 0 without a new instruction.
```

## Phase implementation prompt template

```text
Implement Phase <NUMBER> from PLUMA_BUILD_PLAN.md and no later phase.

Before editing:
1. Re-read the relevant sections of PLUMA_MASTER_SPEC.md.
2. Inspect the existing implementation and tests.
3. List the files you will change and why.
4. List the acceptance tests you will run.

Implementation rules:
- Preserve all existing contracts and earlier passing behavior.
- Keep external libraries behind adapters/interfaces.
- Do not invent UI styling.
- Do not add cloud inference or paid services.
- Do not create untracked subprocesses or detached task branches.
- Check the task stop latch before every tool start and replan.
- Never report success without postcondition verification.
- Redact secrets and do not persist raw audio/screenshots by default.

After editing:
1. Run focused tests for this phase.
2. Run the relevant regression tests.
3. Inspect the complete git diff.
4. Report changed files, test commands/results, measured timings and known
   limitations.
5. Stop and wait for approval.
```

## Review prompt

```text
Act as a strict PLUMA verification engineer. Do not rewrite the implementation.

Read PLUMA_MASTER_SPEC.md, AGENTS.md, PLUMA_BUILD_PLAN.md and
PLUMA_ACCEPTANCE_TESTS.md. Inspect the current git diff and test results.

Audit specifically for:
- missing locked requirements;
- LLM/OCR/STT accidentally running while idle;
- natural-language or unrestricted shell execution paths;
- missing schema validation or policy checks;
- actions that claim success without verification;
- missing undo/pre-state capture;
- STOP races where a new step starts after the latch;
- untracked subprocesses, orphan workers or unsafe cleanup;
- stale UIA/OCR target use;
- screenshot/audio/secret leakage;
- invented AI-looking UI text or styling;
- tests that merely mock the behavior instead of proving it.

Return a severity-ranked finding list with file/function references and the
exact acceptance test that is missing or failing. Do not make changes unless I
explicitly ask you to fix a finding.
```

## Bug-fix prompt

```text
Fix only the approved PLUMA issue below:

<paste one reproducible issue>

First reproduce it with a focused test. Make the smallest safe change. Preserve
the Task Capsule, STOP, policy, verification, rollback and ledger contracts.
Run the focused test and the relevant regression suite. Show the diff and stop.
```
