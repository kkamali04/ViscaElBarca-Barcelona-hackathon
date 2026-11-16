# Competitive-development gap review - 2026-11-15 13:09 Eastern Standard Time

## Correction to the completion claim

The completed goal was an E2E reliability/efficiency campaign around a working
candidate. It did not prove that the broad hackathon problem was solved, that
research/model improvement opportunities were exhausted, or that the entry is
competitive with the top20. The assistant framed that milestone too broadly and
stopped short of the user's requested sustained competitive-development effort.

## What current evidence establishes

- An algorithm produces the exact required full-frame CSV from the supplied
  tactical ATD pair; the exported code repeats it in a minimal environment.
- Independent contract/negative tests, official validation, source/model/input
  bindings, resource measurements and preservation checks pass.
- Noise-v2 training uses J03WOH, selection J03WOY and one fresh external holdout
  J03WMX. The old v1 holdout J03WR9 was not reused for selection.
- J03WMX spellF1:0.472460 clean,0.401379 ball gaps,0.346548 combined errors.
  Frame macroF1:0.902171,0.847002,0.814936. SpellF1 is a segment-matching metric;
  0.472460 is not a statement that47% of frames are correct.
- These are other-match results. Hidden challenge quality and rank are unknown.

## What remains unresolved

1. Generalization: one training game and one fresh test game from one provider
   give limited evidence for transferring control/dead-ball semantics and tracker
   errors to the challenge. Simulated corruptions are not more independent games.
2. Comparative quality: the current evidence compares the organiser reference,
   a heuristic, and two related small-tree/decoder versions. Public competitor
   source inspection is not an equal-input executed benchmark or a rank estimate.
3. Error attribution: current v2 changes both motion estimation and corruption
   training views. We have not isolated which change causes the gain or shown
   reliable improvements across enough independent matches/conditions.
4. Hard cases: possession changes during missing-ball intervals, one-touch control,
   stoppage/restart timing, plausible tracker drift, and motion-window coverage
   remain unresolved performance risks. Synthetic behavior tests are insufficient
   evidence for these football decisions.
5. Optional evidence: tagging is disabled; video/broadcast cues are not used.
   Their incremental value has not been demonstrated in an independently scored
   setting. Their omission is a scope choice, not proof they cannot improve quality.
6. Study safeguards: before another holdout study, enforce full immutable selection/
   protocol/comparator identities and atomic one-attempt tracking. Current-run
   manual readback bounds the old experiment; it does not repair the runner.
7. Submission readiness: team identity/registration confirmation, exact email/form
   requirements, final document naming and project-only public repository remain
   owner-dependent work. Current local artifacts are unsubmitted.

## Next useful authorized technical work

Preserve the accepted candidate as a checkpoint. Predeclare a new study before
any new test-label access; old scored holdouts stay closed for tuning. Broaden
whole-match development/validation coverage using accessible, licensed OTHER-game
labels with verified semantics. Run focused ablations and condition-specific error
analysis, then compare a small set of justified improvements using actual spellF1.
Keep compute/resource budgets and efficiency gates explicit. Accept a new version
only with independent accuracy evidence and fresh blind exact-package E2E.

Do not spend the next development block merely repeating already-passing CSV
hashes or expanding test counts. Evidence of improved possession estimation is
the missing deliverable. Do not promise a win or hidden score.

This note is a gap review and future work order, not evidence that those additional
experiments have been run or that an unattended worker remains active after handoff.

Sources: [current method](../SOLUTION.md),
[external holdout](../reports/noise-v2-holdout.json),
[frozen configuration](../models/selected-noise-v2.json),
[experimental audit](../reports/blind-experiment-audit.json),
[research blueprint](IMPLEMENTATION_BLUEPRINT.md).
