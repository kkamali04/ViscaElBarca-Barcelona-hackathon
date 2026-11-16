# Canonical campaign requirements

Revision4,2026-11-15. **Design awaiting independent acceptance; no implementation.**
Numeric oracle: protocol.json. Typed oracle: contracts.md. Both PRDs must agree.

## User outcomes

1. The owner can compare an independently tested candidate with a preserved
   working fallback and see exactly what was implemented, tested and unresolved.
2. The researcher can attribute a result to the decoder, broader training or their
   combination without challenge tuning, test leakage or unlogged repeated tries.
3. A fresh operator can export and run the exact accepted version to a complete,
   valid CSV with bounded local runtime/memory and safe failures.

## Required constraints

| ID | Requirement | Decisive evidence |
|---|---|---|
| R-01 | Preserve accepted runtime/model/config/ZIP and all original assets | Before/after hashes; separate experiment/release paths |
| R-02 | No challenge GT/public-window tuning or restricted-content exposure to tools/models/services | Allowed-input manifest, local evaluator, aggregate-only logs; synthetic browser inputs |
| R-03 | Catalog license, provenance, FPS, target semantics, club/fixture identities and duplicate sources before split | Source-grounded catalog + independent critique |
| R-04 | Assign complete matches before labels; group duplicate halves/providers/derived copies into one fixture | Canonical fixture IDs, raw digests and explicit disjointness check |
| R-05 | J03WR9/J03WMX stay closed; J03WOH/J03WOY are previously accessed development data, never fresh tests | Permanent accessed-fixture registry checked at reservation and load |
| R-06 | Freeze protocol, executable source closure, metrics, corruptions, data/split, comparator, environment and finalist before test | Immutable manifest; independent tamper tests for every binding |
| R-07 | Reserve study test access atomically before any label-bearing parser/study-cache opens | Concurrent and interrupted synthetic access tests; append-only attempt history |
| R-08 | Candidate grids, seeds, stopping rules and selection tie-breaks precede training | Frozen candidate manifest; exhaustive attempt ledger; no undeclared trials |
| R-09 | Comparison uses identical observation corruptions for candidate/fallback; targets never corrupted | Paired-input fingerprints; metamorphic label-invariance fixtures |
| R-10 | New decoder resets each contiguous positive period and respects hard state constraints | Independent short-sequence exhaustive oracle and long-sequence resource checks |
| R-11 | Every material implementation gets fresh blind acceptance | Freeze receipt + reviewer evidence + root reproduction |
| R-12 | Package has exact source/model dependencies and no private data, predictions or secret material | Allowlist, member hashes, import-closure check, fresh environment run |
| R-13 | Exact public CSV contract and official validation remain mandatory | All-row independent check, official validator with independent valid/invalid fixtures |
| R-14 | Repeated fresh-process inference is deterministic; malformed inputs preserve existing outputs | Three output digests; sentinel/collision/failure checks |
| R-15 | Resources measure the actual worker and complete pipeline | OS process identity, worker high-water RSS/working set, wall time and child-process accounting |
| R-16 | Local review UI/export uses the selected release consistently; synthetic UI only for agents | Version receipt in runner/UI/export, fresh synthetic browser test and package re-export |
| R-17 | No promotion without all scientific, functional and resource gates | Explicit promotion receipt bound to exact candidate and acceptance reports |
| R-18 | Failed/inconclusive improvement leaves accepted fallback unchanged and accurately labeled | No active-pointer change; durable rejected/inconclusive disposition |

## Fixed acceptance and scope

Q-01: A4 fixed roles, threefits, eightchallengers and sixevaluationconditions are
exact in protocol.json. Both requested ideas must be implemented/studied, not
replaced by documentation alone. Failed/incomplete gates are accurately recorded.
The two training curricula differ by ball12 versus stale_players; Bernoulli gap
masks are a v3 design, not byte-for-byte replay of v2's exact-quota masks.

Q-02: Select only eligible candidates onWPY by descending primary mean rounded12,
then macroF1rounded12, then ascendingcandidateID. Primary metric is official pooled H/A
spell_f1_mean (spell_scores mean_f1) over IoU.3/.4/.5/.6/.7; whole-match conditionmeans get equalweight. One
finalist only on WN1/WQQ. No candidate qualifies means no fresh-test reservation.

Q-03: Both selection and final empirical gates use mean paired spellgain>=.04,
eachmatchprimarydelta>=0,mean clean>=-.005,eachmatchclean>=-.01,mean perclassH/A/D
frameF1delta>=-.01,eachconditionmeanprimarydelta>=-.01; comparisonsallow1e-12numeric
slack only. No threshold change afterlabels. All six conditions and bothtestmatches
must complete. State that .04 is an engineering policy informed by organizer
commentary, not a provider-transferable significance theorem. N2 whole-match deltas,
range and dependencylimits are reported; no frame/bootstrap significance claim.

Q-04: Exactly two emitterfits and oneboundaryfit, one fixedrandomstate20261116,
no seedsearch. Relative match/condition/class/inclusion weights finish at global
mean1 with actualfitrowcount; HGB L2=2 is bound to that absolute scale. Dense
features precede rowsampling. No fit/external-framevalidation earlystopping.

Q-05: One heavyworker<=4numericthreads;12GiBprocesstree peak;8haggregatefit;
10GiBaddedcampaign disk target includes neworiginals andscratch; preservealloriginals;
abort before40GiBfree. Exact start/end cutoffs inprotocol, finalfreezeNov 16 20:00NY.
No skipped gate may be called passed to meetdeadline.

Q-06: Freshrelease median3uncached walltimes<=1.20xfallback and<=120s; maximumactual
workerOSpeak<=fallbackmaximum+32MiB and<=512MiB. Use same input/environment/threads,
orderA,C,C,A,A,C,uniqueemptycache peruncachedrun. Reportallruns,actualworkeridentity,
concurrenttree sampling andcachedmeasurements separately. ZIP<=20MiB,head<=512KiB.

Q-07: ExactCSV frame,label,199319 rows0..199318,H/A/D/X; publicperiod/deadcontract;
algorithmic reproducibility; all-row checker plusactual official validator; freshminimal
runtime environment;3identicaloutputs; safe malformed/collision/missingmodel failures;
synthetic desktop/mobile UI andversioned exports. Challenge records/videos/timelines/
GT remain model-invisible. No scientific metric claim from syntheticUI or E2E.

## Requirement/task/test traceability

| Requirements | Implementing tasks | Independent gates | Specific oracle families |
|---|---|---|---|
| R01,R06,R07,R08,R11 | T02,T05 | G02,G05 | hash mutation,stale/cross-study reservation,crash/PID/capability denial |
| R02,R03,R04,R05,R09 | T03 | G03 | label invariance,fixture grouping,early-parser spy,cache member tamper,geometry-only masks |
| R10,TO-F02..06 | T04,T05 | G04,G05 | exhaustive paths,canonical ties,unique-optimum symmetry,28feature windows,numeric export |
| Q01..04,MM-A01..08 | T03,T05,T06,T07,T08 | G03,G05,G06,G07 | role/row/weight/grid counts,official full timeline metrics,paired gate arithmetic |
| R12,R13,R14,R16,Q07 | T09 | G08 | fresh exact ZIP/env,allCSVrows,official invalidfixtures,atomic sentinel preservation,syntheticUI |
| R15,Q05,Q06 | T05,T09 | G05,G08 | recursive OSworker/tree identity,budget stop,allrun resource receipts |
| R17,R18,TO-F10 | T10 | G07,G08 + root | exactreceipt/fallback 29hashes; fail/incomplete candidateunpromoted |

All new tests named in plan.md use invented inputs. Reviewerchecklist is separate
from implementationtracker; boxes there mean requirementsquality, not codecomplete.


Q-08: Canonical slots, exact observed timestamp members/origins, derived masks,
target lexical mapping and complete cache read leases follow contracts.md.
Raw roster/XML permutations must normalize identically; reject noncanonical direct
batches before RNG. Exact Generator calls/shapes/traversal/arithmetic/casts/chunk
semantics and integer-only cap rows follow protocol.corruption_semantics. A fixed
protocol RNG root and independently verified source integrity coexist; authorized
target-only synthetic variants must not alter observation corruption.

Q-09: F080 replaces B050; no grid expansion. Normal selection eligibility applies.
Flattened support is exact ascending-eligible np.mean(dtype=float64) then float32
per run/type; B080-F080 selection-only attribution tests temporal placement.
Transition diagnostics isolate known-run matching then sum TP/FP/FN; pooled official
H/A spell primary is unchanged. core.predict_codes is frozen scientific code used
by both evaluator/release. T09 supplies versioned technical/reproduction documents.

| Additional traceability | Tasks | Gates | Independent oracle |
|---|---|---|---|
| Q08 / MM R1,R2,R4 / XDB01,02 | T03 | G03 | raw permutation, exact interior RNG/row IDs, sparse timestamps, post-check cache replacement |
| Q09 / MM R3 | T05 | G05 | pooled-vs-macro asymmetry, short unknown gap/adjacent-half transition counts |
| Q09 / TD01 | T04,T05 | G04,G05 | per-run/type flattened mean, same frozen model/alpha, selection registry |
| Q09 / XDB-N01,N02 | T05,T09 | G05,G08 | direct core/runner equality and versioned reproduction doc completeness |


Q-10 (SCI-01): Prefit immutable registration binds existing source/config/policy/
environment/comparator bytes. New C0/C1/head seal follows fitting and precedes ANY
selection reservation/access; finalist/comparator seal precedes test; G08 rehashes
all stages. Never placeholder/hash nonexistent models or amend original study.

Q-11 (SYS-F01): Standalone observation-only release caching uses typed ReleaseAccess/
InferenceContext with verified release/source hashes and zero original study/ledger
dependency. CacheAuthority dispatch rejects targets/study caches under release
credentials; closed/wrong study capabilities still fail. Shared code freezes prefit.

Q-12 (SYS-F02): CSV and report names share one absent new generation parent, with
commit.json reserved. Publish all three by one no-replace atomic directory rename;
reject different/existing parents/aliases before input. UI/download/export expose
only committed verified same-generation pairs, never scratch. Hard-kill probes at
every publication boundary preserve previous complete generations; no recovery by
guessing or overwriting. This intentionally restricts arbitrary output paths.

| Additional requirements | Tasks | Gates | Oracle |
|---|---|---|---|
| Q10 | T02,T05,T06,T07 | G02,G05,G06,G08 | nonexistent model prefit valid; missing/changed postfit seal denies selection; immutable study |
| Q11 | T03,T09 | G03,G08 | extracted cached miss/hit without study/control; lookup spies; cross-domain/target denial |
| Q12 | T09 | G08 | kill before/after each stage/rename; same-generation reader and prior-byte preservation |
