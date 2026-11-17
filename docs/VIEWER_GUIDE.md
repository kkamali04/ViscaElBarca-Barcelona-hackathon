# Reading the tracking replay

The coordinate replay displays invented demo positions or positions supplied in
the ATD files. The optional possession overlay separately reads a CSV produced
by the estimator. This viewer does not analyze video, assign stable player
identities, detect passes or shots, or improve the possession model.

## Start with the source badge

| Badge | What you are viewing |
| --- | --- |
| **Invented tracking** | Generated demo coordinates, with **No CSV overlay** in the possession panel. Suitable for screenshots and browser tests; not a real-match accuracy check. |
| **Supplied tracking** | Your locally selected ATD observations, optionally paired with an existing possession CSV. The badge identifies the source, not the correctness of its observations. |

Use `.\replay.ps1 -Demo` after the [README setup](../README.md). The normal teammate
address is [localhost:8771](http://127.0.0.1:8771/). The owner's existing local
session uses port **8767** with a separate private cache. Choose an available port
with `-Port`; use `-NoBrowser` when you want to open the address yourself.

Keep the launcher running while viewing. Stop with Ctrl+C, or
`.\stop-replay.ps1 -Port 8771` from another shell. If you selected a custom
`-CacheDir`, give the stop script the same directory. See [REPLAY.md](../REPLAY.md)
for supplied-data commands and cache details.

For the complete match workflow, run
`.\start-match.ps1 -DataDir 'C:\path\to\challenge\data'`. It reads the tactical
ATD files, generates and checks a fresh possession CSV, then opens this viewer
with that output. The CSV is an algorithmic result, not an answer key supplied
to inference. The organizer permits tracking-only algorithms; video decoding is
optional, while one output label per video frame is required.

Open the printed localhost address. Raw static HTML now shows launch help instead
of a broken Connecting screen. Play/seek/speed sit above the pitch. The original
review application's illustrative pitch is not this coordinate replay.

## What the dots mean

| Marker | Meaning |
| --- | --- |
| **Mint / green player dot** | An observed home-side track slot. |
| **Peach / orange player dot** | An observed away-side track slot. |
| **Small white ball dot** | An observed ball position. |

Team membership comes from ATD metadata. A slot is an anonymous tracker channel,
not a shirt number or a person. The organizer describes **46 tactical track
slots for 22 players**: tracking can fragment, duplicate or switch identities.
Fewer or more than 22 dots does not prove that the number of players changed.
These limits are documented in the
[organizer's ATD description](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/DATA.md#what-it-does-not-contain).

The supplied ATD is automatic and uncorrected. The organizer reports the ball
missing on **43% of all frames** and **41% of graded frames**. This is a property
of the supplied tracking, not a viewer accuracy measurement. See
[organizer DATA.md](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/DATA.md).

Missing coordinate pairs disappear. Adjacent finite observations interpolate
only for display, up to eight metres per frame. Larger jumps snap; missing gaps
are not bridged. The pitch includes eight metres of padding. Finite positions
beyond that area are counted as **outside view**, separately from missing slots.
The Observations card explains what is currently available.

## Possession is a separate overlay

| CSV label | Meaning |
| --- | --- |
| **H** | Home possession, ball alive. |
| **A** | Away possession, ball alive. |
| **D** | Dead ball: the ball is not in play. |
| **X** | No answer: the system declines to guess, or the frame has no ground truth. It does not establish whether play is live. |

These meanings follow the
[organizer's challenge contract](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/CHALLENGE.md#the-four-labels).
The panel displays the attached CSV's existing label; it does not infer a new
label from the visible dots. A missing ball dot is not automatically `D` or `X`,
and `X` does not hide observed coordinates. Without a CSV, the panel reads
**No CSV overlay** while coordinates remain playable.

The default estimator is frozen **noise-v2**. Its version name identifies the
model; the replay supplies no new evidence about its accuracy. Format validation
checks CSV structure, not whether possession is correct. Hidden-match performance
remains unknown.

## Playback and time

Press **Play**, use **Space** to play or pause, drag the timeline to seek, or use
the arrow buttons for single-frame steps. The speed menu changes playback rate.
The clock follows recording time, including non-playing stretches; it is not the
referee's match clock. Frame **0** corresponds to ATD record **1**, following the
[published frame alignment](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/DATA.md#frame-alignment).

When a CSV contains a non-X label, the viewer initially seeks to the first such
frame. All frames remain seekable. Source files are snapshotted at startup:
restart the viewer after changing tracking or CSV inputs.

## Which local app to open

| Launcher | Default port | Purpose |
| --- | --- | --- |
| `.\replay.ps1` | **8771** | Coordinate replay from ATD, with an optional existing CSV overlay. |
| `.\review.ps1` | **8765** | Original estimator controls, CSV generation and review exports. Its pitch animation is illustrative, not an ATD position replay. |

The legacy 106-member code-only ZIP contains the original review app and excludes
the coordinate replay. Its instructions are in [MVP_REVIEW.md](../MVP_REVIEW.md).
Use the full Git repository for the replay described here.

Supplied inputs and prediction rows may be processed by local code, but must not
be printed, attached to models, uploaded, or opened through model-facing browser
tools. Use **Invented tracking** for screenshots shared in agent workflows. Keep
original match assets, CSVs, private packs and caches outside Git.
