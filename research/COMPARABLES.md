# Public implementation and component comparison

Observed November 14 Eastern / November 15 UTC, 2026. Method-source review only;
no external repository was cloned, installed or executed. No competitor output
CSV, model weights, match-derived arrays or tuned parameter file was loaded.

## Exact-competition public implementations

These are code comparables. A public fork does not establish team registration,
rules compliance, official submission, or a leaderboard position. Root inspection
was bounded to repository trees, latest commit metadata, and the files below.

| Repository and observed head | Inspected method | What transfers | What should not be copied |
|---|---|---|---|
| GTT-TalentArena/more-than-a-hack-2027; 0ad8c06cf243d2cceb467ac7c76e7db5a9c597e7; 2026-11-11 | solution/temporal_control.py and solution/a_opus/tags.py | Sustained control evidence; explicit decoding; half reset; offensive/defensive tag polarity | Their parameter choices, large experiment/tooling surface, or any assumption their private performance is established |
| radouane99/more-than-a-hack-2027; 5c3e3614ef539814a6aee50dd774c92c5daecbaa; 2026-11-14 | possession_v2.py | Collective movement as additional stoppage evidence; a NaN-aware moving average; explicit ball-observation continuity; streaming-format checks | Fixed probability weights or treating unsupervised movement clusters as real live/dead labels; dashboard work is not our priority |
| saadyaq/more-than-a-hack-2027; f387b7a69cc486e922521d090353e24af365657e; 2026-11-14 | possession/decode.py | Three-state transition costs; deterministic tie handling; independent half decoding | Learned weights, tuning grids and parameter files; its decoder fixes the first frame to D, which must not be blindly applied to the first-half kickoff |

Pinned source links:

- [GTT temporal control](https://github.com/GTT-TalentArena/more-than-a-hack-2027/blob/0ad8c06cf243d2cceb467ac7c76e7db5a9c597e7/solution/temporal_control.py)
- [GTT tag mapping](https://github.com/GTT-TalentArena/more-than-a-hack-2027/blob/0ad8c06cf243d2cceb467ac7c76e7db5a9c597e7/solution/a_opus/tags.py)
- [Movement-based method](https://github.com/radouane99/more-than-a-hack-2027/blob/5c3e3614ef539814a6aee50dd774c92c5daecbaa/possession_v2.py)
- [Saadyaq decoder](https://github.com/saadyaq/more-than-a-hack-2027/blob/f387b7a69cc486e922521d090353e24af365657e/possession/decode.py)

No competitor code was copied into our synthetic probe or baseline wrapper.
Top-level source licences include the inherited organiser MIT notice; root
confirmed [radouane99's licence](https://github.com/radouane99/more-than-a-hack-2027/blob/5c3e3614ef539814a6aee50dd774c92c5daecbaa/LICENSE).
That does not grant rights to the restricted match assets or prove provenance
of every addition. Recheck any specific component's notices before reusing code.

## Adjacent components

| Component | Evidence | Recommendation and limit |
|---|---|---|
| Organiser baseline | Public Python source already reproduced locally; NumPy/pandas | Retain as fallback and input-format reference. Missing-ball-as-D and nearest-player ownership are its deliberate weaknesses. |
| kloppy | [BSD-3-Clause licence](https://github.com/PySport/kloppy/blob/HEAD/LICENSE); organiser optional loader already targets it | Useful for a new provider/independent-match adapter. Not required to parse the challenge, and installing it is not an accuracy improvement. |
| DataBallPy | Targeted source inspection via Hyperagent; critical parser line independently confirmed by root | Borrow numerical concepts selectively. Its Metrica parser sets missing ball_x to dead; its team-possession helper uses event data. Neither is a drop-in solution here. |
| PathCRF | Official code/paper; [MPL-2.0 licence](https://github.com/hyunsungkim-ds/pathcrf/blob/HEAD/LICENSE); repository describes checkpoints and Sportec preprocessing | Strong research reference for constrained inference, but player-edge representation, preprocessing and known in-play episodes add work. Do not load checkpoints before confirming compatibility and notices. |

DataBallPy source inspected at a2ab78c4c7ba3ad964ab26dd65dd848de3939d18:

- [Metrica parser](https://github.com/Alek050/databallpy/blob/a2ab78c4c7ba3ad964ab26dd65dd848de3939d18/databallpy/data_parsers/tracking_data_parsers/metrica_tracking_data_parser.py)
- [Individual possession helpers](https://github.com/Alek050/databallpy/blob/a2ab78c4c7ba3ad964ab26dd65dd848de3939d18/databallpy/features/player_possession.py)
- [TrackingData schema](https://github.com/Alek050/databallpy/blob/a2ab78c4c7ba3ad964ab26dd65dd848de3939d18/databallpy/schemas/tracking_data.py)

Root verified the parser assignment itself; the more detailed dependency and
helper review is attributed to the independent agent in MODEL_REVIEW.md. No
runtime correctness, install timing or package security claim is made.

## Interpretation

These sources confirm the initial direction rather than requiring a stack change.
The valuable pattern is a small pipeline with explicit observation masks,
control evidence, live/dead reasoning and sequence constraints. The main
competitive uncertainty is feature quality and independent validation, not
whether Python can process a three-state sequence.

More forks or stars would not resolve that uncertainty. This comparison does not
estimate rank, and public self-reported scores are not official hidden scores.
