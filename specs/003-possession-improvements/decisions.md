# Design decisions revision4

2026-11-15. Research-backed choices awaitingG01; no implementation acceptance.
Original proposals archived; final numeric oracle protocol.json.

| ID | Chosen decision and reason | Alternative/why deferred | Requirement/test impact |
|---|---|---|---|
| D01 | Isolated experiments/v3 plus explicitrelease, preservefallback 29 | Inplaceaccepted edits invalidateold evidence | R01; every gate rehashesprotectedfiles |
| D02 | A4 WOH+retiredWOYtrain/WPYselect/WN1+WQQtest | A3 addsnewtraining butreusesknownselection; threefresh testswouldnotexpandtraining | R04/05; noold test reuse, two fresh games only |
| D03 | Two4-viewcurricula C0/C1, oneheadC1, eightchallengers | Fiveviewoneemitter cheaper butcurriculum attributionbundled; largergrid unbounded | Exact3fits,seed20261116; C1-C0replacementclaimonly |
| D04 | Staleplayer2s trainingcorruption;viewgap evaluationstress | AR1drift,identityswaps,SkillCornertraining addsemantic/computecomplexity | Exactoriginalanchor/NaN reset; noclaimrealismcalibrated |
| D05 | Immutablepriorsnapshot plusglobalOS-lockedliveledger | Snapshot-only missesnewconsumption; freezinglivehashblocksownwrites | WBR02; stale/crossstudy/postreservation/restarttests |
| D06 | Capabilitybeforeearliestparser andcachehits; everymemberverified | Legacysportec cache acceptsmanifestalone andparseslabelsinearlyprep | WBR03; spies/missingmember/atomicwritefixtures |
| D07 | Exactofficial full timelineGTvalidruns, noadditionalcensoring | Droppingunknownrows/periodcutsmergesspells; customcensoringchangesmetric | Native25Hzonly, +/-12/25destinationtyping,unknownXfixtures |
| D08 | Canonicaltiepolicy preserved; symmetryonlychosenoutputuniqueness | UnconditionalH/Aswap contradictsHfirsttie | TO-F03/04; optimalset symmetry+canonicalfixtures |
| D09 | Finalglobalmean1sampleweights afterrelativebalancing | Sum1 rescalesHGBL2/Hessianbehavior | FixedL2=2; independentlyderiveweightscaleoracle |
| D10 | Empiricalmean+.04gate withclean/classvetoes; N2limitations | Sixfresh exactmatches unavailable; narrowframeCIinvalid | No population/hiddenperformanceclaim; allmatchdeltasreported |
| D11 | 4threads,12GiBtree,8hfit,10GiBaddeddisk;1.20x/+32MiBinference | Priorlanebudgets16GiB/60GiB/8threads superseded | WBR05; singleprotocol andactualOSmeasurements |
| D12 | Manualsource-guided6.1.1workflow; newsource receipts | Globalupgrade/generator/hostedtracking addsunneededwork | WBR04; paths/hashes,unknownadvisingprovenance explicit |

Root selected A4 before labels. Source-grounded reasons and alternatives come
from research/v3/{data,turnover,workflow}/ plus the reviewed CORRECTIONS.md.
Current design adds no empirical gain claim. Nov 16 deadline doesnotwaive gates;
unpromoted or incomplete challenger leavesworkingfallback usable.


## Revision4 bounded pre-label repair decisions

- D13: Canonical physical slot identity precedes RNG. Exact full logical Generator
  arrays and final float32 cast make stochastic fixtures portable across chunks;
  arbitrary noncanonical index permutation is rejected, not falsely invariant.
- D14: Preserve exact original source UTC-ns values in sparse private arrays plus
  a deterministic period origin. Origin-only reconstruction was rejected because
  it discards permitted sub-millisecond source deviations.
- D15: Use official pooled spell mean_f1 unchanged; transition diagnostics require
  a run-isolated wrapper with pooled counts. Full-helper cross-run matching and
  team/run macro averaging do not meet the declared temporal contract.
- D16: Replace B050 with F080, same B080 models and alpha, valid-run/type mean support.
  Eight challengers/three fits remain; selection-only timing-placement attribution
  distinguishes learned timing from support-level penalty relaxation.
- D17: Fixed protocol digest is RNG root, source/catalog digests separate immutable
  study bindings. Authorized target-only synthetic variants share random namespace
  while independently verifying different source bytes; unauthorized mutation fails.
- D18: Freeze shared scientific core.predict_codes before fits; wrappers only adapt
  transport/output. T09 owns versioned technical explanation/reproduction docs;
  historical fallback documents stay untouched.

These decisions respond to root-reproduced design findings; they do not constitute
implementation, evidence of gain, or acceptance. A new integrated G01 is required.


- D19 (SCI-01): Do not hash future model bytes before fit. Immutable original study
  plus separate postfit model seal, then finalist seal, preserves temporal provenance.
- D20 (SYS-F01): Exact typed release authority for observation-only caches works
  without private study state; union/domain checks preserve live study guards.
- D21 (SYS-F02, root decision): Require CSV/report in the same new absent generation
  directory. One no-replace directory rename publishes CSV/report/commit together.
  Arbitrary differing/existing output parents are rejected for simple crash semantics.
  UI exposes only validated committed generations; no two-file replacement/recovery.
- D22: Public FAQ exact digest is forced-D endpoint authority, preserving the existing
  numerical interval. No new scientific experiment choice accompanies revision4.
