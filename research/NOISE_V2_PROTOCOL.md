# Noise v2 experiment protocol

Registered 2026-11-15 before v2 numerical model results. This is a new experiment version; v1 sources, models, configuration and reports remain frozen. The implementation author is not the acceptance tester. Root will obtain independent acceptance and orchestrate data preparation, training and evaluation.

## Fixed feature intervention

Replace only `FeatureSet.ball_speed` with the magnitude of a centred local-linear coordinate slope. Use a nominal 1.2 s odd window: half-width `max(1, round(0.6 * fps))`, giving 31 observations spanning 1.2 s at 25 Hz. For centred sample times `t`, fit each coordinate's linear slope with weights `t / sum(t*t)`. Compute the x/y slopes before their Euclidean magnitude; do not smooth adjacent speed magnitudes. Implement with NumPy convolution only; inference has no SciPy dependency.

Split observations at missing/nonfinite ball positions, false `ball_observed`, the existing `reliable_ball_mask` jump guard, nonpositive periods and every period change. Require a complete window within one uninterrupted reliable run. Leave insufficient run edges/windows unknown (`NaN`), and reject resulting speeds above 60 m/s. Preserve all other input arrays by reference without mutating them; copy metadata to identify the transformation. No interpolation across gaps, no new loader, no other feature changes.

The coefficient construction is an independent least-squares derivation. SciPy's primary [`savgol_coeffs` documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.savgol_coeffs.html), checked 2026-11-15, specifies derivative order, sample spacing, centred position and dot/convolution coefficient ordering. An optional test can compare against `polyorder=1, deriv=1, delta=1/fps, use='dot'`; production code does not import SciPy and no documentation code is copied.

This linear smoother suppresses uncorrelated jitter but has positive residual magnitude bias and reduces rapid turns, curved travel and accelerations to a window-averaged velocity vector. Opposite-direction motion can cancel. It uses future observations, so it is offline. At 25 Hz it loses 15 frames at each reliable-run edge; outlier guard expansion and fragmented observations can remove many windows. Correlated noise, slow calibration drift and sub-60 m/s erroneous motion can survive. These limitations remain reportable even if synthetic tests pass.

## Preregistered split and model comparison

- Development: J03WOH. Validation/selection: J03WOY. Existing v1 holdout J03WR9 remains closed.
- Fresh holdout: J03WMX, first-division competition COM000001. This is the lexicographically first unused metadata ID, selected from filenames before labels were inspected. This protocol records that root-supplied selection; the implementation author does not open its data or labels.
- Four fixed development and validation conditions: clean; 40% ball-coordinate deletion in 4 s blocks; 40% deletion in 12 s blocks; combined 40%/4 s ball deletion plus 30%/1 s player dropout, 0.25 m coordinate noise and 20 m teleports at probability 1/250 per frame.
- Development condition seeds: `20261118 + n`; validation seeds: `20261128 + n`, with `n=0,1,2,3` in the condition order above. Corruptions are generated independently of target labels. Root must record exact corruption ordering and affected coordinate channels before model evaluation; reuse identical corruptions for both versions.
- Keep the tree family fixed: 64 boosting iterations, 15 leaves, and the remaining declared v1 family parameters. Transition costs: 0.25, 0.5, 1 or 2 seconds. No extra feature, family or parameter search follows validation inspection.
- Select maximum mean spell F1 over the four validation conditions, with mean macro F1 as tie-break. Compare v2 to the frozen v1 candidate on the same four conditions. Advance only with at least +0.02 mean spell F1 and at most 0.02 clean spell-F1 loss. Otherwise retain v1 and do not evaluate a new holdout.
- Freeze source hashes, transformation metadata, model, selected transition cost, data signatures, corruption implementation/seeds and report before any fresh-holdout access. Only then evaluate J03WMX once on clean, 40%/4 s ball gaps and the combined condition. Root must register the fresh-holdout corruption seeds before access. Do not select, tune or reinterpret the frozen experiment after this result.

## Verification and efficient execution

### Final root registration before model evaluation

Corruption order is fixed to the existing `tools/check_robustness.py`
`build_stressed_features` implementation: draw independent fixed-shape Gaussian
noise for x/y of complete observed player and ball pairs, apply one-second
per-slot player dropout, apply the ball block mask, then apply 20 m random-angle
one-frame teleports only where the ball remains observed. Metadata/periods,
frame IDs and target labels are never perturbed. Separate RNG streams use
condition seed +101 (dropout), +202 (noise), +303 (teleports). All conditions are
identical across v1/v2. The clean case has zero perturbation parameters.

Fresh J03WMX holdout conditions are clean (seed20261208), 40%/4s ball gaps
(seed20261209), and the full combined case (seed20261210). Holdout raw bytes were
downloaded and hash-verified by filename only; no parsing or target access occurs
before selection freeze. A failed promotion gate means no fresh holdout scoring.
This registration is before any v2 model/validation numerical result.

Before match-level results, independently accept invented-coordinate tests for a noiseless linear ramp, stationary sigma 0.2 m jitter, true 1 m/s translation with the same jitter, gaps, period resets, sparse teleports, insufficient runs, speed-limit rejection and input immutability. Test coefficient parity against SciPy only if installed in the training environment. Physics tests establish estimator behavior, not football prediction performance.

Replay cached coordinates once per fixed condition and version; never reparse the large XML for each parameter. Run the fixed emitter/decoder grid from cached features without retraining per corruption or transition cost. Report class frame F1, H/A spell F1, transition precision/recall, reliable/finite-motion coverage, runtime and peak memory. Compare clean/perturbed results within the same match; corruption conditions are not independent matches. State provider/target-semantic and measurement-domain limits. No holdout or challenge result is authorized by this implementation task.

## Implementation verification recorded after registration

Command: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_noise_v2_features.py -v`.

All 10 implementation unit tests passed on 2026-11-15 in 0.957 s, including the optional SciPy coefficient and output comparison. For 2,001 invented frames with seed 20261115 and per-axis sigma 0.2 m noise, stationary mean speed was 0.1294804 m/s (95th percentile 0.2532031); true 1 m/s translation under the identical noise had mean 1.0058750 m/s. There were 1,971 finite outputs and 30 unknown edge frames. These are implementation-author unit checks, not independent acceptance, model selection, external-match evidence or validation results. Root must still arrange a fresh acceptance tester and complete the remaining corruption-seed/ordering registration before accessing model results.
