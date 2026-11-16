# Canonical v3 contracts

Revision4,2026-11-15; **design unaccepted, APIs not implemented**. Names below are
binding for implementer handoffs. Future plans may not silently rename them.
`protocol.json` contains all numerical settings and is hashed byte-for-byte.

## Typed data and modules

```python
# experiments/v3/contracts.py; postponed annotations, frozen dataclasses, read-only arrays
Role = Literal["train", "selection", "test"]
@dataclass(frozen=True)
class ReleaseAccess:
    release_digest: str
    source_manifest_digest: str
    input_kind: Literal["challenge_observations", "synthetic_observations"]
    source_files: tuple[tuple[str,int,str],...] # relative filename,bytes,SHA256
    runtime_digest: str
    policy_digest: str
    cache_root: Path
    process_id: int
    process_creation_time: str
@dataclass(frozen=True)
class InferenceContext:
    access: ReleaseAccess
    policy: InferencePolicy
    source_leases: tuple[ReadLease,...] # held verified raw/metadata identities
# CacheAuthority = AccessCapability | ReleaseAccess (after both class definitions)
@dataclass(frozen=True)
class ObservationBatch:
    frame_id: NDArray[int64]          # [N], dense0..N-1; never filter unknown GT
    source_frame_id: NDArray[int64]   # [N], original provider N within period
    period_id: NDArray[int16]         # [N]; positive contiguous runs independent
    positions: NDArray[float32]       # [N,S,2], NaN unknown coordinate pairs
    ball_xy: NDArray[float32]         # [N,2]
    team_of_slot: NDArray[int8]       # [S],0/1, canonical home then away
    slot_ids: tuple[str,...]          # [S], unique PersonId, per-team UTF-8 byte order
    slot_ids_digest: str              # SHA256 of compact UTF-8 JSON list
    source_time_frame_index: NDArray[int64] # [R], observed records' dense frame index
    source_time_slot: NDArray[int32]   # [R], players0..S-1, ballS
    source_time_utc_ns: NDArray[int64] # [R], exact original UTC timestamps
    period_origins: tuple[PeriodOrigin,...] # canonical metadata, not targets
    fps: float                       #25 +/-1e-6 or reject
    pitch: tuple[float,float]        # finite positive metres
    fixture_id: str                  # provenance only, never predictive feature
    source_digest: str
@dataclass(frozen=True)
class PeriodOrigin:
    period_id: int
    source_frame_id: int
    utc_ns: int
@dataclass(frozen=True)
class InferencePolicy:
    kind: Literal["external", "challenge"]
    forced_dead: tuple[tuple[int,int],...] # external empty; challenge exact public intervals
@dataclass(frozen=True)
class CandidateConfig:
    candidate_id: str                 # exact protocol ID
    alpha: float                     # exact protocol value
    support: Literal["none","learned","flattened_valid_run_mean"]
    transition_seconds: float         # exactly0.5
@dataclass(frozen=True)
class ModelBundle:
    emitter: TreeModel                # strict loaded selected numeric H/A/D emitter
    head: NumericHead|None            # shared frozen head only for alpha>0
    manifest_digest: str             # verified model/config/source binding
@dataclass(frozen=True)
class TargetBatch:
    labels: NDArray[int8]            # [N],-1/0/1/2; separate cache and capability
    observation_digest: str
@dataclass(frozen=True)
class BoundaryFeatures:
    values: NDArray[float32]         # [N,28],NaN allowed,inf rejected
    names: tuple[str,...]            # exact28 names in PRD-TURNOVER
    valid: NDArray[bool]             # [N,2], TEAM_CHANGE/LIVE_DEAD
@dataclass(frozen=True)
class AccessCapability:
    study_digest: str
    attempt_id: str
    role: Role
    fixture_ids: tuple[str,...]
    process_id: int
    process_creation_time: str
    reservation_event_digest: str
```

Use `numpy.typing.NDArray`; annotations above indicate exact runtime dtype, not a
permission to accept arbitrary integers. Reject infinities and half-observed pairs;
normalize an incomplete x/y pair to bothNaN only at raw ingestion, record count.
FeatureSet output is the existing class with explicit v3 cache dtypes: period_id
int16[N], ball_xy float32[N,2], ball_observed bool[N], nearest float32[N,2],
tracked_counts int16[N,2], collective_speed float32[N,2], ball_speed float32[N].
No input array is mutated; generated perturbations are separate arrays/memmaps.

```python
# guard.py
register_study(protocol: Path, catalog: Path, fallback: Path, control: Path) -> Path
load_registered_study(study: Path, verify: bool=True) -> dict
seal_fitted_models(study: Path, cap: AccessCapability, models: Mapping[str,Path],
                   parity_receipts: Mapping[str,Path]) -> Path
load_model_seal(study: Path, verify: bool=True) -> dict
reserve_attempt(study: Path, role: Role, fixtures: tuple[str,...], control: Path) -> AccessCapability
assert_access(cap: AccessCapability, fixture: str, kind: Literal["raw","observations","targets"]) -> None
authorize_child(cap: AccessCapability, child_pid: int, creation_time: str) -> AccessCapability
finish_attempt(cap: AccessCapability, result: Path, status: Literal["complete","failed","interrupted"]) -> None
# cache.py -- exact tagged authority dispatch, no duck-typed bypass
CacheAuthority = AccessCapability | ReleaseAccess
verify_cache(path: Path, expected: dict, authority: CacheAuthority) -> CacheLease
write_cache_atomic(path: Path, arrays: Mapping[str,ndarray], metadata: dict,
                   authority: CacheAuthority) -> dict
assert_cache_authority(authority: CacheAuthority, domain: Literal["study","release"],
                       kind: Literal["observations","features","targets"]) -> None
# fetch.py -- opaque acquisition/integrity only, never parse records
fetch_registered_sources(study: Path, fixtures: tuple[str,...], destination: Path) -> Path # receipt
# adapter.py
load_match(study: Path, cap: AccessCapability, fixture: str) -> tuple[ObservationBatch,TargetBatch]
# corruption.py
condition_observations(obs: ObservationBatch, spec: dict, seeds: Mapping[str,int]) -> ObservationBatch
build_features(obs: ObservationBatch) -> FeatureSet
# boundary.py
build_boundary_features(features: FeatureSet) -> BoundaryFeatures
boundary_support(head: NumericHead, batch: BoundaryFeatures) -> NDArray[float32] # [N,2]
flatten_support(q: NDArray[float32], period_id: NDArray[int16],
                valid: NDArray[bool]) -> NDArray[float32] # q/valid[N,2], periods[N]
# decoder.py
# scores[N,3] finite/-inf, period int[N],costs[3,3] nonnegative diag0,+inf offdiag,
# q[N,2] finite in[0,1],alpha finite[0,1); optionalinitialint0/1/2 (bool rejected)
decode_change_aware(scores: ndarray, period_id: ndarray, base_costs: ndarray,
                    q: ndarray, alpha: float, initial_state: int|None=None) -> NDArray[int8]
# training.py
fit_models(study: Path, cap: AccessCapability, output: Path) -> Path #models manifest
# evaluate.py
score_match(truth: TargetBatch, codes: ndarray, periods: ndarray, fps: float) -> dict
select_finalist(study: Path, models: Path, cap: AccessCapability, output: Path) -> Path|None
run_final_test(study: Path, finalist: Path, cap: AccessCapability, output: Path) -> Path
# core.py -- SCIENTIFIC closure, implemented in T05 and frozen before registration
predict_codes(features: FeatureSet, models: ModelBundle, config: CandidateConfig,
              policy: InferencePolicy) -> NDArray[int8] # [N], H0/A1/D2/X3
# cache.py -- scientific closure; available in extracted runtime without study state
open_inference_context(release: Path, data_dir: Path, cache_root: Path,
                       input_kind: Literal["challenge_observations","synthetic_observations"]) -> InferenceContext
assert_release_access(access: ReleaseAccess, source: Path,
                      kind: Literal["raw_observations","observations","features"]) -> None
# runner.py -- release-only adapter, MUST call core.predict_codes unchanged
run_release(release: Path, data_dir: Path, out: Path, report: Path, use_cache: bool) -> dict
# exporting.py / promotion.py
build_release(finalist: Path, destination: Path, root: Path) -> dict
promote(release: Path, science: Path, acceptance: Path, root_verification: Path, receipt: Path) -> dict
```

`NumericHead` is defined in boundary.py as a strict JSON-backed numeric tree
adapter with `raw_scores(values,names)->float64[N,3]`. Format
`numeric-boundary-hgb-v1`, ordered classes NONE,TEAM_CHANGE,LIVE_DEAD, exact feature
names/dtypes, training/study/source digests and finite numeric nodes. No pickle,
object arrays, executable imports or relabeling of the accepted H/A/D model.
Tree primitives may be reused read-only; validate wrapper semantics explicitly.
Before JSON parsing, bounded-read at most524289bytes and reject >524288. Reject
all duplicate object keys, unknown schema keys, invalid class/feature ordering,
nonfinite or illegal numeric fields; <=96 trees and1..13 nodes/tree. Each tree has
root0, all nodes reachable, no cycle/shared child, exactlyone parent per nonroot.
Tree count is3..96 divisible3 with complete class iteration groups0,1,2. Internal
children are distinct; leaves have integer0 left/right sentinels ignored as graph
edges. Leaf/split child/feature-index rules follow strict numeric-tree schema. A valid
JSON file is not automatically a valid graph. Outer boundary_support calls
raw_scores on at most4096 rows each and writes q directly; internal tree chunking
alone does not bound a full raw_scores Nx3 result. Release temporary feature/head
buffers before decoder when no longer needed; measure actual worker memory.

## WBR-02: history, live reservation and restart

`local/v3-control/` is the one canonical control root for ALL studies. Reject a
custom substitute ledger root at normal CLI entry. The immutable study manifest
binds `prior_access_snapshot` bytes, a live-ledger checkpoint sequence/digest, the
protocol/catalog/source closure, comparator bytes and locked environment. It does
not require the current live-ledger digest to remain unchanged after registration.

Under a Windows exclusive OS file lock, replay/validate the COMPLETE live ledger
hash chain, require the snapshot checkpoint to be an authentic prefix, and check
the current fixture roles/reservations. A newer reservation dominates a stale
study snapshot. Reserve the complete selection cohort or two-test cohort in one
atomic event and flush/fsync BEFORE releasing the lock or opening any raw source.
Use monotone sequence, previous/current event digests, UTC, study/attempt IDs,
fixture IDs, role, PID+creation time and status. Partial/corrupt ledger tail fails
closed; never truncate or repair it automatically. Training roles may be reread
only within declared training operations; closed tests are never allowed.

The capability is process-bound and tied to its durable reservation. On each raw
parser/cache hit/miss/target open, replay live state under lock and confirm the
same live attempt owns the whole cohort; mark first access durably before opening.
A fabricated capability, changed PID/creation time, altered source or completed
attempt fails before read. A worker child must obtain an explicitly registered
child capability under the same attempt before opening; arbitrary descendants do
not inherit access. This permits post-reservation reads without mistaking ledger
growth for manifest drift. There is no selection/test retry after reservation,
even if no report exists. Process death marks the cohort consumed/interrupted.
No stale-lock reset or new study ID makes it fresh. Restart can validate a sealed
complete result and finalize metadata; it cannot parse or rescore reserved inputs.
Same-user deliberate bypass remains outside this accidental-leakage threat model.

## WBR-03: parser and cache integrity

`load_match` calls assert_access before any label-bearing raw parser, including
layout discovery, and before both cache hits and misses. Do not call legacy
`validation.sportec._build_cache`. Public metadata-only roster reads may precede
reservation; raw XML with possession fields may not. Exact allowed filenames,
size, source SHA256/MD5 and metadata hashes come from the registered catalog.
No glob fallback, all-game SDK or default-match download is allowed. Raw and
metadata parsing hold the same verified Windows file identity with WRITE/DELETE
denied through hashing and parse; no path close/reopen between integrity and use.
Opaque acquisition/hash does not authorize label parsing; live role capability
is still mandatory at first parse.

Retain full per-period min..max source frame span; missing frame records become
unknown observations/targets, not dropped rows. Validate roster side uniqueness,
positive pitch, recognized periods, integer nonnegative source frame IDs, duplicate
ball/player writes and every observed timestamp against25Hz frame increments
within1ms plus a fixed per-period origin. Normalize XML record order before these
checks; do not mistake a reordered FrameSet for changed observations. Reject conflicting timing/IDs rather
than infer FPS from targets. Whole-match completeness uses metadata/frame layout,
never score/label balance; no post-outcome replacement fixture.

Cache manifest requires schema version, source/config/dependency/env digests,
fixture/role/attempt provenance and EVERY member's filename, byte size,SHA256,
NumPy dtype, shape and ordering. Expected arrays are closed allowlists: observation
members above; target labels separately; feature seven arrays separately. Reject
missing/extra members, symlinks, object dtype, corrupt/truncated files or any shape,
size/hash mismatch before mapping. Derived cache keys include the entire registered
adapter/feature/corruption/dependency closure, conditions and exact seed material.
A metadata-only cache.json never suffices. Acquire and retain Windows handles
that deny WRITE and DELETE for manifest and every member before hashing, mapping
and consuming. Map the same held verified file identities; no close/reopen by path.
Hold all handles through consumer completion, then close. Failure to acquire a
handle or changed identity fails before reads; a post-check replace/write attempt
must fail or be detected before consumption. This is part of verify_cache's return
lease: a context-managed CacheLease containing manifest and held read handles,
not a detached dictionary. verify_cache returns CacheLease; closing invalidates
all mappings. Cache consumers cannot retain arrays after lease exit. CacheLease
is a context manager with manifest:dict and arrays:Mapping[str,ndarray], owns all
read handles and closes mappings before handles in __exit__; use-after-close
raises. load_match returns owned read-only copies of ObservationBatch/TargetBatch
arrays made while the leases are live, never escaped mappings. Other cache readers
consume within the lease or similarly make owned copies counted in resources.

Write to a unique sibling tempdirectory, fsync each member, then write/fsync the
complete manifest, verify it, and atomically rename into an absent final path.
Existing valid cache is immutable. A racing writer may reuse only after verifying
identical complete content. Failed partial dirs remain invalid scratch, never cache
hits. Cache corruption on a reserved selection/test attempt fails the attempt;
it is not an excuse to replay labels. Preserve originals and report the failure.

## Numeric decoder, model and scoring

Feature windows and28 names are in PRD-TURNOVER. Each edge t is t-1 to t; first
rows of contiguous positive runs have no incoming edge. Support is float64 stable
softmax at temperature1, class1/2 castfloat32, invalid rows exactly0. Costs stay
nonnegative; preserve forbidden+inf without multiplying it byzero. O(9N) decoder
work, O(3N) uint8 backpointers and float32[N,2] support, no[N,3,3] allocation.
Canonical ties match accepted output at alpha0 on numerically valid inputs.
Reject positive AND negative overflow in every allowed finite-arithmetic DP
alternative, even a losing alternative; deliberate -inf state/+inf edge prohibitions
remain legal. Do not silently turn finite negative overflow into a forbidden path. Independent tests enumerate short
paths and distinguish unique-optimum output symmetry from tied optimal-set symmetry.

Emitter training rows/weights, boundary population/inclusion weights and eight
candidate IDs are exact in protocol.json. Generate dense features BEFORE sampling;
features never receive targets. Reuse one boundary model for all B/F/D arms. Fit
all three only once; global missing head class, missing emitter class in any
match/condition, empty stratum or row-budget breach fails before model selection.
Relative fit weights MUST finally be scaled to global mean1 (sum equals actual
fit-row count); otherwise HGB L2=2 changes effective regularization. Preserve all
relative stratum/class/inclusion fractions through this final scalar. Bind actual
sklearn1.9.1 and NumPy2.4.4/locked environment at registration.
Numeric export must match sklearn raw outputs <=1e-10 for every retained training
row in bounded batches plus synthetic missing/split probes. Head<=512KiB. Scikit-learn
is training-only; runtime imports only declared NumPy/base dependencies.

Use the pinned organizer metric code directly. Convert internal-1 to scorerX=3.
Compute frame confusion on all known-GT active frames; predictionsX count as
misses. Use official confusion then scored_confusion (3x4) and per_class_prf;
absent/unpredicted classes contribute F1=0 and macro_f1 is unweighted over H,A,D,
never drop an absent class. Build GT-valid runs separately inside each positive period, retaining global
indices. For temporal scoring only, fill predictedX forward then backfill leadingX
within each valid run; allX remainsX. No extra censored-spell rule, no compressed
time, no crossing unknown gaps or periods. Primary is official
spell_scores(gt,filled,runs,ious=(.3,.4,.5,.6,.7))["mean_f1"], exposed as
spell_f1_mean: H/A spells POOLED at each threshold, then threshold F1 mean, never
team-macro or mean-run F1. Use official spell extraction/IoU matching unchanged.
For transition diagnostics, call official transitions and match_transitions
SEPARATELY for each single period/known-GT run with global offsets. Sum pair,
missed and spurious counts to TP,FN,FP; precision=TP/(TP+FP), recall=TP/(TP+FN),
F1=2TP/(2TP+FP+FN), zero for zero denominators. Match destination label (typed="to"),
inclusive +/-12 and +/-25 frame tolerances, first-new-label indexing. This external
wrapper intentionally isolates transition matching; calling the public evaluate
helper on all runs can match across short gaps and is not this diagnostic contract. Non25Hz input
is rejected in this study rather than silently using wrong tolerances.

## Release, failures and evidence

Every CLI parses destinations before opening data: reject aliased CSV/report,
protected input/model/source/fallback paths, symlink/hardlink aliases, directory
collisions and traversal. Reject unknown keys/unsupported schema/source changes
before input access. Exit2 for preflight/schema/access error,3 for budget/integrity,
4 for unsuccessful scientific gate; success0. CSV/report are published together ONLY as a new immutable generation directory
under the exact transaction below; never atomically replace two separate files.
Failure preserves all previous committed generations and logs aggregate reason/hash.
Packages retain their separate single-artifact atomic publication contract.

Fresh release inference produces header frame,label and exactly199319 ordered
rows0..199318; H/A/D/X only, outside public periodsX, published dead intervalD.
No target/public-window labels enter inference. Three uncached identical-input
fresh processes must produce byte-identical CSVs. Independently check every row,
public bounds, official validator and invented invalid fixtures. Record actual
worker high-water memory and full walltime, not parent/array size estimates.

Export cap20MiB, each member<50MB; include exact required runtime/model/protocol/
license/lockfile files only. Versioned review exposes the same release identity in
state, generated report and bundle; stale/mismatched outputs are unavailable.
`ReviewStateV3` implements current/state/timeline/start_run/export in its isolated
root; use unchanged static assets, bind127.0.0.1:8766, enforce existing origin,
Range/path and download protections. Demo mode never opens realdata. Private
bundles remain marked local/not-submitted; code-only package contains no records.
Promotion receipt binds study, finalist, test report, exact ZIP, blind acceptance,
root verification and preserved fallback. A result with any failed gate has no
promotion receipt and leaves the accepted launcher/config untouched.

## Source-closure and transport distinction

The protocol lists the scientific new modules and release-only modules separately.
Registration binds every scientific module plus its transitive legacy dependencies,
public metric code and actual environment. CLI command dispatch is fixed before
training; runner/export/review/promotion implementation may follow only because
these modules are outside fit/selection/test execution. They cannot replace or
modify a scientifically frozen import. The final release manifest additionally
binds the complete runtime/review/export closure. Hash both manifests explicitly;
a release-only edit does not retroactively rewrite scientific provenance.

Opaque acquisition and whole-file cryptographic integrity checks are allowed
before reservation, with no record parsing or field inspection. Decompression
into files only may be allowed by the registered source format; decoding records
or generating STUDY observation/target caches requires a live capability. Every STUDY-domain cache
load including observation-only hits checks role/current ownership. Standalone
RELEASE-domain observation caches use ReleaseAccess below, with no study lookup. The same OS
owner can bypass tooling deliberately; no adversarial security claim is made.

Final uncertainty output is fixed: both per-match paired deltas, observed range,
mean, N=2 and provider/shared-club dependence limitations. Do not choose an interval
or p-value after outcomes; no population or hidden-performance inference follows.

Post-scientific wrappers cannot alter features, costs, parameters, frame/label
mapping, numeric model/config, scoring or add postprocessing. G08 independently
rehashes the scientific closure and checks direct frozen-core inference equals
runner, CLI and UI regeneration on independently invented fixtures and actual local
input, using only aggregate equality/hash evidence. Any disagreement invalidates
release acceptance; a changed scientific core requires new scientific evidence.

## Revision4 canonical observation and random algorithm contract

This section and protocol.json resolve design-round1 ambiguities before any labels.
Every raw roster must have unique nonempty PersonId strings and exactly one side
per player. Sort home(team0) before away(team1), then PersonId.encode("utf-8") byte
lexical order. slot_ids is this tuple; slot_ids_digest is SHA256 of
json.dumps(list(slot_ids),ensure_ascii=False,separators=(",",":")).encode("utf-8").
Canonicalize coordinate columns before corruption; never use XML arrival order as
an RNG identity. Direct ObservationBatch consumers validate canonical slot order,
uniqueness, side assignment and digest before drawing; reject noncanonical arrays.
Raw roster/XML permutation therefore normalizes identically. Clean anonymous
features retain within-team permutation invariance, but stochastic corruption
makes no unqualified same-index RNG permutation claim. Transport slot identities
and masks together in any internal co-permutation.

Retain exact observed timestamp values privately in the three sparse numeric
source_time_* arrays: one row per observed player/ball record, sorted by
(frame_index,slot), including records whose coordinates are absent. All timestamps
must parse as timezone-aware UTC with exact integer nanoseconds (more than9
fraction digits fails; no floating conversion); missing/malformed T fails. Reject
duplicate object/N within a period even if coordinates agree. For each period,
choose the smallest observed source N, then BALL if present else lowest canonical
slot to anchor origin. Validate every T against origin+(N-originN)*40000000ns with
absolute tolerance1000000ns. Preserve original deviations; do not reconstruct
observed T from origin. Dense missing N rows have no timestamp member rows and
unknown observations/targets. Period ordering follows metadata; observed source
N is sorted independently of XML traversal. Cache metadata binds period_origins,
slot_ids and slot_ids_digest; member hashes bind all three timestamp arrays.

player_observed and ball_observed are derived properties isfinite(pair).all over
last axis. They are not persisted independent arrays. Raw incomplete/nonfinite
pairs normalize to float32 quiet NaN bit pattern0x7fc00000 for both coordinates,
with aggregate normalization count; typed batches reject infinity/partial pairs.
Observation cache exact array members: frame_id,source_frame_id,period_id,positions,
ball_xy,team_of_slot,source_time_frame_index,source_time_slot,source_time_utc_ns.
All nine arrays and the canonical metadata are integrity-bound. Targets remain a
separate labels-only member/cache. Target strings match exactly protocol.input:
status"0"=>D; status"1"/owner"1"=>H or owner"2"=>A; other/missing strings=>unknown,
no trim/numeric coercion. Malformed structure/types fail. Natural absence is not D.

Every random stream uses protocol.randomness exact seed encoding and Generator
calls in protocol.corruption_semantics. Jitter draws standard_normal((N,S+1,2),
dtype=float64), canonical players then ball; teleport random((N,2),dtype=float64),
decision first column, angle second. Both draw ALL rows including missing/inactive.
Block streams call random((B,S),dtype=float64) for player/stale, random((B,),dtype=float64)
for scalar gaps once per contiguous positive run in timeline order, ascending
blocks/canonical slots. B is integer ceil(runlength/blockframes). No conditional
draws, per-chunk reseeds or intermediate combined float32 casts. The full-call
arrays define the oracle; alternative chunk generation must prove byte equality.
All effects apply only positive runs; combined arithmetic is float64 until one
final float32 cast; standalone masks/stale preserve original float32 finite pairs.

The fixed protocol bytes intentionally contain no actual source/catalog digests.
Their digest is the label-independent RNG root; study identity separately binds
protocol AND exact source/catalog bytes. Target-mutated invented studies require
independently authorized distinct source manifests but retain the same protocol
root and observation RNG namespace. Unauthorized mutation still fails integrity. Metamorphic equality compares numeric
observations/masks/features/predictions, not source_digest or cache-provenance fields
that legitimately differ between separately authorized target variants.
Row cap selection is eligible_ids[j*(L-1)//(cap-1)], cap30000, integer-only; no
floating linspace. Tests must compare interior selections, not just endpoints.

## Frozen shared scientific inference and flattened control

core.predict_codes validates config against the exact declared candidate, bundle
identity and policy. It builds the accepted motion-transformed emitter matrix,
uses numeric emitter scores, then boundary features/head for alpha>0; F080 alone
calls flatten_support before decode. No target/tag argument exists. For external
policy forced_dead is empty; external period IDs come from observations. For
challenge policy, require the literal public timeline/positive intervals from
protocol.release and apply published forced_dead to scores BEFORE decode:
H/A=-inf,D=0 in those half-open intervals. Outside positive runs outputX=3;
inside outputH/A/D. No post-decoder relabeling or wrapper postprocessing. Both
scientific evaluator and release runner call this same frozen core. Source,
configuration/mapping/policy bytes and accepted comparator model bytes are
hashed in the immutable prefit study. C0/C1/head bytes are sealed only AFTER fit,
before selection reservation/access, in a new immutable models/models.json bound
to the unchanged study digest. No placeholder model hashes or amendments to the
registered study. Finalist/comparator/model seal is bound before test; G08 rechecks
all applicable prefit, postfit, finalist and runtime identities.

flatten_support validates exact q float32[N,2], periods int16[N], valid bool[N,2]
and every q finite in[0,1] even ignored rows, without mutating input. Start a zero
float32[N,2] result. For each contiguous positive run [a,b) and type c, gather
ascending t in[a+1,b) with valid[t,c]. If nonempty, value is
np.float32(np.mean(q[eligible_ascending,c],dtype=np.float64)) with pinned NumPy;
assign only eligible rows; empty/start/invalid/outside remain0. No labels enter.
F080 shares accepted emitter, identical head and alpha.8 with B080. It competes
under ordinary selection rules; report B080-F080 on selection only. This tests
within-valid temporal placement against equal per-run support-level relaxation;
it does not prove exact control identifiability. Invalid support restores baseline
costs, not necessarily final labels under global decoding. Report eligible edge
coverage/positive counts by type without changing windows/sampling afterwards.


## Revision4 provenance stages (SCI-01)

register_study binds only identities that exist before fitting: scientific source,
protocol, numerical hyperparameters/configuration, feature/mapping/public policy,
actual environment/locks, data catalog and accepted comparator model/config bytes.
fit_models emits all three artifacts then an immutable models/models.json seal.
Schema: schema_version1,study_digest,prefit_closure_digest,train_attempt_digest,
models list of exactly C0,C1,boundary with relative path/bytes/SHA256 plus numeric
export/parity receipt hashes. Verify model source/input provenance against study;
never insert future-model placeholders or rewrite study.json. Seal completeness
and all hashes are required BEFORE reserve_attempt(role="selection"). Failure to
produce three sealed models aborts the campaign, not a reduced candidate grid.
Finalist manifest references model-seal digest, selected models/config, comparator,
protocol/scientific closure and selection receipt before test reservation. At
G08 verify all applicable original study, model-seal, finalist and release bytes.

## Revision4 standalone release cache authority (SYS-F01)

An exported observation-only runner has no dependency on original study files or
local/v3-control. CacheAuthority is an exact tagged union, not an optional guard:
AccessCapability authorizes ONLY study domain under the live guard; ReleaseAccess
authorizes ONLY release domain and observations/features. Wrong union/domain/kind
fails before filesystem lookup. ReleaseAccess cannot authorize targets, target
cache members, IDSSE label-bearing XML, closed fixtures, or any study cache.
A closed/invalid study capability never falls back to release authority.

open_inference_context verifies release.json, full scientific/runtime/config/model
closure and exact public policy hashes first. Resolve only the approved challenge
observation filenames tactical/BAR-ATH_tactical_atd.xml and
 tactical/BAR-ATH_tactical_atd.txt under data_dir; schema is the accepted ATD
observation schema, not Sportec/GT/tag input. Synthetic demo uses its separate
invented same-schema files and input_kind; no realdata fallback. Reject aliases,
reparse paths, extra source-manifest members and target-bearing schemas. Acquire
stable ReadLease handles denying WRITE/DELETE, compute source sizes/SHA256, and
freeze this exact observation-only source_manifest in the context; recheck against
those same held identities before parse/use. ReadLease owns verified handle and
closes on context exit. Integrity hashing is local; no original study lookup is
needed or allowed. ReleaseAccess is minted only here, process-bound, with verified
release/source/runtime/policy digests and confined cache root. A fabricated or
changed context fails verification. This guards accidental misuse, not malicious
same-user bypass.

Release cache manifests have schema_version,domain="release",input_kind,release/
source/runtime/policy/feature-transform digests and exact observation/feature member
hashes/bytes/shapes/dtypes. They contain no fixture-role/attempt/target members.
Study caches retain domain="study" and live role/attempt provenance. Both domains
use complete CacheLease verification and immutable publication; no unchecked hit
or compatibility fallback. --no-cache still constructs/verifies InferenceContext
and raw ReadLeases but reads/writes zero cache entries. Cached release miss/hit
must work from an extracted package with the original study/control tree absent;
spies assert zero lookups to it. Study wrong-role/closed/stale tests still reject.
Context objects are not serialized capabilities; serialize only safe source hash
provenance into run report/commit receipt, never raw records.

## Revision4 atomic result generation (SYS-F02)

The runner still takes --out and --report, but both must be distinct regular file
names in ONE NEW ABSENT generation directory, e.g.
local/v3-review/runs/run-0001/candidate.csv and run-0001/run.json. Their common parent
must not exist. Its parent output root must already exist as a regular directory;
reject any symlink/reparse/alias/protected path, differing parents, commit.json
name collision or existing generation parent/destination BEFORE opening any input.
No mkdir of the final generation during inference; no overwrite flag. UI chooses
unique generation IDs; CLI caller supplies a new name. Validate this restriction
before open_inference_context. Prior generations are immutable and protected.

Create a unique sibling scratch directory on the same filesystem. Write CSV there,
check every row/public rules and official validator, flush/fsync it. Write run
report containing schema_version1,generation_id,release_digest,source_manifest_digest,
policy_digest,csv_filename,csv_sha256,frame_count,aggregate runtime/resources; flush/
fsync. Write commit.json LAST with strict schema_version1,kind="v3-run-generation",
generation_id (exact final directory basename),release_digest,source_manifest_digest,
policy_digest,csv:{filename,bytes,sha256},report:{filename,bytes,sha256}. Filenames
are plain basenames and distinct from each other/commit.json. Exact three-file
allowlist; JSON duplicate/unknown keys reject. Commit report identity and CSV hash
must agree across all three artifacts. Validate complete staged pair/manifest,
flush/fsync all files, close writer handles, then perform ONE same-volume atomic
directory rename to the ABSENT final parent; never replace an existing directory.
The rename is the sole publication commit point. An atomic no-replace rename
collision fails with previous generations intact. Guarantee covers process hard
termination; do not claim recovery from storage-device corruption/power loss.

Crash before rename: final directory absent, scratch may remain. Crash after
rename: complete pair+commit are visible. Restart ignores/quarantines scratch or
any directory without a valid complete manifest; never repairs partial results or
publishes a scratch result by guessing. New execution requires a new generation.
No delete/overwrite/recovery of earlier committed runs. Preflight/runtime failure
leaves all previous generations byte-identical. Scratch cleanup is separate from
publication and cannot target originals or committed runs.

UI current()/download/export exposes ONLY a fully verified committed generation,
using held handles for all three members while verifying/consuming. Switch the
in-memory active generation under app.lock only after successful verification;
csv/report properties derive from that same generation. Keep prior active generation
on a failed run. Restart scans only complete directories, verifies each and chooses
the lexically greatest valid generation_id (UTF-8 byte order); selection is a UI
convenience, not scientific selection. Download/export pins the selected generation
through the request. No persistent mutable CSV/report pair or mixed-generation
pointer. Existing server routes/static assets can use ReviewStateV3.current()/csv
under its lock; do not reuse old state's two-file os.replace implementation.

G08 kill probes stop workers after scratch mkdir, partial/full CSV write/fsync,
report write/fsync, commit write/fsync, pre-rename and post-rename. Restart reader
must observe absent final before commit, complete same-generation pair after it,
and unchanged prior committed generations at every stop. Test concurrent final-name
collision, different parent paths, preexisting directory and malicious manifests.
No old success receipt substitutes these fresh exact-package checks.

Public forced-D authority is organizer FAQ.md, URL
https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/FAQ.md,
SHA256 c536ec6401ea1b8c8a6dd54ee80e39518d3a521464ed9fe2bc1cf0ee70b7419b,
7473bytes (verified public cache listed in sources.json). Its explicit
[110808,113742),2934-frame interval controls over the convenience kickoff anchor;
no numerical interval changed in revision4.


## Revision4 exact source and model handoff shapes

The research dataset-catalog.json remains historical/proposed. Before register,
root prepares local/v3-control/catalog-complete.json using public pinned metadata
and opaque file integrity only (no label-bearing record parse). Complete missing
metadata/tracking bytes/SHA256/MD5 and metadata-only identity/overlap receipts;
never invent missing digests or edit the research catalog to imply completeness.
This preparation is a future root operation, not permission for data access now.

Complete catalog schema_version1 has exact keys schema_version,provider,raw_root,
metadata_overlap_receipt_digest,fixtures. provider="IDSSE"; raw_root is the resolved
local/v3-data/originals directory. fixtures has exactly the five allocated fixture
IDs. Each fixture record has fixture_id,canonical_fixture_id,duplicate_group,role,
fps,license,metadata,tracking. role matches protocol; fps25; license identifies
CC-BY-4.0 and attribution receipt. Each metadata/tracking record has exact keys
kind,relative_path,source_url,bytes,sha256,md5; kind is metadata/tracking respectively; normalized confined relative_path unique
under raw_root, no aliases/reparse/traversal; bytes positive integer, SHA25664hex,
MD532hex. Group/identity metadata requires independent root receipt before study.

Study manifest schema_version1 binds study_id,protocol_digest,catalog_digest,
scientific_closure_digest,environment_digest,comparator_digest,prior_snapshot_digest,
ledger_checkpoint:{sequence,digest},raw_root,catalog_path,model_seal_path. Paths
are canonical/contained; model_seal_path is a future path, NOT a future hash.
load_registered_study is the sole consumer entry: verify=True checks canonical
manifest/schema/digest, complete catalog/source bindings, source/config/comparator/
environment closure and authentic prior ledger checkpoint; it does not reserve a
role or authorize parsing. Normal CLI/consumer calls may not set verify=False;
that option is diagnostic inspection only and returns no access authority.
Implementer may choose strict internal ledger JSON fields meeting semantic rules,
document/test them in guard.py; consumers do not duplicate ledger replay.
seal_fitted_models requires the live training capability, exact keys C0,C1,boundary
in models/parity_receipts, complete parity/integrity receipts and unchanged prefit
closure; atomically writes once to model_seal_path, refuses existing/mismatched seal.
load_model_seal verifies all model/parity/study bindings before selection reservation
and test; verify=False never authorizes those operations.
Manifest also has artifact_bindings: sorted list of {relative_path,bytes,sha256}
covering exact reviewed specs/source/environment/comparator files. Its immutable
SHA256 is study_digest. Source bytes are read through catalog_path only after
catalog_digest verification. fetch_registered_sources validates study/catalog,
fixture allowlist and exact destination==raw_root, obtains only registered URLs,
verifies exact bytes/SHA256/MD5, preserves existing originals, and emits an opaque
receipt; wrong-existing content fails, no replace. It never parses XML or authorizes
load_match. load_match resolves only the registered fixture's metadata/tracking
paths and requires the live study capability at parser entry.

boundary.py exact API: NumericHead(document:dict), NumericHead.load(path:Path),
NumericHead.raw_scores(values:float32[N,28],names:tuple[str,...])->float64[N,3],
export_boundary_sklearn(estimator,provenance:dict)->dict. Constructor/load apply the
same strict schema; load additionally bounded-reads before parse. Export uses the
accepted numeric exporter array representation with a distinct boundary wrapper;
never relabel an accepted H/A/D model in place.

Boundary top-level keys are EXACTLY format,class_names,feature_names,baseline,
trees,provenance. format="numeric-boundary-hgb-v1"; class_names and feature_names
are exact canonical ordered lists; baseline three finite numbers. trees is the
3..96 list of {class,nodes}; nodes has EXACTLY value,feature_idx,num_threshold,
missing_go_to_left,left,right,is_leaf arrays of equal length1..13. value and
num_threshold are finite numeric arrays; integer indices and binary integer flags
are validated without bool-to-int coercion. Existing strict graph/leaf rules apply.

Provenance keys EXACTLY: scientific_source_digest,study_digest,protocol_digest,
split_digest,metric_digest,dependency_digest,training_input_digests,weight_recipe,
feature_version,fps,windows_frames,coverage,temperature,tree_parameters,random_state.
All *_digest values are64lowercasehex. split_digest hashes canonical compact sorted
JSON of protocol.split; metric/dependency/source digests reference registered
closures. training_input_digests is exactly eight ordered train-fixture/C1-condition
records {fixture_id,condition,observation_digest,target_digest,sampling_digest};
order is protocol train order then boundary_conditions order. These digests bind
local private arrays/row-selection receipts without embedding rows or labels.
weight_recipe is the exact protocol.fit.boundary_weights string;
feature_version="v3-boundary-28-v1",fps25,windows_frames=[5,15],coverage=.8,
temperature1,random_state20261116. tree_parameters equals protocol.fit.boundary
with its exact key set/values. Canonical JSON for digest objects is UTF-8,
ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False. Unknown or
missing keys at every defined level fail. Aggregate parity/export receipts live
outside the head and are bound by postfit model seal, avoiding a circular model
hash inside its own provenance. This schema adds no fit or numerical choice.
