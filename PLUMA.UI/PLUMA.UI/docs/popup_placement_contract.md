# Shared bottom-right popup placement contract

Date: 2026-10-18. Branch: `ui-polish`.
Owner refinement: 2026-10-19, following two marked desktop screenshots.
Status: the lower hidden-taskbar anchor, reveal/hide glide and stable class
sizes are implemented. The current native preview launch is blocked by Windows
Application Control. Current checks and pending runtime evidence are in
[popup_placement_refinement.md](popup_placement_refinement.md).
This document is the reference before backend wiring. Existing controls,
their dark resources, and their approved appearance remain the starting point.

## Owner decisions

- All floating surfaces listed below appear at the bottom right.
- Popups have comfortable clearance from screen edges and corners and are
  uniformly aligned and spaced. No content, border, shadow, or animation may
  be cut by a screen edge.
- A newly displayed notification is the lowest entry. Older visible entries
  move up smoothly to make room.
- Several notifications must form a clean, readable stack.
- Placement accounts for the owner's auto-hide taskbar, including its reveal
  when the pointer moves to the bottom edge.
- With the taskbar hidden, use the lower screen-edge anchor, roughly matching
  the owner's marked area. Do not reserve the entire invisible taskbar footprint.
  When it reveals, glide up above it; when it fully hides, glide back down.
- Every notification in the same class has the same width and height. Short
  and long messages must not produce miniature or oversized variants.
- Entry, reflow, and disappearance are smooth. Completion must not cause an
  abrupt visual collapse.
- Keep the existing native Windows dark appearance. This is layout and motion
  direction; it does not authorize a new dark palette or a component redesign.

## Surface membership

One coordinated desktop stack owns all these surfaces. Individual components
must not choose independent overlapping desktop positions.

| IDs | Stack content |
|---|---|
| 4, 5, 6, 9, 20 | Task running, step progress, route, rollback, and STOP feedback |
| 7, 8 | Tool call and result cards |
| 11, 12, 13, 14 | One voice entry containing the existing listening/transcription/committed/timeout states |
| 17, 19, 21, 24 | Verification, policy block, worker termination, and general notices |

Surfaces 11-14 are states/parts of the same voice host, not four simultaneous
desktop cards. Modal dialogs 10/18/25 retain native ContentDialog hosting;
capture flash 15 and match indicator 16 retain target-window geometry. Main
pages, feed 22, health 23, and setup 26 keep their established app context.

## Layout baseline for implementation

The owner specified comfortable, consistent spacing. Use these initial layout
values, drawn from the existing spacing scale, when implementing that direction:

| Setting | Baseline |
|---|---|
| Outer clearance | 24 DIPs inside the usable screen area, on every relevant edge |
| Space between entries | 12 DIPs |
| Right alignment | A common right edge for every visible entry |
| Stack width | At most the existing 460-DIP voice width, clamped to available space |
| Component dimensions | Stable class footprints below, clamped only when the usable display is smaller |
| Text | Existing bounded wrapping/scrolling and readable font sizes |

The implementation reserves another 8 DIPs inside the 24-DIP clearance for native
shadows, and measures each native window's frame outside its client area. The
460-DIP limit applies to component content; outer bounds include that frame.
Include shadow and motion extents inside the outer clearance. Measure content
before positioning it. A taller message must not push another entry offscreen.
Clamp available dimensions before arranging text. Longer content scrolls within
the fixed class footprint; it never enlarges the outer window. The existing
voice geometry and transcript viewport remain unchanged.

| Class / surface IDs | Content size in DIPs |
|---|---|
| Task/progress/STOP/termination: 4, 5, 20, 21 | 360 x 152 |
| Route: 6 | 260 x 112 |
| Tool call/result: 7, 8 | 420 x 176 |
| Rollback: 9 | 380 x 276 |
| Unified voice: 11-14 | Existing 460 x 276 |
| Verification/policy/general notice: 17, 19, 24 | 400 x 112 |

`PopupSizing.cs` is the single size source. Existing dark resources, native
controls, text sizes, inner padding and status alignment remain the starting
point. Fixed native client dimensions and the existing scroll viewports keep
message length from changing class size.

Let `safe` be the selected monitor's usable rectangle after taskbar/appbar
exclusions. In DIPs, arrange visible entries from newest to oldest:

```text
inset = 24 + 8  # edge clearance plus shadow reserve
right = safe.right - inset
bottom = safe.bottom - inset
for entry in newest_to_oldest:
    measure entry within the available width and height
    x = right - entry.width
    y = bottom - entry.height
    require x >= safe.left + inset and y >= safe.top + inset
    bottom = y - 12
```

This produces oldest at the top and newest at the bottom. Fit checks must
include all entries and the animated path. On a very small usable area, keep
unshowable routine entries pending instead of partially displaying them.

## Monitor, DPI, and taskbar behavior

- Select the monitor associated with the invoking task/voice activation. Use
  the PLUMA window's monitor as fallback, then the primary display. Keep one
  stack on that monitor; pointer movement does not select another monitor.
  Actual taskbar reveal/hide changes only the stack's anchor.
- Read the monitor's current work area and docked appbar exclusions. Explicitly
  normalize monitor-relative coordinates and desktop coordinates. Test monitors
  with negative origins and non-primary positions.
- Keep DIPs and AppWindow pixel coordinates separate. Convert once at the
  native window boundary using that monitor/window's current DPI.
- Detect an auto-hide appbar on the selected monitor. Use its current on-screen
  window bounds to distinguish the hidden activation strip (at most 2 DIPs)
  from a revealing bar. Cache its measured full thickness. As soon as reveal
  begins, glide toward the full-thickness exclusion; hold that raised anchor
  until the bar has fully retreated to the activation strip. Do not use the
  narrow strip as the revealed bar's full thickness.
- Do not add the same taskbar exclusion twice when the work area already
  reserves it. The raised stack must stay above the taskbar and must
  leave the edge activation strip available to Windows.
- Re-read/reflow on taskbar configuration, work-area, display, or DPI changes,
  including monitor disconnection and resolution changes. Use native events;
  no cursor polling, OCR, capture loop, or microphone activation is needed.
- Resolve unknown taskbar geometry conservatively and verify the full revealed
  bounds before considering placement accepted. Do not claim taskbar safety
  from a fixed pixel offset or a hidden-taskbar screenshot alone.
- Placement reads Windows state; it never changes the user's auto-hide setting
  or moves, hides, or resizes the Windows taskbar.

Relevant native references:

- [DisplayArea.WorkArea](https://learn.microsoft.com/en-us/windows/windows-app-sdk/api/winrt/microsoft.ui.windowing.displayarea.workarea?view=windows-app-sdk-2.0)
  supplies the work rectangle, with the origin described relative to display
  bounds, and excludes docked desktop elements.
- [ABM_GETAUTOHIDEBAREX](https://learn.microsoft.com/en-us/windows/win32/shell/abm-getautohidebarex)
  locates an auto-hide appbar by monitor and edge; its handle does not by itself
  supply the full revealed rectangle. The placement adapter must obtain and
  validate that geometry separately.
- [GetDpiForWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getdpiforwindow)
  reports DPI according to window awareness; validate the window/DPI result
  before conversion.

## Ordering, updates, and overflow

- Assign an arrival sequence to each new displayed entry. New entries join
  the bottom; existing entries retain their relative order and animate upward.
- Updates to an existing task/tool presentation use its stable identity.
  Transcript partials, elapsed time, and step updates must not create a new
  notification on every change. A tool's result can update its running card.
- Coalesce repeated status updates and repeated identical notices. Every
  distinct factual event remains available to the appropriate event/history
  path; visual coalescing must not invent or erase a ledger result.
- Admit entries according to measured usable height, not an unbounded list.
  Retire the oldest completed/dismissible notices first with an exit animation.
  Keep still-relevant voice/progress state represented; queue routine overflow
  until it fits when no dismissible entry can make room.
- Bound the pending queue, coalesce superseded state, and keep factual history
  available in the app. Burst traffic must not create offscreen windows.
- STOP feedback can replace current progress and takes priority over routine
  queued notices. The STOP latch/cancellation happens first; queue handling or
  animation must never delay it. Modal safety decisions remain outside this
  transient queue.

## Motion and lifetime

Keep the existing Windows motion style. Implementation defaults are a 200-ms
entry/reflow and a 160-ms exit, using cubic ease-out. Native card windows use
uniform opacity for entry/exit and move in physical pixels during reflow. These
are implementation defaults; they do not change factual completion or timeout
semantics.

1. Measure and position the new entry inside the safe bounds before revealing
   it. Fade in at its final position after earlier cards have made room. This
   keeps the clear gap intact throughout the animation.
2. On arrival, smoothly move older entries up while the newest settles at the
   bottom. Retarget interrupted movement from its current visual position.
3. On completion, dismissal, or expiry, fade the entry out before removing
   it from layout. Smoothly close the gap among the surviving entries.
4. Coordinate host motion with existing child animations/timers so a child's
   immediate `Visibility` collapse cannot cut off the shared exit animation.
5. Honor Windows' animation preference; when animations are disabled, place or
   remove immediately with the same safe bounds and ordering.
6. Allow users to scroll/read long content and operate close controls. Prevent
   expiry from removing content while it has pointer/keyboard reading focus.
7. Routine notifications do not steal keyboard focus or block unrelated desktop
   input. Input regions outside the visible cards and taskbar reveal edge stay
   usable.
8. The host owns subscriptions, timers, and animation completion work and
   releases them on dismissal, unload, or shutdown. Visual dismissal does not
   report task success or cancel a task implicitly.

Taskbar reveal/hide uses a shared 200-ms reflow clock and pixel-rounded
translations so neighboring cards retain their gap. If a card is already
exiting, all participating translations use the same 160-ms clock while its
opacity fades. An unsafe overflow or a real monitor/DPI/work-area change may
still require an immediate safe reflow instead of moving content offscreen.

[RepositionThemeTransition](https://learn.microsoft.com/en-us/windows/windows-app-sdk/api/winrt/microsoft.ui.xaml.media.animation.repositionthemetransition?view=windows-app-sdk-2.0)
is a native reference for layout reflow. Microsoft documents its restriction
with virtualizing panels, so use an appropriate bounded layout or composition
animation for the desktop stack. Verify actual enter/reflow/exit behavior;
static component PNGs cannot demonstrate smooth motion.

## Required acceptance evidence

These checks define acceptance for the desktop host. Executed checks and
remaining physical/interactive cases are recorded separately in
[popup_stack_verification.md](popup_stack_verification.md).

| ID | Case | Required result |
|---|---|---|
| P-01 | One popup of each participating type | Common bottom-right anchor; 24-DIP safe inset; all edges/shadows visible |
| P-02 | A, then B, then C | Visible order A/B/C from top to bottom; each arrival smoothly moves earlier entries up |
| P-03 | Remove middle, oldest, then newest | Exit completes cleanly; survivors reflow with no overlap or abrupt collapse |
| P-04 | Mixed voice, tool, progress, and notices | One shared lane; voice uses one entry; consistent right edge and 12-DIP gaps |
| P-05 | Long text, long words, Unicode, enlarged text | Fixed class size; bounded wrapping/scrolling; readable content and controls stay on screen |
| P-06 | Auto-hide taskbar hidden, revealed by bottom-edge pointer movement, then hidden | Lower anchor while hidden; smooth upward glide on reveal and downward glide after hide; edge activation still works; stable card sizes and gaps |
| P-07 | Taskbar auto-hide toggled, docked area changed, Explorer/taskbar restarted | Geometry is refreshed and the stack remains within verified safe bounds |
| P-08 | 100%, 125%, 150%, 200% DPI; negative-origin secondary monitor | Insets/gaps retain their DIP sizes; pixel conversion and selected monitor are correct |
| P-09 | Resolution change, smaller work area, monitor disconnect | Stack reflows or retires/queues overflow; no entry is stranded offscreen |
| P-10 | Burst of arrivals and repeated updates during motion | Stable ordering, retargeted smooth motion, bounded visible/pending state, no duplicate status spam |
| P-11 | STOP during a full stack and active animations | Cancellation is immediate and independent of UI motion; STOP feedback is promptly visible |
| P-12 | Completion/expiry while reading or scrolling | Reading is preserved; coordinated exit is smooth when dismissal is allowed |
| P-13 | Windows animations disabled | Correct placement/order with immediate transitions |
| P-14 | Close/shutdown during movement or expiry | Owned work is cancelled/cleaned up; no orphan popup, timer, or callback |
| P-15 | Dark appearance and popup messages | Existing dark resources retained; readable copy; no visible underscores or em dashes |

Record Windows version, commit, monitor/work-area/taskbar geometry, DPI,
entry order/bounds, animation setting, and pass/fail output. Use owned fixture
windows; explicitly requested recordings/renders are review artifacts. Do not
add routine screenshot persistence or infer backend success from a popup.

## Current implementation and next step

`SurfaceGalleryWindow` previews individual controls. `VoiceOverlayPreviewWindow`
is a legacy standalone microphone preview, with its own fixed-offset positioning;
it does not implement this shared stack. Its current positioning must not be
copied into production as proof of DPI/taskbar compliance.

`PopupStackHost` coordinates card-sized native windows through
`PopupDesktopPlacement`, `PopupStackState`, and `PopupStackLayout`. The bounded
queue admits at most 48 identities; callers must handle a false admission
result and retain factual history. Existing identities update in place. A full
queue does not silently delete active state. Routine displayed overflow fades
out; protected/pending entries wait without offscreen windows or expiry.

`MainWindow.Popups` creates the host lazily. Normal launch opens the main window;
the legacy microphone fixture now requires `--voice-preview`. The explicit
`--popup-stack-preview` and `--popup-stack-audit <directory>` paths use existing
components and deterministic data, without microphone or core activation.

The native adapter reads taskbar/monitor state and observes shell/display events.
It distinguishes an actually hidden auto-hide bar from a revealed one. Measured
full thickness is reserved only during reveal; unverified geometry falls back
to a conservative 64-DIP reservation. Card XamlRoot changes trigger DPI
measurement. Taskbar visibility changes glide; unrelated geometry changes snap
into safe bounds. No Windows setting is modified. Finish the current native
acceptance cases before real event wiring.
This contract does not define a new IPC protocol.

New owned popup windows start transparently without taking foreground focus.
Their first visible frame waits for Loaded and XAML bounds matching the actual
native client rectangle. Root-size changes trigger a frame-aware remeasurement;
pending reconciliation is not considered settled. Existing native InfoBar
backgrounds on surfaces 17, 19 and 24 fill the shared 112-DIP class viewport via
the scoped native minimum-height resource, including the themed border. Short
messages must not leave an unused host-background strip below the notice.

The same readiness gate applies when replacing content in an existing native
window, including a progress-to-STOP update. Preserve its identity and ordering,
pause its display lifetime, and keep replacement content transparent until it
is Loaded and the XAML/native client bounds match. Then use the existing entry
fade; do not animate visible content through a mismatched client size or count
an unready replacement as displayed. Native audit checks both same-class and
STOP replacements and every sampled visible frame.

## Historical verification of the requirements-only update

- Confirmed that membership covers exactly the 15 surface IDs selected by the
  owner, with voice 11-14 grouped as one entry.
- Confirmed that P-01 through P-15 are present and relative Markdown links in
  the updated contract/reference/inventory/gallery/review documents resolve.
- `./PLUMA.UI/check-surface-copy.ps1`: PASS for all 33 compiled XAML files.
- `dotnet build PLUMA.UI/PLUMA.UI/PLUMA.UI.csproj -p:Platform=x64 -p:SurfaceGalleryPreview=true -p:OutDir=D:\Workspace\DEVEL\PLUMA\output\ui-placement-preview\ --no-restore -v:minimal`:
  build succeeded, 0 warnings and 0 errors.
- Inspected `git diff` and confirmed that code changes are preview descriptions
  and a legacy-host comment; no layout, palette, core behavior, or IPC change
  is being claimed by this documentation commit.

Those source/document checks predated the implementation. Current executed
native and simulated evidence is in `popup_stack_verification.md`; that report
does not infer physical taskbar interaction from a static capture.
