# Invented-only exact-reuse benchmark

These are exact copies of the original independent synthetic oracle/acceptance
harness. Their location remains two directories below the repository root, so
the public-source imports resolve without any original `local/` scratch folder.
They generate two invented 1930-frame, six-slot fixtures and use scoped test auth
and adapters. No actual study, cache, model payload or raw match path is opened.

After the root README runtime setup, create a fresh output path:

```powershell
$BenchStamp = Get-Date -Format 'yyyyMMdd-HHmmss-ffff'
.\.venv\Scripts\python.exe benchmarks/speed_reuse/acceptance.py --repeats 3 --output "reports/local-speed-$BenchStamp.json"
```

The output must not already exist. For equivalence groups without timing, pass
`--skip-benchmark`. Only generated `invented-protocol.json`, `prepared-oracles.json`
and the requested aggregate report are written; these are ignored. `freeze_identity`
checks the candidate/spec files in `reports/speed-implementation-freeze.json` and
the eight named public numerical source files in oracle.py. It does not iterate
the freeze's broader historical bindings or open their protected paths.

This measures complete synthetic source preparation plus corpus assembly, with
one warmup and three paired repeats by default. Cold includes session setup and
the stub loader returning generated inputs. Fixture creation, comparison, garbage
collection, close, fitting, model export and inference are outside timing. Cache
accounted payload bytes are not peak process memory. These results cannot imply
a speedup for real complete training or the current MVP inference path.
