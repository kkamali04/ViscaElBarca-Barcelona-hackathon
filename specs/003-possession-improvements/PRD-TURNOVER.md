# PRD: turnover-aware possession decoding

Version 1.1 — 2026-11-15. **Revised design only; no v3 implementation, training or performance acceptance exists.** Owner: turnover specialist. Delivery namespace: `experiments/v3/`. This revision addresses the first design review before any new labels: it adds a fixed flattened-support control within the existing eight-challenger budget and tightens serialization, arithmetic and memory requirements. The prior version and its reports remain historical exact-version evidence; this revision requires fresh integrated design acceptance before coding.

## User outcome and measurable hypothesis

Kian should receive a complete possession timeline that can retain short real changes of control without fragmenting same-team passes, duels or missing-ball stretches into false turnovers. He must be able to compare the candidate with the preserved accepted release, see actual quality/resource evidence and return to that release if the candidate fails.

The hypothesis is that a small classifier of **boundary evidence**, separate from frame-level H/A/D evidence, can improve the official possession-spell metric by lowering selected switching costs near real changes. It is not a promise of improved hidden-match performance. The accepted system already has temporal summaries and an exact constant-cost decoder; the new behavior is **observation-dependent transition cost at each edge**.

User success requires all three: a preregistered external quality gain, a deterministic complete officially valid CSV, and bounded CPU/memory in a fresh package. A scientifically rejected boundary model still counts as an implemented experiment, never as a validated improvement.

## Controlling documents and decision traceability

This document owns turnover behavior, features, boundary targets and head parameters. Shared access control, exact corruption operators, broad-emitter recipes, metrics, candidate selection/promotion, packaging and rollout are canonical in [contracts.md](contracts.md), [architecture.md](architecture.md), [protocol.json](protocol.json) and [plan.md](plan.md). The documents must agree at design freeze. A discrepancy blocks implementation until root resolves and refreezes the design; runtime must never choose between conflicting prose.

| Decision | Evidence and reason |
|---|---|
| Reuse the exact three-state DP structure and numeric tree inference pattern in a separate v3 closure | [Local architecture audit](../../research/v3/turnover/RESEARCH.md); current constant penalties cannot express boundary-conditioned switching. Preserve accepted files and exports. |
| Use a small typed boundary head and nonnegative cost reduction | [PathCRF2026 primary paper](https://arxiv.org/html/2602.12080v2) supports dynamic transitions in soccer, while known in-play episodes, identified-player edges and GPU benchmarks prevent direct transfer claims. This design uses existing anonymous aggregates instead. |
| Separate frame evidence and boundary evidence | [ASRF primary paper](https://openaccess.thecvf.com/content/WACV2021/papers/Ishikawa_Alleviating_Over-Segmentation_Errors_by_Detecting_Action_Boundaries_WACV_2021_paper.pdf) supplies generic segmentation precedent; its activity/video scores do not predict soccer gains. |
| Preserve canonical ties; qualify symmetry tests | [CORRECTIONS.md, TR-1](../../research/v3/turnover/CORRECTIONS.md), independently reproduced by root. Canonical H-first ties and unconditional swapped outputs are incompatible. |
| Require literal CSV and organizer scorer behavior | [TR-2/TR-3 and blind audit](../../research/v3/turnover/CORRECTIONS.md); destination-typed transition matching differs from internal boundary types. |
| Defer PELT, HSMM, full neural scene models | [Reuse matrix](../../research/v3/turnover/reuse-matrix.md) and [Peral2026 bounded check](../../research/v3/turnover/CORRECTIONS.md). They add cost/semantics/input requirements without established local benefit. |
| Fixed A4 whole-match allocation and finite experiment | Root's metadata-only decision: train WOH+formerly selected WOY; fresh-select WPY; fresh-test WN1+WQQ; old WR9/WMX closed. No challenge labels or public-window tuning. |
| Compare temporal support placement with a flattened-support control | [First turnover design review, TD-01](../../reports/v3-turnover-design-blind.md): generic penalty relaxation can improve a timeline without informative boundary timing. Replace B050 with F080 before labels, retaining eight challengers and three fits; B080-F080 is selection-only attribution. |

Research/source versions, licenses and limitations remain in the frozen research artifacts. This PRD does not retroactively change their hashes or earlier evidence.

## Scope and exclusions

In scope: one shared small typed boundary head; 28 invariant observation-derived features; a time-varying three-state decoder; numeric export; finite selection-only ablations; independent functional/scientific/resource/package acceptance; truthful experiment disposition and fallback.

Excluded: inferred persistent player identities, image crops/video analysis, ball trajectory reconstruction, new event annotations, new data providers, SkillCorner auxiliary targets, challenge/public-window tuning, human match corrections, learned duration priors, neural backbones, mandatory dead state at turnovers, in-place changes to accepted model/code/config/package, production publication or competition submission.

The model is offline. Its before/after windows use future **observations**; no live causal latency claim is made. No training/scoring label may enter features, geometry masks, period inference or input-to-CSV inference.

## Functional requirements

| ID | Requirement | Acceptance |
|---|---|---|
| TO-F01 | Separate v3 candidate with accepted release untouched | Before/after accepted hashes equal; imports/export closure pinned; original research/evidence preserved. |
| TO-F02 | Edge-conditioned H/A/D objective below, with independent contiguous positive-period runs | Independent exhaustive short-path oracle agrees, including asymmetric costs, forbidden states, initial-state constraints and repeated nonadjacent period IDs. |
| TO-F03 | Exact alpha=0 canonical compatibility on numerically valid inputs | Byte-identical int8 outputs to accepted decoder across independent valid synthetic fixtures. The new decoder additionally rejects finite-arithmetic overflow even where the legacy decoder accepted a surviving alternative. |
| TO-F04 | Observation-only invariant features and unknown-evidence fallback | Feature/mask equality when target arrays change; H/A feature symmetry fixtures; invalid windows yield q=(0,0), never missing-ball D evidence. |
| TO-F05 | Explicit boundary class semantics, exact target derivation and bounded deterministic training | Manifest counts/weights/sample IDs/hashes reproduce; no absent-class invention; three permitted fits total across shared study. |
| TO-F06 | Strict numeric boundary export and fixed feature order | Full training-row batched raw-score parity <=1e-10 plus independent NaN/threshold fixtures; malformed structures rejected before inference. |
| TO-F07 | Exact complete CSV contract | Header frame,label;199319 rows; integer unique ordered0..199318; H/A/D/X only; no blanks; every row checked plus official validator. |
| TO-F08 | Repeatable package and actual process resources | Three fresh-process uncached outputs have equal hashes; fresh minimal export runs input-to-CSV within shared gates. |
| TO-F09 | Clear candidate identity and private observability | Local runner/review/export bind the same release/model/protocol hashes; logs contain safe aggregates/hashes only. |
| TO-F10 | Local rollout only on complete evidence, reversible to accepted release | Explicit promotion receipt after blind acceptance and root reproduction; rejected/inconclusive experiment leaves accepted selector unchanged. |
| TO-F11 | Fixed flattened-support control removes within-valid temporal placement without labels | Independent run/type mean oracle; unchanged input arrays; invalid/start/outside rows zero; F080 and B080 differ only in this support transform. |

## Exact decoding contract

Canonical proposed API:

```python
BoundaryFeatures(values: float32[N,28], names: tuple[str,...], valid: bool[N,2])
build_boundary_features(features: FeatureSet) -> BoundaryFeatures
fit_boundary(...) -> NumericHead             # role-scoped training only
boundary_support(head, bf) -> float32[N,2]    # TEAM_CHANGE, LIVE_DEAD
flatten_support(q: float32[N,2], period_id: int16[N],
                valid: bool[N,2]) -> float32[N,2]
decode_change_aware(scores, period_id, base_costs, q,
                    alpha, initial_state=None) -> int8[N]
```

For each contiguous run r=[a,b) with the same positive integer period_id, choose y_t in {H,A,D} maximizing:

```text
J_r(y) = sum(t=a..b-1) scores[t,y_t]
         - sum(t=a+1..b-1) C_t(y_(t-1),y_t)

C_t(i,i) = 0
C_t(i,j) = base_costs[i,j] * (1 - alpha*q[t,type(i,j)])  for finite i!=j
C_t(i,j) = +infinity                                  if base forbids i->j
type(H,A)=type(A,H)=TEAM_CHANGE
type(H,D)=type(A,D)=type(D,H)=type(D,A)=LIVE_DEAD
```

Edge t means transition **from t-1 into t**, the first new-label frame. There is no incoming edge at run start a, so q[a] does not affect that run. Nonpositive periods output -1; CSV maps -1 to X. Separate runs never exchange state, context, backpointers or duration assumptions. No compulsory D between H and A and no imposed minimum spell length.

`base_costs` is a nonnegative 3x3 matrix with exact zero diagonal; positive infinity is allowed only off diagonal. Campaign costs are inherited exactly from the frozen fallback configuration, with its fps scale; do not retune them. Preserve infinity by branching, not by multiplication. `alpha` must be a finite scalar in[0,1); campaign values are .5 and .8 plus alpha0 comparator. `scores[N,3]` must contain finite real values or -infinity only, including outside-period rows; -infinity forbids that state. `q[N,2]` must be finite in[0,1] everywhere. `period_id` is an aligned integer vector. `initial_state` is None or0/1/2 and applies to the first frame of every active run. Empty arrays are valid when all aligned shapes agree. NaN, positive-infinite scores, malformed shapes/types, impossible active frames and numeric overflow fail explicitly.

Check every allowed candidate evaluation from a reachable finite DP state for finite-arithmetic overflow in both signs: finite running score minus finite cost, then candidate plus finite emission. Reject overflow even when that alternative would lose the maximization or another path survives. Intentional -infinity scores and +infinity forbidden edges are explicit unreachable sentinels, not the result of arithmetic on finite operands. The accepted decoder itself remains unchanged.

Preserve accepted tie behavior: equal primary objectives prefer fewer transitions, then the current-frame change over an older otherwise unidentifiable change, then lower source-state index; final ties prefer fewer transitions then H,A,D. Alpha0 preserves canonical output exactly on numerically valid inputs; stricter rejection of overflowing legacy inputs is required. On unique-optimum fixtures, transform all team-dependent scores/features/cost axes/constraints/initial states and require swapped outputs. On tied fixtures compare optimum values and mapped optimal sets, then test canonical representatives separately. Do not demand that an H-first representative itself swap.

The head is directionless by design; restarting and stopping share LIVE_DEAD support. Their asymmetry remains in frame evidence. Adding further heads or directed costs is outside this study.

## Feature schema and temporal availability

Feature version: `v3-boundary-28-v1`. Accept fps 25 within absolute1e-6; reject other rates before model use. Define k(s)=max(1,floor(s*fps+.5)): s=.2 gives5 and s=.6 gives15. For edge t, before=[t-k,t), after=[t,t+k); both are half-open. Full windows must lie inside the same contiguous positive-period run. Never truncate windows or interpolate across missing observations.

Reuse the frozen observation-derived reliable_ball_mask/teleport policy and accepted noise-v2 ball-speed transform. Geometry-valid at u requires reliable ball observation, finite nearest distances for both teams, finite ball_xy and tracked_counts>=1 for each team. Missing distances stay unknown. Nearest distances must be nonnegative where finite; malformed FeatureSet structure/ranges fail explicitly.

Per-frame bases, evaluated in metres/seconds:

| Name | Definition and bounds |
|---|---|
| min_distance_m | min(nearest_H,nearest_A), clipped[0,30], geometry-valid only |
| abs_margin_m | abs(clip(nearest_A-nearest_H,-10,10)), geometry-valid only |
| ball_speed_mps | accepted noise-v2 speed clipped[0,40], finite and geometry-valid only |
| set_motion_mps | mean of finite anonymous team-motion proxies, clipped[0,12]; NaN if neither finite |
| boundary_distance_m | min(ball_x,pitch_x-ball_x,ball_y,pitch_y-ball_y), clipped[-10,30], geometry-valid only |

Signed margin m_u=clip(nearest_A-nearest_H,-10,10) is an intermediate geometry-valid signal, not an exported feature by itself. Every mean is finite-only and requires at least ceil(.8*k) finite values in that window; otherwise it is NaN. Even if a mean is computable, the whole edge's validity still follows the coverage rule below.

Column order is14 columns for prefix w020, then14 for w060:

1. `<prefix>_pre_` plus the five basis names in table order.
2. `<prefix>_post_` plus the same five names.
3. `<prefix>_margin_product_scaled` = mean(m_before)*mean(m_after)/100.
4. `<prefix>_margin_change_scaled` = abs(mean(m_after)-mean(m_before))/20.
5. `<prefix>_reliable_fraction_pre` and `<prefix>_reliable_fraction_post` = geometry-valid count/k.

The two margin-derived features are NaN if either signed mean lacks its finite minimum. Their values are invariant under H/A swap, as are all other features. The product detects opposite signed proximity advantage without requiring a persistent player identity. It is evidence about geometry, not proof of control.

Both validity columns use the same conservative rule: every one of the four pre/post windows for k5/15 must be full, period-contained and have geometry-valid count>=ceil(.8*k). Otherwise both are false. The permitted full-window edge range is a+15<=t<=b-15 for a run [a,b); every other row has no modulation, including the first run row. Missing motion/speed basis values remain NaN and use numeric-tree missing routing; reliable geometry coverage is still mandatory. Thus long occlusions/reacquisition use baseline costs rather than fabricated boundary timing. This does not guarantee baseline labels inside an invalid window: the optimal path remains globally coupled through other edges in the same run.

Anonymous summaries do not uniquely identify controlled possession. Different unobserved touches/control can produce identical features and different labels. A one-frame sign reversal can be diluted by both the5/15-frame means; the inherited31-observation speed estimator also extends effective raw-observation context beyond the named summary windows. Functional semantic fixtures must state explicit observation/score premises and objective oracles; they cannot require that every trained head resolve every brief touch, rebound, restart or contested ball. Report only aggregate eligible-boundary coverage and positive-event counts, without post hoc feature/threshold tuning.

## Exact target, sampling and head training

Only WOH and previously selected WOY may supply training labels. Boundary training uses the shared **C1 four-condition curriculum**: clean,ball4,combined,stale_players. The exact corruption order, seeds and operators come from protocol.json; the same observation arrays are used by all relevant arms. This is one pooled head, not condition-specific or emitter-specific heads.

Eligible population: every q-valid edge with both adjacent labels known H/A/D and the same positive period. Target is NONE=0 if equal, TEAM_CHANGE=1 for H<->A, LIVE_DEAD=2 for H/A<->D. Unknown truth and run-first edges are excluded. Use exact labels at t-1,t: **no target dilation**, nearest-event repair, event synchronization or ground-truth gap interpolation. Feature windows may include observations whose labels are unknown; those labels are never consulted.

There are 8 fixture-condition strata. Include all positive edges. In each stratum uniformly sample NONE without replacement, n_NONE=min(N_NONE,20*max(1,N_positive)). Seed PCG64 with the first eight SHA256 digest bytes interpreted little-endian from the exact UTF-8 string v3|protocol_sha256|train|IDSSE|fixture_id|condition|0|boundary_none_sampling, substituting the registered protocol digest and canonical fixture/condition identifiers. The protocol also records global seed20261116; no alternate seed encoding is permitted. Selected rows are sorted by original frame index after sampling. No extra sampling seed search is permitted.

Let p_c be each class's prevalence across the **full eligible eight-stratum population before negative sampling**. Positive inclusion probability pi=1; sampled NONE pi=n_NONE/N_NONE. Raw sample weight is1/(pi*sqrt(p_c)); first normalize sampled weights separately in each stratum so each stratum's relative total is1/8; then multiply all actual fit-row weights by one common factor so their final mean is1 (sum equals actual fit-row count). The final step preserves stratum fractions while fixing absolute weight scale for l2_regularization=2. This corrects negative inclusion and moderates class imbalance with a fixed square-root factor. It does not make softmax outputs calibrated event probabilities. Empty eligible strata or a missing class anywhere in the complete pooled class set fail training with safe aggregate counts; do not invent labels or silently remove strata.

No H/A augmentation is required because all 28 inputs and targets are invariant. No additional head fits, random seeds, target neighborhoods or temperature search are allowed.

Fit one HistGradientBoostingClassifier using pinned training dependencies, random_state20261116; max_iter32, max_leaf_nodes7, learning_rate.08, min_samples_leaf80, l2_regularization2, max_bins63, early_stopping=False, categorical_features=None, with sample weights above. No warm start or feature selection. Three-class boosting yields at most 96 numeric trees and 13 nodes per tree. Tree/feature parameters are fixed before selection.

Use stable float64 softmax of exported **raw** three-class logits, temperature 1, then class1/2 probabilities cast to float32 as boundary support q. Invalid edges override both channels to0. Do not use the accepted emitter's clipped log-evidence as boundary logits. Class weighting changes priors; the field is named support and carries no calibration claim.

## Numeric model/export contract

Boundary wrapper format is `numeric-boundary-hgb-v1`; explicit class_names are exactly [NONE,TEAM_CHANGE,LIVE_DEAD] and feature_names are the 28 ordered names above. This is distinct from the accepted numeric-hgb-v1 H/A/D model.

The wrapper binds feature version, fps/window/coverage rules, temperature 1, tree parameters, source/dependency/metric/protocol/split hashes, sampled-population/weight recipe and training-input digests. Numeric payload contains a finite baseline[3] and3..96trees in complete three-class iteration groups0,1,2, with a tree count divisible by3; each tree has **1..13nodes**, class0..2 and arrays value,feature_idx,num_threshold,missing_go_to_left,left,right,is_leaf using the audited numeric-tree pattern. Root is node0; every stored node must be reachable from it; every nonroot node has exactly one internal parent; root has none. Internal children must be distinct and in bounds, with no cycles, shared children or disconnected nodes. Leaf left/right fields are integer0 sentinels and do not create graph edges. Splits reference feature0..27; all field sets, structural types, array lengths and finite thresholds/values are validated. Missing-only infinite sklearn thresholds are converted only through the audited finite-extremum numeric mapping with parity evidence. JSON is strict UTF-8 with finite scientific numbers, never pickle/cloudpickle or executable payloads. Reject duplicate object keys at every nesting level and unexpected schema fields rather than accepting parser-dependent values.

Total boundary JSON, including provenance, must be <=524288bytes. Enforce this bound **before parsing**, with a bounded read of at most524289bytes as well as file/manifest size checks; an oversized or changed/truncated file fails before allocation of its decoded structure. Tree count/node/graph limits are loader requirements, not merely training settings.

Head inference uses **external caller batches of at most4096rows**: call raw_scores on only that slice, perform stable softmax on its at-most4096x3 float64 logits, and write its two float32 support columns directly into the final q buffer. Never call raw_scores once on the full N-row boundary matrix and assume its internal traversal chunks remove its full Nx3 return allocation. Do not concatenate batch logits or normalized three-class arrays. Parity is checked on every selected training row in external batches plus independent synthetic missing-value/threshold probes: maximum absolute raw-score error<=1e-10. Failed parity/schema/size is a failed export, not permission to prune or refit after test.

## Flattened-support control contract

F080 is a fixed no-refit control, using the **same accepted emitter, shared trained head, boundary feature/mask computation, base costs and alpha=.8 as B080**. Only q's within-valid temporal placement changes. Compute full ordinary support first, then call flatten_support; no labels, scorer runs or targets enter this transformation.

Require q exactly float32[N,2], period_id exactly int16[N] and valid exactly bool[N,2], with aligned shapes. Validate every q value as finite in[0,1] before any masking, including invalid/start/outside rows; malformed input fails rather than being repaired. Inputs are read-only and unmodified. Empty aligned arrays are accepted and return an empty float32[N,2] array.

For every contiguous positive-period run r=[a,b) and type c, let E_rc={t:a<t<b and valid[t,c]}. Gather eligible indices in ascending frame order. If E_rc is nonempty, compute exactly numpy.mean(q[E_rc,c],dtype=numpy.float64) under the pinned NumPy version, cast that single result once with numpy.float32, and assign it to every edge in E_rc. Ascending order defines the gathered input, not a different hand-written serial reduction. All other output entries are exactly0: invalid edges, a, nonpositive periods and any empty type/run. Do not merge separated runs sharing the same period number, average across types, include a start edge, change the validity mask or modify feature windows. Check the mean/cast for finite in-range output. A first run/type with no eligible edges contributes nothing to any other run/type.

This preserves each valid-mask support level as a float32-rounded per-run/type mean, while removing learned within-valid placement. Validity-mask timing and run-level support remain informative; F080 is not a label-free oracle or a pure constant-penalty model. The whole-period mean uses future observations, consistent with offline use. B080-F080 on selection tests the contribution of within-valid support placement conditional on the same mask/mean mechanism; it does not establish causal possession recognition or generalization. F080 is eligible for normal selection and promotion. If it wins, report a flattened-support/global-relaxation result and do not credit learned boundary timing.

## Finite study and attribution

Shared A4 allocation is fixed before new labels: WOH+WOY training; WPY selection; WN1+WQQ one fresh-test cohort; WR9/WMX permanently closed. WOY's prior selection history remains recorded. SkillCorner is deferred. All halves, corruptions and caches inherit fixture roles.

| ID | Emitter | Decoder |
|---|---|---|
| A | accepted frozen emitter | accepted constant costs |
| F080 | same accepted emitter | shared head flattened per run/type over eligible incoming edges,alpha.8 |
| B080 | same accepted emitter | ordinary shared boundary head,alpha.8 |
| C0 | broader WOH+WOY emitter,old four-condition curriculum | constant costs |
| C1 | broader WOH+WOY emitter,new four-condition curriculum | constant costs |
| D0050,D0080 | same C0 emitter | same shared head,alpha.5/.8 |
| D1050,D1080 | same C1 emitter | same shared head,alpha.5/.8 |

Exactly 8 nonbaseline configurations, 3 fits total: C0 emitter,C1 emitter,one shared head; one seed 20261116; fixed temperature 1. No undeclared head,alpha,training or selection attempts. C0 old curriculum=clean,ball4,ball12,combined; C1 new curriculum=clean,ball4,combined,stale_players. C1-C0 evaluates that curriculum replacement, not the isolated causal effect of stale-player augmentation.

Evaluate every selection arm on the same ordered six conditions: clean,ball4,ball12,combined,stale_players,view_gap. B080-A compares the complete modulator with the frozen emitter; it cannot alone attribute a gain to learned temporal placement because generic penalty relaxation can change spells. B080-F080 is the predeclared selection-only placement comparison. D0-C0 and D1-C1 test the same ordinary head with each broad emitter. C0-A bundles increased training/data; C1-C0 compares curricula. No discarded arm or placement control is additionally evaluated on fresh tests to explain a failed finalist. The single winner, which may be F080, and fallback A enter the single fresh-test cohort.

## Scientific acceptance

The exact official pinned scorer is authoritative. Mean spell F1 uses maximal same-team H/A spells, excludes D, uses organizer one-to-one matching and averages IoUs .3/.4/.5/.6/.7. Typed transition diagnostics use default destination label and inclusive12/25frame tolerances. Predicted X is a frame miss on graded frames; temporal fill is per scorer GT-valid run, forward then leading backfill, all-X unchanged. GT-valid run information remains evaluator-only; do not add censoring beyond canonical public-score/period rules.

For each match, primary=equal mean spellF1 across all six conditions. Promotion requires paired mean primary gain>=.04 over two fresh games and each game's primary delta>=0. Simultaneous vetoes: mean clean spell delta>=-.005; each game's clean delta>=-.01; mean frame F1 delta for each H,A,D>=-.01; each corruption/clean condition's mean primary delta>=-.01. Use fixed comparison tolerance1e-12. These are empirical engineering gates, not statistical significance.

WPY selection eligibility applies the same numerical gates with one match, without treating it as two independent games. Among eligible candidates choose descending round12(primary), then descending round12(macroF1), then ascending candidate ID. If none is eligible, record selection rejection and do not consume fresh tests. The shared protocol owns the exact executable rounding, absent-class handling and aggregation denominators.

Report full per-match/per-condition paired aggregates and complete fixed denominators; frames, conditions and corruption seeds do not increase N. Two new provider matches and repeated clubs cannot establish a positive 95% population gain or challenge performance. A missing condition, integrity/access failure or unmeasured mandatory gate is inconclusive/fail under protocol, never an omitted row.

## Functional, resource and safe-failure acceptance

A fresh blind tester receives public requirements/frozen candidate, not prior pass/fail assertions. It independently enumerates short 3^N paths and checks the dynamic objective, forbidden states/infinite edges, initial states, edge indexing, alpha0 canonical compatibility on numerically valid inputs, unique-optimum swaps and tied optimal sets/canonical policies. Test positive and negative overflow from finite operands, including unused losing alternatives and a valid surviving path; do not conflate overflow with intentional -infinity constraints. Semantic fixtures cover one-frame/short H-A-H spells, same-team pass motion, contested loose balls, stationary live control, D restarts, disappearance without stoppage, teleports, dropouts, reacquisition, all-missing data and adversarial oscillating q **under independently declared input/score premises**, not an assumed trained-model semantic guarantee. Independent target/feature/weight fixtures verify exact half-open windows,5/15rounding,80%coverage, fullwindow boundaries, absent-class failure, inclusion weights and schema order.

Flattened-control acceptance uses independently invented q, masks and period arrays: exact per-run/type means with partial validity and different type masks; empty eligibility; empty/single-row/short runs; nonpositive rows; separated runs with the same ID; nonzero input q at start/invalid/outside rows excluded from means; dtype/shape/range/NaN/infinity failures even outside eligibility; nonmutation and deterministic repeated results. Check full-window validity endpoints a+15 and b-15 separately before flattening, and show flattening does not make invalid boundary windows eligible. H/A relabeling leaves invariant head features/q/types/masks and therefore flattened support unchanged; combine it with transformed scores/costs/constraints for unique-optimum output symmetry and separate tied-set/canonical tests. A constant ordinary q over an eligible set must equal flattened q on that set; independently verify the float64 mean then single float32 cast rather than copying the implementation helper.

Independent loader fixtures include exactly13 versus14nodes,96 versus97trees, an unreachable stored node, shared child, cycle, duplicate keys at multiple nesting levels, invalid class/feature order, cap versus cap+1 bytes and a truncated file. A head spy/resource probe verifies every raw_scores call has<=4096rows and no full Nx3 logits are retained.

Resource gates apply to the **actual complete fresh-package worker**, not DP arithmetic or a sampler that misses descendants. Three uncached runs must have median<=1.20x same-machine frozen fallback median and <=120seconds. Worker OS peak must be<=fallback peak+32MiB and <=512MiB. Use identical input/thread/cache regimes and record every run. Cached timings are separate. The shared protocol defines interleaving, process identity, peak definition, machine/load evidence and training/storage budgets. The code-only ZIP must be<=20 MiB and each member <50 MB, in addition to the<=524288byte head cap.

Decoder work remains O(9N); pointers use 3N uint8. At199319frames, the full float32 boundary matrix is22,323,728bytes and q is1,594,552bytes: about22.8MiB together. A nonmutating flattened control additionally needs an8N-byte output unless a separately reviewed buffer-lifetime composition avoids overlap; do not assume that saving from an in-place mutation allowed by neither API. These exclude upstream arrays, means/masks, robust-speed copies, tree traversal, frame evidence, pointers, validation and interpreter overhead. Release emitter temporaries and ordinary support when their lifetimes end; use external head batches and per-edge costs without Nx3x3 storage. The +32MiB gate is tight, and neither these arithmetic bounds nor batching proves120seconds/512MiB or relative compliance. Measure the complete worker for the actual finalist, including F080 if selected; a measured budget failure rejects promotion even when asymptotic bounds are satisfied.

| ID | Failure requirement |
|---|---|
| TO-E01 | Malformed q/scores/periods/costs/fps/head/model names or impossible paths raise a safe error, without a partial final CSV or overwritten valid output. Invalid observations represented by masks use baseline modulation; malformed parameters are never silently coerced to that fallback. |
| TO-E02 | Missing/mismatched head, source, model, manifest, split, metric or checksum fails the requested candidate. Never report fallback output under a candidate identity. |
| TO-E03 | An absent target class, empty fit stratum, failed numeric parity/size, exceeded fit/selection budget or nonfinite weights fails the experiment stage and preserves history. |
| TO-E04 | A consumed/incomplete test attempt is not reset. Any allowed pre-access infrastructure recovery follows the frozen shared protocol, with independent evidence; no post-result reruns or tuning. |
| TO-E05 | Input/output/report/model alias, path escape, corrupt cache/archive, missing dependency, disk/resource exhaustion and interrupted writes preserve existing originals/final outputs and emit redacted aggregate failure receipts. |
| TO-E06 | Full package failure or scientific/resource rejection prevents local promotion. Accepted rollback package/config/model remain byte-identical and runnable. |

Actual E2E means a fresh exported package/environment, local authorized input-to-CSV, independent every-row and period contract, official validator, repeated identical outputs, actual runtime/peak memory and a tested safe failure. Unit tests/process success do not substitute. Browser/review checks use synthetic fixtures exclusively for agents.

## Privacy, provenance and rollout

Private records, predictions, boundary arrays, actual timelines, screenshots and labels remain local and never enter model tools/research services. Model-visible logs may contain only aggregate counts/metrics/resources, identities permitted by public metadata, hashes and redacted errors. Feature/label caches remain separate and role-bound. Numeric export is allowlisted, excludes data/secrets/predictions, preserves license notices and binds complete import/source closure.

No new upstream implementation is copied for this small decoder. PathCRF MPL2.0 is conceptual precedent; ASRF MIT and DataBallPy MIT supply design/feature precedent with attribution if later copied. ruptures BSD2 is optional diagnostic only; archived GPLv3/C++hsmmlearn is deferred. No pretrained weights or unverified Peral code/license is assumed usable.

Rollout sequence: fresh design critique -> root-approved frozen protocol -> isolated implementation -> fresh blind functional acceptance/root reproduction -> bounded training/selection -> one frozen finalist/fresh-test verdict -> actual export/minimal-environment/resource/UI gates -> root-verified exact-version promotion receipt -> explicit local selector update. A failure records implemented/not-promoted or inconclusive status and leaves the accepted release selected. Rollback selects the preserved accepted release; it never reconstructs a different model under the accepted identity.

Completion of this PRD means a reviewable design exists. Completion of the turnover experiment requires durable code, exact artifacts, independent evidence and a truthful disposition, including an accurately reported failed hypothesis.

