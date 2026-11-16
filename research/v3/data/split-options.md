# Proposed data splits and reproducibility contract

Date: 2026-11-15. **All options are metadata-only proposals, not frozen protocols or authorization to download labels.** Independent review must choose exactly one plan before ingestion. See [catalog](dataset-catalog.json), [research](RESEARCH.md) and [sources](sources.json).

## Option A — coverage-focused bounded exact-target study

| Role | Genuine IDs | Interpretation |
| --- | --- | --- |
| Train | J03WOH, J03WOY, J03WPY | Three distinct games; WOY was old selection and is explicitly retired from validation. One new train game, plus role reassignment. |
| Selection | J03WQQ | One new selection match, same Fortuna home team/stadium as train; not domain-independent. |
| Final test | J03WN1 | One unused Bundesliga-1 game, different teams/stadium; still Sportec provider. |
| Permanently closed legacy tests | J03WR9, J03WMX | Never reopened/reused for tuning, diagnostics, row sampling or new claims. |

This satisfies genuine multi-match training but does not meet a desired >=6-match final test. Do not claim robust population inference from a single game. No confidence interval by pretending frames, spells or corruption variants are independent matches. Freeze the baseline and one candidate family; select with the one declared objective, then one sealed final-test attempt. Test failure preserves the fallback and ends this campaign version.

Option A2, if preserving old selection is important: train J03WOH+J03WPY; select J03WOY (reused) + J03WQQ (fresh), with equal match weights; final test J03WN1. This is two genuine training games. Reused WOY cannot count as fresh evidence. **Do not run A and A2 and choose retrospectively.**

**Option A3 — two fresh tests with one newly acquired training game**: train J03WOH+J03WPY; retain J03WOY as explicitly reused selection; final tests J03WN1+J03WQQ. This has two genuine training matches, two unopened final tests and no fresh selection match. Repeated selection use risks overfitting research decisions even if the new code has not run there.

**Option A4 — preferred balance if two fresh tests are the priority**: train J03WOH+J03WOY; fresh selection J03WPY; final tests J03WN1+J03WQQ. Training expands from one to two distinct games by moving former selection WOY into train. Its old results remain historical only; fresh WPY is the only new selection source. Two test games allow reporting two paired match effects, but too few for stable population uncertainty. WQQ repeats Fortuna's home team/stadium, WN1 changes teams/stadium/division. This is not a large diverse test. The independent reviewer/root must choose **one of A/A2/A3/A4** before labels; none is silently the accepted protocol.

Three unused tracking files total 1,119,630,725 bytes. Small metadata files were retrieved; no tracking/event content was retrieved. New raw data remain ignored locally with originals preserved; never stage >100 MB files. Compare downloaded hashes against the exact pinned HF LFS SHA256 and Figshare v1 MD5 values in the catalog before parsing.

## Option B — larger, conditional auxiliary source experiment

SkillCorner commit `4340d274572876239c154c90bc507a9b3250a656`, 20 manifest IDs. Exclude 1953632 because manifest status is inconsistent, with no replacement selected from observed results. The following **predeclared chronological split** uses only dates/IDs/status and gives 10 train, 3 selection and 6 fresh auxiliary-provider tests:

- Train: 1874553,1886347,1899585,1925299,1927964,1959846,1986691,1996435,1996436,2006229.
- Selection: 2006363,2007448,2007721.
- Test: 2010085,2011166,2013725,2015213,2016236,2017461.

All are A-League 2024/25. Repeated teams are allowed but reported; these are match-independent temporal partitions, not team-disjoint partitions. One mirrored copy or API representation is still one game. All 20 advertised position files total 1,823,448,331 bytes; the 19 split files total 1,733,420,366 bytes. No raw content was fetched, so complete two-period coverage, labels and status have **not** been audited. Body-pose files (GB-scale) and video are excluded.

This plan cannot become six exact-control H/A/D tests just because kloppy exposes ball_state. Before downloading any of these files, independent reviewers must approve the MIT repository notice, confidence/unknown mask, definition of team ownership between touches, referee dead-ball source and native10Hz contract. If exact semantics remain unavailable, freeze B as **auxiliary home/away provider-label learning only**, no D labels inferred from missing ownership. Keep unknown rows masked; learn the D head only from approved Sportec control/state data or omit this auxiliary model. Final metrics remain source-specific. A six-match auxiliary score estimates agreement with SkillCorner labels, not independent human control accuracy or competition quality.

Do not execute B first, inspect its tests, then repartition for A or a merged model. Freeze the cross-provider training/selection rules and whether six auxiliary tests plus one IDSSE test are opened together only after all model choices are fixed. No source may receive feature/decoder changes informed by its final test. A merged-source model needs explicit provider weighting; no use of provider ID/team/date as predictive features. If the semantic gate fails, execute only A if independently approved; otherwise preserve fallback with no fresh quality claim.

## Before labels: immutable manifests and attempt ledger

Freeze protocol digest, catalog digest, source revisions/licenses, allowed-file exact names+hashes+bytes, match roles, parser and feature versions, normalized target/unknown maps, native FPS/period mapping, corruption parameters+order, RNG algorithm and seed derivation, row budget/weighting, hyperparameter and decoder budget, metric definitions, margins, runtime/memory limits and one-attempt test rule. Every attempt gets a write-once marker created **before** reading test data; record failed/crashed attempts too. Resolve resume semantics before execution (same frozen bytes, no reselection).

Split selection and later exclusions must be based on metadata/schema/integrity failures, never label proportions, scores, observed errors or model success. Any label-dependent quality screen is training-only and predeclared. If a frozen test file is missing/corrupt, report reduced evidence; do not search for a replacement after outcomes. First compare permitted metadata to restricted challenge match identity through manager-local code; block duplicates without displaying challenge records.

## Reproducible corruption and row budget proposal

Proposed master seed `20261115`; use SHA256 of UTF-8 `v3|protocol_sha256|role|provider|match_id|condition|replicate|stream` and the first8 digest bytes interpreted little-endian as a NumPy PCG64 seed. Record exact NumPy/Python versions and masks' hashes. Separate streams for ball gaps/player dropout/jitter/drift/teleports/identity corruption/row sampling. This is a new proposal, not a claim that existing v2 seeds use this rule. Never use Python's randomized hash(). Independent fixtures must use independently chosen seeds/oracles.

Suggested CPU budget: keep native-rate whole-match sequences on disk; extract temporal features at every frame, then select a deterministic 5Hz-equivalent training grid (25Hz stride5;10Hz stride2) plus a single train-only label-transition stratum in fixed +/-1s windows. Transition strata are allowed only for row sampling/loss and are forbidden from feature construction/corruption or evaluation availability. If this extra stratum is too complex to audit, omit it before freeze. Cap each genuine match at30,000 distinct sampled rows before corruptions; cap total fit at750,000 augmented rows and record actual distinct matches/rows separately. These are proposed caps, not observed counts.

Predeclare one small mixture (for example clean + missing-ball + combined existing + one structured view/identity condition) and use one condition per sampled base row via label-independent RNG if needed for memory. Do not materialize every game's every condition. Side-swap augmentation doubles rows but not evidence; preserve equal total weight per genuine match, split weights over augmentations, then apply train-only class weights. Fix sklearn threads<=8, early_stopping=False unless an approved whole-match internal split exists. No random frame validation or default library frame-wise early stopping.

Training diagnostics may stratify by half, side, class, ball missingness, visible player counts and geometry, using only train rows to set bins. Frozen evaluation reports the same bins, class masks and all native known-label frames, including dead play. Do not select a subset of easy spells or remove hard missed transitions. Resource proposals: <=12GiB OS process-tree peak RSS, <=10GiB added disk, one match raw parse in flight, no paid compute. Measure; do not infer resource compliance from file sizes.

## Required isolation and scientific acceptance fixtures

1. Invent two-period asymmetric pitches/rosters, frame gaps, substitutions, unknown targets and duplicated indices. Derive mappings/time rules from public schemas. Assert centered-metres shift, H/A membership and no cross-period interpolation; officials cannot become team players.
2. Replace/delete/permutate **every** label/status/event/score/possession-derived column with adversarial values while coordinates+rosters+timestamps stay fixed. Features, corruption masks, evaluation frame manifest and predictions must remain identical. Only targets/training row weights may change. Include possession-dependent orientation and SDK only_alive filters as explicit negative tests.
3. Verify corrupted coordinates do not change targets; freeze original immutable coordinate hashes. Reordering parser batches/chunk sizes produces identical features/masks. Fixed seed repeats byte-identical; different seed alters masks; whole-match role overlap/mirror duplication/legacy-test access is rejected before reads.
4. Geometry-invariant within-team slot permutations must preserve aggregate team proximity features. Wrong-team membership corruption is a separate stress; do not accept noninvariance to a within-team permutation as realistic necessity. Persistent stale coordinates, clustered missingness and correlated drift each have independent analytical fixtures; NaN/unknown stays unknown.
5. Selection and final testing process complete match sequences, identical baseline/candidate inputs and corruptions; report paired per-match clean/stress deltas, class/spell/transition/dead metrics, known-target coverage and provider-label limitations. Infer match-level uncertainty only where several independent matches genuinely exist. Freeze before final tests and stop on test inspection.
6. Root must inspect actual independent outputs, reproduce failures and run exact fresh package/process input-to-CSV, deterministic-repeat, frame contract, official validator, runtime/OS peak-memory and safe-failure checks. Synthetic or parser success alone does not promote a model.

The independent critic may change these proposals **before labels**. After freeze, material changes require a versioned new protocol, unused test evidence, fresh blind acceptance and preservation of earlier reports. If unused direct-label matches are exhausted, the honest alternative is a frozen diagnostic/engineering improvement with explicit limited evidence, or acquisition of a newly licensed distinct corpus; never recycle closed tests.
