"""Fixed post-selection stress checks on validation match J03WOY only.

This script does not train, rank, select, alter or tune a model. It loads the
frozen selected configuration, verifies its source/model fingerprints, then
compares that one candidate with the reference smooth50 implementation under
two predefined corruptions. No challenge assets/GT or holdout assets are opened.

1. 40% of timeline frames hidden in 12-second ball-gap blocks, seed 20261116.
2. 40% ball gaps in 4-second blocks; independent per-slot 30% one-second block
   dropout; 0.25 m Gaussian coordinate noise; 20 m one-frame ball teleports with
   probability 1/250 per timeline frame, seed 20261117. Teleports are applied
   only when the ball remains observed. They can be smaller/greater than the
   adjacent displacement threshold when combined with real motion and noise.

All corruptions depend on fixed RNG seeds, dimensions and observed coordinates,
never BallStatus/BallPossession. Targets are loaded after feature construction.
Player positions are read one frame at a time from existing disk memmaps.
The mask for player dropout is only (one-second blocks x roster slots).

These are diagnostics on the already-used validation match, not another final
holdout or hidden challenge performance. They do not authorize retuning after
observing their results. The report is write-once to preserve the experiment.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from possession_model.evidence import reliable_ball_mask
from possession_model.features import FeatureAccumulator
from possession_model.pipeline import predict, verify_frozen_sources
from tools.fetch_validation_data import filename
from validation.metrics import measure, reference_baseline
from validation.sportec import PAPER, _build_cache, make_ball_gap_mask, read_metadata


MATCH = "J03WOY"
REPORT = ROOT / "reports/independent-robustness.json"
CONDITIONS = (
    {
        "name": "long_ball_gaps_12s",
        "seed": 20261116,
        "ball_missing_fraction": .4,
        "ball_block_seconds": 12.,
        "player_slot_dropout_probability": 0.,
        "player_block_seconds": 1.,
        "coordinate_noise_std_m": 0.,
        "teleport_probability_per_timeline_frame": 0.,
        "teleport_distance_m": 20.,
    },
    {
        "name": "combined_tracking_errors",
        "seed": 20261117,
        "ball_missing_fraction": .4,
        "ball_block_seconds": 4.,
        "player_slot_dropout_probability": .3,
        "player_block_seconds": 1.,
        "coordinate_noise_std_m": .25,
        "teleport_probability_per_timeline_frame": 1/250,
        "teleport_distance_m": 20.,
    },
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_stressed_features(positions, ball, metadata, layout, condition):
    """Generate corruptions before opening targets, with bounded working memory."""
    started = time.perf_counter()
    n, n_slots, fps = layout["n_frames"], len(metadata["slots"]), layout["fps"]
    blocks = layout["blocks"]
    half_open = [(b["period"], b["start"], b["end"]) for b in blocks]
    acc = FeatureAccumulator(n, metadata["team_of_slot"], fps, metadata["pitch"], half_open)
    ball_gaps = make_ball_gap_mask(n, blocks, fps,
        condition["ball_missing_fraction"], condition["ball_block_seconds"], condition["seed"])
    # Distinct fixed streams prevent one corruption's draw count changing another.
    dropout_rng = np.random.default_rng(condition["seed"] + 101)
    noise_rng = np.random.default_rng(condition["seed"] + 202)
    teleport_rng = np.random.default_rng(condition["seed"] + 303)
    width = max(1, round(condition["player_block_seconds"] * fps))
    segment_counts = [(b["end"] - b["start"] + width - 1)//width for b in blocks]
    drop = dropout_rng.random((sum(segment_counts), n_slots)) < condition["player_slot_dropout_probability"]
    teleport_frames = teleport_rng.random(n) < condition["teleport_probability_per_timeline_frame"]
    angles = teleport_rng.uniform(0, 2*np.pi, n)
    sigma = condition["coordinate_noise_std_m"]
    base_ball_observations = retained_ball_observations = 0
    base_player_observations = retained_player_observations = applied_teleports = 0
    block_offset = 0
    for b, segment_count in zip(blocks, segment_counts):
        for index in range(b["start"], b["end"]):
            points = np.array(positions[index], dtype=np.float64, copy=True)
            current_ball = np.array(ball[index], dtype=np.float64, copy=True)
            players_seen = np.isfinite(points).all(axis=1)
            ball_seen = bool(np.isfinite(current_ball).all())
            base_player_observations += int(players_seen.sum())
            base_ball_observations += ball_seen
            if sigma:
                # Draw a fixed shape regardless of missingness, then apply only
                # to complete observed coordinate pairs.
                player_noise = noise_rng.normal(0, sigma, points.shape)
                ball_noise = noise_rng.normal(0, sigma, 2)
                points[players_seen] += player_noise[players_seen]
                if ball_seen:
                    current_ball += ball_noise
            segment = block_offset + (index - b["start"])//width
            points[drop[segment]] = np.nan
            retained_player_observations += int(np.isfinite(points).all(axis=1).sum())
            if ball_gaps[index] or not ball_seen:
                current_ball[:] = np.nan
            else:
                retained_ball_observations += 1
                if teleport_frames[index]:
                    current_ball += condition["teleport_distance_m"] * np.array([np.cos(angles[index]), np.sin(angles[index])])
                    applied_teleports += 1
            acc.push(index, points, current_ball, b["period"])
        block_offset += segment_count
    features = acc.finish()
    stats = {
        "n_frames": n,
        "n_roster_slots": n_slots,
        "base_ball_observation_rate": base_ball_observations/n,
        "stressed_ball_observation_rate": retained_ball_observations/n,
        "reliable_ball_geometry_rate_after_jump_guard": float(reliable_ball_mask(features).mean()),
        "masked_ball_timeline_frames": int(ball_gaps.sum()),
        "masked_ball_timeline_fraction": float(ball_gaps.mean()),
        "base_player_observations": base_player_observations,
        "retained_player_observations": retained_player_observations,
        "retained_natural_player_observation_fraction": retained_player_observations/base_player_observations if base_player_observations else None,
        "mean_visible_players_per_side": features.tracked_counts.mean(axis=0).tolist(),
        "drawn_teleport_frames": int(teleport_frames.sum()),
        "applied_observed_ball_teleports": applied_teleports,
        "feature_array_bytes": features.array_bytes,
        "player_ring_bytes": acc.ring_bytes,
        "dropout_mask_bytes": drop.nbytes,
        "feature_seconds": time.perf_counter()-started,
    }
    return features, stats


def main():
    if REPORT.exists():
        raise FileExistsError("Robustness report already exists; retain the original fixed experiment")
    started = time.perf_counter()
    config_path = ROOT / "models/selected.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("selection_match") != MATCH:
        raise ValueError("This fixed script may inspect only the declared validation match J03WOY")
    verify_frozen_sources(ROOT, config)
    config_digest = digest(config_path)
    model_path = ROOT / config["model"]
    if digest(model_path) != config["model_sha256"]:
        raise ValueError("Model differs from frozen selection")
    folder = ROOT / "local/external" / MATCH
    meta_path, raw_path = folder / filename(MATCH, "meta"), folder / filename(MATCH, "tracking")
    metadata = read_metadata(meta_path)
    cache_folder, layout = _build_cache(meta_path, raw_path, metadata)
    positions = np.load(cache_folder / "positions.npy", mmap_mode="r")
    ball = np.load(cache_folder / "ball.npy", mmap_mode="r")
    results = []
    for condition in CONDITIONS:
        features, observations = build_stressed_features(positions, ball, metadata, layout, condition)
        # Labels are first loaded here, after all random masks/features exist.
        truth = np.load(cache_folder / "truth.npy")
        candidate_start = time.perf_counter()
        codes = predict(features, config, model_path)
        candidate_seconds = time.perf_counter()-candidate_start
        baseline_start = time.perf_counter()
        baseline = reference_baseline(features)
        baseline_seconds = time.perf_counter()-baseline_start
        row = {
            "condition": condition,
            "observations": observations,
            "candidate": measure(truth, codes, features.period_id),
            "smooth50": measure(truth, baseline, features.period_id),
            "candidate_prediction_seconds": candidate_seconds,
            "smooth50_prediction_seconds": baseline_seconds,
        }
        results.append(row)
        print(f"Validation stress {condition['name']}: candidate spellF1={row['candidate']['spell_f1']:.4f}, "
              f"smooth50={row['smooth50']['spell_f1']:.4f}, "
              f"observed ball={observations['stressed_ball_observation_rate']:.3f}", flush=True)
        del features, truth, codes, baseline
    verify_frozen_sources(ROOT, config)
    if digest(config_path) != config_digest or digest(model_path) != config["model_sha256"]:
        raise ValueError("Frozen configuration/model changed while robustness checks ran")
    report = {
        "split": "post_selection_validation_stress",
        "match": MATCH,
        "is_additional_holdout": False,
        "used_for_selection_or_tuning": False,
        "selection_sha256": config_digest,
        "model_sha256": config["model_sha256"],
        "source_sha256": config["source_sha256"],
        "experiment_script_sha256": digest(Path(__file__)),
        "source": {"name": "IDSSE Sportec/DFL raw observed tracking", "paper": PAPER,
                   "license": "CC-BY-4.0", "match_id": metadata["match_id"],
                   "coordinate_transform": layout["coordinate_transform"]},
        "mask_and_noise_depend_on_truth": False,
        "conditions_declared_before_execution": list(CONDITIONS),
        "results": results,
        "total_seconds": time.perf_counter()-started,
        "limitations": [
            "Already-used validation match; these results are stress diagnostics, not another held-out match.",
            "Provider possession/control semantics differ from corrected Metrica challenge labels.",
            "Synthetic errors do not establish realism for all restricted ATD tracking failures.",
            "No model or constants were adjusted using these stress results.",
            "No challenge inputs, public GT or final holdout inputs were opened by this script.",
            "Reference smooth50 intentionally sees the same corrupted features, without the candidate's jump-geometry guard.",
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with REPORT.open("x", encoding="utf-8") as target:
        json.dump(report, target, indent=2, allow_nan=False)
        target.write("\n")
    print("Wrote reports/independent-robustness.json; fixed model and sources unchanged", flush=True)


if __name__ == "__main__":
    main()
