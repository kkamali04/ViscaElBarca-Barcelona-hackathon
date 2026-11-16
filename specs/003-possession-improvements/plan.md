# Possession v3 implementation plan

For agentic workers: apply the manually read Superpowers6.1.1
subagent-driven-development workflow with disjoint tasks, fresh blind acceptance,
no commits and user-authorized autonomous execution after G01. **Not accepted yet.**
Goal: implement/study both requested improvements and deliver a bounded empirical
promotion or evidenced rejection while preserving the accepted fallback.
Architecture: versioned local experiment/control/runtime modules with one guarded
study, three fixed fits, eight challengers and one fresh-test finalist.
Stack: project CPython3.13.12, NumPy2.4.4, sklearn1.9.1 training only; runtime locks
unchanged. No neural/cloud/SDK dependencies or generators.

## Global constraints and handoff

Read contracts.md, protocol.json, requirements.md and the assigned PRD. All29files
in reports/v3-fallback-preservation.json remain byte-identical. No staging/commit/
push/publication/submission. No actual-label parser before G02+G03; no study before
G05. No training/test retries or extra candidates. Tests below are implementer
checks; independent reviewers derive their own fixtures in disjoint private paths.
Never pass their expected outcomes or hashes from these tests as blind oracles.
Root verifies evidence artifacts and reproduces failures. All commands below are
future commands from project root using `.\.venv\Scripts\python.exe`.

At each code task: write named synthetic failing tests, run them and confirm the
failure is the missing/incorrect behavior, implement the specified contracts, run
those tests, record exact source/test hashes, freeze and request its fresh gate.
No train fixtures contain actual football records. No task may modify another
lane's files. Contract changes return to G01 rather than silently patch consumers.

## T02: immutable guard and control CLI

Create experiments/v3/{__init__,contracts,guard,cli}.py and
tests/test_v3_guard.py. Implement register_study/reserve_attempt/assert_access/
finish_attempt exactly as contracts.md. CLI subcommands call only their defined
module boundaries; heavy imports deferred until command dispatch. Register the complete scientific closure listed in protocol.json (release-only
modules have a separate later manifest), and hashes
of protocol, both PRDs, contracts, catalog, complete source closure, runtime/training
locks, actual package versions, prior-access snapshot and comparator/fallback 29.
No fit starts until these agree with reviewed freeze. Make prior snapshot immutable
and live ledger global. Windows OS lock encloses current-chain validation,
eligibility and durable full-cohort reservation. Capabilities bind PID+creation.

Synthetic test oracles: two studies with stale identical snapshots race for the
same two fixtures; exactlyone reservation succeeds and loser parseszero targets.
A reserved owner's cache reads succeed despite ledger growth; another PID or a
completed/interrupted attempt fails. Simulated partial-tail/stale-lock/restart
cannot reset consumption. Mutate protocol, comparator, metric, raw manifest and
source one at a time: deny before parser. No completed report is needed to consume
an attempt. Command: `-m unittest discover -s tests -p test_v3_guard.py -v`.
Expected: all synthetic checks pass, parser-spy countzero on refusals. GateG02.

## T03: observation/target isolation and complete caches

Create experiments/v3/{cache,adapter,corruption,fetch}.py,
tests/test_v3_cache.py,tests/test_v3_adapter.py,tests/test_v3_corruption.py.
Consumes contracts.py/guard APIs; produces ObservationBatch/TargetBatch and typed
FeatureSet. Fetch only explicit registered file IDs to new local originals with
size/SHA256/MD5 checks; downloading/hashing opaque bytes is not target parsing.
Do not instantiate third-party dataset SDKs or glob rawfiles. New raw downloads
are a later root operation after G05, not implementation setup.

Raw parser checks capability before first parsing; independently accepts only
public schema fields. Validate dense frame reconstruction, rosters, duplicates,
per-period25Hz timestamp consistency/pitch. No label column reaches observations,
orientation, corruption RNG or feature graph. Cache verification/writing obeys the
complete manifest/atomic directory contract on both hits and misses. Shared cache
code also implements ReleaseAccess/InferenceContext and exact CacheAuthority union;
study roles never fall back to release authority. T03 creates source schema and
fetch_registered_sources handoffs exactly as contracts.md. Implement all
six exact conditions from protocol; no undeclared drift/jitter variants. Dense
features use accepted FeatureAccumulator then noise-v2 motion transform, with
immutable input checks and explicit v3 dtype conversion.

Tests invent two periods/timestamps/rosters and all target patterns. Randomize all
labels while observations stay fixed: numeric observation/features/masks identical,
only targets and legitimate source/cache provenance digests differ; do not demand
full manifest-byte equality across distinct source variants. Delete/mutate/truncate/cache-member dtype orshape: reject before
mapping; a cache.json alone cannot pass. Spy first label parser call and require
reservation event alreadyfsynced. Check stale anchors against originalstart-1,
periodstarts/missinganchorNaN, canonical raw roster/XML permutation equivalence,
noncanonical direct-batch refusal and exact slot digest. Independently compare
standard_normal full(N,S+1,2), teleport full(N,2) and per-run block arrays including
inactive/missing rows and chunk-boundary variants; compare final float32 bytes.
Check interior integer cap IDs (L30002), sparse exact timestamp deviations/origin,
derived masks, allgap/partialpair and original-byte immutability. Target-only
variants use distinct authorized source manifests and one fixed protocol RNG root.
Attempt cache member replacement after verification while read handles are held;
replacement must fail or consumption fail, never use unverified bytes. Run each named
unittest file. G03 independently accepts only synthetic data after G02.

## T04: invariant boundary head and exact dynamic decoder

Create experiments/v3/{boundary,decoder}.py,
tests/test_v3_boundary.py,tests/test_v3_decoder.py. Consume FeatureSet; emit the
28-feature BoundaryFeatures and typed support, numeric-boundary-hgb-v1 schema.
PRD-TURNOVER owns exact clipping/window/channel ordering. Decoder follows the
accepted dynamic-programming recurrence, plus flatten_support and strict numeric
head loading; computes two typed incoming costs
peredge using q andalpha without Nx3x3 allocation. Preserve accepted ties,
positive-run independence, forbiddenstates/+inf and impossiblepath errors.

Tests independently enumerate all3^N paths for N<=7 and compute objective from
raw inputs; alpha0 chosen output equals accepted decoder for numerically valid
inputs; both signs of overflow in losing allowed alternatives must reject; dynamic objective/ties
match oracle. Uniqueoptimum H/A swap transforms output; tied optimalsets/objectives
transform while canonical representative maynot. Test edgeoffbyone, periodreset,
shortH-A-H, missinggeometry fallback, allinvalid, forbiddenedges and NaN/shape errors.
Analytic step/ramp/gap windows establish all28 columns. Numeric export on invented
3class inputs checks wrapper classorder and <=1e-10raw parity. Flatten fixtures
cover two runs, independent type masks, invalid/start/outside zeros, empty sets,
constant input, mean preservation on eligible edges and changed support timing;
compare exact pinned-NumPy ascending-gather mean/cast. Assert F080 and B080 share
emitter/head/alpha and differ only support transform, with no extra fit.
Malicious head fixtures test oversized bytes before parse, duplicate keys,
cycle/shared child/unreachable node,13-node/tree and96-tree limits, class groups,
leaf sentinels and external <=4096 head batching. Command: named
unittest files. G04 fresh reviewer uses its own fixtures and source freeze.

## T05: fixed training, exact metrics, resources and study orchestration

Create experiments/v3/{training,evaluate,resources,core}.py; extend only root-owned
cli.py; tests/test_v3_training.py,tests/test_v3_metrics.py,
tests/test_v3_resources.py,tests/test_v3_study.py. Implement exact row population,
strata/inclusion probabilities, side augmentation and FINAL GLOBAL MEAN1 weights.
Use declared estimator parameters,randomstate,early_stoppingFalse. Count actual
fit rows, require all classes/strata, enforce row limits and threefit budget.
Train head once onC1; reuse exactbytes in everyB/F/D. Implement shared
core.predict_codes and immutable CandidateConfig/ModelBundle/InferencePolicy
contracts before registration; both evaluator and later runner call this API.
Public forcedD constrains scores before decode; external policy has no forcedD. Match class-balanced weights
at equalmatch/condition totals; do not use randomframe validation.

score_match calls actual pinned official functions, creates per-period GT-valid
runs with fullindices, applies exactX filling and destination-typed inclusive
transition tolerances. Synthetic hand-derived cases test unknown gaps, headX,
allX, D split/noDspells, periodedges, +/-12/25 inclusive and asymmetric destination
labels. Add asymmetric H/A spell counts proving pooled official mean_f1, plus
one-frame unknown gaps and adjacent halves with transitions on opposite sides:
match each run independently then sum TP/FP/FN, never average run F1. Call public
spell_scores directly; do not call full evaluate for the diagnostic wrapper. Training fixtures verify weightsmean1, equalrelative totals, inverse
inclusion accounting, one fit seed and all candidate IDs. Derive sklearnL2-weightscale
oracle independently; no real scores required. Source closure and model parity
are checked before sealing models/models.json after all three fits. New trained
model hashes never enter prefit registration; sealed model receipt references the
unchanged study. Selection reservation must fail before a complete verified seal.

Resource supervisor binds actual process identities, OSworker highwater and
recursive concurrenttree sampling<=50ms; enforce12GiB and4threads beforeheavyspawn,
aggregatefit8h, deadline anddiskcaps. Test with invented parent/child allocations,
shortlivedchildren and explicit budgetfailure; never accept parentonly sampling.
Record sampled tree lower bound, OS worker highwater and monitor gaps separately;
enforce OS job ceilings and fail preflight if supervisor cannot bound processes.
Synthetic resource preflight must pass before any fresh cohort reservation;
latest-start limits are stop policies, not demonstrated runtime feasibility.
Study synthetic integration must run all3small fits,9selection rowsx6conditions,
exact gate/tie selection and singletestcapability without actual datasets. G05 fresh
scientific/guard integration acceptance required.

## T06-T08: root-operated registered study, not implementer discretion

AfterG05 and before each schedule cutoff:

0. Root completes local/v3-control/catalog-complete.json from opaque/pinned metadata
   integrity and metadata-only overlap receipts, preserving research catalog. Missing
   identities/digests block registration; no target parse. No downloads occur now.
1. `-m experiments.v3.cli register --protocol specs/003-possession-improvements/protocol.json --catalog local/v3-control/catalog-complete.json --fallback reports/v3-fallback-preservation.json`
2. `-m experiments.v3.cli fetch --study local/v3-studies/possession-v3-20261116-a4/study.json --fixtures J03WOH J03WOY J03WPY J03WN1 J03WQQ`
3. `-m experiments.v3.cli fit --study local/v3-studies/possession-v3-20261116-a4/study.json`
4. `-m experiments.v3.cli select --study local/v3-studies/possession-v3-20261116-a4/study.json`
5. AfterG06 only: `-m experiments.v3.cli test --study local/v3-studies/possession-v3-20261116-a4/study.json`

Each command creates a unique immutableattempt directory and aggregate-only report.
Fetch verifies exactlisted IDs and originals without parsing; train/selection/test
reserve and parse only their own role. Model manifest destination models/models.json;
selection output selection/result.json and finalist.json; test outputtest/result.json,
all belowstudyroot. None are rootmodels/active.json. Ineligible selection exits4,
records allcandidates and doesnot reserve fresh tests. Missing/error/capped attempt
remains consumed; no automatic retry. G06 audits exactfinalist beforetest. G07
verifies all six paired conditions, gate arithmetic and N2limits from actual
local artifacts; no cherry-picked seeds/conditions or testablation. Local evaluator
never prints records/targets. Root controls originals andprivate evidence retention.

## T09: explicit versioned runtime, export, review and promotion

Create experiments/v3/{runner,exporting,review,promotion}.py,
tests/test_v3_runner.py,tests/test_v3_export.py,tests/test_v3_review.py.
T09 also owns experiments/v3/TECHNICAL.md and experiments/v3/REPRODUCE.md, both
versioned and included in code export: exact trained models/config/grid, source
licenses/attribution, A4 role/access history, target mapping, corruption algorithms,
local fit/infer/export commands, environment/closure hashes, empirical result or
rejection disposition, limitations/N2 and protected fallback. Never edit historical
MVP_TECHNICAL.md. No private records or unearned acceptance claims in docs.
Runner imports accepted FeatureSet/ATD extraction and public frame rules unchanged,
then calls frozen core.predict_codes with verified explicitfinalist bundle/config. No GT/tag tuning; preserve publicforcedD.
Standalone inference creates a verified observation-only InferenceContext; cached
miss/hit and --no-cache never look up original study/control paths. Study caches
retain live guards. Test wrong authority/domain/target refusal with filesystem spies.
New inferencecache uses complete v3cache validation; no silent reuse of oldnpz.
Implement CSV/report/commit.json in one sibling scratch directory, all-row/official
validation and fsync, then one no-replace atomic rename to the absent generation
parent. Reject different/existing output parents and aliases before any input;
old committed generations remain unchanged. No independent CSV/report replacements. Implement explicit allowlisted reproducible ZIP20MiBcap and freshminimal
environment importclosure. No globs over models/experiments, no privatepayload.

ReviewStateV3 implements accepted state/API interface in newmodule; reuse read-only
CSVinspect/static/HTTPhelpers without monkeypatching. Override provenance,runner,
exports and separateoutputroot. Dedicated loopback8766server uses its ownstate;
real video is owner-only. Demo mode generates its own syntheticdata and never
checks actualdata. Codeexport and privatebundle identify samev3release. Export
privatebundle only locally, clearlynot-submitted. `promote` accepts exactscience,
blindE2E androotreceipt hashes, rechecks fallback 29 and writes a versioned receipt;
it doesnot overwrite accepted activeconfig/launcher.

Prepare the existing trusted output root local/v3-review/runs only; run-0001 must
be absent. Future commands: `-m experiments.v3.cli package --study local/v3-studies/possession-v3-20261116-a4/study.json`; `-m experiments.v3.runner --release local/v3-releases/possession-v3-20261116-a4/release.json --data-dir more-than-a-hack-2027-main/data --out local/v3-review/runs/run-0001/candidate.csv --report local/v3-review/runs/run-0001/run.json --no-cache`; `-m experiments.v3.review --release local/v3-releases/possession-v3-20261116-a4/release.json --port 8766 --demo`.

## G08 and T10: independent exact-package acceptance and handoff

Fresh tester gets normative specs/publicrequirements/frozenpackage path only,
new scratch and no prior scores/expectedhashes. Extract newZIP, make freshCPython3.13
environment with runtime lock only (existing wheelcache preferred), and inventory
imports. Actual input-toCSV3uncached runs, interleaved same-machine fallback order
A,C,C,A,A,C; allrow/publicboundary checks, officialvalidator+inventedmalformedCSV,
byteidenticalrepeat, measuredactualworker/tree peaks,<=1.20medianruntime and+32MiB
peak plus120s/512MiBabsolute. Cached run diagnostic separately. Syntheticdesktop/
mobile UI generation, seeking, status, stablemetrics, safe error, downloads,bundle,
releaseidentity and fresh re-export. Kill synthetic workers after each scratch/
CSV/report/commit/fsync/rename operation; restart sees no final generation before
rename and the complete same-generation pair afterward. Validate UI/download/export
ignore scratch/invalid commits, pin complete generation, and preserve old ones.
Extracted cached miss/hit must succeed with original study/control tree unavailable;
spies assert zero lookups, targets/study cache domain remain denied. No realvideo/timeline enters model tools.

Root rehashes actualoutputs/source/ZIP and reproduces decisive checks; fixes require
fresh gate onchangedbytes. Completepackage by 17:00Nov 16 to allow repairs/reacceptance
before 20:00freeze. Promotion only on bothG07/G08pass and29unchangedfallbackhashes.
Otherwise retain fallback and evidence-backed rejected/incomplete disposition.


## Revision4 design repair entry state

G01 round1 is CHANGES_REQUIRED, root-reproduced; revised specifications are not
accepted fixes. No tasks above may begin until a NEW fresh integrated G01 passes.
Original15 design files and reviewer reports remain archived unchanged. Scope is
canonical identity/RNG/schema/metrics, flattened-control attribution, fixed shared
scientific API and versioned technical documentation, with strict head/arithmetic
and resource caveats. New tests must derive these contracts independently; no
reviewer's prior fixture results or expected hashes are an acceptance oracle.


Revision4 narrow gate: SCI-01 separates prefit freeze/postfit model seal/pretest
finalist/G08 rehash. SYS-F01 supplies typed standalone observation cache authority;
SYS-F02 restricts results to immutable same-parent generations with one commit.
These repairs remain unaccepted until fresh bounded G01. No scientific numerical,
split, candidate, fit, weight, metric or threshold choice changed. Required source
catalog completion and strict model schema are explicit handoffs, not access grants.
