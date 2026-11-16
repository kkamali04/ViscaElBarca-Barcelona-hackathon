# Possession estimator: technical document

Team: {{TEAM_NAME}}

Public code repository: {{REPOSITORY_URL}}

This document describes the frozen **noise-v2** estimator and a local review
application. All possession labels are generated algorithmically. Hidden challenge
performance and ranking are unknown; the application does not establish submission
or public repository availability.

## Approach and assets

Required inference inputs are the supplied tactical tracking metadata XML and
tracking TXT, read locally. Player/ball geometry is converted to metres. Features
include team proximity, observation quality, anonymous collective movement and
period-bounded temporal summaries. A centred local-linear ball-motion estimator
uses 31 reliable observations. A small histogram boosting model supplies H/A/D
evidence to an exact three-state dynamic program. The selected transition penalty
is 0.5 seconds × frame rate (12.5 score units at 25 Hz), with independent half resets.

The selected estimator uses no video detection, broadcast tracking, homography,
human match records or challenge ground truth. Automatic phase-tag support was
implemented but dropped from the selected model (weight zero). Tactical video is
optional for private local playback in the review interface; playback does not
feed inference or training. No manual timeline edits enter the exported CSV.

## Training data, creators and labels

The only labelled training source is **IDSSE Sportec/DFL**, *An integrated dataset
of spatiotemporal and event data in elite soccer*, by **Bassek, Rein, Weber and
Memmert (2025)**. Source: [Scientific Data paper](https://www.nature.com/articles/s41597-025-04505-y),
[original Figshare record](https://doi.org/10.6084/m9.figshare.28196177), acquired
through the [PySport mirror](https://huggingface.co/datasets/pysport/idsse-data).
The dataset is CC BY 4.0. Control/play-state labels are the **Sportec/DFL provider's
annotations**, rather than labels made by our team or the challenge's corrected
tracking. We map `BallStatus=0` to D; active play with `BallPossession=1` to H and
`2` to A; missing/unknown values to X. These targets are isolated from features.
Provider speed, ball height and event data are not feature inputs.

Development/training is one full other match, **J03WOH: 137214 frames at 25 Hz**.
Stride five supplies **27443 original rows per view**; four fixed views (clean,
4-second ball gaps, 12-second ball gaps, combined tracking errors) and home/away
swap augmentation yield **219544 training rows**. These are augmented examples
of one game, not 219544 independent observations or four separate games.
Selection uses different match **J03WOY**. The original v1 holdout **J03WR9** stays
closed; v2's fresh final holdout is different match **J03WMX**, scored once after
source/model/configuration/protocol freeze. No challenge public-window tuning,
private GT, supplied-game labels or hand corrections were used for this estimator.

## Possession rules implemented

H/A mean live home/away control, D means dead play and X means abstention/outside
the published play intervals. Proximity and motion are imperfect control proxies;
a touch or nearest-player change does not directly force a turnover. The temporal
decoder penalizes state changes and carries evidence through loose/contested
balls, with a deterministic delayed switch on unidentifiable neutral evidence.
It approximates the last-controlled-team convention; it does not prove control or
implement an explicit referee/duel/pass recognizer. Missing ball alone never forces
D. Learned dead-play evidence and the published pre-second-kickoff preparation
interval determine dead play; halves are decoded independently. Restarts do not
inherit a possession state across a half boundary.

## External evidence and resources

Preregistered mean selection spell F1 over four conditions was **0.423677** (v1:
0.388848). Fresh external J03WMX spell F1 was **0.472460 clean**, **0.401379 with
40% ball deletion in four-second blocks**, and **0.346548 with combined simulated
tracking errors**. The organiser's actual metric implementation scored provider
labels on a different game; these are **external validation, not challenge scores**.
Repeated corruptions are not independent matches. V2 changes both features and
training augmentation, so this comparison does not isolate the smoother's effect.
No tuning followed the holdout. Reports are preserved in `reports/`.

Historical complete Windows CPU input-to-validated-CSV runs of the frozen estimator
took **49.662 seconds** uncached and **9.057 seconds** cached; first-run peak working
set was **118521856 bytes**. An independent exact-package run measured **52.158
seconds**, with inference-worker peak at most **119648256 bytes** across three
runs. These measure the estimator, not review-interface overhead or synthetic demo
performance. Training peak memory was not measured. Numeric model size: **767185
bytes**; no GPU or scikit-learn is required for inference.

Frozen model SHA256:
`856114a7693414db9652bb50e37ab527f958f84e75200b69ce07be28be24bff2`.
Historical validated 199319-row candidate CSV SHA256:
`d000a49eb8db71ac94da4877abe5b85506d05be233db1f43644df1e4c9e653fd`.
The new MVP package manifest binds its actual source bytes. Historical estimator
acceptance does not by itself verify a changed application/package.

## Reproduce and review

Use Python 3.13, create `.venv`, and install `requirements-lock.txt`. Place your
authorized tactical XML/TXT under `more-than-a-hack-2027-main/data/tactical/`.
Run `.\review.ps1` as shown in the review README, or reproduce directly:

```powershell
.\run-candidate.ps1
# Explicit input location, with a fresh extraction pass:
.\.venv\Scripts\python.exe tools/run_candidate.py --data-dir C:\path\to\data --no-cache
```

The exact frozen weights/configuration are the byte-reproduction path. Source
hashes, full row/frame/label checks, official validation and atomic writes protect
the output. `MVP_REVIEW.md` describes local-only review and export. Original
estimator documentation is preserved as `ESTIMATOR_README.md` in the MVP code ZIP;
`SOLUTION.md` and `THIRD_PARTY.md` retain full method/provenance/license details.
Training replay belongs in a separate experimental copy under its preregistered
protocol; completed holdouts must not be reopened for selection.

## Limitations and submission state

One provider holdout, related clubs/league and synthetic tracking errors give
limited transfer evidence. Sparse touches, provider control conventions and
turnovers hidden in tracking gaps remain difficult. Centred motion averages fast
turns/reversals and loses coverage near unreliable observations. Training resource
use and hidden-match accuracy are unresolved; competitive development is not
exhausted. Further work needs a separate preregistered study and fresh independent
acceptance. The local review UI does not change the frozen estimator.

Only publish a separately authorized **code-only project export**. Restricted
assets, actual possession CSVs and the private outer review ZIP never belong in a
public repository. Confirm the exact registered team name, registration/eligibility,
public repository URL and organiser email/form before any authorized submission.
