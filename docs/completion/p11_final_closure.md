# E57: historical P11 closure claim (superseded by E58)

**Correction (2026-10-25): [E58](p11_production_dispatch_repair.md) supersedes this completion claim. Production dispatch, child cleanup and DNS postcondition defects were subsequently confirmed and repaired. The current request requires passing checks; unavailable interactive checks do not constitute acceptance. The following is historical evidence only.**

2026-10-22, Asia/Calcutta; branch `ui-wiring`, source parent `ca96cd6`.
P11 is complete under the specific owner-approved test limitation recorded
below. P12 has not been started.

## Final P11 gaps closed

`D-10` now has one shared runtime adapter dispatcher in
`pluma/tools/base.py`. Its priority list must match its registered `ToolSpec`.
It advances only when an adapter raises `AdapterUnavailable`, which means the
adapter declined before dispatch. A returned failure, ordinary exception,
invalid result or tool-name mismatch stops the chain; no weaker adapter is
tried after effects may have occurred. Tests cover ordered fallback, no retry
after failure, no undeclared adapter, and priority binding.

`H-05` now dispatches only the registered, argument-free
`flush_dns_cache` ADMIN operation. The policy engine must return
`REQUIRE_ELEVATION`; the registry checks the exact fixed operation, ownership,
process isolation and a durable non-undoable intent before dispatch. The native
adapter uses a fixed PowerShell DNS-cache command, requests one UAC operation,
retains the exact child handle, contains and bounds that child, reads back its
exit, and records the irreversible commit. No generic script, service action,
permanent elevated process or test-mode success path remains. Other ADMIN calls
fail closed.

The native UAC adapter was not launched during verification. The registry,
policy, journal, worker and verifier path was exercised with a named inert
runner; this proves routing and refusal behavior, not Windows UAC or DNS-cache
behavior.

## Owner-approved test limitation

The owner instructed on 2026-10-22: “no need to test. if i encounter any error
during using ill take care” and “if any test is failed, fix it. cant test it?
mention in any other doc that it is not yet tested and finish p11 fully.” This
explicitly approves closing P11 with concrete native checks recorded as
untested. The following physical operations were not performed and are not
claimed as verified:

- switching the active desktop foreground to exercise `focus_window` or
  `focus_app`;
- changing the owner's physical volume, mute state or default audio device;
- locking, sleeping, restarting or shutting down the active computer;
- accepting a real UAC prompt or running the privileged DNS-cache operation.

The guarded implementations, readback/refusal paths and conflict-safe inverse
contracts have prior fixture evidence in E34, E38 and E45. This owner decision
accepts their lack of new physical operation evidence for the P11 milestone;
future use may expose issues that the owner will report. No physical success is
inferred from fixture results. H-04's native confirmation surface remains
owned by P16. The 16 missing screen-control catalog names remain explicit P12
work.

## Verification

Using `output/p11-native-env/Scripts/python.exe` (Python 3.12.10):

```text
python -m pytest tests/unit/test_tool_adapter_dispatch.py tests/unit/test_elevation_dispatch.py tests/unit/test_policy_engine.py tests/unit/test_policy_boundary.py tests/unit/test_schemas.py tests/unit/test_tools_ui.py -q
90 passed in 4.10s
```

This focused suite covers the changed dispatcher and elevation integration,
existing policy boundaries, schemas and UI ToolSpec construction. Its elevation
tests inject an inert runner; none opens UAC. Physical focus/audio/power/UAC
tests above were deliberately not run under the owner's instruction. Earlier
focused attempts exposed a missing dataclass import and two incorrect fixture
expectations; those were fixed before the final passing run. `compileall` passed
for all changed Python modules and tests. The final requirements-matrix check
reported **298 source items and 324 traceable rows PASS**; `git diff --check`
passed.

P11 is recorded complete under this concrete limitation. P12 is the next safe
milestone; do not begin it automatically.
