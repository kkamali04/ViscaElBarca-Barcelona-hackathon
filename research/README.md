# Research decision packet

**November 15 implementation follow-up:** the proposed pipeline below is now
implemented and independently tested. [SOLUTION.md](../SOLUTION.md) is the current
method/result record. It includes an original small trained emitter, exact
decoder, an untouched external holdout, fixed stress tests, full-frame runtime
and memory measurements, and a deterministic validated submission candidate.
The remainder records the preceding research decision process.

This packet answers what we are building, which files matter, which existing
approaches transfer, and what to implement before November 17. Research started
November 14, 2026 Eastern (November 15 UTC). The three-person team and receipt of
the submission email are user-reported; the team name, exact registration status
and available hours are accepted unknowns, not blockers for technical research.

## The result in ordinary language

We are building an algorithm that watches the match through its supplied data and
produces a time history: **Barcelona controls the ball; then Athletic controls
it; then play stops; then it restarts.** It labels every video frame, rather than
only reporting one possession percentage for the whole game.

The required output is one CSV with 199,319 rows. H means Barcelona controls a
live ball, A means Athletic controls it, D means play is stopped, X means no
answer. Control persists through a pass or loose-ball contest until the opponent
gains control. A deflection does not automatically transfer possession. A stopped
ball in someone's control can still be live. A ball lost by the tracker can still
be live. These distinctions are the engineering problem.

The competition also requires reproducible public source and a technical document.
A timeline, possession percentages or a replay viewer can explain results later,
but they do not replace the frame CSV or improve its ranking by themselves.
See the [official definitions](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/CHALLENGE.md)
and [submission contract](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/SUBMISSION.md).

## Files to use first

All supplied files are under `../more-than-a-hack-2027-main/data/`.

| File in tactical/ | What we learn from it | Initial role |
|---|---|---|
| BAR-ATH_tactical_atd.xml | Track slots, team membership, coordinate metadata | Required input |
| BAR-ATH_tactical_atd.txt | Ball and tracked-player positions over time, plus exported speed | Required input |
| BAR-ATH_tactical_smart_tagging.xml | Automatic offensive/defensive phases and restart windows | Weak contextual evidence |
| BAR-ATH_tactical_homography.csv | Maps pitch coordinates to image pixels | Local overlays/debugging; not needed for metric distances |
| BAR-ATH_tactical.mp4 | Actual scene: control, deflections, restarts, occlusion | Local debugging and optional algorithmic visual evidence |

The four broadcast assets are optional. They have a different timeline with cuts
and replays; direct frame-by-frame fusion would be wrong. Keep them, but defer
alignment until there is evidence that tactical-only inference is insufficient.
The public ground-truth CSV under evaluation/gt is a pipeline check only, never
a tuning or model-selection set. [Official data contract](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/DATA.md).

## Recommended stack and architecture

**Use the existing Python/NumPy/pandas environment and a small temporal model.**
Parse the tracking once, calculate geometry and observation quality, derive weak
tag and live/dead evidence, then decode a coherent H/A/D sequence per half. Keep
the confidence signals separate from the final decision so failures are visible.

This fits the deadline, the working baseline, the available structured data and
the modest sequence size. It gives up the potential expressiveness of a trained
video or graph model. Its biggest limitation is uncertainty during long gaps,
especially when control changes while the ball is unobserved. More persistence
cannot manufacture missing evidence.

The alternative is a learned temporal model trained on independently labelled
other matches, possibly a small tabular/TCN emission model plus the same decoder.
That becomes preferable only if compatible other-match labels, a stable loader,
and held-out gains are established early enough to finish reproduction. Training
a new detector/tracker or adapting a full graph/video system first is a higher
integration risk. See [implementation blueprint](IMPLEMENTATION_BLUEPRINT.md).

## What changed after research

- **Public competitors exist.** Three exact-competition repositories contain
  additional possession code, including temporal decoding, movement-based
  stoppage evidence and tag priors. We inspected generic code, not their output
  CSVs, learned weights or tuned parameter files. Registration, compliance and
  hidden scores are unknown. Their code confirms plausible patterns, not a
  winning recipe. [Source comparison](COMPARABLES.md).
- **Dead-ball detection deserves its own workstream.** The 2022 event paper uses
  provided play-status information or a visibility proxy. PathCRF runs within
  known in-play episodes. Neither removes our live/dead problem.
- **An off-the-shelf neural result is not a benchmark for us.** The 2023 TCN paper
  predicts H/A/D, but trains on other labelled matches selected for relatively
  good ball coverage. Its frame accuracy does not establish challenge spellF1.
- **Python computation is adequate for the decoder.** Our deliberately simple
  synthetic three-state loop processed 199,319 invented frames in 3.28 seconds
  on this machine. This is a component timing, not a football-accuracy or
  end-to-end benchmark. No evidence supports switching to C++/Rust now.
- **Tie handling changes boundaries.** With identical evidence surrounding a
  20-frame neutral gap, two equal-score tie conventions placed a turnover at
  frame 10 versus 30. A smooth-looking sequence can hide an arbitrary boundary.
  Explicit uncertainty and tie semantics matter.

## Completed artifacts versus proposed work

Completed: public-source research, generic method comparisons, Hyperagent
research/review calls, an eight-case synthetic decoder probe, a local asset
quality profile, and this decision packet. The baseline from setup is preserved.

- [Synthetic check results and timing](../reports/synthetic-decoder-probe.json)
- [Synthetic research script](synthetic_decoder_probe.py)
- [Private owner-only data-quality report](../local/private-data-quality.json)
- [Evidence ledger](EVIDENCE_LEDGER.md)
- [Independent model review and corrections](MODEL_REVIEW.md)
- [Implementation sequence and validation protocol](IMPLEMENTATION_BLUEPRINT.md)

The private report contains aggregate diagnostics only and remains Git-ignored.
Its contents were not sent to the research models. It reads no ground truth,
does not label frames, and does not demonstrate accuracy. The synthetic checks
use wholly invented evidence and establish software properties only.

Not completed: a new competitive estimator, independent-match accuracy testing,
neural training, video-based event inference, publication, or final submission.
No hidden score or top-20 probability has been measured. We should preserve
that distinction even if a method looks convincing.

## Immediate decision

Keep the validated fallback. Build one original tactical-data method with an
explicit live/dead branch and temporal decoding. Reserve time for exact
reproduction and the document. Do not spend the remaining days on a dashboard,
new language, cloud architecture or chasing more papers after the evidence has
converged. The decisive next evidence is an independent validation result, not
another collection of promising links.
