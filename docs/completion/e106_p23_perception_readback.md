# E106 - P23 packet 1: transient perception observation readback

Implementation checkpoint; final checks pending. P23 is in progress, not complete.
P24 has not started. Base 681c439 on p12-preparation; recovery point
recovery/pre-p23-e106-20261104. Main stays 0468a03.

AGENTS, unchanged complete master (blob 01b693dbf898b662aa4cd67736c1a0e8a21cf3e3),
P23/shared execution contract, E105 handoff, applicable E-01 through E-10 and
surface contracts/matrix were reviewed. Pre-edit affected prerequisites: 76 pass.

This bounded packet adds metadata-only, task-owned observation readback before
wiring surfaces 15/16. Three production producers are covered: capture_target_window,
read_visible_text and find_visible_text. Capture success now rechecks target
identity/geometry after pixels are obtained: a reproduced movement race previously
returned success, and now fails closed. OCR matches use actual observed element
geometry/confidence and publish a marker candidate only for a unique match.
Zero/ambiguous matches retain that fact without inventing a selected element.

Private worker receipts are admitted only after verified result and history
recording, anchored to the same task's snapshot registry. No screenshot bytes,
OCR text, query or window title appears in this new channel. A hash replaces
the title, and native process creation identity plus HWND/PID/class/bounds/DPI
travel as observation metadata. This is not action or success authority.

New strict perception_query / perception_snapshot contracts and C# parsing/client
provide bounded explicit readback. Reads do not capture, spawn workers or poll.
Unknown/partial/malformed/cross-task metadata is refused. STOP, task terminal,
snapshot removal and three-second maximum wall/monotonic expiry remove facts;
queries cannot renew expiry. Snapshot registry reads are bounded, and STOP has
priority over a held readback lock. Cleanup clears private metadata before
releasing task snapshots/storage.

Every observation carries requires_target_revalidation=true. This packet does
not validate the current native target on every IPC read and does not display
an overlay. A later native host MUST recheck identity/creation time/class/title
hash, geometry/DPI, age and task/STOP state before presentation. Reading stored
geometry alone never makes it a currently valid target.

Fresh evidence root: output/p23-e106-20261104-193102-8e392d74/.
Capture movement reproduction fails before repair. Focused selection after
joining the test-owned asynchronous STOP operation: 58 pass. An earlier fixture
closed isolated SQLite while its STOP writer still ran, causing a native access
violation; the test now joins that owned operation before storage teardown.
It is retained as failed evidence, not counted as acceptance or a product fix.
Native owned-window capture/worker/readback: 1 pass, using a target-bound
foreground-context seam in the test worker so no personal foreground is changed.
Identity/geometry/PrintWindow capture, Job ownership, saved verification and
worker absence are native; this is not native OCR recognition or overlay acceptance.
Final source identities/regressions/Windows IPC gate are still pending.

Remaining P23: live/in-worker observation delivery and remaining capture paths;
target-bound native overlay hosting and freshness/monitor/DPI/TTL/STOP invalidation;
full combined surfaces 15/16/17 acceptance with owned moved/closed windows.
Keep verification 17 tied to saved actual readback, not observation facts.
Keep image bytes transient. No styling, dependency or master change.
