# Repository scope and provenance

The original MVP ZIP has 106 code/model/document members. It excludes actual
timelines and match assets. Its existing .gitignore is bound by both retained
legacy manifests, so it remains byte exact. setup-git.ps1 configures the tracked
.gitignore.team as the repository-local core.excludesFile using a resolved absolute
path in each clone, together with .githooks, pull.ff=only and pull.rebase=false.
Clone with --config core.autocrlf=false before the first checkout; setup-git.ps1
also keeps core.autocrlf=false locally so exact manifest-bound bytes are preserved.
Run that script before adding local data or environments. Git has no size-based
ignore syntax; the preserved hooks enforce the 100 MB repository rule, while this
curated handoff is checked under 50 MB per file.

PACKAGE_MANIFEST.json covers only the 106-member runtime export scope. Its README
entry is refreshed for the teammate guide; all other entries and model/runtime
members remain exact. ESTIMATOR_PACKAGE_MANIFEST.json retains historical estimator
provenance and references intentionally excluded old GT/baseline members; its
README corresponds to ESTIMATOR_README.md, not the teammate README.
TEAM_REPO_MANIFEST.json separately binds the extended repository, including the
coordinate replay, its guide and an invented-only screenshot. It excludes itself,
REPLAY_MANIFEST.json and explicitly named mutable checkpoints/generated acceptance
receipts. The replay manifest binds its runtime/spec/guide records and the TEAM
manifest hash, making the dependency one-way rather than circular. Git commits
bind the excluded operational documents at publication. This does not extend the
106-member legacy export to include experiments or replay_v2. Rebuilding that ZIP
uses MVP_REVIEW.md as its standalone README.

The original teammate handoff is preserved in commit259b1c3. A documentation or
packaging refresh updates the affected records, with the previous manifest hashes
recorded as provenance; old reports retain their tested-version scope. Model,
scientific runtime and ESTIMATOR_PACKAGE_MANIFEST.json remain byte-exact. A later
publication report must distinguish fresh package checks from historical evidence.

Added evidence is an explicit selected list of aggregate historical reports.
Some historical links name local controls or reports deliberately excluded here.
The proposed public research dataset catalog is public metadata; actual bound
study catalogs, ledgers, licensed match downloads and extra fitted models are
excluded. Existing reports record only their historical tested versions. They
do not validate a future change or authorize replay of a closed study.

Frozen model JSONs were copied opaquely from the vetted base ZIP and verified
against their manifest digests. No other model payload was copied. Organizer
starter notebooks retain zero outputs. Third-party notices and source documents
are retained. The owner authorized public code publication on November 17, 2026.
Publication is not a competition submission. Private review packs contain actual
CSVs and must stay local; only the audited code/model/document repository is
eligible for public sharing. The README's generated conceptual illustration and
invented-only screenshot contain no match data. The generation prompt is recorded
in [assets/README.md](../assets/README.md).
