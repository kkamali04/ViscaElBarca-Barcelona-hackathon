# Tracking replay v2 — 2026-11-16

User approved replaying the supplied tracking coordinates. The current demo has
fixed player circles, an invented sine-wave ball and a clock that loses elapsed
time under delayed animation callbacks. It is not a match replay.

Build a separate local `replay_v2` viewer without changing the frozen estimator,
review_app, models, original 218-file handoff or old manifests/evidence. New files
have their own replay manifest. No commits/push/submission in this task.

Show every finite observed anonymous track slot at its supplied pitch position.
Read normalized ATD coordinates using declared metadata channel order; display in
metres on a 105.3 by 68 m pitch. Frame 0 is ATD record 1. Ball/player missingness
is visible: never invent, extrapolate or interpolate through absent observations.
Track-slot indices are not player identities or shirt numbers. Support positions
outside the pitch without silently clamping them onto the pitch. Current CSV
possession is a separate prediction overlay; it must not determine object motion.

Use a streaming parser and disk-backed float32 cache. Browser reads bounded
250-frame windows with at most three retained windows, not the full match tensor.
No video decoding, new detector/model downloads, CUDA or cloud infrastructure.
An existing predictions CSV is optional and read-only; never retrain/regenerate
the frozen candidate as a side effect of opening this viewer.

Playback uses a monotonic wall-clock anchor. At 1x, 4 elapsed seconds mean 100
frames at 25 fps even if rAF fires once per second. Pause/seek/speed changes reset
anchors, delayed requests must not overwrite a newer seek, and loading/missing
observations must be explicit. All finite markers move according to observations;
synthetic browser tests must check actual coordinates, not just clock text.

Keep local-only host/origin checks and fixed routes. Restricted files may be
processed locally but never printed, inspected through model/browser tools or
uploaded. Model-facing tests/screenshots use invented fixtures only. Actual-input
verification may report only aggregates, hashes and resource/timing summaries.

Acceptance: fresh exported replay plus runtime environment; independently created
moving/missing/reordered-channel fixtures; strict bytes/frame alignment; malformed
inputs and bounded HTTP failures; synthetic browser delayed-rAF/speed/pause/seek,
coordinate/ball missingness, responsive layout and console checks; actual full
input preparation and sampled window parity through local code only; deterministic
repeated cache/chunk bytes, measured runtime/process peak and original artifact
preservation. Fresh blind acceptance after source freeze; root reproduces outputs.

Limits: this is an honest viewer of noisy supplied tracks, not corrected tracking,
stable player identification, a new vision model, or evidence of possession-score
improvement. Large slot jumps remain source discontinuities. Existing video and
generation/export dashboard remain separate.
