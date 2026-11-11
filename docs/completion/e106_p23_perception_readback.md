# E106 - P23 packet 1: transient perception observation readback

Packet 1 verified on source 3e4a03e0f8a261074e98ba9dc6f3baaacefba707.
P23 is in progress, not complete.
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
Final source 3e4a03e0f8a261074e98ba9dc6f3baaacefba707 passes **1,118 required
regressions**, no skips/xfails (145.47s pytest), and **1 owned native capture**
case (1.54s pytest). Final focused P23 selection: **20 pass**. Core IPC Release
build: zero warnings/errors. Commands and machine identity are in each
run's command.json/results.xml/results.txt below the ignored root.

Commands use the declared E98 test-env/Scripts/python.exe:
- run_checks.py final-focused tests/unit/test_p23_perception_readback.py
- required_regressions.py (deduplicated E105 required selection plus P23,
  screen catalog, capture/context and UIA snapshot coverage; desktop isolation)
- run_checks.py native-committed tests/windows/test_p23_capture_feedback.py
  -p tests.fixtures.desktop_isolation
- dotnet build PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj -c Release --nologo
- Windows workflow PLUMA.UI/verify-ui.ps1 on the exact pushed source.

[Windows run 41847337439](https://github.com/sai161812/pluma/actions/runs/41847337439)
passes **356 IPC, 237 legacy native UI, 15 P22 native UI, 663 popup and 195
formatting** checks with complete teardown. The IPC native service path checks
empty metadata readback; positive capture metadata and C# contract shape are
separate evidence, not a claimed positive native capture-to-render flow.
Artifact 13331423632 SHA256:
19c213b10369ce4fa683e9ee37afb11eb2f9fc6156c92619ffa40a00f203c718,
verified against GitHub's artifact digest. Executable SHA256:
EABC69B748593E401BB5FBE08B2F703A6362645033DBFB25EBFE12774338FF8E
(unsigned). Full summary/artifact remains in ci-41847337439/.

Packet 1 is ready for independent Sol review; approval is not assumed.

Remaining P23: live/in-worker observation delivery and remaining capture paths;
target-bound native overlay hosting and freshness/monitor/DPI/TTL/STOP invalidation;
full combined surfaces 15/16/17 acceptance with owned moved/closed windows.
Keep verification 17 tied to saved actual readback, not observation facts.
Keep image bytes transient. No styling, dependency or master change.
