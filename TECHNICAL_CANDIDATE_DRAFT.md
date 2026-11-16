# Team technical document - noise-v2 candidate (draft)

Registered team name: pending confirmation.

Our method estimates framewise home possession, away possession and dead play
from tactical tracking. We compute metre-based player-ball geometry, observation
quality, anonymous collective movement and period-bounded temporal summaries.
A 31-observation local-linear x/y slope estimates ball motion while suppressing
coordinate jitter. Missing/unreliable windows remain unknown. A small histogram
boosting model learned from a separate Sportec/DFL match supplies evidence for
an exact three-state penalized temporal decoder, reset independently each half.
We enforce only the published preparation interval before the second kickoff.

The tactical XML and TXT are the required inference assets. We use no challenge
GT/manual labels, video detection or external human records about this match.
Phase-tag support has zero selected weight. Missing ball does not automatically
mean dead play. The estimator is offline; centred motion windows average turns
and lose edge coverage around gaps. Turnovers hidden inside gaps remain ambiguous.

Development J03WOH, selection J03WOY and fresh holdout J03WMX are separate matches.
After a preregistered clean/noisy validation comparison, the frozen v2 achieved
mean spell F1 .423677 versus v1 .388848, passing the fixed promotion gates.
An untouched fresh holdout scored spell F1 .472460 clean, .401379 with 40%/4s ball
gaps, and .346548 with combined gaps, player dropout, coordinate noise and sparse
ball jumps. The frozen v1 comparator scored .467405, .401362 and .201626.
These use the organiser's actual scoring functions on external-provider labels.
They do not establish hidden challenge performance; simulated errors and one
holdout match limit generalization. No tuning followed the holdout.

The 767185-byte numeric JSON model uses NumPy at inference; pandas supports the
official format check. On our Windows CPU, the full 199319-frame input-to-CSV run
took 49.662 seconds with peak process working set
118521856 bytes. A cached rerun took 9.057
seconds and produced identical UTF-8/LF bytes. Both passed the official validator.
Candidate SHA256: `d000a49eb8db71ac94da4877abe5b85506d05be233db1f43644df1e4c9e653fd`.

Install `requirements-lock.txt` in Python 3.13, supply the tactical inputs under
`more-than-a-hack-2027-main/data/`, then run `python tools/run_candidate.py`.
`--data-dir` supports another input location. The code-only package includes
frozen source/model/configuration and evaluation evidence, with private inputs
excluded. [SOLUTION.md](SOLUTION.md) explains reproduction and limitations;
[THIRD_PARTY.md](THIRD_PARTY.md) credits Sportec/DFL CC BY 4.0 data, Metrica metrics
and the separately preserved reference baseline.

Before submission, insert the registered team name and apply the email's exact
file naming, form and repository requirements. This prepared draft is unsubmitted.
