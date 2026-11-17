# Morning review — November 17

- Owner tracking viewer: [port 8767](http://127.0.0.1:8767/) or [port 8771](http://127.0.0.1:8771/).
- Mint dots are anonymous home slots, peach dots are away slots, and white is the ball.
- Positions follow supplied observations. Missing observations disappear; automatic tracking may jump. Prediction labels do not move the dots.
- Play, Space, timeline, single-frame buttons and speed control the replay.

## What to review

1. Reload the served page, press Play, pause, seek and change speed.
2. Read the possession panel: H is home live possession, A away, D dead play and X no answer.
3. Check the exact version-specific evidence in the [overnight receipt](../reports/overnight-acceptance.json). This guide is not a test receipt.
4. Review the [technical document](TECHNICAL_SUBMISSION.md) and [requirements/readiness matrix](REQUIREMENTS_AND_READINESS.md).

The selected estimator remains frozen **noise-v2**. This release addresses viewer
failure explanations and generated-cache recovery; it introduces no training run
or new hidden-match accuracy claim. Interface, format and runtime acceptance do
not establish possession accuracy.

## Regenerate a CSV and view it

Follow [README.md](../README.md) to clone, run setup-git.ps1 and install the pinned
Python 3.13 environment. Set the authorized data root on your own computer:

```powershell
$DataRoot = 'C:\path\to\authorized\data'
.\start-match.ps1 -DataDir $DataRoot -Port 8772
```

The root must contain the tactical ATD XML/TXT pair. The command recomputes
predictions, checks the format, writes a fresh ignored `local/match-runs/`
directory, and opens replay. Port 8772 avoids the owner's existing viewers.
The launcher prints the output directory. Preserve the generated CSV/report;
the viewer itself does not run inference or train a model.

If an input is invalid, correct the stated problem and restart the launcher.
Try again reconnects after restart. See [replay commands](../REPLAY.md).

## Before the final form

- Confirm the registered team name and eligible team members. The team name remains pending; the friend knows it and is handling final touches.
- Name the generated CSV and technical document after that exact team name. Markdown or PDF is accepted for the document.
- Run the official validator on the exact renamed CSV, using this repository's Python environment:

  ```powershell
  .\.venv\Scripts\python.exe more-than-a-hack-2027-main/evaluation/validate_submission.py 'C:\path\to\TEAM_NAME.csv'
  ```

- The form requires a **public** code repository. The current teammate repository is private; visibility and competition submission remain separate owner decisions.
- Keep restricted match assets, prediction timelines, private reports and caches outside the public code repository. Bundled weights and source regenerate the output without retraining.
- Submit the CSV, public repository URL and short technical document through the emailed form. This repository has not submitted them.

The organizer email supplied by the team states **November 17, 2026 at 23:59 CET
(17:59 New York)**. Confirm the final form instructions. There is no live
leaderboard or hidden-performance guarantee. The [official submission guide](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/SUBMISSION.md)
remains the authority.
