# Implementation blueprint and proof plan

Recommendation: one Python tactical-data pipeline, with independent evidence
functions and a small temporal decoder. Preserve the existing fallback. This is
a proposed implementation, not a claim that a new estimator has been validated.

## End-to-end sequence

```text
tactical ATD XML/TXT -> valid positions + teams + frame masks
                             |
                    distances / motion / observation quality
                             |
tactical Smart Tagging -> weak team/restart context
                             |
                 home / away / dead evidence
                             |
                 per-half sequence decoding
                             |
                   deterministic frame CSV
                             |
                 official format validator
```

Homography/video are a separate local inspection path. No frontend, API server,
database, job queue or deployment is needed to produce the submission.

## Slice 1: trustworthy inputs and team evidence

Use a streaming raw loader based on the official format. Require exactly one
record for each ID 1..199319, correct channel counts, and known team membership.
Reject malformed, duplicate or missing rows; do not silently pad or trim. Keep
player slots anonymous. Do not use legacy corrected-tracking offsets for this ATD.

Represent positions as arrays plus observation masks. Convert differences into
metres by scaling x by 105.3 and y by 68. Homography is not part of this calculation.
For each frame derive minimum observed distance per team, distance difference,
number of usable observations, and ball-motion plausibility. All-missing teams
must stay unknown; avoid nanargmin or infinity arithmetic producing a default H.

Proximity is a candidate observation, not proof of control. Use short, sustained
support and local ball-motion consistency to strengthen it. A genuine one-touch
control can be short, so do not turn the docs' illustrative multi-pass examples
into a universal minimum-duration or minimum-pass rule.

Acceptance: synthetic team-slot permutations preserve team evidence; malformed
frames fail; missing observations yield unknown evidence; a pass crossing an
opponent's position does not automatically become a confirmed turnover.

## Slice 2: live/dead evidence and missingness

Keep ball visibility separate from ball-in-play state. Useful possible evidence:
temporally coherent ball excursions beyond the boundary, ball stillness with
appropriate player movement/configuration, automatic set-piece context, and
subsequent motion consistent with a restart. None is universally sufficient alone.

Differentiate only adjacent trustworthy observations in the same half/continuous
run. A slot disappearing and reappearing is not a physical trajectory. A large
ball jump can be a tracker error. Do not interpolate a long gap, smooth across
halftime, or fabricate zero speed when motion is unknown.

Short bounded interpolation may support geometry, but retain an imputed mask and
lower confidence. It must not become independent confirmation of the same event.
Do not use a pandas interpolation limit that partially fills the first portion
of a long gap and then accidentally treats it as a fully reliable short gap.

During unobserved intervals, previous possession is a useful prior. It is not a
hard prohibition on a change supported by other evidence. Long-gap transitions
remain uncertain. Missing ball does not require X, and X does not eliminate the
cost of a wrong carried-forward label under the temporal scorer.

Acceptance: a live stationary ball and a missing ball do not independently force
D; a supported stoppage splits two same-team possessions; a known restart ends D.
These require constructed or independent labelled tests, not annotations of this
match.

## Slice 3: soft tactical context

Normalize code/tag case and handle N/A explicitly. Offensive phases support the
named team; defensive phases weakly support the opponent. Set-piece intervals
bracket a possible restart and can include preparation plus live action. Their
start/end timestamps are not exact possession boundaries. Goals also provide
context rather than a precise blanket H/A/D interval.

Combine overlapping tags with bounded support rather than counting every phase
as an independent vote. Tags and tracking were generated from related footage;
agreement is not independent validation. If calibrating tag reliability against
unlabelled geometric anchors, call it internal consistency, not measured accuracy.

Acceptance: correct offensive/defensive polarity, ignored unknown teams,
deterministic resolution of contradictory tags, no hard erasure of a supported
short opposing possession inside a long phase.

## Slice 4: temporal decision

Start with a state machine for observable transitions. The credible alternative
is an exact three-state penalised decoder using H/A/D scores and transition
costs. Describe heuristic scores honestly; an arbitrary weighted sum is not a
calibrated probability or a learned HMM.

Prefer persistence without making it impossible to detect short possessions.
Decode each half independently. Use the organisers' published graded/kickoff
boundaries and explicit pre-second-half-kickoff D interval; do not infer that
the first frame of every half is D. Outside scored regions X is appropriate.

Specify tie behavior. Our synthetic probe found an equally scored H -> neutral
gap -> A transition can move by the whole gap with a different tie convention.
Record the interval of weak boundary evidence in the local trace. Offline
lookahead can confirm a turnover and backdate to its evidence onset, but cannot
identify the real instant within a totally unobserved interval.

Acceptance: passes through gaps do not fragment; genuine supported H/A changes
are retained; D separates same-team possessions; no half-state leakage; repeated
runs produce identical bytes. Inspect boundary displacement and count changes
as well as frame agreement. Do not choose the model on public-window scores.

## Independent validation protocol

The best next source is other-match data with explicit ball status and usable
ownership/event semantics. The [Sportec Open DFL record](https://springernature.figshare.com/articles/dataset/An_integrated_dataset_of_spatiotemporal_and_event_data_in_elite_soccer/28196177)
lists seven matches and a 2.45 GB archive. Acquisition and adapter implementation
were not done in this research pass.

1. Inspect a single other match's schema and status/ownership semantics before
   downloading or adapting everything. Verify it is not the challenge match.
2. Define the H/A/D mapping and its limitations before fitting anything. Event
   timestamps/last-touch attribution may disagree with controlled team possession.
   Derived labels must not be described as equivalent to corrected challenge GT.
3. Split by entire match, with a final held-out match. Random frame/window splits
   leak nearly identical adjacent sequences. Keep tuning and final evaluation apart.
4. Evaluate on original data and controlled corruptions: block ball occlusion,
   slot fragmentation, position noise and false ball jumps. Whole-match gaps are
   not well represented by independent random NaNs. Do not match corruptions to
   hidden labels or tune to challenge possession counts.
5. Use the organiser's metric definitions where target semantics allow. Report
   frame macroF1 and possession spellF1, boundary error, H/A/D confusion and
   runtime separately. External gains are not a guaranteed challenge gain.

If the external adapter/labels are not usable within a bounded first work block,
retain the transparent classical model and synthetic checks. Report limited
validation explicitly. Do not replace independent labels with the method's own
pseudo-labels and call cross-validation proof. Algorithmic pseudo-label learning
is permitted, but evaluating on those same labels is circular.

Freeze constants and design before the public five-minute sanity check. Use
that check for frame alignment, format and side/label interpretation only. A
different public score is not permission to tune or select the new method.

## Efficiency and language decision

Keep Python. The synthetic three-state loop took 3.28 seconds for the whole
199319-frame sequence. This is not the full feature-loader/video runtime, but it
removes an unsubstantiated need for another language for decoding.

A float32 full-frame distance matrix for 46 slots is about 36.7 MB decimal;
two coordinate channels about 73.3 MB before temporaries. Chunk feature generation
to reduce peak memory and keep only small rolling windows where possible. These
are storage arithmetic, not measured process RSS. Stream video frames if later
needed; do not materialise the whole decoded video in memory.

Use NumPy for distance reductions and prefix sums for rolling evidence. Profile
parsing, features and decoding separately with perf_counter before optimization.
Only consider Numba/C++/Rust if a reproducible hot path exceeds the team's actual
iteration budget. No GPU/cloud service is required for the initial method. No
claim is made about a GPU/CPU accuracy advantage or cloud pricing.

## Ranked backlog

| Priority | Observable outcome | Stop/acceptance condition |
|---|---|---|
| 1 | Strict loader and explicit evidence arrays | Alignment checks and synthetic edge cases pass |
| 2 | Live/dead logic plus team control in one sequence | One complete deterministic CSV validates; failure cases have local reasons |
| 3 | Independent other-match evaluation | Documented semantics and held-out evidence support a selection; otherwise disclose gap |
| 4 | Bounded tag integration | Does not erase constructed opposing-control/restart cases; independent ablation if available |
| 5 | Reproduction/documentation package | Fresh documented command regenerates exact bytes; private inputs ignored |

Defer full video detection, player identification, unsynchronised broadcast
fusion, dashboards and new languages. Revisit only for a specific failure that
the available structured signals cannot resolve and with time to verify it.
