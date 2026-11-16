# Local possession review MVP

From this project folder, start the private local review application:

```powershell
.\review.ps1
```

Open **http://127.0.0.1:8765**. Keep the launcher running; stop it with Ctrl+C or
`.\stop-review.ps1`. The app binds to localhost. Tracking, predictions and optional
video playback remain on this computer. There is no hosted upload service.

Use the interface to run the frozen noise-v2 estimator, inspect aggregate status,
play authorized local tactical video, and download the validated possession CSV,
technical document and private review pack. Inference requires the authorized
tactical XML/TXT in `more-than-a-hack-2027-main/data/tactical/`; video is optional.
The output has all 199319 ordered frames with H/A/D/X labels. Format validation
does not prove football accuracy, hidden ranking or competition acceptance.

## First setup or fresh code export

The code ZIP excludes the environment and all match assets. Use Python 3.13 and
install the pinned runtime requirements once:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\review.ps1
```

For invented fixture testing without supplied match assets, start
`.\review.ps1 -Demo`. DEMO markers identify synthetic data throughout the review
and its exports. Demo output is not an actual match prediction or an accuracy
score. Historical model training, external-match metrics and runtime figures in
the technical document describe the frozen estimator, not the demonstration.
Demo mode does not modify the model, its selection or old holdout evidence.

## Direct reproduction and preserved fallback

```powershell
.\run-candidate.ps1
# Portable Python entry point and explicit input directory:
.\.venv\Scripts\python.exe tools/run_candidate.py --data-dir C:\path\to\data
# Preserved selected-safe estimator, without changing models/active.json:
.\.venv\Scripts\python.exe tools/run_candidate.py --config models/selected-safe.json --out submissions/candidate-safe.csv --report reports/candidate-safe-run.json
# Original organiser reference fallback:
.\run-baseline.ps1
```

The current model is frozen noise-v2. The review app wraps existing inference;
it does not train a new model or manually adjust labels. See `MVP_TECHNICAL.md`,
`SOLUTION.md`, `THIRD_PARTY.md`, and the preserved `ESTIMATOR_README.md` in the new
MVP code ZIP. The original estimator package remains unchanged locally.

## Review exports and owner gates

Enter the **exact registered team name** and, when available, the separately
published public GitHub repository URL. Review packs are always marked
**not submission-ready**: team registration/eligibility, actual public repository
availability, organiser email/form requirements and owner authorization need
separate verification. Providing a URL does not publish or verify that repository.
No competition submission or receipt is created by the app.

The **outer review ZIP is PRIVATE** because it includes the actual possession
CSV. It contains a team-named CSV and Markdown technical document, a nested
code-only ZIP, README and integrity manifest. CSV bytes are copied exactly after
full contract checks. Only the code-only ZIP is a public-repository candidate;
keep CSVs, real timelines, videos, tracking, caches, logs and private review ZIPs
out of public Git. Publishing this college repository is outside this workflow.

The submitted labels must come from the algorithm. No challenge GT/public-window
tuning, match hand labels or hosted-model inspection of supplied inputs is part
of this workflow. Hidden performance remains unknown; this is a working local
review tool with bounded evidence, not a claim of a finished competitive solution.
