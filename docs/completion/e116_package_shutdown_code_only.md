# E116 — Unified package and graceful Core shutdown source preparation

Date: 2026-11-10 (Asia/Calcutta); branch: `p12-preparation`; source base:
`3fb26f70be6e8918e915212aa44d02d19cefdac1`.
Status: **SOURCE PREPARED ONLY — NO TESTS, BUILDS, INSTALLS OR PRODUCT PROCESSES RUN**

## Code prepared

- `build_release.py` now prepares one x64 Windows candidate containing the Core
  wheel, resolved Windows/media/STT/OCR wheelhouse, self-contained WinUI
  publish, and retained Python/NuGet lock and package inputs. The package is hash-manifested,
  uses fixed archive timestamps, refuses output-directory reuse, isolates
  generated build output, and limits MSBuild to one worker. It does not clean the
  checkout. The package is explicitly unsigned and not a production release.
- `install.ps1` requires the unified bundle and validates every listed SHA-256
  before changing the target. It installs the runtime dependencies with pip's
  offline-only wheelhouse, checks that the installed Core version matches the
  packaged Core wheel, copies and hashes back the WinUI payload, publishes only
  the lightweight Core in Startup, and provides an explicit Start Menu UI link.
  It refuses unmarked UI directories and ambiguous live processes.
- `pluma/core/health_contracts.py`, `pluma/core/host.py`, `pluma/core/ipc.py`,
  and `pluma/app.py` add an authenticated, identity-bound `core_shutdown`
  request. The request validates the exact install executable, PID, creation
  time and Core instance; it latches admission and task shutdown, acknowledges
  before the owner loop drains, and requires bounded process-exit readback. The
  IPC control is admitted through the priority-control lane. No force-kill path
  was added.
- `uninstall.ps1` requests that same authenticated Core shutdown and checks for
  remaining install-owned processes. It refuses while the WinUI shell remains
  open, removes only recorded app payload/shortcuts, and retains user data by
  default. Existing purge confirmation and reparse-point protections remain.
- `README.md` describes the package candidate and its actual unsigned/unverified
  limits. No WinUI visual or interaction code changed.

## Verification limits

At the owner's request, no tests or builds were run. No PowerShell installer or
uninstaller was invoked, no dotnet or pip command ran, and no PLUMA resident or
UI process was launched. Consequently, Python compilation, PowerShell syntax,
archive creation, bundle integrity, offline dependency
resolution, graceful IPC shutdown, native launch, upgrade, recovery and
uninstall are **unverified**. This document records implementation intent, not
acceptance evidence.

Remaining blockers include the authorized Windows signing route; exact-build
package/install/upgrade/recovery acceptance; UI/Core launch and IPC readback;
P24's 120 unaccepted corpus cases and retained E112 cold-run failure; P25
physical checks; P26 target-laptop measurements; P27 adversarial/crash gates;
P30 independent review; P31 final acceptance; and gated P32 integration/P33
handover. Models remain external. P28/P29 and the overall project are not
complete, and `main` was not changed.

The root `uv.lock` was preserved and is not part of this work. No test/build
output was created.
