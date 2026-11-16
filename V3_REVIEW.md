# Possession estimator: v3 experiment and owner review

Snapshot: **November 15, 2026, 11:51 PM New York / November 16, 04:51 UTC**.
The two requested ideas are implemented and the fixed training/selection study
has finished. **No challenger met the preregistered eligibility gate. The frozen
noise-v2 MVP remains the default.** No new test, v3 release package, promotion or
competition submission has occurred.

## What we are making

The task is to recover **team possession over time**, including dead play. The
deliverable is a `frame,label` CSV with exactly **199,319 ordered frames**:
`H` = home possession, `A` = away possession, `D` = dead ball, and `X` outside
the declared active periods under the exact output contract. It does not name
the individual player with the ball.

Our inference uses the supplied **tactical tracking XML/TXT**: player/ball
coordinates, observation availability and period metadata. It does not run
computer vision on either large video. Video is optional for the owner's local
review; automated agents use synthetic UI fixtures. Missing ball observations
must not automatically mean dead play.

The organizer ranks complete **H/A possession spells**, using spell F1 over
temporal IoU thresholds 0.3–0.7. Getting individual frames mostly right can still
fragment a real possession and score poorly. A polished interface supports
review; it does not change the automatic ranking. See the organizer's
[task](more-than-a-hack-2027-main/README.md) and
[evaluation rules](more-than-a-hack-2027-main/EVALUATION.md).

## The two ideas and implementation

| Idea | Implemented behavior | What it can establish |
| --- | --- | --- |
| Turnover-aware decoding | A small typed boundary classifier uses 28 observation-derived features. It lowers the three-state decoder's switching cost near supported team changes or live/dead boundaries. A flattened-support control separates boundary timing from generic penalty relaxation. | A testable attempt to preserve short genuine changes without adding false turnovers; the present study did not earn promotion. |
| Broader, robust training | Two genuine licensed matches train two small boosted-tree emitters with balanced match/class/condition weights. Fixed missing-ball and combined corruptions are compared with a curriculum replacing long ball gaps with stale-player coordinates. | Agreement under six declared synthetic conditions on one selection match, with provider/annotation limitations. |

The implementation is isolated in [experiments/v3](experiments/v3/). It includes
role-gated ingestion, verified caches, deterministic corruption, numeric model
export, scoring, one-attempt access records, resource supervision and guarded
release tooling. Training uses scikit-learn; the intended inference path uses
numeric trees and NumPy without scikit-learn, SciPy or a GPU. Whole-worker
inference performance still needs exact-package measurement for any future
eligible release.

The professional [turnover PRD](specs/003-possession-improvements/PRD-TURNOVER.md)
and [multi-match PRD](specs/003-possession-improvements/PRD-MULTIMATCH.md) are frozen
design snapshots. Their original pending-design headers are historical, not the
current execution status. The [protocol](specs/003-possession-improvements/protocol.json),
[task tracker](specs/003-possession-improvements/tasks.md) and
[latest checkpoint](PROJECT_STATE.md) provide the execution trail.

## Research and reuse decisions

Public-source research used Exa/Firecrawl and pinned primary papers/repositories
through **November 15, 2026**. Licenses and source revisions are recorded in the
[turnover research](research/v3/turnover/RESEARCH.md),
[data research](research/v3/data/RESEARCH.md) and
[workflow research](research/v3/workflow/REUSE.md).

| Source | Decision and reason |
| --- | --- |
| PathCRF, MPL-2.0; ASRF, MIT | Reuse the dynamic-transition and separate-boundary concepts. Their neural/video/player-identity assumptions do not supply a ready CPU tracking-to-H/A/D solution; no upstream application code was copied. |
| IDSSE / DFL data, CC BY 4.0 | Use the pinned 25 Hz tracking/control/state source with DFL attribution and Bassek et al. citation. Ten original files were integrity-verified locally; provider labels are not proof of challenge accuracy. |
| DataBallPy, MIT; ruptures, BSD-2-Clause | Physics/segmentation reference material. Neither is a team-possession oracle for these anonymous inputs; neither became a runtime dependency. |
| hsmmlearn, GPLv3; SkillCorner; Peral | Defer the archived compiled HSMM dependency, unresolved cross-provider label semantics, and unavailable/unverified reusable Peral implementation. |
| Spec Kit and Superpowers, MIT | Adopt requirements → plan → bounded tasks → independent review, with fresh blind acceptance and root reproduction. Avoid unnecessary generators, global upgrades and extra services. |

## Actual fixed experiment: results

Training used **J03WOH + J03WOY**; WOY's earlier selection history is retained.
**J03WPY alone** was the fresh selection match. Its six conditions were clean,
4-second ball gaps, 12-second ball gaps, combined corruption, stale players and
view gaps. These are **six correlated views of one game, not six independent
games**. The 9 candidates × 6 conditions produced all **54 planned rows** once.

The table reports equal-condition mean official spell F1; gains are absolute
percentage points relative to A. All eight challengers were ineligible.

| Candidate | Emitter / boundary treatment | Mean spell F1 | Gain, pp |
| --- | --- | ---: | ---: |
| A | Frozen noise-v2 / constant costs | 0.438746 | 0.0000 |
| F080 | A / flattened boundary support, α=0.8 | 0.440507 | +0.1762 |
| B080 | A / learned boundary timing, α=0.8 | 0.448049 | +0.9304 |
| C0 | Broader emitter / constant costs | 0.440510 | +0.1764 |
| C1 | Stale-player curriculum / constant costs | 0.442390 | +0.3644 |
| D0050 | C0 / learned boundary timing, α=0.5 | 0.446540 | +0.7794 |
| D0080 | C0 / learned boundary timing, α=0.8 | **0.449270** | **+1.0525** |
| D1050 | C1 / learned boundary timing, α=0.5 | 0.446031 | +0.7285 |
| D1080 | C1 / learned boundary timing, α=0.8 | 0.442345 | +0.3599 |

Eligibility required **at least +4.0000 pp** mean spell gain, alongside fixed
clean/class/condition non-regression checks. Best-scoring D0080 gained only
**+1.0525 pp**, a **2.9475 pp shortfall**. Every challenger failed the gain gate;
C0 also breached the condition non-regression bound. The protocol therefore
requires **stopping before fresh testing**, rather than choosing the best score
and calling it an accepted improvement. These are empirical selection results;
they establish neither statistical significance nor hidden-match performance.

Sources: [root aggregate observation](reports/v3-actual-selection-root-observation.json),
[independent disposition audit](reports/v3-selection-disposition-blind-audit.json)
and [current root reproduction/acceptance](reports/v3-selection-disposition-root-acceptance-r2.json).
The eligibility stop is **independently audited and root-reproduced**. This audit
checks aggregate arithmetic and provenance; it does not rerun raw match scoring.

## Timing, memory and verification boundaries

| Actual stage | Wall time | Actual worker OS peak working set |
| --- | ---: | ---: |
| Training stage, exactly three fits | **20m 37s** | **787.7 MiB** |
| Complete 54-row selection grid | **14m 59s** | **592.0 MiB** |
| Fresh v3 candidate input-to-CSV package inference | **Not run: eligibility stop** | **Not measured** |

These stage timings are not the time to process the challenge file once.
Worker peaks are distinct from sampled concurrent process-tree memory and the
12 GiB committed-memory Job ceiling. See the exact
[training receipt](reports/v3-actual-train-root.json) and selection receipt above.
Training exported all three numeric models with zero reported raw-score parity
error on the declared training/probe rows. This is export equivalence, not accuracy.

For the existing MVP, an [earlier accepted uncached full-file run](reports/mvp-final-root-acceptance-verification.json)
took **53.7 seconds** with **114.0 MiB** actual worker peak memory. That historical
run produced the complete 199,319-frame CSV; this campaign preserved its artifacts
and did not repeat that inference benchmark.

Fresh blind tests plus root reproduction accepted bounded design, functional and
synthetic supervised-CLI behavior: [G01](reports/v3-g01-root-acceptance.json) and
[complete synthetic G05](reports/v3-g05-root-acceptance.json). Separate strict
measurement-tool checks passed 29 mock cases and 30 corrected native synthetic
cases, with [root reproduction](reports/v3-native-measure-v5-strict-root-acceptance.json).
Those checks do not constitute candidate E2E acceptance. **The G06 disposition
audit completed with no eligible finalist. T08/G07 fresh testing and scientific
acceptance, and G08 exact candidate-package E2E, did not run.** WN1/WQQ remain
unreserved and unparsed by scientific stages; old closed WR9/WMX remain closed.

## Review the working MVP and prepare the owner handoff

From this project folder run `.\review.ps1` and open
**http://127.0.0.1:8765**; use `.\review.ps1 -Demo` for invented data. Stop with
Ctrl+C or `.\stop-review.ps1`. [MVP_REVIEW.md](MVP_REVIEW.md) gives exact setup
and export instructions. The default model, validated private CSV and existing
code packages remain unchanged; the 29 protected artifacts were rehashed after
selection. Their provenance is in [fallback preservation](reports/v3-fallback-preservation.json).
The outer review pack contains private predictions; the nested code-only package
is the separate public-repository candidate. Nothing has been published.

The useful next owner inputs are the **exact registered team name and registration
confirmation**, the **submission email/form**, and teammates' roles/time budgets.
The chosen freeze is **November 16, 8:00 PM New York**. The supplied submission
deadline, from the **October 22 organizer email supplied in this conversation**,
is **November 17, 11:59 PM CET / 5:59 PM New York**. Review the existing
MVP and submission instructions before authorizing any publication or submission.
Further model work requires a new reviewed protocol and fresh evidence; this
study's thresholds, cohort and result are preserved.
