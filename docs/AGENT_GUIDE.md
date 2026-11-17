# Handoff for people and AI agents

This repository estimates team possession from supplied tactical tracking. The
active release is **frozen noise-v2**: ATD XML/TXT enters a local Python process,
and a validated `frame,label` CSV leaves it. The coordinate viewer explains that
output; it does not run a video detector or establish prediction accuracy.

Start with [README](../README.md), the latest checkpoint at the **top** of
[PROJECT_STATE](../PROJECT_STATE.md), [AGENTIC_GOAL](../AGENTIC_GOAL.md), and
[AGENTS](../AGENTS.md). Use [PROJECT_MAP](PROJECT_MAP.md) to navigate. Dated
checkpoints and reports describe their stated versions; older status, deadlines
and publication notes can be historical.

## Set up a full checkout

Use Git and Python 3.13. Run these from the new checkout; the launchers use its
`.venv` directly, so activating the environment is unnecessary.

```powershell
git clone --config core.autocrlf=false https://github.com/kkamali04/ViscaElBarca-Barcelona-hackathon.git
cd ViscaElBarca-Barcelona-hackathon
.\setup-git.ps1
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\replay.ps1 -Demo
```

Open [localhost:8771](http://127.0.0.1:8771/), wait for preparation and press Play.
The invented tracking demo needs no match download and shows **No CSV overlay**.
Keep the terminal running; stop with Ctrl+C or `.\stop-replay.ps1 -Port 8771`
from another terminal. If `py` is unavailable, create the environment with the
full path to an installed Python 3.13 executable. macOS/Linux users can install
the same lockfile in a virtual environment and run
`.venv/bin/python -m replay_v2 --demo --open`.

## Run authorized tracking through the estimator

Get match assets through the organizer's
[enrollment and terms process](../more-than-a-hack-2027-main/DATA.md#getting-it).
Use the download link supplied to eligible participants. Source-code access does
not grant access to or permission to redistribute those assets. Keep originals
local; do not upload tracking, video, ground truth or prediction timelines.

The input directory must contain `tactical/BAR-ATH_tactical_atd.xml` and
`tactical/BAR-ATH_tactical_atd.txt`. Replace this placeholder with that directory:

```powershell
$DataRoot = 'C:\path\to\challenge\data'
.\start-match.ps1 -DataDir $DataRoot
```

This runs uncached inference, writes a unique CSV/report under ignored
`local/match-runs/`, performs the official format check and launches `replay_v2`
with the generated CSV. Use `-Port 8772` if 8771 is busy; `-NoBrowser` suppresses
automatic browser opening. It does not take an existing possession CSV as an
inference input.

For inference alone, with explicit local destinations:

```powershell
.\run-candidate.ps1 --data-dir $DataRoot --no-cache --out local/manual-run/candidate.csv --report local/manual-run/run.json
```

The equivalent Python entry point is
`.\.venv\Scripts\python.exe tools/run_candidate.py` with the same flags. It
defaults to [models/active.json](../models/active.json), verifies frozen source
and model hashes, and invokes the organizer's validator. Its report records
aggregate timing, hashes and Windows peak working set; non-Windows peak memory
is not supplied by that function. A valid report is format evidence, not an
accuracy score. Do not print or attach CSV rows to a model.

To view an existing locally generated CSV, without inference:

```powershell
.\replay.ps1 -DataDir $DataRoot -Predictions 'C:\path\to\candidate.csv'
```

See [REPLAY](../REPLAY.md) for cache, stopping and recovery behavior. If startup
rejects a path or preparation fails, correct the named input/cache/port problem
and restart the launcher. The browser's Try again reconnects; it cannot change
the running process's selected files. Preserve inputs and large originals.

## Read the result correctly

| Label | Meaning |
|---|---|
| H | Home possession, ball alive; Barcelona for the supplied match. |
| A | Away possession, ball alive; Athletic Club for the supplied match. |
| D | Dead ball, regardless of which side will restart. |
| X | No answer; it does not identify whether play is live or dead. |

The contract is exactly 199,319 ordered frames, numbered 0 through 199318, with
the header `frame,label`. See the [challenge](../more-than-a-hack-2027-main/CHALLENGE.md).
Player dots are anonymous home/away **track slots**, not shirt numbers or stable
player identities. The small white dot is the ball. Missing observations
disappear; tracking gaps and jumps remain. Display interpolation does not repair
the source. The CSV overlay controls the possession readout, never dot positions.

Use `replay_v2` for coordinate replay. The older **Touchline** app in `review_app`
is a separate local review/export workflow on port 8765 (`.\review.ps1 -Demo`).
Its demo pitch animation and labels are illustrative. Its optional local video
playback is not tracking reconstruction. Neither app is evidence of computer
vision detection, pass/shot recognition, hidden ranking or competition acceptance.

## Full repository versus legacy ZIP

The full checkout includes `replay_v2`, launchers, experiments and selected
historical evidence. The legacy **106-member code-only ZIP** contains the frozen
estimator and Touchline review app; it does **not** contain `replay_v2` or the
extended experiment tree. Its standalone instructions are [MVP_REVIEW](../MVP_REVIEW.md).
A private review pack includes a prediction CSV and must stay private even when
its nested code-only ZIP is eligible for sharing.

[PACKAGE_MANIFEST](../PACKAGE_MANIFEST.json) binds the legacy scope;
[TEAM_REPO_MANIFEST](../TEAM_REPO_MANIFEST.json) binds the extended checkout.
[ESTIMATOR_PACKAGE_MANIFEST](../ESTIMATOR_PACKAGE_MANIFEST.json) preserves older
estimator provenance, and [REPLAY_MANIFEST](../REPLAY_MANIFEST.json) binds replay
artifacts. Read [repository scope](REPOSITORY_SCOPE.md) before changing packaging.
Do not rewrite a legacy manifest to imply it tested newer code.

## Continue work without losing scientific evidence

Before changes, run `git pull --ff-only` and inspect the working tree. On
divergence, inspect commits and preserve local work; do not merge automatically.
Keep `.githooks`, `core.autocrlf=false`, `pull.ff=only` and `pull.rebase=false`
configured by `setup-git.ps1`. Do not bypass hooks. No Git file may exceed
100,000,000 bytes; this curated handoff has a stricter 50,000,000-byte bound.
Inspect generated artifacts before staging, retain large originals locally and
use the supplemental ignore rules rather than changing the frozen `.gitignore`.

Preserve noise-v2 model/config/source bytes, v1 evidence and completed holdouts.
The speed work and closed v3 study are historical experiments, not active
inference improvements. A semantic/model/feature change needs a new versioned
experiment, a predeclared split and gates, genuinely fresh held-out evidence and
independent validation. Do not reopen closed holdouts, tune on challenge ground
truth/public windows, hand-correct labels or silently promote an experiment.
See [SOLUTION](../SOLUTION.md), [noise-v2 protocol](../research/NOISE_V2_PROTOCOL.md)
and [V3_REVIEW](../V3_REVIEW.md) for the evidence and limitations.

Every material implementation/model/package change requires a fresh independent
blind acceptance agent (`fork_turns=none`) before it is called verified. Give it
public requirements, a bounded task, disjoint files and a private temporary
directory. Do not supply prior pass/fail results, scores, expected hashes,
implementation rationale or earlier tests. It must generate its own fixtures
and derive its own oracles. Freeze the tested source while it runs; the root
agent reproduces failures and inspects actual aggregate acceptance artifacts.

E2E acceptance requires a fresh exported package/process/environment, actual
input-to-CSV inference, exact frame/label checks, deterministic repeat output,
the official validator, measured runtime and process peak memory, and a safe
failure case. Unit-test success alone is insufficient. Restricted data may be
processed by local code, but never printed, visually inspected by model tools,
attached to models or uploaded. Use invented data for model-facing browser tests;
only aggregate pass/fail/resource summaries and hashes may enter agent messages.

Maintain the latest dated checkpoint and durable goal after material findings
and before stopping: objective, phase, changed files, evidence, limits and exact
next action. Record what was executed versus planned. Historical reports and
valid CSVs do not guarantee hidden performance. Obtain the owner's separate
authorization for staging, commits, pushing, publication or competition submission.

## Recover a committed change safely

For a future authorized recovery, inspect history and work on a new branch.
The following is a template, not an instruction to execute it during review:

```powershell
git status --short
git log --oneline -n 12
git pull --ff-only
git switch -c codex/recover-change
git revert <commit-to-undo>
```

`git revert` creates a new commit, so obtain commit authorization before that
step. Preserve uncommitted work first; do not use a destructive reset or force
push. Review the inverse diff, reconcile affected manifests and complete the
required acceptance checks before any separately authorized push. Reverting a
scientific change does not erase its reports or restore unused holdout status.
