# Replay v2 wire/interface contract

Python module `replay_v2`, independent of original frozen review app.
CLI: `python -m replay_v2 --demo --port 8771`; local mode accepts `--data-dir`
(directory containing tactical/), optional `--predictions` CSV and `--cache-dir`.
Default cache lives under repo `local/replay-v2/`; never copy original datasets.

GET `/api/health` is safe aggregate metadata only:
`{app:"touchline-tracking-replay",version:2,mode:"demo"|"local",status:"building"|"ready"|"failed"}`.

GET `/api/replay` returns metadata. Building/failed states have status/message;
ready includes mode,status,frames,fps,pitch:[105.3,68], slots:[{slot:0,side:"H"},...],
chunk_frames:250, row_floats:2*(slots.length+1)+1, initial_frame, predictions_ready,
label_codes:["X","H","A","D"]. Slot integers identify ordered ephemeral ATD
slots only; side is H/A. Ball object follows all player slots. Coordinates are
metres. A final float per row is prediction code 0..3, or NaN when no CSV exists.
Metadata may include aggregate progress, source/cache hashes and preparation
timing. Never include raw records/errors/paths in safe error messages.

GET `/api/frames?start=N&count=C`: C integer 1..250, N integer 0..frames-1.
Truncate at the last frame. Return `application/octet-stream`, float32 little
endian, shape [actual_count,row_floats], player XY in slot order, ball XY, label.
Missing/partial-NaN observations become a pair of NaNs. Do not invent speed-based
coordinates. Headers `X-Start-Frame`, `X-Frame-Count`, `X-Row-Floats` bind payload.
Invalid queries 400; not-ready 409; prohibited origins/hosts 403; unknown routes404.
No arbitrary file serving, CORS, raw video/data downloads or unbounded windows.

GET `/`, `/static/app.css`, `/static/app.js`, `/static/clock.js` serve only fixed
assets. App CSS/JS may have separately imported local static helpers only if
backend allowlist is extended explicitly before source freeze.

Browser canvas has id `pitch`; seek input id `seek`, button `play`, speed select
id `speed`, text id `clock`, status id `status`, current state id `possession`,
ball status id `ball-status`. Canvas overlays are derived only from each supplied
frame's XY. In demo, clear permanent "Invented tracking" wording. In local mode
use "Supplied tracking". Visible track-slot warning; no player/jersey identities.

Clock helper exported from `/static/clock.js` as ES module. Injectable timestamps
allow deterministic delayed-callback tests without real sleeps. Anchor-based time
never caps/discards elapsed seconds. Stop cleanly on final frame. Browser keeps
<=3 chunks and cancels/discards stale seeks; interpolate only adjacent finite
coordinates, never through a missing frame. Large discontinuities snap instead
of drawing invented travel; document any fixed visual interpolation threshold.

Optional local shutdown route may use nonce authentication but must not expose
private paths or nonce in health/log output. No other POST mutations permitted.

## Clarifications from independent contract review

- ATD grammar is the public organizer EPTS export: record ID, colon-separated
  semicolon player groups, colon-separated ball group; each group contains three
  comma-separated declared channels. Metadata declares normalized position_x,
  position_y, speed units, ordered PlayerChannelRef/BallChannelRef, Score home/away,
  and startFrame=1/endFrame=N. Namespaces may be present. All N ordered IDs1..N
  are required; duplicates/skips/decreasing/extra IDs fail. Metadata must declare
  a positive finite fps; generic fixtures can use another rate, actual tactical
  input is 25fps. No broadcast timeline substitution.
- NaN/partial NaN XY means missing: emit pairNaN. Infinite numeric channels or
  coordinates exceeding float32 metre storage fail safely, never become invented
  valid coordinates. Finite off-pitch values survive encoding unchanged.
- Interpolate only between adjacent observed pairs whose distance is <=8 metres.
  Larger discontinuities snap to observed endpoints; this is a fixed display
  policy, not an inferred track repair or a model feature. Pitch viewport uses
  8metres padding. Values beyond the viewport remain preserved in the API and
  are counted/labeled outside view, not silently clamped onto a field boundary.
- initial_frame is first non-X prediction if a valid CSV contains one; otherwise
  first frame with an observed player or ball; otherwise0. Users can still seek
  to every frame, including pregame/halftime.
- Coordinate-cache identity binds content hashes of metadata/raw, parser version,
  dimensions/fps/pitch. Validate its length/content hash before reuse; corrupted,
  truncated or stale cache is rebuilt atomically or safely rejected. Never serve
  stale bytes. Prediction contents are validated/read freshly for the current
  process, with their own hash; changing CSV may reuse coordinate bytes but must
  change the label payload. Speed channels never determine XY.
- Optional prediction CSV has exact header `frame,label`, exactly N rows ordered
  `0..N-1` with labels only H/A/D/X, no duplicate/skipped/extra frames. Reject
  malformed CSV without altering it. Generic fixtures use metadata N; actual
  challenge predictions require199319 rows. No CSV is a supported explicit mode.
- Measure cold/warm actual preparation and true worker peak working set. Resource
  acceptance target on this workstation: cold preparation <=180s and peak working
  set <=256MiB for the supplied199319-frame tactical input. Treat target failures
  as findings, not grounds to weaken the target after seeing the result. Browser
  coordinate cache <=3 windows, each <=250 frames, API response <=1MiB with an
  explicit128-player-slot limit. No full-frame video or full-match browser tensor.
