# E110 — P24 owned read-only corpus slice

Date: 2026-11-10 (Asia/Calcutta)
Tested source commit: `530dfceaf39d33907f71f261e3f617ecfdab560b`
Branch: `p12-preparation`
Status: **bounded P24 packet passed; P24 remains incomplete**

## Scope

Added [`tests/windows/test_p24_owned_readonly_acceptance.py`](../../tests/windows/test_p24_owned_readonly_acceptance.py)
as the first owned-target end-to-end P24 harness. It executes these 14 unique
cases from the fixed 140-case corpus through `PlumaApplicationRuntime`, the
real deterministic router, registered typed tools, policy, executor,
verification and isolated SQLite Activity Ledger:

`GC-046`, `GC-047`, `GC-048`, `GC-056`, `GC-057`, `GC-058`, `GC-059`,
`GC-076`, `GC-077`, `GC-078`, `GC-079`, `GC-084`, `GC-085`, `GC-087`.

The activity queries read only each test runtime's private temporary ledger.
Directory listing changes the test process working directory to a pytest-owned
directory and pytest restores it. File searches use owned temporary roots and
the registered process-isolated worker; each worker identity is checked absent
after terminal cleanup. The native system-status cases take a short resource
snapshot and validate the bounded CPU/RAM/disk readback. No values from that
snapshot are printed into the durable test log. No models, OCR/STT, audio,
clipboard, desktop windows, personal files or resident process were used.

Two explicit parity tests replay `GC-076` and `GC-078` as direct typed text and
voice requests. This proves router/tool/output parity for those two safe flows;
it does **not** exercise microphone capture or Whisper/STT.

## Verification

Environment: isolated Python 3.12.10 under ignored `output/`, pytest 9.2.0,
Pydantic 2.14.3 and PyYAML 6.0.3. Process-local `TEMP`, `TMP`, `LOCALAPPDATA`
and `APPDATA` were redirected beneath the ignored evidence directory. The
entire selection ran sequentially in one pytest process; native read-only
workers and two short-lived junction fixture commands were scoped to test-owned
fixtures. No Python, uv, resident or model process remained when checked after
the run.

Exact test invocation (the listed interpreter was used):

```powershell
$evidence = "$PWD/output/p24-20261110-530dfce"
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
$env:TEMP = "$PWD/output/p24-20261110-530dfce/temp"
$env:TMP = $env:TEMP
$env:LOCALAPPDATA = "$PWD/output/p24-20261110-530dfce/localapp"
$env:APPDATA = "$PWD/output/p24-20261110-530dfce/roamingapp"
New-Item -ItemType Directory -Force -Path $env:TEMP,$env:LOCALAPPDATA,$env:APPDATA | Out-Null
& "$PWD/output/p24-20261110-c9f597f/test-env/Scripts/python.exe" -m pytest tests/unit/test_router.py tests/unit/test_file_search_native.py tests/windows/test_p24_owned_readonly_acceptance.py -p no:cacheprovider -q --junitxml=output/p24-20261110-530dfce/p24-regressions.xml
```

The actual interpreter was
`output/p24-20261110-c9f597f/test-env/Scripts/python.exe`; the durable command
above is shown relative to the repository. Result: **238 passed, 0 failed,
0 errors, 0 skipped in 11.46 seconds**. The router, existing native file-search
and new P24 acceptance cases account for 194, 28 and 16 tests respectively.
JUnit and full command output are retained under the ignored directory
`output/p24-20261110-530dfce/`.

Production source was unchanged from the starting checkpoint `c9f597f`; the
only tracked change since that checkpoint is the acceptance test. Its Git blob
is `fda47d9c10e4880e896cbb206b28d26b61623108`; working-tree SHA-256 at test
time was `63AAA5E398A41FD94C584B598ED17E3C090575848FF04D06EB82A9DF90AE389B`.
The tested commit is `530dfceaf39d33907f71f261e3f617ecfdab560b`. The
subsequent E110/handoff/matrix edits are documentation only and do not alter
the tested code.

During harness development, early runs exposed incorrect test expectations
(schema-added defaults, fixture directory collisions, and output-shape
assumptions). Those assertions were corrected; the final exact-commit run above
is clean. No production defect was reproduced by those harness failures.

## Limits and next packet

This is **14 of 140 unique corpus cases**, all FAST/READ. P24 remains open.
Remaining corpus IDs are `GC-001`–`GC-045`, `GC-049`–`GC-055`,
`GC-060`–`GC-075`, `GC-080`–`GC-083`, `GC-086`, `GC-088`–`GC-125`, and
`GC-N001`–`GC-N015` (126 cases).
Unexecuted work includes the remaining corpus and route classes; screen/UIA/OCR;
native-model planning; real STT; confirmations; mutation/undo/conflict; STOP
across multiple steps; live/saved UI outcomes; and failure/reconnect scenarios.
The two direct `InputMode.VOICE` checks are not native voice acceptance. The
system-status sample is not the P26 resident/performance measurement.

Next safe packet: continue P24 with read-only cases backed by owned data or an
isolated test runtime. Do not inspect personal clipboard, windows or files, or
exercise device/power actions on the owner's desktop. Before native-model or
combined UI acceptance, confirm a bounded isolated environment and available
memory; do not load a large model on the resident path. P25 and later milestones
remain gated by P24 and their own prerequisites.
