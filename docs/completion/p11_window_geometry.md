# P11 native window geometry (E30)

2026-10-21, Asia/Calcutta. Started at pushed ui-wiring `27bee2c`.
P11 incomplete; P12 forbidden. Only owned hidden fixture windows were moved or
resized. No user window/input, UI design, device, clipboard, power, security,
dependency or immutable specification change. Action entry stays disabled.

## Implemented

- Exact registered move_window / resize_window with strict HWND, PID, creation
  FILETIME and bounded integer geometry. LOW deterministic policy precedes
  capture. Required owned worker; no title substring or foreground fallback.
- Native checks original process identity, top-level normal window, owning PID/
  thread, class digest, DPI and awareness. Capture preserves position/size and
  expected geometry. A changed target/geometry before dispatch is refused.
- Geometry uses the target window's native DPI coordinate units, explicitly
  reported as coordinate_space=window_dpi. Thread awareness matches the target
  for reads/writes and is restored. It does not claim that legacy logical units
  are physical screen pixels. No screen perception or raw-input coordinates.
- SetWindowPos is asynchronous, bounded by readback, with NOACTIVATE/NOZORDER
  and NOSIZE for move or NOMOVE for resize. Success requires exact native
  geometry and unchanged identity/DPI; a return value alone is insufficient.
  Application clamping, changed DPI/identity, hung/refused updates and timeout
  remain failed/unverified with the pre-state retained.
- Guarded window_geometry inverse is integrated with automatic recipes and
  durable manual undo. It restores only when identity/DPI and current geometry
  still match the recorded output. Newer owner geometry is preserved. Actual
  inverse readback and journal consumption precede success.

Changed: pluma/adapters/window_geometry.py, tools/windows.py, memory/undo.py,
rollback/recipes.py, brain/tool_subset.py, tests/unit/test_window_geometry_native.py;
handoff, matrix/current audit checkpoints and this evidence.

## Checks and provenance

```powershell
output/p11-native-env/Scripts/python.exe output/p11_window_geometry/run_checks.py window-geometry-focused-2
output/p11-native-env/Scripts/python.exe output/p11_window_geometry/run_checks.py window-geometry-regression-final
output/p11-native-env/Scripts/python.exe output/p11_window_geometry/run_checks.py raw-e30-final
output/p11-native-env/Scripts/python.exe output/p11_window_geometry/run_checks.py containment-e30-final
output/p11-native-env/Scripts/python.exe output/p11_window_geometry/run_checks.py recovery-e30-final
output/p11-native-env/Scripts/python.exe docs/completion/verify_requirements_matrix.py
```

- Focused before final denial/automatic-inverse additions: 15 passed in 12.25s.
- Reviewed affected regression: **348 passed in 137.21s**, wall 138.223s.
  Includes all **18 final native geometry cases**, process controls, native file
  inverse, memory/manual undo, recipes/journal, policy/admission, owned capture/
  verification, shutdown/outcomes/cleanup and schema selection. Unselected
  elevation/physical UI/model/device/performance/release gates are not passes.
- Raw backend --runxfail **15 passed (0.54s)**, native containment **3 (3.63s)**,
  recovery **5 (0.56s)**. Actual exits zero, isolated fixture keys zero, all
  recorded runtime/test hashes match reviewed source. Existing 20-second
  per-test / 240-second suite bounds unchanged; no test assertion weakened.
- First focused run: 10 passed / 4 failed. Native direct geometry worked but
  worker success/undo failed exact readback. A retained diagnostic isolated
  requested x=17 versus actual x=18 when physical awareness forced a legacy
  window through scaling. Matching the target awareness fixed native semantics;
  exact assertions stayed intact. Both failed diagnostic runs are retained.
  No claim of multi-monitor or all-scale physical application certification.
- Earlier E28/E29 regression numbers retain their original source provenance;
  they are not reruns of E30. Do not add overlapping counts.

Catalog now: **40 registered / 33 unregistered; 22 IMPLEMENTED / 33 MISSING /
2 DEFECTIVE / 16 UNVERIFIED**. Sixteen untouched P12 names; **17 missing P11
names** plus existing native/legacy inverse and A/D/H gates remain mandatory.
This is bounded normal top-level geometry, not certification of other window
operations, app adapters, full P11 or eligibility for P12.

Reviewed official native references:
[GetWindowDpiAwarenessContext](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowdpiawarenesscontext),
[Windows DPI contexts](https://learn.microsoft.com/en-us/windows/win32/hidpi/high-dpi-desktop-application-development-on-windows).
