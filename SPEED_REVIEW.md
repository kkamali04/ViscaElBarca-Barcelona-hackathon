# Faster preparation: exact-reuse prototype

Snapshot: 2026-11-16T19:14:44.422540+00:00. **Bounded synthetic component acceptance complete.**
The current MVP and the closed v3 study remain unchanged. This prototype is not
integrated into the active model, registered training runner or exported package.

## What the twenty minutes included

The [historical timing audit](reports/speed-historical-timing-audit.json) extracted
only aggregate fields from existing sealed receipts, without a new fit or data
replay. Calling the entire20m37s stage “model training” hid its main cost:

| Recorded work | Seconds | Approximate time |
| --- | ---: | ---: |
| Loading, feature preparation and corpus assembly | 1104.704 | 18m25s |
| All three fits, numeric export and equivalence checks together | 60.298 | 1m00s |
| Remaining stage overhead | 72.384 | 1m12s |
| Total | 1237.386 | 20m37s |

The first row includes initial ingestion. The second is not a pure fit timer.
Existing receipts do not separate those finer costs. Compressing model weights
would target a small part of this stage. The existing histogram estimator already
uses63 bins; [official docs](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html)
explain its binning. No dependency, bin count, tree setting or thread change occurred.

## Implemented idea

Remember identical prepared observations instead of repeating their calculations.
The [isolated module](experiments/speed_v1/preparation.py) retains immutable
conditioned features, input identities and corruption receipts within one train
session. It still performs per-use access checks, revalidates original observations,
and recomputes labels, sample selection and weights. Changed inputs miss the cache;
changed protocol/capability or denied access refuse. No frames, features or numeric
precision are discarded. LRU retention is capped at128MiB of accounted payload;
zero capacity disables it, oversized entries skip retention, and close releases it.

The source asked for24 preparation passes covering10 unique fixture/condition
combinations. The prototype performs those10 once and reuses14. It does not cache
across sessions, write persistent data, bypass the existing loader or fit models.
[Primary research](research/speed-20261116/RESEARCH.md) records five official
documentation sources and the memory/copying/compression tradeoffs.

## Measured result and its limits

Fresh independent fixtures contained two invented matches,1930 frames each and
six slots, with multiple periods, missing observations and unknown labels. Both
versions ran all three curricula and complete corpus assembly, with one warmup
per mode and three paired timing repeats. Fixture generation, output hashing,
garbage collection, close and fitting were outside timing. Cold includes the
session constructor and synthetic loader, which returns already generated data.

| Complete synthetic preparation | Independent median | Root median |
| --- | ---: | ---: |
| Original | 5.436s | 5.414s |
| New session with reuse | 2.421s | 2.453s |
| Original/new time ratio | 2.25x | 2.21x |

All24 strata and assembled corpora matched byte for byte on the tested fixtures.
The independent seven acceptance groups and all seven exact-copy root replays
passed: authorization calls/refusal, input/target/protocol mutations, deterministic
repeat/reordering, immutable ownership, LRU/zero/oversize limits, clear/close and
invalid inputs. The fixture retained 699,151 bytes of accounted
cache data. This is not peak process memory; inputs, output matrices, temporaries
and Python allocator overhead are excluded. Already-warm timing is separately
recorded in the report and is not the headline cold-session result.

Evidence: [independent acceptance](reports/speed-reuse-blind-acceptance.json), [root reproduction](reports/speed-reuse-root-reproduction.json),
[bounded root acceptance](reports/speed-reuse-root-acceptance.json).
Original59 scientific files and29 protected MVP artifacts were rehashed unchanged.

**No new full20-minute actual training-stage benchmark was run.** The result does
not imply20minutes becomes9minutes: actual initial ingestion and other overhead
were not measured again. No current single-match inference speedup, new model
quality, live authority or actual CSV/package E2E is claimed. The existing MVP's
earlier53.7-second full-file result retains its old unchanged-version scope.

## Next integration boundary

Use this session in a newly bound, separately verified experiment runner before
measuring a real complete training stage. Preserve the closed v3 attempt, original
evidence and frozen model. Do not copy old acceptance onto changed code. This
performance prototype does not change the earlier no-eligible-finalist decision.
The source README/spec retain their pre-acceptance design wording as frozen
snapshots; this handoff and current checkpoints report execution status.
