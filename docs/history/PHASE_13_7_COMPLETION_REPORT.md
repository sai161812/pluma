# Phase 13.7 Release-Hardening Completion Report

## 1. App Job Object Containment
- Removed WindowsJobObject from the worker payload since Windows kernel handles cannot cross process boundaries through multiprocessing.Process serialization.
- Transferred Job Object instantiation and assign_process() binding to the parent process within ToolRegistry.execute (registry.py).
- Added robust error handling in the parent process to terminate processes (taskkill) and fail-closed if Job Object containment cannot be established.
- Confirmed fix with test_phase13_7_job_object_stop.py which demonstrates strict bounding: stopping the parent task safely kills its descendant PLUMA windows while preserving independent instances. (Switched test to charmap.exe to avoid false positives caused by Windows 11 notepad.exe UWP delegation behavior).

## 2. Deterministic STOP Sequence
- Wired RollbackEngine inside TaskSupervisor properly for clean shutdown handling.
- Implemented grace_s parameter in stop_task for cooperative cancellation timeouts.
- Allowed valid transitions from CREATED directly to STOPPING within the finite state machine so aborted voice-capture intents do not deadlock.

## 3. Tool Permissions & Replanner Boundaries
- Updated ToolSubsetSelector logic to strictly fail-closed for the FAST route, preventing malicious input from circumventing SMART authorization.
- Added explicit unit testing covering FAST route subset checks for critical operations.
- Resolved permission revalidation failures during MultiStepOrchestrator execution by passing RouteMode securely into the tool_permitted check.

## 4. UI Freshness Grounding
- Overhauled ui.py click and type executors to demand deep freshness checks via SnapshotRegistry.resolve(snapshot_id).
- Replaced ambiguous soft warnings with hard deterministic failures terminating click_element when freshness constraints (20px window position drift, elapsed TTL) are violated.
- Wrote integration test test_phase13_7_ocr_grounding.py.

## 5. Adversarial Corpus Release
- Populated tests/fixtures/golden_commands.yaml with 15 strictly verified negative adversarial inputs.
- Hardened test infrastructure to correctly expect DENY outcomes in test_phase135_adversarial.py instead of breaking test flow.
- Removed legacy update_golden.py bypassing validation.

## Release Evidence
- Full test suite execution: 182 Passed, 0 Failed.
- Git working tree: Clean (0 uncommitted files).
- SHA-256 build: Release ZIP successfully generated with build_release.py.

Phase 13.7 is locked and successfully passes the PLUMA_ACCEPTANCE_TESTS.md master specification without regression.
