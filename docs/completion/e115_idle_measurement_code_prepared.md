# E115 - Resident resource measurement code preparation

Date: 2026-11-10 (Asia/Calcutta)
Branch: `p12-preparation`
Code base before these edits: `caaec5b0f9f1bcebc27b4eb5c6dd627c7065b8ad`
Prepared source checkpoint: `4918bf5a70c987f72b9c2f562e58b1809015270f`
Push: source and status commits pushed normally to `origin/p12-preparation`;
measurement remains deferred.
Status: **CODE PREPARED, NOT MEASURED; P26 GATE REMAINS OPEN**

## Source change prepared

`benchmark/idle_baseline.py` now requires an explicit resident PID and install
root, accepts an optional process creation timestamp, samples that process plus current descendants, and
marks absent/reused/inaccessible targets as failures. It no longer treats the
sampler's own CPU and RAM as PLUMA's footprint. Global GPU telemetry is clearly
separate from target attribution; target GPU and remote ML-module checks remain
unverified and therefore cannot pass the aggregate gate. Reports default to a
new ignored `output/idle-baseline-*.json` path and refuse to overwrite or write
outside the checkout.

## Verification and limitations

The owner asked to defer measurement and test activity. No resident was
launched or sampled and no ten-minute baseline or cycle run was attempted. No
P26 acceptance item is closed. This script alone does not attribute GPU work,
inspect remote Python module state, or establish the required target-laptop
resource/quality/latency/soak results.

## Acceptance checks still required

Use a disposable resident/owned-child fixture to verify executable containment,
PID plus creation-time binding, actual CPU-time deltas, RSS totals, process exit/PID-reuse failure, and
non-overwrite output behavior. Then measure the actual installed resident for
the full ten minutes and 50 cycles on the target laptop. Add target-attributable
GPU and loaded-runtime evidence before treating those gate fields as anything
other than unverified.
