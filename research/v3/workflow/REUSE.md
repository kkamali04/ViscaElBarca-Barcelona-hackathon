# Selective workflow reuse and architecture audit

Observed2026-11-15; cutoff2026-11-15. **Research draft, not independent acceptance.**
Use the installed requested Superpowers6.1.1; upstream research is not an upgrade.
Only public primary repositories/docs were sent to Exa/Firecrawl or downloaded.
No project implementation, labels, training or historical holdout execution.

## Primary source receipts

| Source | Actual revision/version observed | License evidence | What transfers |
|---|---|---|---|
| [github/spec-kit](https://github.com/github/spec-kit/tree/2ee2b1e8005905db05f5717300a469b3068b908f) | Commit2ee2b1e8005905db05f5717300a469b3068b908f,2026-11-12; latest releasev1.4.0 published2026-11-10 | [MIT at exact commit](https://github.com/github/spec-kit/blob/2ee2b1e8005905db05f5717300a469b3068b908f/LICENSE), Copyright GitHub, Inc. | Independently testable user stories; requirements separated from plan; exact-path dependency tasks; reviewer-owned requirements checklist |
| [obra/superpowers](https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7) | Commit22f0b463e7a5e579904dd6211a520321035526f7,2026-11-03; plugin.json says7.0.2; installed requested package remains6.1.1 | [MIT at exact commit](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/LICENSE), Copyright2025 Jesse Vincent | Fresh task-scoped agents; isolated ownership; spec and quality review; whole-change final review |
| [Organizer evaluation](https://github.com/metrica-sports/more-than-a-hack-2027/blob/f8f2629ff1e0985f81d7e59d8413678514ee1530/EVALUATION.md) | Commitf8f2629ff1e0985f81d7e59d8413678514ee1530,2026-10-23 | Reference only; no source copied into this documentation | Ranking endpoint is H/A run spell F1 averaged over IoU0.3,0.4,0.5,0.6,0.7; organizer describes approximately0.04 full-match noise scale |

The0.04 observation supports considering a conservative engineering margin; it is
not a universal statistical theorem for another provider, match or corruption.
Two fresh external games cannot establish hidden-domain significance. Exact
per-match deltas and a bounded uncertainty discussion are mandatory.

Primary downloads, SHA256 and acquisition metadata are in [sources.json](sources.json).
Public cache: `local/v3-workflow-public-20261115/`. GitHub API commit queries used
`until=2026-11-15T23:59:59Z`; raw files were fetched by the resulting immutable
commit, not mutable main. Exa discovered primary repositories; Firecrawl live-read
the pinned spec-kit tree; direct public GitHub API/raw retrieval supplied exact
version and manageable template contents. Stars/community discussion did not
influence the recommendation. No community sources were requested or needed.

## Reuse decisions

Reuse the structure of [spec template](https://github.com/github/spec-kit/blob/2ee2b1e8005905db05f5717300a469b3068b908f/templates/spec-template.md),
[plan template](https://github.com/github/spec-kit/blob/2ee2b1e8005905db05f5717300a469b3068b908f/templates/plan-template.md),
[task template](https://github.com/github/spec-kit/blob/2ee2b1e8005905db05f5717300a469b3068b908f/templates/tasks-template.md),
and [requirements checklist](https://github.com/github/spec-kit/blob/2ee2b1e8005905db05f5717300a469b3068b908f/templates/checklist-template.md).
Write project-specific documents in original language; do not copy sample tasks.
An implemented checkbox and a reviewer-satisfied requirements checklist mean
different things. The upstream task template makes tests optional by default;
this project's user explicitly requires independent acceptance, so tests are
mandatory here. No CLI generator, extension registry, branch automation or global
installation is necessary to use these document patterns.

Reuse Superpowers' context-limited work assignment and review boundaries, adapted
to stricter blind acceptance. A reviewer receives normative requirements and
public inputs, not the implementer's expected scores/output hashes or prior
success reports. The current upstream7.0.2 is merely a comparative source: run the
installed6.1.1 workflow requested by the user with documented authorization and
no-commit adaptations in [WORKFLOW.md](../../../specs/003-possession-improvements/WORKFLOW.md).

Retain the existing root goal/checkpoints and append-only progress stream. A new
project-management server would duplicate these surfaces. Add only the scientific
manifest/attempt machinery required to enforce new-label boundaries. Public text
downloads do not execute repository code. Any future copied MIT code/templates
must retain their copyright and license notice; this research does not silently
install or vendor either framework.

## Alternatives and when the recommendation is wrong

| Approach | Benefit | Cost / failure condition |
|---|---|---|
| Recommended: hand-authored scoped specs + existing project ledger + small local guards | Minimal operational burden, exact privacy/experiment controls, fits deadline | Wrong if repeated concurrent teams require enforced cross-machine access or audit retention beyond this workstation |
| Full spec-kit installation and generated workflow | Consistent conventions across many features and agents | Adds generator/config/integration surfaces; unjustified for two bounded experiments unless manual docs demonstrably drift |
| Full hosted experiment/workflow tracker | Shared identities, richer experiment search and access policies | Installation/cloud/privacy costs; not needed for local CPU study; revisit for many users or long-lived infrastructure |
| Ad hoc notes and direct code edits | Lowest initial setup | Cannot enforce provenance, blind gates or interrupted test access; incompatible with this project's requirements |

## Bounded local architecture inspection

Mapped `possession_model/`, `validation/`, `experiments/noise_v2/`, `tools/`,
`review_app/exporting.py` and research protocol paths. Deep reads sampled decoder,
pipeline/source freeze, external adapter cache/target boundary, experiment
selection/holdout, metric adapter and export integration; resource harness code was
sampled for worker identity. No general repository rewrite or exhaustive security
audit. Historical outcome claims were not used as acceptance proof.

High-confidence source findings: incomplete immutable protocol/comparator binding;
final-report-only retry guard; target parsing during cache preparation; constant
transition interface; frozen-ZIP export integration; fixed25-frame transition
tolerance requiring an explicit10Hz policy. Full findings, limitations and closure
targets are in [known-issues.md](../../../specs/003-possession-improvements/known-issues.md).

Next: freeze these artifacts; fresh research critique; resolve material findings;
synthesize two professional PRDs and feasible two-fresh-test study; fresh design
critique; then executable plans with exact interfaces/tests. No new labels or
implementation precedes those gates. Experiments freeze Nov16 at20:00 New York.
