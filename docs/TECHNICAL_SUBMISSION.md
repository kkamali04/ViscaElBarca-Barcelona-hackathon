# Possession estimation from automatic tactical tracking

**Registered team name: PENDING — complete before submission.**

**Code repository:** [kkamali04/barcelona-possession-hackathon](https://github.com/kkamali04/barcelona-possession-hackathon).
It is currently private and therefore does **not** yet satisfy the organizer's
public-repository requirement. This is a prepared, unsubmitted technical draft,
dated November 17, 2026.

## Approach and selected assets

The frozen **noise-v2** estimator generates one possession label for each of the
199,319 tactical frames. It reads the supplied tactical ATD metadata XML and raw
tracking TXT locally. The XML establishes home/away membership and channel order;
the TXT supplies automatic player and ball observations. Ordered ATD IDs
`1..199319` map to output frames `0..199318`. Normalized x/y coordinates are
converted to metres on the published 105.3 × 68 m pitch. Slots remain anonymous;
they are not persistent player identities.

Twenty-two model inputs summarize team-to-ball proximity, observed object
counts, anonymous collective movement, ball motion, missing observations and
distance to pitch boundaries. Unknown evidence remains unknown. A centred
local-linear x/y slope uses 31 uninterrupted reliable observations at 25 Hz to
estimate ball velocity before taking its magnitude. It does not bridge gaps or
period boundaries. The slope reduces coordinate jitter without averaging
already biased speed magnitudes; it also averages fast turns and reversals.

A histogram gradient boosting model has 64 rounds, three numeric trees per
round, at most 15 leaves per tree, learning rate 0.08, L2 regularization 2,
minimum leaf size 80 and 63 bins. Frozen numeric JSON weights supply bounded
H/A/D evidence to an exact three-state temporal dynamic program. A state change
costs `0.5 × fps`, or 12.5 score units at 25 Hz. Halves reset independently.
Inference requires NumPy and the organizer validator's pandas dependency; it
requires neither a GPU nor scikit-learn.

The selected model uses **no video detection, broadcast tracking, homography,
human match records or challenge possession GT**. Automatic phase-tag support
was implemented but dropped from the selection: its weight is zero. Supplied
video is not required for inference. The coordinate replay reads the supplied
automatic observations and a separate generated possession CSV; it does not
repair tracking or feed new labels back into the estimator.

## External training data and labels

The labeled source is **IDSSE Sportec/DFL**, *An integrated dataset of
spatiotemporal and event data in elite soccer*, by **Manuel Bassek, Robert Rein,
Hendrik Weber and Daniel Memmert (2025)**. The
[Scientific Data descriptor](https://www.nature.com/articles/s41597-025-04505-y)
and [original Figshare record](https://doi.org/10.6084/m9.figshare.28196177)
describe the source; acquisition used the public
[PySport mirror](https://huggingface.co/datasets/pysport/idsse-data).
The data is CC BY 4.0. Ownership and play-state targets are the Sportec/DFL
provider's annotations, not labels made by our team or the challenge's corrected
tracking.

Targets map `BallStatus=0` to `D`; active play (`BallStatus=1`) with
`BallPossession=1` to `H` and `2` to `A`; missing/unknown cases to `X`.
Targets are stored separately from geometry and supplied only to training or
scoring. Provider speed, ball height and event data are not feature inputs.
Centred provider coordinates are translated to a pitch-corner origin.

Frozen training provenance records one other match, **J03WOH: 137,214 frames at
25 Hz**. Stride five supplies **27,443 original rows per view**. Four fixed views
are clean tracking; 40% ball deletion in four-second blocks; 40% deletion in
twelve-second blocks; and combined four-second ball gaps, 30% one-second player
dropout, 0.25 m coordinate noise and sparse 20 m ball jumps. Home/away feature
and target swaps produce **219,544 augmented training rows**. They remain
examples from one game, not independent matches. Classes are balanced during
fitting.

The recorded split uses **J03WOY** for selection and **J03WMX** as v2's fresh
external holdout after the source/model/configuration/protocol freeze. The
original v1 holdout **J03WR9** is preserved and is not reopened for selection.
The protocol and historical reports are retained in the repository. This draft
introduces no training run or new performance claim. Challenge public-window
labels are not training or tuning data; private GT, human-produced data about
the challenge game and hand corrections are excluded from this estimator.

## Possession rules implemented

`H` and `A` mean live home/away control, `D` means dead play, and `X` means
abstention or an ungraded frame. A nearest-player change or isolated touch does
not directly force a turnover. Temporal decoding penalizes state changes and
carries evidence through loose or contested balls. Its deterministic tie rule
delays an otherwise unidentifiable switch until supporting opposing evidence.
This approximates the last-controlled-team convention; it does not establish
control from a touch or explicitly recognize every duel, pass or referee action.
Missing ball observations alone do not force dead play.

Published inclusive graded ranges become `[11185,90652)` and
`[110808,190198)`; other frames receive `X`. The sole fixed dead-play interval
is `[110808,113742)`, explicitly published as dead play in the organizer
[FAQ](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/FAQ.md).
This is a public preparation interval before the second kickoff. Other dead-play
decisions come from model evidence and temporal decoding. No manual timeline
edits enter the generated CSV.

## Reproduction

Use the full repository with its frozen model/configuration and Python 3.13.
From the repository root on Windows:

```powershell
.\setup-git.ps1
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
$DataRoot = 'C:\path\to\challenge\data'
.\.venv\Scripts\python.exe tools/run_candidate.py --data-dir $DataRoot --no-cache
```

The authorized data root must contain
`tactical/BAR-ATH_tactical_atd.xml` and `tactical/BAR-ATH_tactical_atd.txt`.
The command writes `submissions/candidate.csv` and `reports/candidate-run.json`.
It checks exactly 199,319 codes, writes UTF-8/LF `frame,label` rows atomically,
and invokes the organizer's actual format-validator functions. The report
contains input/configuration/output hashes, timings and Windows process peak
working set. To run the standalone organizer validator on that exact file:

```powershell
.\.venv\Scripts\python.exe more-than-a-hack-2027-main/evaluation/validate_submission.py submissions/candidate.csv
```

For fresh inference followed by served coordinate replay, use:

```powershell
.\start-match.ps1 -DataDir $DataRoot
```

That launcher uses `--no-cache`, creates a new
`local/match-runs/<UTC timestamp>-<run ID>/` directory, generates its CSV/report,
and starts replay only after inference succeeds. It prints the output location.
The legacy `run-candidate.ps1` wrapper and direct `tools/run_candidate.py`
command remain valid. An invented replay demo is an interface check, not a
substitute for match inference.

The exact bundled weights/configuration are the byte-reproduction path; do not
retrain to regenerate a submission. The selected numeric model is 767,185 bytes,
SHA256 `856114a7693414db9652bb50e37ab527f958f84e75200b69ce07be28be24bff2`.
Source/model bindings reject changed frozen code. Keep restricted assets,
actual prediction CSVs, caches and private review packages outside the public
code repository. The CSV for the competition must use the confirmed registered
team's filename.

## Evaluation scope and limitations

The competition ranks **spellF1**, with macroF1 as the first tie-break. External
provider validation and simulated tracking errors do not establish a hidden
challenge score or rank. Historical estimator evidence is preserved in
[SOLUTION.md](../SOLUTION.md); changed launcher/viewer packages require separate
fresh acceptance. This prepared document is not a new execution receipt.

One training game, one selection game and one external holdout give limited
transfer evidence. Provider control conventions can differ from corrected
Metrica labels. The automatic challenge feed has ball gaps, fragmented slots and
identity switches. Sparse touches, plausible tracking errors and turnovers
hidden inside gaps remain difficult. The offline motion estimate uses future
observations, smooths rapid turns/reversals and loses 15 frames at each reliable
run edge. The decoder cannot recover evidence that was never observed.

Training peak memory and hidden-match accuracy remain unresolved. Frozen
estimator evidence does not guarantee the current viewer package or hidden
performance. Further semantic model changes require a versioned experiment,
predeclared split, fresh held-out evidence and independent blind acceptance.
Registered team identity, eligibility, a public repository and the emailed
submission form remain to be finalized; **no competition submission has occurred**.
