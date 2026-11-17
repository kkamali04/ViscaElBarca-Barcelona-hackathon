# Tracking replay v2

If a selected input conflicts with a runtime-state or generated-cache path,
startup refuses it without changing the file. Choose another cache directory
or port as instructed, then restart the launcher. Input symlink targets receive
the same protection.

This viewer replays the supplied ATD player and ball coordinates. It replaces the
old dashboard's illustrative pitch animation. It does not detect objects from
video, train a model, change possession predictions, or identify individual players.
The original estimator and review app remain frozen for reproducibility.

If preparation fails, the page explains the input or preparation problem. Correct
the selected XML/TXT or CSV, or resolve the stated disk/permission issue, then
restart the PowerShell launcher. **Try again** reconnects to the restarted server;
it cannot change files selected by an already running process. Transport failures
also show **Unavailable**, without a current prediction, until recovery.

At startup, the cache removes recognized generated temporary files only when
their owning process has exited. Live or unknown owners, unrelated files, links
and legacy anonymous temporary files are preserved. A malformed cache index is
discarded and rebuilt from the read-only inputs. Original downloads are preserved.

From this repository, after the normal Python environment setup:

```powershell
.\replay.ps1 -Demo
```

That opens **invented tracking**, useful for testing and sharing screenshots.
For your locally downloaded challenge data, choose the directory containing
`tactical/` and optionally an existing possession CSV:

For a complete fresh inference-to-viewer run:

```powershell
.\start-match.ps1 -DataDir 'C:\path\to\challenge\data'
```

This runs uncached ATD-to-label inference, writes a unique local/match-runs/
CSV/report, validates the output format and launches the coordinate replay with
that generated CSV. It does not read GT or an existing prediction CSV to generate
the answer. Use `-Port` for another free port or `-NoBrowser` for terminal-only
startup. Keep the launcher running; original inputs and prior outputs stay intact.

To replay a separately generated CSV without rerunning inference:

```powershell
.\replay.ps1 -DataDir 'C:\path\to\challenge\data' -Predictions 'C:\path\to\candidate.csv'
```

The default address is http://127.0.0.1:8771/. Use `-Port 8767` to choose another
free port, `-NoBrowser` to run without opening a tab, or `-CacheDir` for a private
cache outside the input directory. Stop with Ctrl+C, or from another shell:

```powershell
.\stop-replay.ps1 -Port 8771
```

If you chose a custom cache directory, pass the same `-CacheDir` when stopping.
Launchers use `.venv\Scripts\python.exe`; runtime dependencies are pinned in
`requirements-lock.txt`. They work when invoked by absolute path from another
directory. Opening this viewer does not run possession inference.

## Reading the pitch

- Play, pause, seek, single-frame steps and speed controls use ATD frame time.
  Frame zero corresponds to ATD record one. Standalone playback follows elapsed
  wall time; a deliberately linked local MP4 supplies the shared media clock.
- Player dots are anonymous track slots, colored by the metadata's home/away
  side. Fragmented slots do not establish a persistent player identity.
- Missing observations stay unobserved. Optional stationary dashed player
  last-seen markers fade within 0.24 seconds; they are not current observations.
- Natural display uses bounded adjacent curves with presentation guards of
  15 m/s for player slots and 75 m/s for the ball. Larger changes hold then snap;
  source endpoints stay exact. Exact samples disables interpolation. No gap is
  bridged and no ball position is invented. Eight metres of pitch padding remain;
  finite positions beyond it are counted separately from missing data.
- The optional CSV supplies the current H/A/D/X possession state. Without a CSV,
  coordinates still replay, and possession is explicitly unavailable. A valid
  CSV initially opens at its first non-X frame; all frames remain seekable.

H and A mean home/away possession with the ball alive. D means dead ball. X means
**no answer**: it does not establish whether the ball is in play. The overlay
never determines marker positions, including when its label is X.

## Storage and verification

Preparation streams observations into a private disk cache under
`local/replay-v2/`. It reads original files without moving or altering them.
Content hashes bind the metadata, tracking, optional CSV and parser version;
cache bytes are checked before reuse and while serving windows. The browser
retains at most three 250-frame coordinate windows. Tracking alone needs no video
decoder or GPU. Optional local comparison uses one native browser video decoder
and a file object URL, with no whole-file JavaScript buffer or upload. Changing
the CSV currently rebuilds the combined coordinate/label cache.

## Compare the actual footage

Choose the local tactical MP4 and intentionally enable **Link controls — same
tactical timeline**. Full tactical offset is 0. Native playback, timeline seeks,
steps and speed share the video clock. Clips need the documented viewing offset;
broadcast cuts/replays cannot be aligned throughout with one offset.

An optional Google Drive file link opens a sandboxed **independent/manual**
preview. It cannot share our controls; permission/cookie/processing failures use
the local-file fallback. No Drive request occurs until the user clicks its button.
See [the video and motion guide](docs/VIDEO_COMPARISON.md) for all controls,
coverage boundaries, source states and limitations. No CSV or model is modified.

Data, caches, CSV outputs and virtual environments are ignored locally. Never
add challenge inputs, tokens or large originals to Git. The tracked size hook
also rejects large files; Git itself has no size-based `.gitignore` syntax.

Requirements and acceptance criteria: [PRD](specs/005-tracking-replay/PRD.md),
[contract](specs/005-tracking-replay/CONTRACT.md),
[research](specs/005-tracking-replay/RESEARCH.md).
Current evidence and remaining limits are recorded in
[replay checkpoint](replay_v2/PROJECT_STATE.md). A moving pitch is a visualization
check, not evidence of improved possession accuracy or hidden-test performance.

Restricted match inputs may be processed locally by code. Model-facing browser
tests and screenshots must use invented tracking only.

## Opening the viewer correctly

Open the localhost address printed by a launcher. Double-clicking the static
HTML file displays launch instructions because modules need the local server.
If no application is running, start it before opening the link. The demo displays
invented coordinates and **No CSV overlay**; use start-match.ps1 with authorized
ATD inputs to generate real predictions. The replay controls sit above the pitch
on desktop and mobile so Play is reachable without scrolling past the canvas.
