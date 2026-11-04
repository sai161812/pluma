# P23 perception feedback contract

E106 adds observation transport; E107 adds a native target probe and revocable
presentation lease. Neither checkpoint enables a renderer. UI-15/16 remain
UNWIRED until native delivery, hosting and combined acceptance pass.

## Observation channel

`perception_query` is an explicit authenticated read-only V1 query with only
request identity. `perception_snapshot` carries at most 256 unique task entries.
Each observation is scoped to the original task/request, snapshot and sequence.
It contains HWND/PID/native process FILETIME, class, caption SHA256, window
bounds, DPI, captured window-relative region, UTC observation/expiry and the
actual match state. UNIQUE alone includes a registered OCR element's UUID,
bounds and finite confidence. No screenshot, caption, recognized text, search
query or input command is transported by this channel.

Three E106 producers publish after verified execution and saved history:
capture_target_window, read_visible_text and find_visible_text. Reads neither
capture nor renew lifetime. STOP, terminal state, removed snapshots and original
wall/monotonic expiry clear the observation. `requires_target_revalidation`
must always be true. This metadata cannot authorize input or prove success.

## E107 freshness boundary

`NativePerceptionTarget.Read` inspects an explicit HWND without activating it,
capturing pixels, sending app commands or owning the target. It reads current
PID, process creation FILETIME, class, hashed caption, bounds, DPI, monitor,
visibility and foreground status. Native handles are closed; caller thread DPI
context is restored. Identity/geometry/DPI/class/caption are checked again during
the probe. Same-process targets are refused because native caption reads would
otherwise send a synchronous message to PLUMA's UI thread.

Bounds follow the existing backend's **window_dpi** contract: the probe matches
the target's DPI awareness context. These are not necessarily physical pixels.
The E107 lease refuses legacy/system-aware coordinates; a subsequent host must
implement and verify explicit native conversion before presenting those targets.
Do not silently multiply their coordinates by the reported target DPI.

`PerceptionPresentation` admits a strict observation only for the same RUNNING
task/request on an authenticated connected, ready runtime with priority STOP
clear, fresh native identity and a visible foreground target. NONE/AMBIGUOUS
matches grant no lease. Capture-only observations can supply flash geometry.
The host must pass fresh runtime/STOP state and call native revalidation before
each presentation/update. A changed HWND/PID/creation/class/caption/geometry/
DPI/monitor, hidden/minimized/foreground-lost target, missing task, disconnect,
STOP, exception, wall reversal or expiry permanently revokes that lease.
Revalidation includes time spent probing and never extends original expiry.

For validated physical coordinates only, returned DesktopX/Y are physical ROI
origin; Width/Height and match offsets/sizes are DIPs at the observed target
DPI. A unique marker uses actual confidence. Negative monitor coordinates and
ROI origin subtraction are retained. No guessed label is supplied by this layer.

## Remaining production integration

The future owner must serialize observation readback under shell lifetime,
deduplicate original observation IDs/sequences, revoke on immediate priority
STOP/terminal/disconnect, and bound/native-check every display update. Do not
recreate revoked leases to resurrect the same observation or restart TTL.
Live/in-worker delivery and other capture paths remain open; current post-tool
publication can be too brief for single-step tasks. No new idle capture loop
or ML worker is permitted.

Surfaces 15/16 require an owned, input-transparent, nonactivating native host
bound to the captured target/region, outside the notification stack. Keep their
existing XAML geometry/styles and transient image policy. Validate host DPI and
actual screen bounds, legacy conversion, moved/closed targets, monitor changes,
stale/duplicate/ambiguous matches and STOP with owned fixtures. Surface 17 stays
in its existing notification lane and requires saved actual verifier readback;
a capture flash or match never supplies that proof.

Native read-only probe evidence and deterministic lease evidence are separate
from combined visual/foreground/device acceptance. No full P23 claim is made.
