"""Fit on one independent match, select on another, then freeze for holdout.

Never opens challenge inputs or its public GT. Fixed match split and occlusion
seeds are declared before fitting. Training uses every fifth frame; whole-match
separation avoids neighbouring-frame train/validation leakage.
"""
from __future__ import annotations

import os
os.environ.setdefault("OMP_NUM_THREADS", "4")
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from possession_model.evidence import feature_matrix
from possession_model.pipeline import predict, source_fingerprints, verify_frozen_sources
from possession_model.trees import TreeModel, export_sklearn
from validation.metrics import measure, reference_baseline
from validation.sportec import load_sportec
from tools.fetch_validation_data import filename

CONDITIONS = {"clean": {}, "occluded": {"ball_missing_fraction": .4, "block_seconds": 4., "seed": 20261115}}
COSTS = (.25, .5, 1., 2.)


def load(match, condition, conditions=None):
    folder = ROOT / "local/external" / match
    return load_sportec(folder / filename(match, "meta"), folder / filename(match, "tracking"), (conditions or CONDITIONS)[condition])


def dump(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def train():
    from sklearn.ensemble import HistGradientBoostingClassifier
    import sklearn
    xs, ys, provenance = [], [], []
    for condition in CONDITIONS:
        features, truth, source = load("J03WOH", condition)
        matrix, names, pairs = feature_matrix(features)
        rows = np.arange(0, len(truth), 5)
        rows = rows[(truth[rows] >= 0) & (features.period_id[rows] > 0)]
        x, y = matrix[rows], np.asarray(truth[rows]).copy()
        swapped = x.copy()
        for h, a in pairs:
            swapped[:, [h, a]] = x[:, [a, h]]
        xs.extend([x, swapped])
        ys.extend([y, np.where(y == 2, 2, 1-y)])
        provenance.append({"condition": condition, "source": source})
        print(f"Training features ready: {condition}, {len(rows)} sampled frames", flush=True)
    x, y = np.concatenate(xs), np.concatenate(ys)
    counts = np.bincount(y, minlength=3)
    weights = len(y)/(3*counts[y])
    model = HistGradientBoostingClassifier(max_iter=64, max_leaf_nodes=15,
        learning_rate=.08, l2_regularization=2., min_samples_leaf=80,
        max_bins=63, early_stopping=False, categorical_features=None, random_state=20261115)
    start = time.perf_counter()
    model.fit(x, y, sample_weight=weights)
    document = export_sklearn(model, names, {"training_match": "J03WOH", "sklearn": sklearn.__version__,
        "stride": 5, "side_swap_augmentation": True, "conditions": CONDITIONS,
        "parameters": model.get_params(), "source": provenance})
    portable = TreeModel(document)
    probe = x[::max(1, len(x)//4096)]
    maximum_error = float(np.max(np.abs(model._raw_predict(probe)-portable.raw_scores(probe, names))))
    if maximum_error > 1e-10:
        raise ValueError(f"Portable export parity failed: {maximum_error}")
    document["provenance"]["export_maximum_raw_score_error"] = maximum_error
    document["provenance"]["training_seconds"] = time.perf_counter()-start
    path = ROOT / "models/independent_trees.json"
    dump(path, document)
    print(f"Model exported: {path.name}, parity error {maximum_error:g}", flush=True)
    return path


def selection():
    if (ROOT / "reports/independent-holdout.json").exists():
        raise FileExistsError("Holdout already evaluated; preserve frozen artifacts. New experiments need a separate run/split.")
    model_path = train()
    results = []
    for condition in CONDITIONS:
        features, truth, source = load("J03WOY", condition)
        results.append({"condition": condition, "emitter": "smooth50", "metrics": measure(truth, reference_baseline(features), features.period_id)})
        for emitter in ("heuristic", "trees"):
            for cost in COSTS:
                config = {"emitter": emitter, "transition_seconds": cost, "tag_weight": 0.}
                start = time.perf_counter()
                codes = predict(features, config, model_path)
                row = {"condition": condition, **config, "seconds": time.perf_counter()-start,
                       "metrics": measure(truth, codes, features.period_id)}
                results.append(row)
                print(f"Validation {condition} {emitter}/{cost}: spell={row['metrics']['spell_f1']:.4f}, macro={row['metrics']['macro_f1']:.4f}", flush=True)
    candidates = []
    for emitter in ("heuristic", "trees"):
        for cost in COSTS:
            matching = [r for r in results if r["emitter"] == emitter and r.get("transition_seconds") == cost]
            candidates.append({"emitter": emitter, "transition_seconds": cost, "tag_weight": 0.,
                               "validation_mean_spell_f1": float(np.mean([r["metrics"]["spell_f1"] for r in matching])),
                               "validation_mean_macro_f1": float(np.mean([r["metrics"]["macro_f1"] for r in matching]))})
    best = max(candidates, key=lambda r: (r["validation_mean_spell_f1"], r["validation_mean_macro_f1"]))
    best.update({"selection_match": "J03WOY", "training_match": "J03WOH", "holdout_match": "J03WR9",
                 "model": "models/independent_trees.json", "conditions": CONDITIONS,
                 "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
                 "source_sha256": source_fingerprints(ROOT),
                 "selection_rule": "Maximum mean clean/occluded spellF1, macroF1 tie; no challenge GT opened"})
    dump(ROOT / "models/selected.json", best)
    dump(ROOT / "reports/independent-validation.json", {"split": "validation", "match": "J03WOY", "conditions": CONDITIONS,
         "candidate_grid_declared": {"emitters": ["heuristic", "trees"], "transition_seconds": COSTS},
         "results": results, "selected": best, "limitation": "One validation match; domain transfer and occlusion realism remain uncertain"})
    print("Frozen selection:", json.dumps(best), flush=True)


def holdout():
    report_path = ROOT / "reports/independent-holdout.json"
    if report_path.exists():
        raise FileExistsError("Final holdout already evaluated; keep original report and do not tune against it")
    config_path = ROOT / "models/selected.json"
    config = json.loads(config_path.read_text())
    verify_frozen_sources(ROOT, config)
    model_path = ROOT / config["model"]
    if hashlib.sha256(model_path.read_bytes()).hexdigest() != config["model_sha256"]:
        raise ValueError("Model differs from frozen selection")
    results = []
    for condition in config["conditions"]:
        features, truth, source = load("J03WR9", condition, config["conditions"])
        start = time.perf_counter()
        codes = predict(features, config, model_path)
        seconds = time.perf_counter()-start
        results.append({"condition": condition, "candidate": measure(truth, codes, features.period_id),
                        "smooth50": measure(truth, reference_baseline(features), features.period_id),
                        "candidate_seconds": seconds, "source": source})
        print(f"Holdout {condition}: candidate {results[-1]['candidate']['spell_f1']:.4f}, smooth50 {results[-1]['smooth50']['spell_f1']:.4f}", flush=True)
    dump(report_path, {"split": "final_holdout", "match": "J03WR9", "selection_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
                      "results": results, "used_for_tuning": False,
                      "limitation": "External provider labels and simulated missingness; not hidden challenge performance"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["select", "holdout"])
    args = parser.parse_args()
    selection() if args.phase == "select" else holdout()
