"""Use the organiser's actual metric functions on independent matches."""
from pathlib import Path
import sys
import numpy as np

UPSTREAM = Path(__file__).resolve().parents[1] / "more-than-a-hack-2027-main"
sys.path.insert(0, str(UPSTREAM / "evaluation"))
import possession_metrics as pm


def _label_codes(values, name):
    """Accept internal -1/0/1/2 or official X=3 before narrowing storage."""
    codes = np.asarray(values)
    if (codes.ndim != 1 or codes.dtype.kind not in "fiu"
            or not np.isin(codes, (-1, 0, 1, 2, pm.X)).all()):
        raise ValueError(f"{name} must contain only label codes -1, 0, 1, 2 or 3")
    return np.where(codes == -1, pm.X, codes).astype(np.int8)


def measure(truth, prediction, period_id):
    """Score aligned codes; integer period IDs <= 0 mark ungraded frames.

    Label -1 and the organiser's 3 both mean unknown/X. Period IDs must be a
    one-dimensional integer array, preventing accidental temporal boundaries.
    """
    gt = _label_codes(truth, "Truth")
    pred = _label_codes(prediction, "Prediction")
    periods = np.asarray(period_id)
    if periods.ndim != 1 or periods.dtype.kind not in "iu":
        raise ValueError("period_id must be a one-dimensional array of integers")
    if gt.shape != pred.shape or periods.shape != gt.shape:
        raise ValueError("Truth, prediction and period arrays must align")
    gt[periods <= 0] = pm.X
    cm = pm.scored_confusion(pm.confusion(gt, pred))
    # Independent matches concatenate halves. Preserve their run boundaries even
    # when both adjacent frames have the same known label (no halftime X row).
    from possession_model.evidence import period_slices
    runs = [(start+a, start+b) for start, stop in period_slices(periods)
            for a, b in pm.valid_runs(gt[start:stop])]
    filled = pm.fill_abstentions(pred, runs)
    spells = pm.spell_scores(gt, filled, runs)
    # Match transitions separately so a late first-half transition cannot pair
    # with an early second-half one in the compact concatenated timeline.
    transition_reports = [pm.transition_scores(pm.transitions(gt, [run]),
                          pm.transitions(filled, [run]), 25) for run in runs]
    matched = sum(r["n_matched"] for r in transition_reports)
    n_gt = sum(r["n_gt"] for r in transition_reports)
    n_pred = sum(r["n_pred"] for r in transition_reports)
    precision = matched/n_pred if n_pred else 0.
    recall = matched/n_gt if n_gt else 0.
    boundary = {"n_matched": matched, "n_gt": n_gt, "n_pred": n_pred,
                "precision": precision, "recall": recall,
                "f1": 2*precision*recall/(precision+recall) if precision+recall else 0.}
    return {"macro_f1": float(pm.macro_f1(cm)),
            "spell_f1": float(spells["mean_f1"]),
            "n_truth_spells": int(spells["n_gt"]), "n_predicted_spells": int(spells["n_pred"]),
            "graded_frames": int(cm.sum()), "confusion": cm.tolist(),
            "per_class_f1": {label: float(pm.per_class_prf(cm, i)[2]) for i, label in enumerate("HAD")},
            "transitions_1s": boundary}


def reference_baseline(features, width=50):
    """Official smooth50 logic, with independent match half resets."""
    from possession_model.evidence import period_slices
    d = features.nearest
    valid = np.isfinite(d).any(axis=1)
    winner = np.argmin(np.where(np.isfinite(d), d, np.inf), axis=1)
    out = np.full(features.n_frames, -1, np.int8)
    for start, stop in period_slices(features.period_id):
        side = winner[start:stop]
        known = valid[start:stop]
        i = np.arange(stop-start)
        lo, hi = np.maximum(0, i-width), np.minimum(stop-start, i+width+1)
        h = np.r_[0, np.cumsum(known & (side == 0))]
        a = np.r_[0, np.cumsum(known & (side == 1))]
        hc, ac = h[hi]-h[lo], a[hi]-a[lo]
        out[start:stop] = np.where(hc+ac == 0, 2, np.where(hc >= ac, 0, 1))
    return out
