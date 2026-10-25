# P12 exact screen-control catalog and E-01 to E-10 verification (E66)

## Outcome

All 16 exact Section 21 screen-control names are now registered as typed
`ToolSpec`s and available on the SCREEN and DEEP routes. The current owned
Win32 acceptance suite passes all seven cases, covering E-01 through E-06,
E-08 and E-09; E-07 and E-10 pass in the focused OCR integration tests. P12 is
still open: the locked PaddleOCR/ONNX tiny/small configuration and its accuracy
evidence are not part of this catalog change and remain `CORE-OCR` work. No P13
work was started.

## Catalog implementation

The public catalog contains:

- **Perception:** `get_active_window_context`, `inspect_window_controls`,
  `capture_target_window`, `read_visible_text`, `find_visible_text`,
  `refresh_screen_snapshot`.
- **UI interaction:** `find_control`, `invoke_control`, `set_control_text`,
  `read_control_text`, `wait_for_control`, `invoke_screen_element`.
- **Input fallback:** `press_key`, `hotkey`, `type_text`,
  `click_window_relative`.

Each entry has a strict argument schema, an ordered adapter declaration, a
bounded timeout and a route entry. Grounded operations resolve task-owned
snapshot and element references, recheck process creation identity, HWND,
window class/title, geometry and DPI, and refuse ambiguous or stale targets.
UIA is used for semantic controls; the combined screen-element action uses OCR
only for an OCR-grounded target. OCR observes only an on-demand target window
or requested region. Capture bytes are discarded in memory, and OCR/control
text is redacted from Activity Ledger output.

Text edits use the UIA Value pattern, not the accessible label, and refuse
password or unclassified controls. The previous value stays in a bounded,
30-minute parent-process cache; the durable undo record contains only target
identity and a random reference. Manual undo and STOP rollback require the
same process/window/control identity and the expected post-edit value, then
read the restored value back. Stable key and hotkey actions require an explicit
postcondition; `type_text` requires an expected UIA text value.

`pluma/tools/screen_catalog.py` contains the 16 ToolSpecs. `pluma/tools/ui.py`
registers them while retaining the existing aliases. `pluma/brain/tool_subset.py`
exposes them to SCREEN and DEEP plans. `pluma/tools/registry.py` carries only a
fresh snapshot into each owned worker and registers new snapshots in the task
registry before stripping the raw tree from the returned result. `app.py` wires
the private text inverse into automatic rollback.

## E-01 to E-10 evidence

| Gate | Current evidence |
|---|---|
| E-01 | Native Win32 semantic inspection passes in `test_p12_e01_e02_semantic_inspection_and_submit_use_uia_only`; the exact catalog's native UIA inspection also passes. The WPF fixture was attempted and is blocked by Windows Application Control, as detailed below. Its earlier successful run remains in E62. |
| E-02 | The owned Win32 Submit control is invoked through UIA, with an independent enabled-state and status readback; OCR is not called. |
| E-03 | Duplicate UIA labels are refused before mutation in the owned Win32 fixture. |
| E-04 | A changed target HWND/process is rejected before the UIA action adapter is reached. |
| E-05 | Moving the owned window during OCR causes stale geometry refusal and no click. DPI drift and identity changes are also covered by unit cases. |
| E-06 | The native owned-window test captures only the requested window-relative region and feeds that crop to OCR. Region bounds/offsets also have focused unit coverage. |
| E-07 | OCR target transition is checked against the target text and bounds; unrelated text-count changes do not verify the action. Post-recognition errors remain failures. |
| E-08 | The owned textless window returns a bounded refusal and dispatches no guessed click. |
| E-09 | Native and unit checks confirm captures remain in memory; no image bytes, image references or temporary capture files are returned/persisted. |
| E-10 | An uncooperative OCR worker is stopped through `TaskSupervisor`; the worker is absent and no later click marker is created. |

The OCR transition and STOP fixtures inject deterministic OCR output. They do
not certify the production OCR engine's accuracy or the locked ONNX runtime
configuration.

## Verification

Environment: Windows 11 build 26200, Python 3.12.10, pytest 8.3.3,
pywinauto 0.6.9, .NET SDK 10.0.401, .NET 8.0.31.

```text
Focused screen/UIA/OCR/dispatch/rollback regressions: 251 passed in 45.37s; zero skips.
tests/windows/test_p12_uia_semantic_controls.py: 7 passed in 3.02s; zero skips.
py_compile: passed for all 18 changed Python source/test modules.
requirements matrix: PASS, 298 source items and 324 traceable rows.
git diff --check: PASS; Git emitted only LF-to-CRLF normalization advisories.
```

The WPF fixture was executed, not skipped, but failed before readiness with
CLR exit `3762504530` (`0xE0434352`). Windows Application log event 1026 records
`FileLoadException` for the locally built fixture DLL with
`0x800711C7` (“An Application Control policy has blocked this file”). Rebuilding
under the repository's ignored `output/` directory produced the same policy
block. The application-control policy was left unchanged; E62 retains the
earlier passing WPF inspection evidence. This is an environment limitation,
not a passing retest.

The ancillary clipboard-write regression was also attempted because this
change extends `undo_last`. Its 21 native cases failed at fixture setup when
Windows reported that the named window station already exists; 22 other cases
in that command passed. The fixture refused to reuse the existing station, so
no clipboard mutation ran. The directly relevant manual-undo and rollback
regressions passed in the focused suite.

## Remaining P12 work

The exact 16-name screen catalog is complete. P12 overall remains open for the
locked PaddleOCR/ONNX tiny/small backend configuration and associated accuracy
evidence (`CORE-OCR`). The WPF rerun remains blocked by the active application
control policy; no setting was weakened. Await the owner's next instruction;
do not start P13 automatically.
