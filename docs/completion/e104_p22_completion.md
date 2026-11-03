# E104 — P22 health, setup and controlled recovery

Status: implementation checkpoint; final acceptance pending. P23 is not started.

Base 9d6653e3df6eb1ca7bd509590d58e401376a7262 on p12-preparation.
Recovery: recovery/pre-p22-e104-20261103. Main stays 0468a03.

P22 connects dashboard/health 23, setup 26 and recovery 25 using typed,
authenticated readback. One leased CoreHost retains the IPC endpoint while
replacing only its own drained runtime graph. Dead/unverified hosts require
manual startup: no speculative process launch or termination is permitted.
Registered check_setup/restart_core use the shared capsule, policy, STOP,
verification, owned-worker cleanup and factual ledger. Restart is explicitly
non-undoable and requires exact material approval. Recovery success requires
same PID/creation time, new graph identity and authenticated ready/hotkey proof.

Setup is explicit and microphone access is separately consented. Local native
llama.cpp vocabulary, whisper.cpp model, OCR ONNX models, UIA and microphone
access are checked in a bounded process. No downloads, inference, screen capture
or retained audio. Real worker absence and all native receipts are required;
fixture results can never enable Continue. Proof expires after 60 seconds in
Core and 45 seconds in UI, on config/instance change or disconnect. Continue
re-reads Core. No additional background poller: existing bounded runtime reads
invalidate stale proof; explicit check/recovery operations have owned budgets.

Pre-edit: 117 passed. Focused host checks: 17 passed, no skips/xfails;
affected interim: 94 passed. SurfaceControls compilation: zero warnings/errors.
Native setup reports under ignored output/p22-e104-20261103-233337-bd70b644/:
- native-health.json: unavailable UIA dependency reported truthfully.
- native-health-declared.json: cross-environment pywin32 path incomplete;
  UIA correctly remained unavailable. These are not all-capability passes.
- native-health-complete.json: all five probes passed with declared Windows
  environment plus existing native-model environments; real microphone access,
  native models and UIA root verified, worker absent and resident cold.
These pre-commit results identify base plus the P22 working diff; final results
will identify the committed source. Full logs stay ignored. Final regression,
Windows UI run and completion determination are pending.

Unchanged limits: E94 owner-approved C-02 physical timing retest at P25;
installation/signing, physical UI/device review, broad security/performance and
release gates keep their existing milestone owners. Model access checks do not
claim end-to-end speech/planner accuracy or OCR corpus acceptance.
