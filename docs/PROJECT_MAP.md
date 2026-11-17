# Project map

This map describes the existing layout; historical evidence stays in place.
Begin with [README](../README.md) for setup and [AGENT_GUIDE](AGENT_GUIDE.md) for
human/agent operating rules. The latest top-of-file checkpoints in
[PROJECT_STATE](../PROJECT_STATE.md) and [AGENTIC_GOAL](../AGENTIC_GOAL.md) take
precedence over older snapshots below them.

## Active execution path

```text
authorized tactical ATD XML + TXT
  -> tools/run_candidate.py
  -> possession_model/features.py
  -> experiments/noise_v2/features.py (frozen local-linear transform)
  -> models/active.json + models/noise-v2-trees.json
  -> possession_model/pipeline.py + trees.py + decoder.py
  -> frame,label CSV + official format check + aggregate run report

ATD XML + TXT + optional prediction CSV
  -> replay_v2 -> local coordinate cache -> localhost viewer
```

`start-match.ps1` connects these paths: fresh uncached inference first, then
coordinate replay with that output. `replay.ps1` alone only starts the viewer.
No video decoder, GPU, training package or precomputed answer CSV is needed for
the active estimator. Optional automatic phase-tag support exists, but the
selected configuration uses weight zero. The frozen transform's location under
`experiments/` does not make it optional in noise-v2 inference.

| Location | Purpose and status |
|---|---|
| [possession_model/](../possession_model/) | Active streaming ATD features, numeric tree inference, temporal decoder, schema and atomic CSV writer. Frozen scientific source. |
| [models/](../models/) | `active.json` selects noise-v2 and its JSON weights. `selected.json`, `selected-safe.json` and other retained weights/configurations preserve earlier methods; file presence does not select them. |
| [tools/run_candidate.py](../tools/run_candidate.py) | Authoritative CLI for input-to-validated CSV, frozen hash checks and aggregate resource report. |
| [run-candidate.ps1](../run-candidate.ps1) | Windows wrapper using `.venv/Scripts/python.exe`; forwards Python CLI flags. |
| [start-match.ps1](../start-match.ps1) | Windows supplied-data workflow; unique local outputs, then replay with generated predictions. |
| [replay_v2/](../replay_v2/) | Current coordinate replay: CLI/server, read-only parsing/cache and browser assets. Anonymous slots, source gaps and an optional H/A/D/X overlay. |
| [replay.ps1](../replay.ps1), [stop-replay.ps1](../stop-replay.ps1) | Coordinate-viewer lifecycle, default port 8771. |
| [review_app/](../review_app/) | Legacy Touchline local review/export app. Synthetic demo animation is illustrative; optional actual local video is a separate mode. Not the coordinate replay. |
| [review.ps1](../review.ps1), [stop-review.ps1](../stop-review.ps1) | Legacy app lifecycle, default port 8765. |
| [requirements-lock.txt](../requirements-lock.txt) | Pinned Python 3.13 runtime/validator dependencies. |

## Reproduction, research and evidence

| Location | What to consult |
|---|---|
| [SOLUTION.md](../SOLUTION.md) | Implemented noise-v2 method, declared split, measured results, reproduction and scientific limitations. |
| [validation/](../validation/) | External Sportec adapter and metric support. Its [README](../validation/README.md) explains target semantics; external labels are not challenge labels. |
| [tests/](../tests/) | Regression and historical acceptance tests across active and experimental code. Test names/reports retain their original scope; a suite run is not fresh package E2E. |
| [experiments/noise_v2/](../experiments/noise_v2/) | Frozen runtime motion transform plus the completed v2 training/selection protocol implementation. Do not rerun completed holdouts. |
| [experiments/v3/](../experiments/v3/), [V3_REVIEW.md](../V3_REVIEW.md) | Closed versioned study and review. No eligible finalist was promoted; noise-v2 remains active. Preserved source does not authorize reopening it. |
| [experiments/speed_v1/](../experiments/speed_v1/), [benchmarks/speed_reuse/](../benchmarks/speed_reuse/) | Separate preparation/reuse engineering experiment and invented-data benchmark. Not integrated into active inference; its timings are not full-match estimator speedups. |
| [research/](../research/) | Decision history, source attribution and protocols. Start with the [index](../research/README.md); [NOISE_V2_PROTOCOL](../research/NOISE_V2_PROTOCOL.md) governs the completed v2 study. Proposals are not implementations merely because they appear here. |
| [specs/](../specs/) | Requirements/contracts for possession improvements, training speed, coordinate replay, teammate release, rendering repair and release hardening. |
| [reports/](../reports/) | Selected aggregate historical evidence, audits and acceptance receipts. Match each claim to its tested code/package and workload; some old references intentionally point to excluded private controls. |
| [more-than-a-hack-2027-main/](../more-than-a-hack-2027-main/) | Retained organizer public documentation/starter/evaluator. [CHALLENGE](../more-than-a-hack-2027-main/CHALLENGE.md), [DATA](../more-than-a-hack-2027-main/DATA.md) and [RULES](../more-than-a-hack-2027-main/RULES.md) explain the task/data boundaries; `evaluation/possession_metrics.py` supplies the actual format validator. |

## Guides, packaging and local-only material

| Location | Purpose |
|---|---|
| [docs/VIEWER_GUIDE.md](VIEWER_GUIDE.md), [REPLAY.md](../REPLAY.md) | Reading the coordinate viewer, launch commands, storage and recovery. |
| [docs/MORNING_REVIEW.md](MORNING_REVIEW.md), [docs/REQUIREMENTS_AND_READINESS.md](REQUIREMENTS_AND_READINESS.md) | Dated owner review and requirement/submission checks. Recheck mutable facts before action. |
| [docs/TECHNICAL_SUBMISSION.md](TECHNICAL_SUBMISSION.md) | Technical submission draft; verify registered team details and requirements separately. |
| [MVP_REVIEW.md](../MVP_REVIEW.md), [MVP_TECHNICAL.md](../MVP_TECHNICAL.md), [ESTIMATOR_README.md](../ESTIMATOR_README.md) | Legacy code-only package and estimator handoff documents. |
| [docs/REPOSITORY_SCOPE.md](REPOSITORY_SCOPE.md) | Exact legacy versus extended package boundaries and provenance. |
| [PACKAGE_MANIFEST.json](../PACKAGE_MANIFEST.json), [ESTIMATOR_PACKAGE_MANIFEST.json](../ESTIMATOR_PACKAGE_MANIFEST.json) | Separate legacy export and historical estimator records. Preserve their scope and frozen bytes. |
| [TEAM_REPO_MANIFEST.json](../TEAM_REPO_MANIFEST.json), [REPLAY_MANIFEST.json](../REPLAY_MANIFEST.json) | Extended checkout and coordinate-replay integrity records; refresh affected authorized packaging records without reinterpreting old evidence. |
| [.githooks/](../.githooks/), [setup-git.ps1](../setup-git.ps1), [.gitignore.team](../.gitignore.team) | Tracked size safeguards and clone-local exact-byte, privacy and pull configuration. Original `.gitignore` remains frozen. |
| [THIRD_PARTY.md](../THIRD_PARTY.md) | Third-party source/license attribution; code publication does not redistribute match assets. |
| [assets/](../assets/) | Public presentation assets, including the invented-data replay screenshot. |
| `local/`, `submissions/`, `.venv/`, downloaded `data/` | Ignored runtime outputs, private CSVs/caches/review packs, environment and licensed inputs. These are not public-repository contents. Never inspect their restricted records through model tools or add them to Git. |

The full Git checkout includes the coordinate viewer and experiment history.
The legacy **106-member ZIP excludes those extensions**, including `replay_v2`;
its README is based on MVP_REVIEW. No directory should be moved or deleted merely
to make the handoff look newer. Historical code, reports and protocols remain
useful only when their original version and evidence boundaries remain intact.
