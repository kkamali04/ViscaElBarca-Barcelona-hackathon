# Requirements and submission readiness

Prepared November 17, 2026 against organizer commit
`f8f2629ff1e0985f81d7e59d8413678514ee1530`. The
[official challenge](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/CHALLENGE.md),
[data guide](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/DATA.md),
[rules](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/RULES.md),
[submission specification](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/SUBMISSION.md)
and scorer remain the authority.

## What must be produced

The task is to predict possession for **every frame of the tactical recording**.
It does not require decoding every video frame. The organizer explicitly permits
an algorithm built only on the supplied automatic tracking.

| Requirement | Exact contract |
|---|---|
| Output | One UTF-8 CSV with header `frame,label`, no index column or blank cells |
| Length and index | 199,319 data rows; integer frames `0` through `199318`, in order |
| Labels | `H`: home live possession; `A`: away live possession; `D`: dead play; `X`: abstention/ungraded frame |
| Reference recording | Tactical video timeline, 25 fps; ATD record ID minus one is the output frame |
| Graded ranges | Inclusive `11185..90651` and `110808..190197` |
| File validation | Run the organizer validator on the exact file to be submitted |

During loose or contested live play, possession stays with the last team that
controlled the ball. A touch, deflection or aerial duel without subsequent
control is not itself a turnover. Dead play has no requested team owner: its
answer is `D`. The organizer
[FAQ](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/FAQ.md)
explicitly publishes `[110808,113742)` as 2,934 graded dead-play frames before
the second kickoff.

## Inputs, predictions and ground truth have different roles

The selected workflow is:

```text
supplied automatic ATD XML + TXT -> frozen estimator -> generated prediction CSV -> coordinate replay
```

| Material | Role and permitted use |
|---|---|
| Supplied tactical ATD XML | Metadata describing teams, anonymous slots, channels and record layout; an algorithm input |
| Supplied tactical ATD TXT | Automatic, uncorrected player/ball observations; an algorithm input |
| Generated `frame,label` CSV | The estimator's output and the replay's possession overlay; the frozen inference command generates it from ATD |
| Supplied homography CSV, Smart Tagging, broadcast assets or video | Allowed optional algorithm inputs; the selected estimator does not use them |
| Public five-minute possession GT | A narrow check of alignment, format and label meaning; never training, tuning or version selection |
| Private GT or human-produced labels, events, possession data or corrected tracking about this match | Forbidden as estimator training, validation or inference material |

An XML/TXT tracking observation is not a possession answer. A CSV extension does
not establish its role: the permitted homography CSV differs from a prediction
CSV or possession GT. The chosen estimator reads the tactical XML/TXT; it does
not decode video or copy a previous prediction CSV into its output. Automatic
Smart Tagging support exists, but the selected weight is zero.

Algorithms may improve tracking or learn without human labels. Hand-correcting
positions, identities, transitions or output labels on this game is forbidden,
as are rules/constants tied to specific frames derived from watching the game.
Accessible labeled data from **other games** is allowed when fully disclosed.
Do not redistribute restricted assets or reconstructive derived exports. The
organizer FAQ also prohibits disclosing restricted material or extracts to
hosted/cloud LLMs. Keep actual inputs, predictions, caches and media local;
use invented data for model-facing browser checks and screenshots.

## Scoring and reproducibility

Ranking uses **spellF1**: one-to-one temporal matching of H/A possession spells,
with F1 averaged over IoU thresholds 0.3, 0.4, 0.5, 0.6 and 0.7. **macroF1** is
the first tie-break. The scorer then uses transition F1, latency and filename.
Dead-play stretches are stoppages, not possession spells. On graded frames, `X`
misses macroF1; before spell scoring it is filled within the same half. Public
five-minute scores must not choose model versions or hyperparameters. See
[EVALUATION.md](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/EVALUATION.md).

The repository must regenerate the **same submission file**, not an approximate
one, from the authorized data bundle. It must include runnable source, frozen
model/configuration, pinned dependencies, installation instructions and an exact
execution command. Bundled frozen weights are the reproduction path; retraining
is not required for inference.

## Run the selected workflow

From the full repository, first create the Python 3.13 environment and install
`requirements-lock.txt` as described in [README.md](../README.md). Obtain the
authorized bundle separately. Its data root must contain
`tactical/BAR-ATH_tactical_atd.xml` and `tactical/BAR-ATH_tactical_atd.txt`.

```powershell
$DataRoot = 'C:\path\to\challenge\data'
.\start-match.ps1 -DataDir $DataRoot
```

`start-match.ps1` runs uncached ATD-to-CSV inference, stops if inference fails,
then serves coordinate replay with that newly generated CSV. Each run writes
`candidate.csv` and `candidate-run.json` under a new
`local/match-runs/<UTC timestamp>-<run ID>/` directory and prints its path.
The report includes input/model configuration information, the official format
check, output hash, timings and Windows inference-process peak working set.
Replay displays supplied automatic coordinates and generated possession labels;
it is not video understanding or corrected tracking. Use the served localhost
page rather than opening a static HTML file directly.

The direct command remains valid for a CSV-only run:

```powershell
.\.venv\Scripts\python.exe tools/run_candidate.py --data-dir $DataRoot --no-cache
```

That direct command writes `submissions/candidate.csv` and
`reports/candidate-run.json`. The legacy `run-candidate.ps1` wrapper invokes the
same estimator. To replay that output separately:

```powershell
.\replay.ps1 -DataDir $DataRoot -Predictions '.\submissions\candidate.csv'
```

An invented demo validates interface behavior, not match inference quality.
Fresh package acceptance must also check actual input-to-CSV execution, exact
frame/label contract, repeated output, official validation, resource use and
safe failure. Changes to the launcher or viewer do not improve the frozen model
or inherit acceptance automatically.

## Current readiness and remaining actions

| Item | Current state |
|---|---|
| Selected estimator | Frozen `noise-v2`; tracking-to-label source and training provenance are documented in [TECHNICAL_SUBMISSION.md](TECHNICAL_SUBMISSION.md) |
| Registered team name | **ViscaElBarca** — supplied by the team owner on November 17 |
| Team registration/eligibility | Must be confirmed; the published rule is 3–5 members, with teams below three ineligible for the later Innovation Challenge/Final Pitch |
| Repository | [kkamali04/ViscaElBarca-Barcelona-hackathon](https://github.com/kkamali04/ViscaElBarca-Barcelona-hackathon); owner authorized public visibility on November 17. Confirm that this URL opens while signed out before submitting |
| Technical document | Prepared draft identifies ViscaElBarca; use `ViscaElBarca.md` or PDF and complete the team's final review |
| New launcher/viewer package | Version-specific status is in the [repair acceptance receipt](../reports/render-repair-acceptance.json) and latest PROJECT_STATE.md; this document is not a test receipt |
| Competition submission | **Not submitted** |

The organizer requires three deliverables through the emailed form: the
possession CSV, a **public** repository URL, and a short PDF/Markdown technical
document. The document must disclose the approach, assets, all labeled training
data with sources/creators/amount, possession rules, limitations and reproduction.
Name the CSV and technical document after the registered team. There is one
response per team; the last edited response before the deadline is scored.

The published deadline is **November 17, 2026**. The organizer email supplied by
the team states **23:59 CET (17:59 New York time)**; confirm the final form instructions. There is no live leaderboard. Confirm the registered team identity,
eligibility, public repository availability and exact final deliverables before
any separately authorized publication or submission. Preserve restricted data
outside the public repository.
