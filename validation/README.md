# Independent match validation

Use public matches from the **IDSSE Sportec/DFL dataset**, described by Bassek,
Rein, Weber and Memmert (2025), *An integrated dataset of spatiotemporal and event
data in elite soccer*, Scientific Data 12,195.
[Primary paper](https://www.nature.com/articles/s41597-025-04505-y),
[original dataset](https://doi.org/10.6084/m9.figshare.28196177),
[PySport mirror](https://huggingface.co/datasets/pysport/idsse-data),
[official kloppy URL mapping](https://github.com/PySport/kloppy/blob/master/kloppy/_providers/sportec.py).
These are German 2022/23 matches, independent of the Spanish challenge match.
The dataset is CC BY 4.0; retain author/source/license attribution when using it.

## Fixed match split

| Match | Role | Fixture | Frames at 25 Hz |
|---|---|---|---:|
| J03WOH | Development/training | Fortuna Düsseldorf vs SSV Jahn Regensburg | 137214 |
| J03WOY | Validation/model selection | Fortuna Düsseldorf vs F.C. Hansa Rostock | 142536 |
| J03WR9 | Final holdout, after freezing | Fortuna Düsseldorf vs 1. FC Kaiserslautern | 146810 |

Do not split randomly by frame/window. All three games have the same home club,
so even this match split does not establish transfer to unseen clubs/leagues.
Do not use the holdout to select constants. Repeated corruption evaluations are
robustness checks on the same games, not additional independent games.

## Target and leakage boundary

The paper defines `BallPossession=1` as home control and `2` as away control,
and `BallStatus=0` as inactive after a referee interruption, `1` as active.
The adapter maps inactive frames to `D` (2), active home/away to `H` (0)/`A` (1),
and other/missing values to `X` (-1). Unknown possession never defaults to away.
These are provider control labels, not corrected challenge ground truth; metric
values on these games must be reported as external validation only.

`validation/sportec.py` isolates these attributes in a separate `truth.npy` array.
They do not determine frame coverage, periods, coordinate masks or features.
Only X/Y, N/T, GameSection and roster identity enter the feature adapter.
Provider speed, ball height, events and labels are not used as input features.
The roster is reduced to anonymous slots with home/away membership; referee
tracks are excluded. Centered metre coordinates are translated by half the pitch
dimensions into the corner-origin system used by the shared feature accumulator.
No side/orientation flip is required for distances or pitch-boundary features.

Period coverage is obtained from raw frame-ID ranges within GameSection, not
from live/dead labels. IDs are contiguous within each period's compact range;
any absent raw ID remains an unknown observation and unknown truth. Halves are
concatenated without a synthetic halftime interval. Original raw ranges remain
in provenance for auditing.

## Acquisition and use

From this project directory:

```powershell
& .\.venv\Scripts\python.exe tools/fetch_validation_data.py
& .\.venv\Scripts\python.exe -m unittest discover -s tests -p test_sportec.py -v
```

The acquisition script downloads only metadata and raw observed tracking;
events and videos are unnecessary. It checks file size and raw-file SHA256
against Hugging Face LFS metadata, and non-LFS metadata against the Git blob
SHA1. Existing originals are verified and reused, never overwritten. A failed
download remains `.xml.part` for inspection instead of silently becoming input.
Download manifest: ignored `local/external/download-manifest.json`.

```python
from pathlib import Path
from validation.sportec import load_sportec

folder = Path("local/external/J03WOH")
features, truth, provenance = load_sportec(
    next(folder.glob("*matchinformation*.xml")),
    next(folder.glob("*positions*.xml")),
    corruption={"ball_missing_fraction": 0.4, "block_seconds": 4, "seed": 123},
)
# Give features only to the estimator; give truth only to training/scoring.
```

Corruption masks exactly the requested fraction of timeline frames in contiguous
blocks, independently of labels, geometry and existing ball visibility. Blocks
are sampled without replacement and the last block may be clipped to achieve
the exact fraction. Blocks never cross a half boundary. Natural gaps can overlap
synthetic gaps, so requested timeline fraction is not the resulting total ball
missing fraction. Report the actual feature observation rate separately.

## Efficiency and checks performed

The raw XML is grouped by player, so two streaming `iterparse` passes build
compact float32 position/ball arrays on disk; XML nodes are removed immediately.
No multi-million-record Python dictionary/tree is retained. Initial parsing
took 60.7,62.1,63.4 seconds locally for the three games (one run each).
Initial clean feature extraction on J03WOH took **22.332 seconds** and retained
**4,665,276 bytes** in the FeatureSet arrays. Repeated cached load took **0.009
seconds**, with equal arrays. These are measured component timings, not a full
estimator benchmark or measured process peak RSS.

Derived caches remain beside originals under ignored `local/external/`.
Raw-cache identity includes source filename, size, modification time, metadata
SHA256 and parser version. Feature-cache identity additionally includes the
extractor source SHA256 and corruption settings. No truth file is loaded into
the estimator's FeatureSet. Returned truth is a small owned array to avoid
retaining Windows file locks.

Five synthetic fixture tests passed: unknown-label handling, grouped XML order,
coordinate translation, period/reset layout, deterministic exact-fraction block
corruption, and full feature invariance when only labels change (including cache
repeatability). These tests establish adapter behavior, not football accuracy.
All full-match raw files were downloaded and verified. No estimator holdout
evaluation was performed by the adapter acquisition step.
