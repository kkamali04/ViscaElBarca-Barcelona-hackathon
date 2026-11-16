# Independent public reuse advisory (Hyperagent)

Retrieved 2026-11-15. Thread: cmwi9m9pl010h06ad666cwp0p. Public-only specialist advisory, not an acceptance test. References and proposed gates require local independent review; no experiment results were supplied.

## 1. Verdict

Keep the accepted estimator unchanged and test a turnover-aware decoder as an isolated challenger, not a replacement **[Likely]**. Use **ruptures** for interpretable change-point proposals, not as a complete possession decoder, and avoid its full-match RBF cost because the implementation constructs a dense pairwise matrix **[Verified implementation; Likely recommendation, [source](https://github.com/deepcharles/ruptures/blob/master/src/ruptures/costs/costrbf.py)]**. The strongest external supervision found is the **seven-match DFL/Sportec dataset**, whose paper explicitly documents frame-level controlling-team and active/dead-ball fields under CC BY 4.0 **[Verified, [source](https://www.nature.com/articles/s41597-025-04505-y)]**. Use **kloppy** for ingestion and treat **DataBallPy** as a source of control-evidence features, while keeping SkillCorner’s broadcast-derived possession labels as weaker, provider-generated supervision **[Likely, sources below]**. Neither proposed direction has established transfer gains, novelty, or a better hidden score, so promotion should depend on a frozen external whole-match experiment **[Unknown]**.

**Evidence convention:** all observations below were made **2026-11-15**, the research cutoff; **Verified** means directly present in fetched primary text or code, not independently reproduced.

## 2. Parts table

Four candidates, ranked by practical reuse priority rather than popularity.

| Piece / candidate | Exact licence text inspected | Version and maintenance evidence | Transferable pattern, mismatch and status |
|---|---|---|---|
| **1. Ingestion: [PySport/kloppy](https://github.com/PySport/kloppy)** | **BSD-3-Clause:** “Redistribution and use in source and binary forms, with or without modification, are permitted…”; includes non-endorsement condition. [LICENSE](https://github.com/PySport/kloppy/blob/master/LICENSE) | [Release](https://github.com/PySport/kloppy/releases): **v3.19.1, 2026-10-03**, `bd68afc`. [Latest observed commit](https://github.com/PySport/kloppy/commits/master/): **2026-11-06**, `a9651eb`. Repo snapshot: **572 stars / 110 forks**, created **2020-04-22**, **98 open issues**. | **Verified:** vendor-independent tracking/event model; Sportec, Metrica and SkillCorner loaders. **Likely:** highest ingestion savings. Does **not** establish that this challenge’s ATD schema is supported, synchronize cameras, or reconcile possession definitions. **PASS; adopt externally first.** |
| **2. Temporal proposals: [deepcharles/ruptures](https://github.com/deepcharles/ruptures)** | **BSD-2-Clause:** “Redistribution and use in source and binary forms, with or without modification, are permitted…” [LICENSE](https://github.com/deepcharles/ruptures/blob/master/LICENSE) | [Release](https://github.com/deepcharles/ruptures/releases): **v1.1.10, 2025-09-10**, `a3f8c43`. [Latest observed commit](https://github.com/deepcharles/ruptures/commits/master/): **2026-05-26**, `ee1c8ff`, **older than 90 days**. **2,113 / 206**, created **2018-01-20**, **48 open issues**. Associated review: Truong, Oudre and Vayatis, *Signal Processing* **2020**, listed in [repo](https://github.com/deepcharles/ruptures). | **Verified:** offline segmentation; configurable costs, `min_size` and `jump`. **Likely:** useful boundary proposals on team-evidence signals. A change point has no inherent H/A/D meaning; tracker loss can resemble a turnover. **PASS; experimental, not turnkey.** |
| **3. Control features: [Alek050/databallpy](https://github.com/Alek050/databallpy)** | **MIT:** “to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies…” [LICENSE](https://github.com/Alek050/databallpy/blob/develop/LICENSE) | [Release](https://github.com/Alek050/databallpy/releases): **v0.8.1, 2026-08-11**, `3a8ebc1`. [Latest observed commit](https://github.com/Alek050/databallpy/commits/develop/): **2026-11-03**, `a2ab78c`. **106 / 31**, created **2023-01-24**, **10 open issues**. Oonk, Grob and Kempe: [JOSS paper](https://joss.theoj.org/papers/10.21105/joss.10223), **2026-04-21**. | **Verified documentation:** player-zone entry plus ball direction/speed changes; team possession also offers last-on-ball-event propagation. **Likely:** reuse control evidence, not its final labels. Documentation explicitly warns about event quality, synchronization and unsuccessful first actions. **PASS; selective reuse.** |
| **4. Noisy external tracking: [SkillCorner/opendata](https://github.com/SkillCorner/opendata)** | **MIT repository licence:** same permission to “use, copy, modify… and/or sell”. [LICENSE](https://github.com/SkillCorner/opendata/blob/master/LICENSE) **Unknown:** whether any separate asset-specific terms supersede it. | [Latest observed commit](https://github.com/SkillCorner/opendata/commits/master/): **2026-09-14**, `4340d27`. Release version **not established**. **458 / 189**, created **2020-10-08**, **2 open issues**. | **Verified provider documentation:** ten A-League matches, **10 Hz**, possession fields, detected/extrapolated players and in-play phase intervals. **Unknown:** independently corrected control/dead-play reference. **Conditional:** useful robustness/weak-supervision source, not decisive ground truth. |

**Maintenance and security qualification:** the fetched star/fork/age combinations do not themselves show an obvious anomaly, but cannot authenticate popularity or maintainer responsiveness **[Unknown]**. Counts are page snapshots, not audited live inventories; latest commit is not an exact `pushed_at` timestamp. Install-time phone-home behaviour remains **Unknown for all four** because installation hooks and transitive dependencies were not comprehensively inspected. SkillCorner’s [documentation configuration](https://github.com/SkillCorner/opendata/blob/master/mkdocs.yml) explicitly enables Google Analytics **[Verified]**, which is not evidence of runtime package telemetry.

### External labels: strongest source and important limits

| Source | What is genuinely available | What it does not establish |
|---|---|---|
| **DFL/Sportec integrated dataset** | **Verified:** Bassek, Rein, Weber and Memmert, [paper published 2025-02-01](https://www.nature.com/articles/s41597-025-04505-y); seven full matches, 25 Hz, **1,002,644 tracking frames**. Ball records include `BallPossession` = home/away and `BallStatus` = inactive/active; possession is defined through player control. Authors explicitly authorize the dataset under **CC BY 4.0**. The [licence text](https://creativecommons.org/licenses/by/4.0/legalcode.en) grants rights to “reproduce and Share” and create adapted material, subject to attribution. | **Unknown:** exact agreement with Metrica’s controlled-possession convention, annotation errors and match-specific missingness. **Verified:** released dataset excludes video. It cannot directly validate camera alignment. |
| **SkillCorner** | **Verified:** public full-match tracking with provider possession and phase outputs. | Missing phase coverage should **not automatically become D** without establishing completeness. Provider-generated possession is not independent human/corrected truth. |
| **SoccerTrack-v2, not shortlisted as a dependency** | Its [dataset card](https://huggingface.co/datasets/atomscott/soccertrack-v2) documents ten full matches, action labels and game-state annotations. | **Verified warning:** auxiliary ball tracks are event-anchored interpolations and therefore carry event timing. These are not documented continuous H/A/D control labels; using them to “discover” turnover timing risks circular evaluation. |

## 3. Glue diagram

**Proposed design [Likely], informed by the sources above:**

```text
[External DFL/Sportec data]
        │ kloppy: normalize units, periods, IDs, timestamps
        ├── [BallPossession + BallStatus] ──> reference-only evaluation branch
        │
        └── [geometry + explicit missingness masks]
                    │
            [frozen corruption adapter]
                    │
       [accepted estimator's evidence interface]
                    ├── accepted decoder
                    └── change-point proposals
                          + controlled-turnover evidence
                          + separate dead-play evidence
                          ──> challenger decoder
                                      │
                        [identical whole-spell evaluator]
```

**Binding separation:** provider possession/status fields belong in the reference branch, never classifier inputs. Preserve missing observations as missing; do not silently interpolate them into confident control evidence. Any future two-stream fusion needs independently established per-period clock mappings and residual-error bounds, not equal frame-number assumptions.

The public [task definition](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/CHALLENGE.md) retains the last controlling team during loose/contested live play and distinguishes D from ownership **[Verified]**. Its [evaluation documentation](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/EVALUATION.md) also says X is filled within each half before spell scoring, so X is not a neutral fourth possession state **[Verified documentation]**.

## 4. Code still to be written

**Planning estimates [Likely], not measured implementation costs:**

| Module | Approximate effort | Main integration trap |
|---|---:|---|
| External canonical schema and DFL reference mapper | 1–2 engineer-days | Preserve periods, dead frames and original sampling times; never use an alive-only loader view. |
| Control-feature adapter from DataBallPy patterns | 1–2 days | Derivatives amplify gaps and jitter; documented `main`/`develop` behaviour may differ from released v0.8.1. |
| Boundary proposal and H/A/D decoder adapter | 2–4 days | Distinguish control changes from camera/tracker discontinuities; avoid minimum-duration rules that erase short real spells. |
| Corruption generator and paired evaluation harness | 2–3 days | Whole-match splits, reproducible seeds and reference-field leakage checks. |

For CPU/memory, start with low-dimensional signals and L2/change proposals, then refine candidate boundaries at native rate **[Likely]**. [PELT documentation](https://centre-borelli.github.io/ruptures-docs/user-guide/detection/pelt/) gives conditional complexity, not a universal linear-time guarantee **[Verified]**. RBF’s dense matrix at 199,319 samples would require roughly **318 GB just for float64 matrix entries**, before temporaries, by \(N^2 \times 8\) arithmetic **[Likely estimate grounded in inspected code]**.

## 5. Smallest decisive external experiments

These are **proposed gates**, not results.

| Hypothesis | Smallest useful whole-match test | Failure / promotion condition |
|---|---|---|
| **H1: explicit turnover-aware decoding beats current temporal handling** | Use **one complete external match for development and two untouched complete matches for testing**. Freeze emissions; compare accepted decoder, change-point-only segmentation, and change-point plus control/dead-play decoding. Test clean inputs and identical corrupted inputs. | Promote to a larger test only if mean **ΔspellF1 ≥ +0.04**, neither held-out match regresses, macroF1 drops by no more than **0.01**, and boundary errors improve rather than merely deleting short possessions. Thresholds are conservative engineering choices, not universal significance bands. |
| **H2: broader licensed training plus realistic tracker errors improves robustness** | On the seven DFL matches, preregister **3 train / 2 validation / 2 untouched test** by match. Hold model/features fixed; compare narrow-training, broader-training, and broader-plus-corruption variants. Remove all reference-derived possession/status features. | Require **ΔspellF1 ≥ +0.04** on the corrupted held-out mean, no clean-match regression greater than **0.01**, and gains across multiple fixed corruption seeds. If feasible, follow with independently labelled cross-provider matches before asserting transfer. |

**Corruptions:** contiguous missing-ball bursts, player-track dropout/fragmentation, ID swaps, coordinate jitter/outliers and timestamp shifts. An isolated 41% missing-ball rate is insufficient to define a realistic corruption process; vary burst lengths and whether missingness concentrates near turnovers. Without measured external tracker-error statistics, label this **stress testing**, not proven challenge-noise simulation.

**Report:** whole-possession spellF1 using the published temporal-IoU thresholds **0.3–0.7**, macroF1, over/under-segmentation, turnover boundary error, D-boundary error, runtime and peak RSS. Use paired possession-block resampling for exploratory intervals, not independent-frame bootstraps; two test matches can reject an unhelpful variant but cannot establish broad generalization.

**Provisional efficiency gate:** single CPU process, no GPU, end-to-end processing faster than match duration, peak RSS **≤2 GB**, and separately reported decoder overhead. No candidate has been measured against that gate here.

## 6. Risks and build-now versus defer

| Decision | Recommendation | Cost of deferring |
|---|---|---|
| External DFL label/ingestion contract | **Build now** | No credible whole-match selection criterion. |
| Turnover-aware decoder | **Small isolated experiment now** | May leave avoidable spell fragmentation, but replacing the accepted system prematurely is riskier. |
| Broader training and corruption | **After reference/leakage audit** | Continued sensitivity to provider and missingness patterns. |
| SkillCorner weak supervision | **Defer until label and rights scope are checked** | Less broadcast-domain coverage, but avoids treating vendor predictions as truth. |
| Multi-camera fusion | **Defer until independent alignment evidence exists** | Leaves possible complementary observations unused without introducing false transitions. |

**Principal risks:** cross-provider control semantics, synthetic-noise mismatch, label leakage, smoothing away short spells, Python object/dataframe overhead, and mutable documentation diverging from release behaviour **[Likely]**. Permissive code licences do not automatically license separately supplied match assets **[Verified distinction in the public challenge repository](https://github.com/metrica-sports/more-than-a-hack-2027)**.

## 7. What I could NOT establish and why

- **No measured improvement, CPU/RSS result or hidden-score implication:** no code was installed or executed.
- **No fully vetted drop-in constrained H/A/D decoder:** ruptures supplies segmentation, leaving semantic decoding and dead-play handling to glue.
- **No proof that DFL control labels exactly match Metrica’s corrected-tracking convention:** public definitions are similar, not demonstrated equivalent.
- **No independent validation of SkillCorner possession/dead-play labels or comprehensive asset-specific rights audit.**
- **No complete install-hook, dependency-security or telemetry audit.**
- **No camera synchronization evidence:** no supplied streams or match assets were accessed.
- **No novelty claim:** the sources establish reusable methods, not an exhaustive prior-art clearance.

Only public documentation, licence text, metadata and source pages were read. No challenge GT files, supplied tracking/video/tags/predictions, private repositories or accounts were accessed; nothing was installed, run, changed, uploaded, published or sent.

