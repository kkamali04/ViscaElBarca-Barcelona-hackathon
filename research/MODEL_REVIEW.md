# Independent Hyperagent review and root verification

The user explicitly requested Hyperagent assistance. Three existing agents were
invoked using only public challenge facts, public source URLs and a proposed
method. No supplied match file, private record, frame, tracking excerpt or private
quality report was attached. No agent configuration or schedule was created.

| Agent | Thread ID | Assignment |
|---|---|---|
| Atlas Researcher | cmwhchebi00o607adqn8dp8fz | Primary papers, public comparables, transfer assumptions |
| Frankenstein Architect | cmwhchemb00r707adphroqqmt | Adjacent component source/licence/integration costs |
| Grader-Gemini | cmwhche2c010207adgwcg1bgq | Independent skeptical method review |

Agent names are the connected service's labels, not independent proof of model
version. Their conclusions are leads to inspect, not experimental validation or
an automatic consensus. Only assistant answer text was considered for the review;
internal tool traces/reasoning are not part of this packet.

## Findings retained

Atlas independently confirmed the important transfer limits of the three primary
papers in EVIDENCE_LEDGER.md: TCN study selection and different metrics, PathCRF's
known in-play episodes, and the event paper's play-status input/proxy. Root read
the primary texts and confirmed those claims. PathCRF section 3.1 is the clearest
source for the in-play-only protocol; outside nodes do not remove that limitation.

The component researcher inspected DataBallPy's source and identified an important
mismatch: its Metrica parser infers dead play from missing ball_x. Root fetched
the exact commit-pinned parser and confirmed that assignment. The detailed
individual-possession helpers/dependency findings are static agent observations;
we did not execute them. They do not establish a package defect or runtime score.

The reviewer usefully emphasized half-boundary handling, costly transition
uncertainty and keeping phase tags soft. Those points were checked against the
organiser's docs and reflected in the implementation blueprint.

## Findings rejected or corrected

The initial skeptical review contained material errors. Root challenged them
with the authoritative data/metric rules and requested a correction. The reviewer
explicitly retracted the following claims:

- Homography is required to calculate player-ball distances. **False:** tracking
  is already in normalised pitch space; scale the two axes to metres. Homography
  maps pitch to video pixels.
- Public-five-minute corruption tests can select/tune the model. **Rejected:**
  use wholly invented evidence or other-match labels for those experiments.
- Eight frames is a spellF1 threshold floor. **False:** spellF1 uses temporal IoU
  thresholds. A timing error's effect depends on possession length and overlap.
- Cross-validating against the method's own heuristic pseudo-labels proves
  accuracy. **False:** that is circular; algorithmic pseudo-label learning and
  independent validation are different activities.
- Stillness, an unseen ball, or one untrusted outside coordinate proves D.
  **False:** those are uncertain observations requiring context.
- A Voronoi fallback is mandatory during ball gaps. **Unsupported:** no source
  establishes that requirement or its benefit for this dataset.

We also do not adopt unconditional advice to guess at every transition or emit X
for every missing-ball frame. X has documented carry-forward behavior, and the
choice depends on available evidence and uncertainty. Persistent control is a
prior, not proof that no turnover occurred during a long gap. The reviewer's
numeric rubric ratings have no status as benchmark measurements and are omitted.

This is why the packet distinguishes tool/agent advice, verified source facts,
constructed checks and unknown private performance.
