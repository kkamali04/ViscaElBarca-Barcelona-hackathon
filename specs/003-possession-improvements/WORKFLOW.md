# Managed workflow for possession v3

Final checkpoint: 2026-11-16 04:59 UTC. **Completed with no eligible finalist.**

T00-G05 and the actual three-fit training/54-row selection study completed.
G06 independently accepted the no-finalist disposition; root reproduced it. T08/G07
and actual G08 correctly stopped at eligibility. T09 tooling remains bounded; no
actual v3 release. T10 rejection/handoff is complete. The accepted MVP is unchanged.

Current evidence: PROJECT_STATE.md, AGENTIC_GOAL.md, V3_REVIEW.md and tasks.md.
The root selection receipt is reports/v3-selection-disposition-root-acceptance-r2.json.
Native-tool acceptance is reports/v3-native-measure-v5-strict-root-acceptance.json,
explicitly synthetic tooling only. Final handoff review, integrity, archive and
limits are linked by reports/v3-campaign-closeout-r2.json. Older workflow status is
preserved in local/v3-final-handoff-evidence-20261116.zip, never current acceptance.

Protocol/design status strings are frozen historical snapshots; changing
protocol bytes would change the preregistered identity. Consult current tracker
and dated exact-version receipts. No new science run or gate bypass is authorized.

## One canonical sequence

IDs and states are defined only in tasks.md: T00research,T01design,G01designreview,
T02guard/G02,T03data/G03,T04decoder/G04,T05integration/G05,T06training,T07selection,
G06finalistfreeze,T08fresh test,G07science,T09release/G08freshE2E,T10rootdisposition.
Every gate has an owned row and evidence link. Do not use earlier R/I/S/E phase
identifiers; they are historical and were corrected afterWBR-01.

Research/doc authors do not accept their own work. Root manages goal/checkpoints,
reports/agentic-progress.jsonl, sharedtracker andowners. All implementation lanes
have disjoint files; after G01, pure-synthetic T02/T03/T04 can run concurrently.
G02+G03 must pass before any new label-bearing parser; G05 before registeredstudy.
One heavyworker runs at a time. Root alone integrates sharedCLI/source manifests.

## Blind gate and repair rules

Freeze exactscope/hashmanifest before dispatch. Fresh fork_turns=none critic gets
public normative requirements, artifact paths, own writes/scratch andbounded task; never
prior verdicts,scores,expected prediction hashes,implementation rationale or previous
tests as an oracle. It derives independent fixtures and source-backed oracles.
Report spec compliance andquality separately with tested version,evidence paths,
actual artifact hashes,failures andlimits. Root readsactual artifacts,reproduces material
failures anddecisive checks, thenreleases freeze. Assertion of success alone is not proof.

A repair changes version andrequiresfresh acceptance for thatscope. Scientific
changes after test reservation require a new study andunused test fixtures; no retuning
against consumed tests. Packaging-only repairs can retain unchanged science evidence
only after independent scope/hash verification, then fresh package acceptance. Report
all failures; never overwrite an earlier report to imply it tested later bytes.

## Applied local skill sources and authorized adaptation

Manually read locally installed advise-project-approach and Superpowers6.1.1
brainstorming,writing-plans,dispatching-parallel-agents,subagent-driven-development.
These paths are source documents, not advertised invocable skills in this session.
Exact paths/hashes/registered commit are in research/v3/workflow/sources.json revision3 (original receipts preserved; public FAQ receipt appended).
Upstream7.0.2 was research only; no skill install/upgrade happened. Advising source's
upstream revision/license is unverified and is not inferred from its local presence.

User authorized autonomous implementation after independentdesigncritique, so skill
human approval pauses yield to G01; no repeated human permission is needed. Skill
commit/worktree/finish-branch defaults yield to no staging/commit/push. Existing
ledger/checkpoints replace extra workflow platform. Specs live here. Plans express
exact interfaces/algorithms/test oracles rather than copying full production code into
a document; actualcode iswritten in bounded reviewed implementation tasks. This is
an explicit adaptation of writing-plans, preserving actionable zero-context handoffs
without claiming it is a literal generator output. No unrelated refactor or new stack.

## Deadline, privacy and completion

Protocol fixes latest fit start Nov 16 00:00NY and final freezeNov 16 20:00NY, leaving
Nov 17 for submission preparation. Missed cutoff means no new dependent study stage;
retain accepted fallback and accurately report incomplete work. Root cannot satisfy the
user's two implementation requests with paperwork alone; both ideas are tasks with
real code/training/evidence requirements. Failed hypotheses are legitimate outcomes.

No restricted records/targets/footage/timelines enter model tools or public services.
Local code may process permitted data only after gates; messages contain aggregates/hashes.
Browser fixtures are invented. No challenge GT/public-window tuning or hand corrections.
No staging/commit/push/publication/submission/new paid cloud. Accepted 29 files and
original downloads are protected. Evidence establishes only exacttested version and
bounded two-match engineering choice; hidden performance/ranking are unknown.


## Historical design rounds (superseded by G01 receipt above)

Round1 design evidence is immutable: reports/v3-design-round1-root-verification.json
records root reproduction of all three critics' actual harnesses. Original15files
are archived in local/v3-design-round1-frozen.zip. This revision repairs canonical
RNG/identity/observations/scoring and replaces B050 with F080 before labels. Prior
research acceptance or intrinsic PRD caveat verdicts do not accept the repaired
cross-document set. No implementation or new labels until its fresh G01 passes.


Round2 root verification is reports/v3-design-round2-root-verification.json;
original15files archived local/v3-design-round2-frozen.zip. Revision4 changes only
prefit/postfit sealing, standalone observation cache authority and atomic result
generations, plus exact source/model handoff schemas and FAQ provenance. Both PRDs
remain unchanged. No earlier scientific-quality pass accepts these repaired bytes;
fresh bounded design acceptance is still required before code/new labels.


2026-11-16T01:35UTC root milestone: T05 author implementation frozen; G05 resource round2 root findings reproduced.
T05 author integration is frozen with40 checks on invented fixtures, including3 fits,
54 selection rows,24 test rows and dead-owner metadata recovery. Root verified
all7 source hashes. Receipt:reports/v3-t05-integrator-author.json. These checks
do not establish actual model quality or normal-CLI full scientific acceptance.
Resource round2 root replay:17/19 checks passed. Same-identity original edits
with restored timestamps were admitted; root also observed2 subject sampling
gaps above50ms (maximum59.804ms). CLI refuses such incomplete measurements.
Exact versions/reports archived:reports/v3-g05-resources-r2-root-verification.json.
Resource-only repair/fresh acceptance and normal-CLI science G05 remain required.
No real-match registration, acquisition, target parsing, fitting, selection or test.
