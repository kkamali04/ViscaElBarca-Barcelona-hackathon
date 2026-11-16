"""Predeclared noise-v2 experiment: select on one match, freeze, fresh test once.

Only OTHER matches enter this script. It never opens challenge inputs, its GT,
or the original v1 holdout. Corruptions follow research/NOISE_V2_PROTOCOL.md.
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.noise_v2.features import robustify_ball_motion
from possession_model.evidence import feature_matrix
from possession_model.pipeline import predict, source_fingerprints, verify_frozen_sources
from possession_model.schema import FeatureSet
from possession_model.trees import TreeModel, export_sklearn
from tools.check_robustness import build_stressed_features
from validation.metrics import measure, reference_baseline
from validation.sportec import _build_cache, read_metadata

ARRAYS = ("period_id", "ball_xy", "ball_observed", "nearest", "tracked_counts", "collective_speed", "ball_speed")
COSTS = (.25, .5, 1., 2.)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def condition(which, seed):
    return {"name": which, "seed": seed, "ball_missing_fraction": 0. if which == "clean" else .4,
            "ball_block_seconds": 12. if which == "long_gaps" else 4.,
            "player_slot_dropout_probability": .3 if which == "combined" else 0., "player_block_seconds": 1.,
            "coordinate_noise_std_m": .25 if which == "combined" else 0.,
            "teleport_probability_per_timeline_frame": 1/250 if which == "combined" else 0.,
            "teleport_distance_m": 20.}


def conditions(seed, holdout=False):
    names = ("clean", "occluded", "combined") if holdout else ("clean", "occluded", "long_gaps", "combined")
    return [condition(name, seed+i) for i, name in enumerate(names)]


def load(match, spec):
    folder = ROOT/"local/external"/match
    meta, raw = next(folder.glob("*matchinformation*.xml")), next(folder.glob("*positions_raw_observed*.xml"))
    metadata = read_metadata(meta)
    raw_folder, layout = _build_cache(meta, raw, metadata)
    identity = {"raw_cache": raw_folder.name, "spec": spec,
                "extractor": sha(ROOT/"possession_model/features.py"),
                "corruption": sha(ROOT/"tools/check_robustness.py")}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
    cache = ROOT/"local/noise-v2"/f"{match}-{key}.npz"
    stats_path = cache.with_suffix(".json")
    if cache.exists() and stats_path.exists():
        with np.load(cache, allow_pickle=False) as stored:
            base = FeatureSet(fps=layout["fps"], pitch=tuple(metadata["pitch"]), **{name: stored[name] for name in ARRAYS})
        stats = json.loads(stats_path.read_text())
    else:
        positions, ball = np.load(raw_folder/"positions.npy", mmap_mode="r"), np.load(raw_folder/"ball.npy", mmap_mode="r")
        base, stats = build_stressed_features(positions, ball, metadata, layout, spec)
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache, **{name: getattr(base, name) for name in ARRAYS})
        dump(stats_path, stats)
    # Targets are first loaded after condition generation/feature extraction.
    truth = np.load(raw_folder/"truth.npy")
    provenance = {"match": match, "raw_sha256": sha(raw), "metadata_sha256": sha(meta),
                  "condition": spec, "observations": stats, "labels_used_for_features": False}
    return base, robustify_ball_motion(base), truth, provenance


def select():
    if (ROOT/"reports/noise-v2-holdout.json").exists():
        raise FileExistsError("Fresh holdout already scored; preserve frozen experiment")
    from sklearn.ensemble import HistGradientBoostingClassifier
    import sklearn
    train_specs, val_specs = conditions(20261118), conditions(20261128)
    xs, ys, sources = [], [], []
    start = time.perf_counter()
    for spec in train_specs:
        base, robust, truth, provenance = load("J03WOH", spec)
        x, names, pairs = feature_matrix(robust)
        rows = np.arange(0, len(truth), 5)
        rows = rows[(truth[rows] >= 0) & (robust.period_id[rows] > 0)]
        x, y = x[rows], truth[rows]
        swapped = x.copy()
        for h, a in pairs:
            swapped[:, [h, a]] = x[:, [a, h]]
        xs.extend([x, swapped]); ys.extend([y, np.where(y == 2, 2, 1-y)])
        sources.append(provenance)
        print("V2 training features:", spec["name"], len(rows), flush=True)
    x, y = np.concatenate(xs), np.concatenate(ys)
    counts = np.bincount(y, minlength=3)
    if (counts == 0).any():
        raise ValueError("Development data lacks a required target class")
    weights = len(y)/(3*counts[y])
    model = HistGradientBoostingClassifier(max_iter=64, max_leaf_nodes=15, learning_rate=.08,
        l2_regularization=2., min_samples_leaf=80, max_bins=63, early_stopping=False,
        categorical_features=None, random_state=20261115).fit(x, y, sample_weight=weights)
    document = export_sklearn(model, names, {"experiment": "noise-v2", "sklearn": sklearn.__version__,
        "training_match": "J03WOH", "parameters": model.get_params(), "conditions": train_specs,
        "stride": 5, "side_swap_augmentation": True, "source": sources})
    portable = TreeModel(document)
    probe = x[::max(1, len(x)//4096)]
    error = float(np.max(np.abs(model._raw_predict(probe)-portable.raw_scores(probe, names))))
    if error > 1e-10:
        raise ValueError("V2 numeric export parity failed")
    document["provenance"]["export_max_raw_error"] = error
    model_path = ROOT/"models/noise-v2-trees.json"
    dump(model_path, document)
    del x, y, xs, ys, swapped, model, portable
    original = json.loads((ROOT/"models/selected-safe.json").read_text())
    verify_frozen_sources(ROOT, original)
    rows = []
    for spec in val_specs:
        base, robust, truth, provenance = load("J03WOY", spec)
        v1 = measure(truth, predict(base, original, ROOT/original["model"]), base.period_id)
        for cost in COSTS:
            config = {"emitter": "trees", "transition_seconds": cost, "tag_weight": 0.}
            metrics = measure(truth, predict(robust, config, model_path), robust.period_id)
            rows.append({"condition": spec["name"], "transition_seconds": cost, "candidate": metrics,
                         "v1_reference": v1, "provenance": provenance})
            print(f"V2 validation {spec['name']}/{cost}: spell={metrics['spell_f1']:.4f}, v1={v1['spell_f1']:.4f}", flush=True)
    candidates = []
    for cost in COSTS:
        matching = [r for r in rows if r["transition_seconds"] == cost]
        candidates.append({"transition_seconds": cost,
            "mean_spell_f1": float(np.mean([r["candidate"]["spell_f1"] for r in matching])),
            "mean_macro_f1": float(np.mean([r["candidate"]["macro_f1"] for r in matching]))})
    best = max(candidates, key=lambda item: (item["mean_spell_f1"], item["mean_macro_f1"]))
    chosen = [r for r in rows if r["transition_seconds"] == best["transition_seconds"]]
    reference = float(np.mean([r["v1_reference"]["spell_f1"] for r in chosen]))
    clean = next(r for r in chosen if r["condition"] == "clean")
    promote = best["mean_spell_f1"] >= reference+.02 and clean["candidate"]["spell_f1"] >= clean["v1_reference"]["spell_f1"]-.02
    config = {"release": "noise-v2", "emitter": "trees", "transition_seconds": best["transition_seconds"],
        "tag_weight": 0., "feature_transform": "local-linear-v2", "model": "models/noise-v2-trees.json",
        "model_sha256": sha(model_path), "source_sha256": source_fingerprints(ROOT),
        "experiment_script_sha256": sha(Path(__file__)), "corruption_script_sha256": sha(ROOT/"tools/check_robustness.py"),
        "protocol_sha256": sha(ROOT/"research/NOISE_V2_PROTOCOL.md"),
        "training_match": "J03WOH", "selection_match": "J03WOY", "holdout_match": "J03WMX",
        "holdout_conditions": conditions(20261208, True), "promotion_gate_passed": bool(promote)}
    dump(ROOT/"models/selected-noise-v2.json", config)
    dump(ROOT/"reports/noise-v2-validation.json", {"rows": rows, "grid": candidates, "best": best,
        "v1_mean_spell_f1": reference, "mean_spell_gain": best["mean_spell_f1"]-reference,
        "promotion_gate_passed": bool(promote), "training_export_max_error": error,
        "seconds": time.perf_counter()-start, "config_sha256": sha(ROOT/"models/selected-noise-v2.json")})
    print("V2 frozen; promotion gate:", bool(promote), "mean spell gain:", best["mean_spell_f1"]-reference, flush=True)


def holdout():
    destination = ROOT/"reports/noise-v2-holdout.json"
    if destination.exists():
        raise FileExistsError("Fresh holdout already evaluated; never overwrite")
    path = ROOT/"models/selected-noise-v2.json"
    config = json.loads(path.read_text())
    verify_frozen_sources(ROOT, config)
    if not config["promotion_gate_passed"]:
        raise ValueError("Predeclared promotion gate failed; do not access fresh holdout")
    if (sha(Path(__file__)) != config["experiment_script_sha256"] or sha(ROOT/config["model"]) != config["model_sha256"]
        or sha(ROOT/"tools/check_robustness.py") != config["corruption_script_sha256"]):
        raise ValueError("Experiment changed after freeze")
    original = json.loads((ROOT/"models/selected-safe.json").read_text())
    results = []
    for spec in config["holdout_conditions"]:
        base, robust, truth, provenance = load(config["holdout_match"], spec)
        start = time.perf_counter()
        codes = predict(robust, config, ROOT/config["model"])
        seconds = time.perf_counter()-start
        row = {"condition": spec["name"], "candidate": measure(truth, codes, robust.period_id),
               "v1_reference": measure(truth, predict(base, original, ROOT/original["model"]), base.period_id),
               "smooth50": measure(truth, reference_baseline(base), base.period_id),
               "candidate_seconds": seconds, "provenance": provenance}
        results.append(row)
        print(f"Fresh holdout {spec['name']}: v2={row['candidate']['spell_f1']:.4f}, v1={row['v1_reference']['spell_f1']:.4f}", flush=True)
    dump(destination, {"match": config["holdout_match"], "config_sha256": sha(path),
                       "used_for_selection_or_tuning": False, "results": results,
                       "limitation": "One fresh external provider match with simulated corruptions; not challenge accuracy"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("select", "holdout"))
    phase = parser.parse_args().phase
    select() if phase == "select" else holdout()
