# Morning review release hardening

Preserve the frozen noise-v2 scientific estimator, weights, configuration,
inference output contract and historical evidence. Tracking-only inference is
allowed; the organizer's exact frame/label contract and possession rules apply.

- Preparation errors must identify a safe input/preparation reason and tell the
  user what to correct and when to restart the launcher. Retry must not imply it
  reselects or reloads invalid inputs in a running server. Status/badge must be
  truthful rather than permanently Connecting after a terminal failure.
- Unavailable/preparing states must not present old coordinates or an old label
  as current. Recovery restores the correctly associated supplied coordinates
  and generated overlay; labels never move coordinates.
- Repeated forced interruptions of generated-cache writes must recover on a
  later successful startup without accumulating the new abandoned temporaries.
  Cleanup is confined to recognized generated files inside the selected cache;
  preserve live/unknown owners, selected inputs, unrelated files/directories,
  symlinks and legacy anonymous artifacts whose ownership cannot be established.
  No process may be killed by cleanup. PID reuse must conservatively preserve.
- Every selected XML/TXT/CSV must remain byte-identical when its resolved path
  conflicts with runtime state, payload or index destinations, including input
  symlink targets. Refuse before any conflicting write or deletion and explain
  how to choose a different cache directory or port.
- Corrupt cache indexes, including valid JSON of the wrong type, must rebuild
  correctly or fail safely with actionable status. Same-cache concurrent viewers
  must preserve one another and read correct independently checked windows.
- Preserve input-to-CSV and actual code-only browser privacy restrictions,
  frame0/record1 mapping, H/A/D/X semantics, supplied sides, gaps, bounded stores,
  wall-clock rates, stale-seek protection, responsive transport and raw-file help.
- README and morning guide must provide reproducible commands and distinguish
  prepared deliverables, unknown team identity, current private repository and
  separately authorized public release/submission.

## Acceptance

A fresh fork-none reviewer freezes public oracles/invented recipes before
candidate access, without prior outcomes, expected output hashes or rationale.
Freeze the exact exported candidate throughout review. Fresh Python3.13 package
and processes must run actual uncached ATD inference twice, independently check
the exact199319-row contract, official validator, deterministic bytes, true worker
lifetime peak memory/wall time, safe failure and source/model/input preservation.
Root inspects artifacts, reproduces failures and checks real outputs.

Invented UI tests cover actionable failure/restart, truthful unavailable state,
mouse/keyboard, play/pause/seek/speed/steps, gaps, label independence, responsive
layouts, bounded caching, corruption/interruption and concurrent-owner safety.
Actual inputs, rows, labels, media and DOM/screenshots remain local and never
enter model-facing tools; actual browser checks use standalone local code that
emits only aggregate pass/fail/resources/hashes. No GT/scoring/tuning/retraining.

Historical tests apply only to their tested versions. A baseline soak cannot
establish changed-source soak acceptance. Retain original failed harnesses and
report emulation/capability limits, not invented native coverage.
