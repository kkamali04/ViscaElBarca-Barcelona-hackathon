# Technical document — baseline fallback (draft)

Team name: pending confirmation. This document describes only the current
fallback; replace it when the team's original method is implemented.

## Approach and assets

We reproduce the organisers' reference `baseline_smooth50` algorithm. For each
tactical tracking frame with a ball observation, we choose the nearest tracked
player using distances in metres and assign that player's team. Where no usable
observation exists, the raw baseline has no team answer. A centred majority vote
over +/-50 frames assigns H/A when either team has observations in that window;
otherwise it emits D. We explicitly acknowledge the organiser implementation.

Only tactical ATD metadata and tracking are used for inference. Video,
homography, broadcast data and Smart Tagging are available locally but are not
inputs to this baseline. No model is trained and no labelled training dataset is
used. The public five-minute labels are reserved for a pipeline sanity check;
the smoothing window is the organisers' published fallback, not selected by us
using that window's score.

## Possession rules and limitations

This fallback does not explicitly infer controlled possession, contested balls,
referee stoppages or restart instants. Smoothing reduces transient nearest-player
switches. Missing ball observations can wrongly produce D, and genuine stoppages
can be missed when the ball remains visible. Team control and short turnovers
are imperfectly represented. This is a reproducible starting point, not a claim
to solve these issues or outperform the published baseline.

## Reproduction

Use Python 3.13 and `requirements-lock.txt`. Put the supplied match assets in
`more-than-a-hack-2027-main/data/`, or set `MTAH_DATA_DIR`. From this project root:

```powershell
.\run-baseline.ps1
```

The inference entrypoint is `tools/build_baseline.py`; it never reads ground truth.
It writes UTF-8/LF CSV bytes deterministically and invokes the official validator
through the PowerShell wrapper. Linux/macOS equivalent:

```bash
python tools/build_baseline.py
python more-than-a-hack-2027-main/evaluation/validate_submission.py submissions/baseline_fallback.csv
```

Before submission, replace the draft team name, rename the CSV/document after
the registered team, publish a code-only repository, and validate/reproduce the
exact CSV. Uploading and publication have not been performed.
