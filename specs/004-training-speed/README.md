# Exact-reuse training preparation prototype

Date: November16,2026. Status: implementation pending independent acceptance.

The user requests faster training using a smart compression-like approach. This
bounded performance experiment preserves the completed v3 study and accepted MVP.
No actual study, raw inputs/caches/targets/model files, refit or changed predictor
is authorized here. Training/quality evidence is not transferred to changed code.

Historical aggregate timing extraction is reports/speed-historical-timing-audit.json.
Source/assembly includes initial ingestion; it is not a pure feature-build timer.
Fitting/export/parity are likewise one combined timer. Never invent finer costs.

Implement a separate experiments/speed_v1/ preparation module using the unchanged
v3 numerical/corruption/sampling/weight functions. It must expose an explicitly
scoped TrainingPreparationSession(study, cap, protocol, owned_matches=None,
max_cache_bytes=134217728), source_strata(name), clear()/close(), and read-only
aggregate statistics. source_strata yields the same strata/names as frozen
experiments.v3.training._source_strata for any supported ordered curricula.

The session can only reuse pure conditioned-feature preparation. Cache keys bind
protocol identity, exact original observation content/schema and fixture/condition;
targets never influence observation features or corruption RNG. Current target
labels/sampling/stratum weights are always recomputed. No array precision loss,
sampling change, dropped frame, feature change, altered RNG or tree recipe.

Call existing observations/targets access authorization before every fixture use,
including cache hits; refuse non-train capabilities and protocol identity drift.
No cross-session/capability/attempt/disk cache, file-open bypass, new data-loader,
process-global monkeypatching or persistent publication. Existing load_match is the
only loader. Owned observations changing must miss/refuse, never reuse stale values.

Use bounded LRU retention measured from retained numeric arrays and owned metadata;
zero capacity disables reuse; entries larger than the cap are not retained. Cache
entries must own immutable values; returned mutable diagnostics/strata cannot
poison future hits. Close clears retained values and prohibits subsequent use.
Preserve input validation, output dtypes/order/NaN bytes/weights/provenance digests.
Do not change any of the59 registered v3 files or29 protected fallback artifacts.

Acceptance: fresh blind reviewer derives independent invented observations and
oracles from this document and frozen public v3 source, not prior author tests.
Compare every stratum array byte-for-byte, names, metadata and assembled corpora
across all three curricula; exercise periods, unknowns, missingness/corruptions,
protocol/input drift, authorization on hits, eviction/zero cap, mutation attempts,
fresh sessions and close. Count expensive pure preparation calls independently.
Benchmark cold/warm end-to-end preparation on invented data, same machine, repeats,
no sklearn fitting. Report workload, wall time, retained bytes and measurement
limits. Root reproduces decisive checks. Synthetic preparation savings establish
neither actual full-stage speedup nor actual input-to-CSV/package E2E acceptance.

Any later scientific integration needs a new bound source/protocol and appropriate
actual acceptance. The closed v3 attempt is never rerun or rewritten.
