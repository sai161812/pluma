# E105 - P22 completion recheck

Status: bounded corrections implemented; final acceptance pending. P23 has not started.

Base `38825bcd9cee6e27fd29626f2a77d6702cfba044` on p12-preparation.
Recovery: recovery/pre-p22-e105-20261104. Main remains 0468a03.
The unchanged complete master was reused (blob
01b693dbf898b662aa4cd67736c1a0e8a21cf3e3); AGENTS, P22/shared contract,
build/acceptance, matrix, E104 and current source/tests/Git were refreshed.

The recheck identified three bounded P22 gaps:

- Failed startup returned after an incomplete owned drain without scheduling
  its continuation. CoreHost now retries that retained drain before creating
  a fresh control-only graph; storage and leases stay owned until verified.
- A stopped mandatory voice polling owner left Core ready while its text/STOP
  registration thread lived. Readiness now requires both owners; loss seals
  readiness and triggers the existing verified drain/control recovery path.
- Health/runtime disconnect cleared setup proof but could leave ordinary
  command readiness cached. HealthController now revokes readiness on explicit
  read failure or disconnected/not-ready runtime and restores it from live
  authenticated runtime evidence. Native acceptance includes actual IPC loss.

Pre-edit: 78 affected Python checks pass. Two new isolated backend regressions
fail on base at the expected state/readiness assertions, then the affected
selection passes 80 checks. C# compilation: zero warnings/errors. New C# tests
cover disconnected/reconnected runtime and failed explicit health reads.
The native fixture stops only its owned IPC server and tests disabled command
entry/unavailable recovery; no personal process or desktop state is touched.
The native Python harness can stop only its own voice polling owner after real
setup acceptance and verify a new cold control graph without fake readiness.

Unique ignored evidence root:
output/p22-e105-20261104-184859-3b59f9d2/.
Each run has separate argv, JUnit, text, source identity and artifact records.
E104 evidence remains historical; no reports are overwritten or reconstructed.
Full regressions/native gates, final review and completion checkpoint are pending.
Existing P25 owner-approved C-02 timing and later physical/installed/release
limitations are retained. No dependency, master or approved styling change.
