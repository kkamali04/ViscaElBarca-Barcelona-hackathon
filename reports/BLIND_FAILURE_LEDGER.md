# Independent findings and repair ledger - November 15, 2026

Initial blind evidence remains unchanged in `blind-adversarial.json`,
`blind-quality.json` and `blind-e2e.json`. Root independently reproduced the
adversarial failures and the motion-jitter probe. The original v1 ZIP/config/
key reports are preserved under ignored `local/releases/v1/`. Model/holdout
evidence is not relabelled as a test of changed source.

| Finding | Impact | Repair / current evidence |
|---|---|---|
| Identical CSV/report paths | Valid CSV replaced with JSON on successful exit | CLI rejects aliases before inference; independent frozen regression passes |
| Output aliases raw input | Source can be overwritten | Input/model/config/source/fallback aliases rejected; regression passes |
| Invalid later code truncates CSV | Existing deliverable lost on failure | Domain validation plus temporary file and atomic replacement; regression passes |
| Invalid metric codes narrow into valid int8 | Plausible incorrect scores | Validate code domain before cast; regression passes |
| Same-size/mtime raw edit reuses cache | Stale features/targets | Raw SHA256 streamed into cache identity; regression passes |
| Invalid tree class/schema/routing | Wrong class or possible looping | Strict class/node/graph validation; regression and sklearn parity pass |
| CLI absent from source freeze | Frame constraints can change without provenance failure | CLI and v2 runtime transform included in source binding; regression passes |
| Extreme finite coordinate overflows distance storage | Infinite evidence | Reject unrepresentable distance before float32 assignment; regression passes |
| --no-cache still writes cache | Ambiguous/low; unexpected persistence | Flag now explicitly disables reads and writes; regression passes |
| Coordinate jitter appears as fast motion | Real domain/physics weakness | Frozen noise-v2 passed validation promotion and fresh external holdout; independent physics/source acceptance passed |
| Sparse teleports change heuristic state sequence | Heuristic weakness, not scored learned-model result | Preserved diagnostic; v2 combined-noise holdout improves spell F1; no universal robustness claim |

The initial repair suite had 96 tests; the current root suite passes 130.
Fresh independent source acceptance passed on the final safety code/v2 transform;
exact final-package/minimal-environment acceptance is separately required. Accuracy/generalization and failure-safety are separate
claims. No private challenge score is known.

Second independent pass found additional report-directory/nested-output and
tag-input collisions, finite score overflow, malformed period identifiers,
missing executed-source fingerprints and declared extra-time periods that the
accumulator rejected. Root reproduced these; destination preflight now rejects
directories/containment/data-root writes, accumulated scores and periods fail
closed, executable init/scorer/dependency-lock sources are bound, and anonymous
features consistently accept regular/extra football periods1..4. Current root
suite:130 passing tests. The saved second report spans explicitly identified
source snapshots, not one final-version acceptance. Fresh independent acceptance passed seven source-contract checks, including
two full invented actual-CLI matches and protected-write failures. See
[release-blind-acceptance.json](release-blind-acceptance.json). Root verified the
actual report/test hash and exact current-source equality. This source gate does
not substitute for final exported-package reproduction.


## Final experimental validity review

Fresh blind [experiment audit](blind-experiment-audit.json) passed invented-data
label invariance, corruption repeatability, export parity and source stability.
Root independently reran its probes. Initial missing experiment package sources
were repaired; its corrective invented export includes all frozen runtime files.

Remaining experimental-runner risks are explicitly bounded: it does not enforce
all recorded validation/protocol/v1 comparator hashes internally, and an interrupted
partial holdout can be retried before a final report exists. This actual frozen
run completed once; root's final audit separately compares all recorded hashes,
selection arithmetic and exact conditions. Do not reuse it for new holdout work
without stronger attempt/freeze safeguards. No current-result drift was found.
A synthetic exact +.02 threshold can be rejected due floating-point rounding;
actual validation gain +.034829 is safely away from this boundary.

Motion coverage was measured after freeze from existing feature caches without
truth/prediction rescoring: [noise-v2-coverage.json](noise-v2-coverage.json).
Training peak memory is unavailable. Full inference process memory is measured.
Any v2 improvement is a joint motion-feature/noise-augmented-training comparison,
not an isolated causal test of smoothing. Hidden challenge accuracy remains unknown.


## Minimal-environment regression correction

Root's additional runtime-only environment suite exposed one unconditional
scikit-learn import in an export-parity test. The test now skips only when the
sklearn package is absent; broken installed dependencies still fail. All 130
checks succeed with training dependencies; runtime-only environment succeeds
with 127 passes and three optional training/SciPy skips. Numeric runtime/model/
configuration are unchanged. Final blind package testing paused before its first
inference, explicitly released the first ZIP, and resumes only on the corrected
export. No earlier ZIP acceptance is relabelled as a test of this package.
