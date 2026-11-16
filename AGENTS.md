# Teammate repository workflow

Read README.md, PROJECT_STATE.md and TEAM_REPO_MANIFEST.json before changes.
Run ./setup-git.ps1 in each clone before working. Pull with git pull --ff-only
before repository changes; never create automatic merge commits. Preserve local
work on divergence. Keep tracked .githooks enabled, pull.ff=only and
pull.rebase=false. Never bypass hooks. Files above 100,000,000 bytes must never
enter Git; this curated handoff has a stricter 50,000,000-byte publication bound.
Clone with core.autocrlf=false as shown in README.md and keep it false; legacy
manifests bind exact bytes for Markdown/static assets as well as Python/model files.
Preserve large originals locally, using explicit ignore rules, never truncation.

The base estimator/runtime/model bytes and ESTIMATOR_PACKAGE_MANIFEST.json are
frozen. The original .gitignore is also frozen: configure .gitignore.team through
setup-git.ps1. PACKAGE_MANIFEST.json has the original 106-member export scope;
TEAM_REPO_MANIFEST.json binds the extended checkout. Refresh exact manifest file
records after authorized docs/packaging changes. Do not extend the legacy runtime
manifest to claim it includes experiments. Do not modify app export logic casually.

Actual match inputs, GT, prediction rows, caches and private review packs stay
local. Never print, visually inspect through model tools, attach to models or
upload restricted data. Aggregate summaries/hashes are allowed. No challenge
GT/public-window tuning or hand corrections. Run demo/synthetic checks when data
is unnecessary. The closed v3 study must not be replayed or promoted implicitly.

Every material implementation/model/package change requires a fresh independent
blind acceptance agent, fork_turns=none, bounded public requirements and independently
generated fixtures. Give it no prior results, scores, expected hashes or rationale.
Freeze tested source while it runs; keep temporary files disjoint. Root reproduces
failures and checks actual outputs. Unit/process success alone is not package E2E.
E2E requires fresh package/process/environment, input-to-CSV inference, exact
frame/label and deterministic output checks, official validator, measured runtime
and process peak memory, plus safe failure. Do not claim hidden performance.

Maintain a dated PROJECT_STATE.md checkpoint with objective, priority, changed
files, actions, verification evidence, limits and exact next commands. Historical
aggregate evidence applies only to its tested version. Do not stage, commit, push,
publish, invite collaborators or submit competition deliverables without the
owner's instruction for that action. This checkpoint is not authorization.
