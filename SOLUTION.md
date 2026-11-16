# Efficient possession estimator - noise-v2, November 15, 2026

The current candidate produces the complete required possession CSV locally from
tactical tracking. A small independently trained tree model feeds an exact
three-state temporal decoder. It needs no GPU, video decoding or training package
at inference. The original v1 and organiser fallback are preserved locally.

## Task and output

For all 199319 tactical frames, output H (home/Barcelona live possession),
A (away/Athletic live possession), D (dead play), or X (outside graded periods).
The target is a coherent possession timeline, including passes and stoppages.
The candidate is `submissions/candidate.csv`; it has not been submitted and its
hidden challenge accuracy/rank is unknown.

The two required private inputs are `tactical/BAR-ATH_tactical_atd.xml` and
`tactical/BAR-ATH_tactical_atd.txt`. XML channel/team ordering is explicit; the
reader requires ordered record IDs 1..199319 and converts normalized coordinates
to metres on the 105.3 x 68 m pitch. Slot identities remain anonymous.

## Efficient features and inference

We retain per-side nearest player-ball distance and observation counts, ball
coordinates/visibility, anonymous collective movement, and conservative motion.
Geometry stays at 25 Hz. Collective movement is symmetric median nearest-set
displacement over one second, sampled at 5 Hz, using a bounded player ring.
It is a movement proxy, not identified-player speed. Twenty-two numeric model
features include period-bounded observation, proximity and motion summaries.
Unknown inputs remain NaN. Missing ball alone never means dead play.

The v2 change replaces adjacent-step ball speed with the magnitude of a centred
local-linear x/y slope over 31 observations (1.2 seconds at 25 Hz), implemented
with NumPy. Windows require continuous reliable coordinates and never bridge
missing data or periods. Geometry near adjacent >60 m/s jumps is suppressed;
resulting speeds >60 m/s are unknown. This suppresses independent coordinate
jitter without smoothing already biased speed magnitudes. The transform costs
0.020 seconds on the challenge timeline.

The transform is offline and averages turns, accelerations and reversals.
It loses 15 frames at each reliable-run edge; fragmented observations can remove
many motion windows. Correlated drift and plausible tracking errors can survive.
These are limitations, even though independent invented-motion tests pass.

A 64-round histogram gradient boosting model uses three numeric trees per round,
at most 15 leaves per tree, learning rate .08, L2=2, minimum leaf 80, and 63 bins.
Training samples every fifth frame, includes four fixed corruption views and
H/A-swapped augmentation, and balances target classes. Numeric JSON inference
matched sklearn raw scores exactly on the export probe. Sklearn is training-only;
the frozen v2 JSON is 767185 bytes and does not contain executable pickle objects.

Bounded log evidence feeds an exact H/A/D dynamic program with O(N*9) work and
three uint8 backpointers per frame. The selected transition cost is 0.5*fps=12.5
score units, not a minimum spell length. Ties prefer fewer transitions and delay
an unidentifiable switch through neutral evidence. Each half resets independently.
Published inclusive graded ranges become [11185,90652) and [110808,190198).
Only the documented pre-second-kickoff interval [110808,113742) is forced D.
Automatic phase-tag support is implemented but its selected weight is zero.

## Selection and genuinely separate evaluation

Sportec/DFL J03WOH is development; J03WOY is selection. BallStatus/BallPossession
supply labels only to training/scoring, not feature extraction. A regression test
changes statuses and checks feature identity. Centred metre coordinates are
translated to the tactical corner origin. No challenge labels, frames, manual
corrections or human match records enter this method. The public five-minute GT
was not opened for this model/experiment; earlier fallback checks are historical.

After blind synthetic probes exposed jitter sensitivity, v2 was preregistered in
[NOISE_V2_PROTOCOL.md](research/NOISE_V2_PROTOCOL.md). Development/validation each
use clean tracking, 40% ball deletion in four-second blocks, 40% deletion in
12-second blocks, and a combined case: 40%/4s ball deletion, 30%/1s player dropout,
0.25 m per-axis coordinate noise and sparse one-frame 20 m ball teleports.
Seeds/corruption ordering are fixed and identical for both models.

The only v2 parameter search is transition cost .25/.5/1/2 seconds. Mean spell F1
over four validation conditions selects the cost; macro F1 breaks ties. Promotion
required at least +.02 mean spell F1 with at most .02 clean loss. V2 achieved
0.423677 versus v1 0.388848 (+0.034829), passing both gates. Validation clean
spell F1 was .528930 versus .522835; long-gap performance slightly declined
(.404645 versus .411297). There was no subsequent retuning. V2 also adds two development corruption views
relative to v1; the comparison evaluates the combined training/feature package
and does not isolate the smoother as the sole cause of any gain.
[Full selection evidence](reports/noise-v2-validation.json).

The old v1 holdout J03WR9 stayed closed. Fresh holdout J03WMX was chosen by unused
filename before parsing and accessed only after v2 model/config/source/protocol
freeze. It was scored once. These use the organiser's actual spellF1 functions:

| Fresh holdout J03WMX | V2 spell F1 | V1 spell F1 | Smooth50 spell F1 | V2 macro F1 |
|---|---:|---:|---:|---:|
| Clean | .472460 | .467405 | .307233 | .902171 |
| 40% ball gaps, 4-second blocks | .401379 | .401362 | .189199 | .847002 |
| Combined tracking errors | .346548 | .201626 | .111458 | .814936 |

[Fresh holdout evidence](reports/noise-v2-holdout.json) and
[adapter/target semantics](validation/README.md). Corruption conditions are not
independent matches. One new provider match and simulated error patterns do not
establish general robustness or challenge improvement. Macro F1 declined slightly
on clean/ball-gap holdout data despite spell F1 being stable. Provider differences,
ambiguous control definitions, sparse touches and turnovers inside missing
intervals remain material limitations. Historical v1 reports remain separately
bound to `models/selected.json`; the current entry point uses `models/active.json`.

## Measured complete local run

| Measurement | Noise-v2 result |
|---|---:|
| Uncached full input-to-validated CSV | 49.662 seconds |
| Feature extraction | 40.639 seconds |
| Numeric/temporal inference | 8.451 seconds |
| Cached complete rerun | 9.057 seconds |
| Peak process working set, first run | 118521856 bytes |
| Retained feature arrays | 6776846 bytes |
| Bounded player ring | 9568 bytes |

Whole-process peak memory includes Python, NumPy, validator imports and temporaries;
array storage is separate. These are Windows CPU measurements, not guarantees.
Both complete runs passed the actual official validator with identical CSV SHA256:
`d000a49eb8db71ac94da4877abe5b85506d05be233db1f43644df1e4c9e653fd`.
[First run](reports/final-candidate-run.json),
[repeat](reports/final-candidate-repeat.json).

## Reproduce and test

```powershell
# Frozen model/config already included:
.\run-candidate.ps1
# Portable command; arbitrary supplied data location is supported:
python tools/run_candidate.py --data-dir /path/to/provided/data
python -m unittest discover -s tests
```

Install `requirements-lock.txt` in Python 3.13. Runtime inference uses NumPy;
pandas is required by the organiser's validator. Frozen source/model hashes reject
untracked method changes. Cache keys include input content hashes. CSV writes
validate all labels before atomic replacement; output/report aliases with inputs,
models, protected code and fallback are rejected. `--no-cache` reads/writes no
feature cache. The targeted regression suite passes 130 tests.

Fresh-context blind testers derived independent public/synthetic oracles. The
[final source acceptance](reports/release-blind-acceptance.json) exercised real
CLI-to-CSV synthetic matches, safe failures, NumPy-only motion imports and numeric
contracts. Exact final-package/minimal-environment acceptance and root audit are
recorded separately after package export; no earlier report substitutes for them.
[Failure/repair ledger](reports/BLIND_FAILURE_LEDGER.md).

Optional v2 training reproduction, in a separate clean copy without the final
v2 holdout report (never rerun this frozen workspace's holdout):

```powershell
python -m pip install -r requirements-training-lock.txt
python tools/fetch_validation_data.py
python experiments/noise_v2/fetch_holdout.py
python experiments/noise_v2/run_experiment.py select
python experiments/noise_v2/run_experiment.py holdout
```

Retraining need not produce identical model JSON bytes: provenance timing and
library/hardware behavior can differ. Supplied frozen weights are the exact CSV
reproduction path. Experimental replay has procedural safeguards in addition to
hashes; preserve the protocol and reports and do not overwrite or reinterpret a
completed holdout. The blind experiment audit identified incomplete automatic
protocol/comparator/config-freeze checks and a retry window after partial failure.
Root independently verifies all current stored hashes, split/gates and completed
reports; this run completed in one invocation. Future experiments need stronger
attempt tracking and freeze enforcement before any new holdout access. A tiny
floating-point boundary can reject an exact +.02 gain; this experiment clears the
gate by .014829 and is unaffected. See
[the independent source audit](reports/blind-experiment-audit.json).

Post-freeze feature-cache diagnostics (no labels/scoring rerun) show finite v2
motion on 97.46% of clean J03WMX frames, 51.10% under ball gaps and 42.74% under
combined errors. V1 coverage is 99.38%, 57.13% and 54.56%. Reduced coverage is an
explicit cost of requiring complete reliable windows.
[Coverage evidence](reports/noise-v2-coverage.json). Training peak memory was not
instrumented. Restricted/raw data, caches and outputs remain local/ignored.

## Team handoff

Confirm the registered team name and exact submission email/form requirements;
complete the team-name field in the technical draft. The public code repository
must contain only the allowlisted project export. Preserve the exact uploaded
CSV and submission receipt. No commit, push, publication or submission occurred.
[Attribution and licences](THIRD_PARTY.md).
