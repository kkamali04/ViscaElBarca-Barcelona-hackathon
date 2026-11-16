"""Evidence, bounded optional automatic tags, temporal decoding and CSV output."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
import numpy as np

from .decoder import decode_scores
from .evidence import feature_matrix, heuristic_scores
from .trees import TreeModel

OFFENSIVE = {"players in the box", "ball in final third", "ball in the box",
             "progression", "creating chances", "long ball", "attacking transition", "build up"}
DEFENSIVE = {"defending in defensive third", "defending in middle third",
             "defensive transition", "defending in attacking third"}

FROZEN_SOURCES = ("possession_model/__init__.py", "possession_model/features.py", "possession_model/evidence.py",
    "possession_model/decoder.py", "possession_model/trees.py", "possession_model/pipeline.py",
    "possession_model/schema.py", "validation/sportec.py", "validation/metrics.py", "tools/train_and_validate.py",
    "tools/run_candidate.py", "experiments/__init__.py", "experiments/noise_v2/__init__.py", "experiments/noise_v2/features.py",
    "more-than-a-hack-2027-main/evaluation/possession_metrics.py", "requirements-lock.txt")


def source_fingerprints(root):
    return {name: hashlib.sha256((Path(root)/name).read_bytes()).hexdigest() for name in FROZEN_SOURCES}


def verify_frozen_sources(root, config):
    if config.get("source_sha256") != source_fingerprints(root):
        raise ValueError("Source differs from frozen validation run; audit and validate changes before inference")


def tag_support(path, n_frames, fps, home="Barcelona", away="Atletic Club"):
    """Return bounded H/A weak phase support, never hard possession/dead labels.

    Set-piece/goal interval endpoints are deliberately not used as boundaries.
    Overlap is capped per side, so correlated duplicate tags cannot accumulate.
    This optional channel cannot be independently validated on Sportec inputs.
    """
    sides = {home.strip().casefold(): 0, away.strip().casefold(): 1}
    out = np.zeros((n_frames, 2), np.float32)
    for event in ET.parse(path).iter("instance"):
        code = (event.findtext("code") or "").strip().casefold()
        tags = {(x.findtext("group") or "").strip().casefold():
                (x.findtext("text") or "").strip().casefold() for x in event.findall("label")}
        side = sides.get(tags.get("team", ""))
        if side is None or code not in OFFENSIVE | DEFENSIVE:
            continue
        weight = 1. if code in OFFENSIVE else .5
        if code in DEFENSIVE:
            side = 1-side
        start = max(0, round(float(event.findtext("start"))*fps))
        stop = min(n_frames, round(float(event.findtext("end"))*fps))
        if stop > start:
            out[start:stop, side] = np.maximum(out[start:stop, side], weight)
    return out


def predict(features, config, model_path=None, tags=None, forced_dead=()):
    if config["emitter"] == "heuristic":
        scores = heuristic_scores(features)
    elif config["emitter"] == "trees":
        if model_path is None:
            raise ValueError("Tree emitter requires model_path")
        matrix, names, _ = feature_matrix(features)
        scores = TreeModel.load(model_path).scores(matrix, names)
    else:
        raise ValueError("Unknown emitter")
    weight = float(config.get("tag_weight", 0))
    if tags is not None and weight:
        scores[:, :2] += weight*tags
    for start, stop in forced_dead:
        scores[start:stop, :2] = -np.inf
        scores[start:stop, 2] = 0
    penalty = float(config["transition_seconds"])*features.fps
    costs = np.full((3, 3), penalty, dtype=np.float64)
    np.fill_diagonal(costs, 0)
    return decode_scores(scores, features.period_id, costs)


def write_submission(path, codes):
    path = Path(path)
    values = np.asarray(codes)
    if values.ndim != 1 or values.dtype.kind not in "fiu" or not np.isin(values, (-1, 0, 1, 2)).all():
        raise ValueError("Prediction codes must be a one-dimensional sequence of -1/0/1/2")
    path.parent.mkdir(parents=True, exist_ok=True)
    labels = ("H", "A", "D")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent,
                                         prefix=".possession-", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            output.write("frame,label\n")
            for frame, value in enumerate(values):
                code = int(value)
                output.write(f"{frame},{'X' if code < 0 else labels[code]}\n")
            output.flush()
            os.fsync(output.fileno())
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        os.replace(temporary, path)
        return digest
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_config(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
