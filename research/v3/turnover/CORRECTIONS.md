# Turnover research corrections and bounded literature addendum

Date/cutoff: **2026-11-15**. Status: **frozen addendum for fresh PRD critique**. This supplements the original three frozen research files; it does not rewrite them, their receipts or the independent review. No implementation, training or empirical gain is certified.

## TR-1: symmetry and canonical ties

The original RESEARCH.md acceptance wording required H/A output-swap equivariance without qualifying ties. That requirement conflicts with retaining the accepted decoder's H-before-A canonical tie policy. The independent reviewer and root reproduced the contradiction with separately invented symmetric fixtures: [blind review](../../../reports/v3-turnover-research-blind.md), [root reproduction](../../../reports/v3-root-tie-contract-reproduction.json). This corrects the **proposed acceptance contract**, not an established defect in the accepted decoder.

The controlling PRD contract is:

1. **Alpha=0 preserves the exact accepted canonical output**, including its objective, constraints, independent period runs, fewer-transition preference, boundary-placement convention and final/source state tie ordering. Do not alter accepted ties to satisfy a mathematically impossible symmetry assertion.
2. **H/A output equivariance applies to unique-optimum fixtures.** Transform every team-dependent input consistently: score columns; H/A feature pairs and any resulting boundary support; source/destination axes of asymmetric costs; allowed-state masks; team-dependent initial state; labels used only by the independent oracle; and any other team-conditioned configuration. D and outside-period status retain their meanings. Swapping a subset of the inputs is not a valid equivariance test.
3. **For tied fixtures, test objective values and optimal-path sets for permutation equivariance**, including the fewer-transition secondary objective if considered. Test canonical tie selection separately against the documented policy. A canonical representative selected by numeric H-before-A order need not swap with the inputs.
4. A fresh tester must derive unique and tied fixture oracles independently, enumerate short paths where feasible, and test alpha=0 exact output equivalence separately from the unique-optimum symmetry property.

Example: on one active row with equal H/A evidence and forbidden D, H/A-swapped inputs are identical. The canonical output remains H, while swapping that chosen output gives A. The two optimal paths transform correctly; a fixed H-first representative cannot.

## TR-2: literal CSV and official metric precision

The PRD must explicitly preserve **199,319 rows**, header `frame,label`, integer unique ordered frames **0..199318**, labels H/A/D/X and no blanks. Published grading/period rules remain the public oracle; no GT-derived valid runs may control inference.

The proposed boundary head's directionless NONE / TEAM_CHANGE / LIVE_DEAD classes are internal features. They are **not** the official transition matching key. The organizer implementation's default `typed="to"` matches by **destination label**, with inclusive tolerances **+/-12 and +/-25 frames**. A boundary index denotes the first frame carrying the new label. Use the actual pinned organizer functions, with independent invented fixtures; do not replace them with an intuitively similar matcher.

For official temporal metrics, predicted X is filled within each GT-valid run: forward-fill, then backfill any leading X; an all-X run stays X. Frame-level X remains a miss on graded frames. This is scorer behavior, not an inference permission to use truth/run masks. Primary mean spell F1 averages the official H/A-spell F1 across IoUs .3/.4/.5/.6/.7; D runs are excluded from possession spells.

Source: [independent public-oracle audit and synthetic receipts](../../../reports/v3-turnover-research-blind.json), corroborated by the local public scorer source. PRD acceptance should repeat exact behavior, including inclusive endpoints, first-new-frame indexing, destination typing, all-X and run-boundary fixtures.

## TR-3: precision to freeze before implementation/training

The research intentionally proposed a design rather than complete executable training specifications. Before training or fresh-test access, the PRD/immutable experiment manifest must fix:

- Exact half-open before/after edge windows, fps conversion/rounding, endpoint behavior, finite-observation minima, period/gap isolation and per-type boundary validity. Unknown boundary evidence must recover baseline costs rather than invent a negative event.
- Explicit boundary schema/class order, finite numerical ranges, safe softmax/temperature and class-prior treatment; negative sampling population/weights; absent-class behavior; exact versus tolerant targets and any conflict handling. Features/reliability cannot consume labels.
- Finite small-tree/leaf/model-size caps; selection parameter/attempt budget and deterministic ordering; approved data/license/label semantics; whole-match train/selection/genuinely unused test allocation; factorial attribution when boundary-head corpora differ.
- Numerical primary quality and clean/corruption non-regression gates; aggregate uncertainty method suitable for matches/segments; fresh same-machine **absolute and relative** CPU wall time, actual whole-process peak RSS and package-size gates. The original20%/32MiB proposals are not measured results or an established competition cap.
- Exact fresh-export/minimal-environment input-to-CSV, official validator, deterministic repeated hashes and safe-failure/no-partial-final-file contracts; independently generated exhaustive functional oracles.

For an optional PELT diagnostic, `jump=1` alone does not permit every short spell: declare `min_size` and its cost-imposed lower bound too. Do not silently introduce segmentation constraints while comparing boundary methods.

These are required PRD decisions, not new implementation tasks authorized by this addendum. No threshold may be chosen after fresh-test scores are observed.

## Bounded 2026 literature check: Peral et al.

Primary source: [Multi-Modal Soccer Scene Analysis with Masked Pre-Training, WACV2026, pp.3536-3545](https://openaccess.thecvf.com/content/WACV2026/html/Peral_Multi-Modal_Soccer_Scene_Analysis_with_Masked_Pre-Training_WACV_2026_paper.html), [accepted 10-page paper](https://openaccess.thecvf.com/content/WACV2026/papers/Peral_Multi-Modal_Soccer_Scene_Analysis_with_Masked_Pre-Training_WACV_2026_paper.pdf). CVF proceedings metadata gives **March2026**. An [arXiv record](https://arxiv.org/abs/2512.19528) was also located, indexed2025-12-22; conclusions below use the accepted CVF paper, not search-result scores. Retrieval2026-11-15: Firecrawl returned10/10pages; Exa retrieved primary metadata and searched for an official release; Firecrawl developer search returned unrelated projects, which were excluded. This was a bounded targeted check, not an exhaustive repository search.

| Question | Primary evidence / disposition |
|---|---|
| Inputs and model | Sections3.1-3.3 use per-player trajectories, player/team-type information and image crops; an auxiliary ball-action-trained ResNet provides visual features, followed by coarse/fine temporal-social attention. The temporal per-player representation requires correspondence over time; robustness to arbitrary anonymous-slot reassignment is **not established**. Our compact FeatureSet omits crops, boxes and persistent player trajectories. |
| Targets/data | Section4.1 uses a proprietary283-match dataset. Crucially, it **excludes sequences containing out-of-play frames**. Its state/possessor targets therefore do not establish complete dead-play/team-possession inference or the challenge's spell metric. |
| Available pretrained models, official code/license/pin | No official code/project URL or released pretrained-weight link was identified in the accepted paper, its CVF page, or the bounded exact-title/author/CropDrop searches. Consequently **official repo, checkpoint availability, code license and current commit pin remain unverified/not identified**. Paper access is not a code/weight reuse license. This does not prove that no release exists elsewhere. |
| CPU/memory | No CPU latency/peak-RSS benchmark was identified in the inspected paper, and no runnable released implementation was identified. Visual extraction plus temporal/social attention would add dependencies/work beyond the current pipeline; that is an engineering implication, **not a measured resource estimate**. A GPU requirement is not asserted. |
| Incremental usefulness | CropDrop masks an individual player's visual features across a sequence to avoid shortcut reliance. It supports realistic temporal missing-modality augmentation as a research idea. It does not establish that ball-coordinate deletion, anonymous-slot corruption or team-boundary decoding will improve. |
| Decision | **Defer deployment and pretrained reuse; retain as supporting multimodal/masking literature only.** Do not add video crops, player re-identification or a new neural backbone to the reviewed small boundary-decoder scope. Revisit only with lawful aligned modalities, an identified licensed release, declared semantics and independent CPU/scientific acceptance. No score or transfer gain is claimed. |

Public-only retrieval evidence is added under `local/v3-turnover-research-20261115/corrections-public-evidence.json`. No match records, private footage, labels, actual predictions or dataset contents were accessed; no package was installed.

## Preservation and next gate

Original research remains frozen at:

- RESEARCH.md: `3d984d3488856a971bf9933d00fd6309d17e36824731ea55ad33bbad18a4e0bb`
- sources.json: `3dcf9af01d0b3d3951e2ff604a2a0198077e6cab2f01a03665ea7b67811b519c`
- reuse-matrix.md: `2d1b7cf13bfbcb4c855e798bb41e46d355f12021e9f719140d67d3ed1f9b8abb`

Root owns incorporation into the PRD and fresh independent critique. This addendum is ready to freeze; it establishes neither an implemented decoder nor acceptance of future training/package results.

