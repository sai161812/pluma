# P23 perception feedback contract

E106 adds observation transport; E107 adds a native target probe and revocable
presentation lease. E108 connects owned-worker live observations and a native
host. UI-15/16 are wired candidates, UNVERIFIED until combined acceptance passes.

## Observation channel

`perception_query` is an explicit authenticated read-only V1 query with only
request identity. `perception_snapshot` carries at most 256 unique task entries.
Each observation is scoped to the original task/request, snapshot and sequence.
It contains HWND/PID/native process FILETIME, class, caption SHA256, window
bounds, DPI, captured window-relative region, UTC observation/expiry and the
actual match state. UNIQUE alone includes a registered OCR element's UUID,
bounds and finite confidence. No screenshot, caption, recognized text, search
query or input command is transported by this channel.

E108 streams actual capture/match evidence during execution for capture_target_window,
read_visible_text, find_visible_text, OCR refresh and click_ocr_text fallback.
Final verified tool receipts retain the E106 path without replay. Reads neither
capture nor renew lifetime. STOP, failed terminal state, removed active snapshots and original
wall/monotonic expiry clear the observation. `requires_target_revalidation`
must always be true. This metadata cannot authorize input or prove success.

## E107 freshness boundary

`NativePerceptionTarget.Read` inspects an explicit HWND without activating it,
capturing pixels, sending app commands or owning the target. It reads current
PID, process creation FILETIME, class, hashed caption, bounds, DPI, monitor,
visibility and foreground status. Native handles are closed; caller thread DPI
context is restored. Identity/geometry/DPI/class/caption are checked again during
the probe. E108 uses Windows' cached InternalGetWindowText for same-process
captions, avoiding synchronous WM_GETTEXT. If that cache API is unavailable,
presentation is refused; no unsafe message-based fallback is used. Windows
documents this cache API as compatibility-sensitive, so native acceptance must
verify it on the supported Windows build.

Bounds follow the existing backend's **window_dpi** contract: the probe matches
the target's DPI awareness context. These are not necessarily physical pixels.
The E107 lease refused legacy/system-aware coordinates without a converter.
E108 supplies LogicalToPhysicalPointForPerMonitorDPI for every ROI/match corner,
then converts relative physical geometry into host DIPs using its actual scale.
The original identity is rechecked after mapping. A failure clears the layer.
Do not multiply legacy coordinates by the reported target DPI.

`PerceptionPresentation` admits a strict observation for the same RUNNING
task/request, or a parent-stamped SUCCEEDED observation after terminal persistence,
on an authenticated connected, ready runtime with priority STOP
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

## E108 production integration and required acceptance

The runtime observer serializes observation readback under shell lifetime.
The native host must continue to
deduplicate original observation IDs/sequences, revoke on immediate priority
STOP/failure/disconnect, and bound/native-check every display update. Do not
recreate revoked leases to resurrect the same observation or restart TTL.
Worker messages are enabled only for admitted registered producers and bounded
to four per call. Intermediate fresh snapshots are private observation evidence;
they never become admitted planner/action refs. A verified successful short task
retains metadata only until the original observation expiry; its snapshot registry
and all image resources are released. This supersedes E106/E107's terminal-clear
candidate behavior, which could lose captures between UI polls. The parent alone
stamps task_phase; worker evidence cannot supply it. Failed persistence withholds
the tail. Global/scoped STOP and shutdown revoke it without changing completed
history. The shared observer reads for at most three seconds after running work
or a terminal ledger notice, then returns to idle. Native priority STOP also
rejects observations captured before its cutoff, including late completed tails.
No observation is replayed or granted a new TTL. No idle capture loop or ML worker
is introduced.

Surfaces 15/16 use an owned, input-transparent, nonactivating native host
bound to the captured target/region, outside the notification stack. Keep their
existing XAML geometry/styles and transient image policy. Validate host DPI and
actual screen bounds, legacy conversion, moved/closed targets, monitor changes,
stale/duplicate/ambiguous matches and STOP with owned fixtures. Surface 17 stays
in its existing notification lane and requires saved actual verifier readback;
a capture flash or match never supplies that proof.

Native read-only probe evidence and deterministic lease evidence are separate
from combined visual/foreground/device acceptance. E108 records the exact-source
gate result before any full P23 claim. Model preparation is on-demand before
fresh capture; only installed local weights are loaded during execution.

API contracts: [native point conversion](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-logicaltophysicalpointforpermonitordpi),
[SystemBackdrop attachment](https://learn.microsoft.com/en-us/windows/windows-app-sdk/api/winrt/microsoft.ui.xaml.media.systembackdrop.ontargetconnected),
[composition backdrop brush](https://learn.microsoft.com/en-us/windows/windows-app-sdk/api/winrt/microsoft.ui.composition.icompositionsupportssystembackdrop.systembackdrop).
