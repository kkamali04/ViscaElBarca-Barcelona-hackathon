# Exact-reuse preparation prototype

This isolated experiment exposes `TrainingPreparationSession` and is not imported
by registered `fit_models`, the model exporter or the current MVP. It changes no
model, feature, corruption stream, labels, sampling, weighting or tree recipe.
Only repeated pure conditioned features, their observation digest and corruption
receipt are retained within one train capability and protocol identity.

```python
from experiments.speed_v1 import TrainingPreparationSession
from experiments.v3.training import assemble_corpus

# Requires a separately authorized live train capability; do not replay a closed
# registered study. owned_matches may supply already authorized adapter values.
with TrainingPreparationSession(study, cap, protocol, owned_matches) as session:
    for name in ("C0", "C1", "boundary"):
        strata, names = session.source_strata(name)
        x, y, weights, summary = assemble_corpus(name, strata)
    aggregate_statistics = dict(session.stats)
```

Every fixture use checks existing observation and target authority, including
cache hits. Every use revalidates/hashes original observation values and binds
protocol bytes; targets and sample/weight/provenance computations are fresh. A
changed protocol or capability refuses. Changed observation bytes miss. No disk
cache, cross-session reuse, alternate loader, fitting or publication is provided.

The LRU default is 128 MiB. Zero disables retention; larger entries are skipped.
`stats` is a read-only aggregate snapshot. `clear()` drops all prepared entries;
`close()` additionally releases the session's input references and refuses use.
The caller's supplied input dictionary remains its property. The synchronous
session is intended for one thread, and requires inputs not to mutate concurrently.

Retained-byte accounting is exact for numeric buffer payloads plus serialized
keys, array schema/scalars, feature diagnostic metadata and receipt bytes. It is
not peak process memory: owned adapter input matches, returned strata, temporary
arrays and Python allocator overhead are excluded. Cached arrays own immutable
bytes and outputs/diagnostics do not alias retained mutable containers.

Author-only invented-data comparison (no fitting, actual study or raw access):

```powershell
.\.venv\Scripts\python.exe local\speed-reuse-author\synthetic_check.py --frames 2400 --repeats 1
```

This private helper compares every stratum and assembled corpus byte-for-byte,
then reports illustrative baseline/cold/warm preparation times. Its explicit
test-only authority stub does not validate actual study authorization. Fresh
independent synthetic acceptance and root reproduction remain required. Synthetic
preparation savings establish neither actual full training-stage speedup nor
new model quality or fresh input-to-CSV/package acceptance. Historical v3 study
and accepted fallback evidence do not transfer to this prototype.
