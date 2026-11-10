# E114 - Release and installation safety code preparation

Date: 2026-11-10 (Asia/Calcutta)
Branch: `p12-preparation`
Code base before these edits: `caaec5b0f9f1bcebc27b4eb5c6dd627c7065b8ad`
Prepared source checkpoint: `4918bf5a70c987f72b9c2f562e58b1809015270f`
Status: **CODE PREPARED, NOT BUILT OR TESTED; P28/P29 GATES REMAIN OPEN**

## Source changes prepared

- `build_release.py` no longer deletes repository `build`, `dist`, `release`,
  egg-info, caches, or bytecode. It writes to a new checkout-contained ignored
  output directory, routes PyInstaller's work and distribution paths there,
  verifies archive hashes, and labels its result backend-only. It explicitly
  does not claim to produce the required unified Core + WinUI signed release.
- `install.ps1` checks the selected Python version numerically, checks each
  native exit code, installs the declared Windows/media/STT/OCR extras, verifies
  installed distribution metadata before startup publication, and writes an
  installation ownership marker. Existing unmarked target data is refused.
- `uninstall.ps1` removes process-name force termination. It requires the
  installer marker, checks exact installation paths, refuses while matching
  installed executables are running, checks recursive-removal targets for
  reparse points, removes only its own matching startup link, and preserves
  user data by default. Purge requires the exact canonical path typed by the
  user. It currently asks the owner to close PLUMA; it does not yet initiate a
  graceful resident shutdown, so the P29 shutdown/readback requirement remains
  open.
- `tests/windows/test_p24_owned_undo_acceptance.py` prepares GC-054/GC-055
  owned undo coverage; see E113.

## Verification and limitations

The owner directed that code work continue before tests. No build, repository
installer/uninstaller script, test suite, or product process was launched.
These source changes are therefore **unverified**; no P24/P28/P29 gate is
closed by this record. `git diff --check` and source review are the only checks
intended before committing this preparation. The exact WinUI distribution,
signing, offline dependency closure, cold packaged launch, clean install,
upgrade, recovery, and uninstall acceptance remain open. PowerShell behavior,
filesystem race resistance, and archive output still require isolated Windows
verification.

E113's tests remain unverified. P24 still has 20 accepted cases out of 140 and
the E112 cold-run failure remains unexplained. This preparation does not
authorize advancing the ordered release gates or merging to `main`.

## Acceptance checks still required

- Build in a unique ignored output path while placing sentinel data in existing
  root `build`, `dist`, `release`, cache and egg-info paths; verify every
  sentinel is unchanged and validate every archive manifest entry.
- In a disposable install profile, exercise Python below 3.12, failed venv,
  failed package install, missing runtime distributions and startup-shortcut
  conflicts. Each failure must preserve the preexisting startup entry and must
  not report success. Verify a successful install's exact path, version,
  ownership marker, Core/UI handshake and startup readback. Verify that an old
  unmarked target is refused without modification.
- In a disposable uninstall profile, verify a same-name process outside the
  install path remains untouched, an exact install-path process causes safe
  refusal, default removal preserves data, and purge/reparse/custom-path cases
  cannot escape the marked installation root. Close the remaining graceful
  shutdown/readback requirement without process-name or force-kill shortcuts.
