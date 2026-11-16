# Evidence ledger

Observed November 14, 2026 Eastern / November 15 UTC. Source support is distinct
from an implementation result. Source code was inspected as text; external code,
model checkpoints and datasets were not executed or downloaded.

| Decision or claim | Primary evidence | What it establishes | Limit |
|---|---|---|---|
| Exact deliverable and metric | [Organiser SUBMISSION](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/SUBMISSION.md), [EVALUATION](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/EVALUATION.md), local possession_metrics.py | Frame contract, possession-overlap scoring, X filling | No public hidden-match labels or live ranking |
| Input semantics and alignment | [DATA](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/DATA.md), [OVERVIEW](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/OVERVIEW.md), local helpers | Normalised pitch coordinates, unstable slots, missing ball, phase tags, distinct timelines | Exported quantities still need local validity checks |
| Rules for research and evaluation | [RULES](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/RULES.md), [FAQ](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/FAQ.md) | No match hand labels or public-window tuning; no supplied assets/extracts to hosted LLMs | The signed participant terms remain authoritative for data use |
| Evidence-first project workflow | [advise-project-approach SKILL](https://github.com/AaravKashyap12/advise-project-approach/blob/main/skills/advise-project-approach/SKILL.md) | Constraint fit, comparables, alternatives, reversal conditions, bounded research | A planning aid, not a possession implementation; no global installation performed |
| Geometry and event rules are a useful reference | [Vidal-Codina et al. 2022](https://arxiv.org/html/2202.00804v3) | Player-ball possession zones and event reasoning | Uses dead/live information or a missing-ball proxy; event detection rates are not spellF1 |
| Temporal neural models can learn H/A/D | [Borghesi et al. 2023 author PDF](https://iris.polito.it/retrieve/8cc27103-7ee0-4243-8a04-0b256f77ad39/eswa_tcn_authors_accepted_version.pdf) | Direct game-state learning, permutation-invariant aggregation, other-match splits | Selects eight lower-missingness matches from 35; no demonstrated transfer to this test or spellF1 |
| Structured possession paths are plausible | [PathCRF v2](https://arxiv.org/html/2602.12080v2), especially section 3.1 | Context-dependent constrained sequence inference | Reported train/infer windows are within known live episodes; edge/event metrics differ |
| Independent data is available in principle | [Sportec Open DFL Figshare](https://springernature.figshare.com/articles/dataset/An_integrated_dataset_of_spatiotemporal_and_event_data_in_elite_soccer/28196177) | Seven Bundesliga matches, paired tracking/events, listed download 2.45 GB, CC BY | Not downloaded here; event-derived possession requires a documented definition and alignment checks |
| Real public comparables use temporal methods | Pinned code links in [COMPARABLES](COMPARABLES.md) | Source exists beyond the organiser baseline; observable design choices | No qualification, compliance or hidden-score claim |
| A general library may embed an unsuitable shortcut | [DataBallPy Metrica parser](https://github.com/Alek050/databallpy/blob/a2ab78c4c7ba3ad964ab26dd65dd848de3939d18/databallpy/data_parsers/tracking_data_parsers/metrica_tracking_data_parser.py) | Parser maps missing ball_x to dead | Static source behavior; not an executed package benchmark |
| Licence identity | [kloppy LICENSE](https://github.com/PySport/kloppy/blob/HEAD/LICENSE), [PathCRF LICENSE](https://github.com/hyunsungkim-ds/pathcrf/blob/HEAD/LICENSE) | BSD-3-Clause and MPL-2.0 respectively | Code, weights and datasets can have distinct notices; inspect before adoption |
| Python decoder cost is small locally | [Synthetic report](../reports/synthetic-decoder-probe.json) and script | Eight constructed cases pass; 199319-frame component run ~3.28 s | Invented evidence, one CPU run, not measured football accuracy or total inference time |
| Data assets can be profiled without sharing records | [Local owner report](../local/private-data-quality.json) and profile_local_assets.py | Local aggregate diagnostic completed, no GT read | Ignored private output; not an independent accuracy measurement |

## Research limits and stop decision

GitHub connector search found exact-competition repositories that general Exa
search did not surface. The connector rejected its forks-list endpoint; repository
search and direct file APIs supplied the comparison instead. Nature's article
page redirected to an inaccessible authentication/cookie page; the linked primary
Figshare record and author paper established the dataset facts used here.

Primary sources, public code and local evidence were sufficient. Social media,
Reddit, YouTube, Chrome interaction, exhaustive fork enumeration, external code
execution and new cloud services were not needed. No claims rely on those sources.
The next useful step is a falsifiable implementation/validation experiment rather
than expanding the bibliography. Agent conclusions are not accepted as primary
evidence when they contradict the official contract.
# November 15 implementation research update

Exa search and Firecrawl search/extraction reached the primary
[Scientific Data descriptor](https://www.nature.com/articles/s41597-025-04505-y).
Unlike the earlier access attempt recorded below, this established explicit
framewise BallStatus (inactive/active) and BallPossession (home/away control)
semantics, metre coordinates, and the CC BY 4.0 dataset licence. The
[PySport public mirror](https://huggingface.co/datasets/pysport/idsse-data) supplies
raw observed tracking and metadata. Three other matches were downloaded and
integrity-verified, then used in a fixed whole-match development/validation/
holdout split. Targets are isolated from inference features; altered-label tests
verify that boundary. See [adapter evidence](../validation/README.md) and
[measured results](../SOLUTION.md). No restricted challenge data was sent online.

Exa also located the official
[HistGradientBoostingClassifier documentation](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html)
for native missing-value routing and efficient histogram training. The installed
and pinned training release is 1.9.1. The deployable NumPy tree evaluator was
independently parity-tested; no sklearn runtime import is needed for inference.

The following table and access-limit notes are the earlier research snapshot.

