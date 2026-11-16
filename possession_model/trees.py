"""Portable numeric boosted-tree inference. Runtime dependency: NumPy only.

Training uses pinned scikit-learn separately. Export is equivalence-tested before
use. JSON stores data/thresholds only; no executable pickle is loaded.
"""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np


class TreeModel:
    def __init__(self, document):
        if not isinstance(document, dict) or document.get("format") != "numeric-hgb-v1":
            raise ValueError("Unsupported tree model format")
        self.document = document
        names = document.get("feature_names")
        if (not isinstance(names, list) or not names
                or any(not isinstance(name, str) or not name for name in names)
                or len(set(names)) != len(names)):
            raise ValueError("Feature names must be unique nonempty strings")
        self.names = list(names)
        self.baseline = self._real_array(document.get("baseline"), "baseline")
        if self.baseline.shape != (3,):
            raise ValueError("Expected finite three-class baseline")
        if not isinstance(document.get("trees"), list):
            raise ValueError("Expected a list of numeric trees")
        self.trees = []
        for tree in document["trees"]:
            if not isinstance(tree, dict):
                raise ValueError("Invalid numeric tree structure")
            target = tree.get("class")
            if (isinstance(target, (bool, np.bool_))
                    or not isinstance(target, (int, np.integer)) or not 0 <= target < 3):
                raise ValueError("Tree class must be integer 0, 1 or 2")
            self.trees.append((int(target), self._validated_nodes(tree.get("nodes"))))

    @staticmethod
    def _real_array(values, name):
        try:
            raw = np.asarray(values)
            if raw.dtype.kind not in "fiu":
                raise ValueError("not real numeric")
            result = raw.astype(np.float64, copy=True)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"Invalid numeric model {name}") from exc
        if not np.isfinite(result).all():
            raise ValueError(f"Model {name} must be finite")
        return result

    def _validated_nodes(self, raw):
        keys = {"value", "feature_idx", "num_threshold", "missing_go_to_left", "left", "right", "is_leaf"}
        if not isinstance(raw, dict) or set(raw) != keys:
            raise ValueError("Numeric tree node schema differs from numeric-hgb-v1")
        nodes = {}
        for key, values in raw.items():
            if key in ("value", "num_threshold"):
                nodes[key] = self._real_array(values, key)
            else:
                try:
                    array = np.asarray(values)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Invalid tree node array {key}") from exc
                allowed = "biu" if key in ("is_leaf", "missing_go_to_left") else "iu"
                if array.dtype.kind not in allowed:
                    raise ValueError(f"Tree node {key} must contain integers")
                nodes[key] = array.copy()
        lengths = {array.size for array in nodes.values()}
        if (any(array.ndim != 1 for array in nodes.values()) or len(lengths) != 1
                or not lengths or not 0 < next(iter(lengths)) <= np.iinfo(np.int32).max):
            raise ValueError("Tree node arrays must have the same positive one-dimensional length")
        count = len(nodes["value"])
        for key in ("is_leaf", "missing_go_to_left"):
            if not np.isin(nodes[key], (0, 1)).all():
                raise ValueError(f"Tree node {key} must contain only 0 or 1")
            nodes[key] = nodes[key].astype(bool)
        if ((nodes["feature_idx"] < 0).any() or (nodes["feature_idx"] >= len(self.names)).any()):
            raise ValueError("Tree feature index outside model schema")
        for key in ("left", "right"):
            if (nodes[key] < 0).any() or (nodes[key] >= count).any():
                raise ValueError("Tree child index outside node arrays")
        for key in ("feature_idx", "left", "right"):
            nodes[key] = nodes[key].astype(np.int64)
        internal = ~nodes["is_leaf"]
        parents = np.zeros(count, dtype=np.int64)
        for key in ("left", "right"):
            np.add.at(parents, nodes[key][internal], 1)
        if parents[0] or (parents[1:] != 1).any():
            raise ValueError("Tree routing requires one root and one parent per other node")
        visited = np.zeros(count, dtype=bool)
        pending = [0]
        while pending:
            index = pending.pop()
            if visited[index]:
                raise ValueError("Cyclic or repeated tree routing")
            visited[index] = True
            if not nodes["is_leaf"][index]:
                pending.extend((int(nodes["left"][index]), int(nodes["right"][index])))
        if not visited.all():
            raise ValueError("Unreachable or cyclic tree nodes")
        for array in nodes.values():
            array.flags.writeable = False
        return nodes

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def raw_scores(self, matrix, feature_names, chunk_size=8192):
        if isinstance(chunk_size, (bool, np.bool_)) or not isinstance(chunk_size, (int, np.integer)) or chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer")
        x = np.asarray(matrix, dtype=np.float32)
        if list(feature_names) != self.names or x.ndim != 2 or x.shape[1] != len(self.names):
            raise ValueError("Feature schema differs from trained model")
        out = np.empty((len(x), 3), dtype=np.float64)
        for start in range(0, len(x), chunk_size):
            part = x[start:start+chunk_size]
            scores = np.broadcast_to(self.baseline, (len(part), 3)).copy()
            for target, nodes in self.trees:
                index = np.zeros(len(part), np.int32)
                active = np.ones(len(part), bool)
                while active.any():
                    rows = np.flatnonzero(active)
                    node = index[rows]
                    leaf = nodes["is_leaf"][node].astype(bool)
                    try:
                        with np.errstate(over="raise", invalid="raise"):
                            scores[rows[leaf], target] += nodes["value"][node[leaf]]
                    except FloatingPointError as exc:
                        raise ValueError("Tree score accumulation exceeds finite float64 range") from exc
                    active[rows[leaf]] = False
                    rows, node = rows[~leaf], node[~leaf]
                    if len(rows):
                        value = part[rows, nodes["feature_idx"][node]]
                        left = np.where(np.isnan(value), nodes["missing_go_to_left"][node],
                                        value <= nodes["num_threshold"][node]).astype(bool)
                        index[rows] = np.where(left, nodes["left"][node], nodes["right"][node])
            out[start:start+len(part)] = scores
        return out

    def scores(self, matrix, names):
        raw = self.raw_scores(matrix, names)
        try:
            # Exponential underflow is expected for low-probability classes;
            # overflow or invalid centring must never become a nonfinite score.
            with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
                raw -= raw.max(axis=1, keepdims=True)
                # Log probabilities. A common frame offset cannot change DP.
                normalized = raw-np.log(np.exp(raw).sum(axis=1, keepdims=True))
        except FloatingPointError as exc:
            raise ValueError("Tree score normalization exceeds finite float64 range") from exc
        return np.clip(normalized, -8, 0).astype(np.float32)


def export_sklearn(estimator, names, provenance):
    """Export numeric predictors only. Fail closed on changed sklearn internals."""
    if list(estimator.classes_) != [0, 1, 2]:
        raise ValueError("Expected classes H=0 A=1 D=2")
    trees = []
    keys = ("value", "feature_idx", "num_threshold", "missing_go_to_left", "left", "right", "is_leaf")
    for iteration in estimator._predictors:
        if len(iteration) != 3:
            raise ValueError("Unexpected multiclass predictor structure")
        for target, predictor in enumerate(iteration):
            if np.any(predictor.nodes["is_categorical"]):
                raise ValueError("Categorical trees are not supported")
            nodes = {key: predictor.nodes[key].tolist() for key in keys}
            # sklearn uses +inf for missing-only splits. All inference features
            # are float32, so a finite float64 extremum has identical routing
            # while keeping the artifact valid strict JSON across languages.
            thresholds = np.asarray(nodes["num_threshold"], dtype=np.float64)
            if np.isnan(thresholds).any():
                raise ValueError("Unexpected NaN split threshold")
            nodes["num_threshold"] = np.nan_to_num(thresholds, posinf=np.finfo(np.float64).max,
                                                   neginf=-np.finfo(np.float64).max).tolist()
            trees.append({"class": target, "nodes": nodes})
    return {"format": "numeric-hgb-v1", "feature_names": list(names),
            "baseline": estimator._baseline_prediction.ravel().tolist(),
            "trees": trees, "provenance": provenance}
