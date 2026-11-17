# Rendering and end-to-end workflow repair

Preserve frozen noise-v2 estimator/model bytes, input provenance and historical
acceptance records. Repair only the coordinate viewer, launcher and truthful
documentation. This version succeeds the published replay2.1 UI; previous passing
receipts do not establish acceptance of the new version.

- Direct file opening of the replay HTML must show readable launch instructions,
  rather than a broken Connecting screen. Served application still loads with
  external module/CSS under its existing CSP; no inline-script exception.
- Play, seek and speed controls appear before the canvas in DOM and visually.
  At1280x720 and1440x900 desktop viewports controls are within the first viewport;
  mobile390x844 and DPR2 remain usable without horizontal overflow. Canvas backing
  uses rounded device-pixel dimensions, with no geometry distortion.
- Keep frame0/ATD1 alignment, supplied slot sides, missing-pair hiding, no invented
  movement across gaps, bounded250-frame/three-window browser store, stale-seek
  protection, wall-clock playback and correct H/A/D/X meanings. CSV labels never
  move tracking coordinates. Demo remains invented and has no prediction overlay.
- start-match.ps1 -DataDir <root> [-Port <port>] [-NoBrowser] runs fresh uncached
  ATD inference, writes its own unique local/match-runs directory, then launches
  the coordinate viewer with that generated CSV. It must not take a prediction
  CSV as its inference input, read GT, train, overwrite existing outputs or modify
  input files. Both invocation from a different working directory and paths with
  spaces must work. Missing input/occupied port must fail safely before inference;
  failed inference must not open a fake successful viewer.
- Document supplied ATD input versus predicted CSV output versus forbidden GT,
  the organizer's allowance of tracking-only methods, and submission requirements.
  Current private repository is not represented as a public competition deliverable.

## Independent acceptance

Freeze before fresh blind reviewer candidate access. Reviewer independently
derives fixtures/oracles from organizer CHALLENGE/DATA/RULES/SUBMISSION/FAQ and this
contract. No prior results, expected hashes or implementer rationale as oracles.
Use a fresh exported package, fresh Python3.13 environment and new processes.
Actual input-to-CSV twice, exact ordered199319 frame,label rows with H/A/D/X,
deterministic bytes, official validator, elapsed time/actual worker lifetime peak,
missing-input/occupied-port failures, launcher→generatedCSV→served replay binding,
and source/input/model preservation are required. Root checks real artifacts and
reproduces in its own export/environment; a tester success assertion is insufficient.

Invented inputs only in model-facing browser tools/screenshots. Actual browser
integration may be exercised by standalone local headless automation code only,
with no screenshots/video/traces, DOM/snapshots, coordinates, labels or timelines
emitted to models. Only aggregate pass/fail/resource summaries and hashes may be
returned. Do not use interactive/model-facing browser tools for actual mode.
All actual files/logs/CSVs/caches remain private and ignored. No GT/scoring/tuning.

UI tests must exercise raw-file fallback, desktop/mobile layout, real Play/Pause/
seek/speed, missingness and stale requests, safe backend failure and recovery;
actual local-code-only rendering checks span uniformly predeclared recording
positions and verify bounded endpoint success and coordinate/overlay fidelity.
No hidden-accuracy guarantee, competition submission or public visibility change.
