# More Than A Hack 2027 - efficient possession estimator

This code-only package contains noise-v2 source, frozen numeric tree weights and
configuration, independent evaluation evidence, and public organiser sources.
Restricted competition inputs are excluded. Team/repository naming is pending.

Use Python 3.13 for the pinned environment. No GPU/video decoder is needed.

```bash
python -m venv .venv
# Activate .venv, then:
python -m pip install -r requirements-lock.txt
python tools/run_candidate.py --data-dir /path/to/provided/data
```

The data root must contain `tactical/BAR-ATH_tactical_atd.xml` and
`tactical/BAR-ATH_tactical_atd.txt`. No other private asset is required by the
selected configuration. Or put tactical/ beneath
`more-than-a-hack-2027-main/data/` and omit `--data-dir`.

The command defaults to `models/active.json`, writes `submissions/candidate.csv`,
checks it with the official validator, and writes `reports/candidate-run.json`.
The Windows shortcut is `run-candidate.ps1`. Expected frozen CSV SHA256:
`d000a49eb8db71ac94da4877abe5b85506d05be233db1f43644df1e4c9e653fd`.
Repeated runs should produce identical CSV bytes; timings/cache state can differ.
`--no-cache` disables both feature-cache reads and writes. Inference needs NumPy;
the format checker uses pandas. Training libraries are not runtime requirements.

Read [SOLUTION.md](SOLUTION.md) for design, results, test evidence and limitations.
[TECHNICAL_CANDIDATE_DRAFT.md](TECHNICAL_CANDIDATE_DRAFT.md) is the team draft;
insert the registered name before submission. [THIRD_PARTY.md](THIRD_PARTY.md)
contains source/data attribution. Hidden challenge accuracy/rank is unknown.

```bash
python -m unittest discover -s tests
```

The core suite uses invented fixtures, not private assets. Optional sklearn/SciPy
checks skip when training dependencies are absent. Standalone blind acceptance
scripts document their own scope. Source/model integrity is enforced; retain the
supplied `.gitattributes` when publishing/cloning so Git preserves frozen bytes.
Historical v1 configuration/reports remain separately versioned and do not bind
to the repaired/new source. Use active.json for current reproduction.

Optional v2 training reproduction uses a separate clean copy without
`reports/noise-v2-holdout.json`; preserve completed holdouts without rescoring:

```bash
python -m pip install -r requirements-training-lock.txt
python tools/fetch_validation_data.py
python experiments/noise_v2/fetch_holdout.py
python experiments/noise_v2/run_experiment.py select
python experiments/noise_v2/run_experiment.py holdout
```

Read [the fixed protocol](research/NOISE_V2_PROTOCOL.md) before experimental work.
The supplied frozen weights, rather than retraining, are the exact-output path.
Raw inputs, caches, videos and submission CSVs stay local/Git-ignored.
No publishing or submission has occurred.
