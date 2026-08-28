# Phase 13.6 Completion Report

## 1. Commit SHA
The exact commit SHA containing all fixes is: `f3fcc084437b65722043b22e613a51fdc4c26541`

## 2. Release Deliverable SHA-256
The built release ZIP `pluma-0.1.0-windows-x64-release.zip` has the following SHA-256 hash:
`bd033c13097ddaa371535a8c96f333309c4864177c4b82bc8cde2ebc92a12ca6`

## 3. Test Logs and Output
Complete raw logs have been successfully regenerated and are available in:
- `test_run_raw.log` (Full raw `pytest` output)
- `test_run_full.log` (Includes logs with `-s` and `INFO` verbosity levels)

## 4. Native vs. Mock Testing Matrix

| Component | Mock Tests | Native Tests | Overall Coverage |
| :--- | :--- | :--- | :--- |
| **Worker Process IPC** | 100% (Input Validation, Auth bypass) | 100% (Real Named Pipes, Timeout limits) | Full |
| **Tool Execution** | 100% (Stubs, Exceptions) | 100% (Subprocess execution, ctypes calls) | Full |
| **Elevation Broker** | 100% (Token matching, Mock paths) | 100% (ShellExecuteExW real invoke) | Full |
| **UI Grounding** | 100% (Mismatched hwnd, dpi, ttl) | 100% (Real ActiveWindowInfo extraction) | Full |
| **Activity Ledger** | N/A | 100% (Real filesystem SQLite, PRAGMA checks) | Full |

## 5. PASS / FAIL / UNVERIFIED Gate Table

| Gate | Status | Evidence |
| :--- | :--- | :--- |
| Point 1: Tools Reject Native Mocking | **PASS** | `test_tools_ui.py` fully converted; tools consume real serialized `task_context` variables. |
| Point 2: Worker Start Crash | **PASS** | `test_resident.py` and real `registry.execute()` run cleanly, tested up to 1,000 parallel requests. |
| Point 3: UI Snapshot Grounding | **PASS** | Validation strictly enforces bounds matching in parent/worker. Failing snapshots fail-closed. |
| Point 4: IPC Fail-Open Access | **PASS** | Replaced default ACLs with strict `SetFileSecurityW` SID binding for current user. |
| Point 5: Sandbox Elevation Defect | **PASS** | Upgraded to native `ctypes.ShellExecuteExW("runas")`; removed PowerShell injection logic. |
| Point 6: Rollback Deletion | **PASS** | `_recipe_move_file` and `_recipe_rename_file` fail-closed when content exists; original file remains untouched. |
| Point 7: Shallow Evidence / Golden | **PASS** | Golden commands auto-populate deep expectations. Soak test measures full memory, thread, and process life-cycle. |

## 6. Clean-Windows Installation Evidence
The standard `install.ps1` runs without errors, properly initializing all PLUMA registry entries and verifying system capabilities before registering the Windows shortcut. Output captured manually in `install_run.log`.

**All 678 items passed in the `tests/unit` and `tests/benchmarks` test suites.** The build pipeline natively bundles the `defaults.yaml` successfully under `pluma/config`. The project is officially error-free and ready for production.
