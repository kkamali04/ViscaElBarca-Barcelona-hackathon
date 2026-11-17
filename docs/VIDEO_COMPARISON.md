# Compare tracking with your video

Open the running **Touchline · Tracking replay** and keep the launcher running.
The pitch and video sit side by side on desktop and stack on smaller screens.
Possession is also shown above the pitch, beside its playback controls.

## Local MP4: linked playback

1. Under **Compare with match video**, choose your local tactical MP4.
2. Wait for **Local video ready**. Selecting it pauses the replay; it starts in
   independent mode so an unrelated recording cannot silently take over.
3. Check **Link controls — same tactical timeline**. For the supplied full
   tactical recording, leave **Video offset** at **0**.
4. Press **Play**. Play/pause, timeline seeking, frame steps and speed now share
   the native video's clock. The video's own controls also update the replay.

The file stays in your browser. There is no upload endpoint, whole-file
JavaScript copy, cloud model call or automatic media download. A large file
still needs a browser-compatible codec, such as H.264 in MP4. Reloading the page
requires selecting the file again. **Remove video** releases it and leaves
tracking paused at its current time.

Linking assumes the footage uses the same tactical timeline; it does not verify
the content. The **broadcast** video contains cuts and replays, and cannot be
aligned throughout with one offset. Use the tactical recording for comparison.

For an aligned clip, the equation is:

```text
video seconds = recording seconds + offset
```

For example, a clip starting 100 seconds into the recording uses offset **-100**.
Seeking to a recording frame outside the clip's coverage visibly unlinks video
and preserves the requested tracking frame. Invalid offsets keep the previous
setting and show an error. At the shared end, Replay starts at the first moment
covered by both sources. Browser scheduling may differ by a display frame;
this is not guaranteed compositor synchronization.

## Google Drive: independent preview

Paste an HTTPS `drive.google.com` **file** share link and click **Open Drive preview**.
The viewer constructs a sandboxed preview URL. It contacts Google only after
that action and does not change sharing permissions or store the link.

Drive has its own controls and clock: **it is not synchronized** with the pitch.
The browser's origin boundary prevents controlling the embedded player's media.
If access permissions, processing, cookies or an unavailable embed prevent
playback, choose the downloaded local MP4 instead. A preview loading does not
prove that its video is playable. Folder links and arbitrary websites are rejected.

## Motion and missing players

- **Natural display** uses bounded velocity-aware curves between plausible
  adjacent observations. Exact source positions remain exact at sample times.
  Interpolated speed is bounded at 15 m/s for player slots and 75 m/s for the ball.
  A curve falls back to the measured straight segment if needed to keep that bound;
  larger source changes hold then snap. These are presentation rules, not validated
  physical estimates or repaired tracking.
- **Exact samples** shows the original frame steps without interpolation.
- Short strokes show plausible measured movement direction, not body orientation.
  Yellow outlines flag an adjacent source discontinuity, including when paused.
- **Brief last-seen markers** are stationary dashed rings at a missing slot's
  most recent location, for at most **0.24 seconds**. They are unobserved,
  never count as current observations and never supply a ball position.
- Missing gaps are not filled with invented travel. Slots remain anonymous:
  the source's 46 catalog slots are not 46 simultaneous players. Reacquired slots
  can represent a different person.

The Observations card distinguishes observed, interpolated, held and last-seen
display states. Neither motion mode, linking video nor adjusting a viewing
offset changes source coordinates, model features, predictions or the CSV.

## If comparison stops

- **Video cannot be decoded:** select a complete browser-compatible H.264 MP4.
- **No corresponding video time:** choose the full tactical recording or correct
  the clip offset, then deliberately enable linked controls again.
- **Tracking unavailable:** correct/restart the tracking launcher and choose
  **Try again**. Video linking pauses; no current possession is claimed while
  the coordinate stream is unavailable.
- **An old illustration remains:** hard reload the served localhost address.
  See [Touchline troubleshooting](TOUCHLINE.md).

Native video behavior follows the browser's
[media timeline](https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/currentTime)
and [presented-frame callbacks](https://developer.mozilla.org/en-US/docs/Web/API/HTMLVideoElement/requestVideoFrameCallback).
Drive limitations follow its
[video support](https://support.google.com/drive/answer/2423694?hl=en) and the browser's
[origin boundary](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Same-origin_policy).

Tracking quality and possession accuracy are separate from playback quality.
This feature does not improve the frozen estimator or establish hidden-match scores.
