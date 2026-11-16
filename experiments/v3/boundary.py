"""Invariant observation-only boundaries and strict portable numeric head.

Inputs are the explicit v3 FeatureSet, already motion-transformed once by the
feature producer. No target, fixture identity or label enters feature inference.
NumPy is the only nonstandard runtime dependency; sklearn is never imported here.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import re

import numpy as np
from numpy.typing import NDArray

from possession_model.evidence import period_slices, reliable_ball_mask
from possession_model.schema import FeatureSet
from possession_model.trees import TreeModel, export_sklearn
from .contracts import BoundaryFeatures


_BASE_NAMES = ("min_distance_m", "abs_margin_m", "ball_speed_mps",
               "set_motion_mps", "boundary_distance_m")
BOUNDARY_NAMES = tuple(name for prefix in ("w020", "w060") for name in (
    *(f"{prefix}_pre_{x}" for x in _BASE_NAMES),
    *(f"{prefix}_post_{x}" for x in _BASE_NAMES),
    f"{prefix}_margin_product_scaled", f"{prefix}_margin_change_scaled",
    f"{prefix}_reliable_fraction_pre", f"{prefix}_reliable_fraction_post"))
CLASS_NAMES = ("NONE", "TEAM_CHANGE", "LIVE_DEAD")
FEATURE_VERSION = "v3-boundary-28-v1"
MAX_HEAD_BYTES = 524288
HEAD_BATCH_ROWS = 4096
TREE_PARAMETERS = {"max_iter": 32, "max_leaf_nodes": 7, "learning_rate": .08,
                   "l2_regularization": 2., "min_samples_leaf": 80, "max_bins": 63,
                   "early_stopping": False, "categorical_features": None}
WEIGHT_RECIPE = ("inverse inclusion probability times sqrt(N_eligible/(3*N_class)) using full known eligible fit population; "
                 "normalize final per-match-condition sum to1/8; finally divide ALL actual fit-row weights by their "
                 "global mean so sum(weights)=actual retained fit-row count")
_TRAIN = ("J03WOH", "J03WOY")
_CONDITIONS = ("clean", "ball4", "combined", "stale_players")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _array(value, dtype, shape, name):
    if not isinstance(value, np.ndarray) or value.dtype != np.dtype(dtype) or value.shape != shape:
        raise ValueError(f"{name} requires exact dtype and aligned shape")
    return value


def _validate_features(f):
    if not isinstance(f, FeatureSet):
        raise ValueError("FeatureSet required")
    if (isinstance(f.fps, (bool, np.bool_)) or not isinstance(f.fps, (float, int, np.floating, np.integer))
            or not math.isfinite(float(f.fps)) or abs(float(f.fps) - 25.) > 1e-6):
        raise ValueError("boundary features require 25Hz within1e-6")
    if not isinstance(f.pitch, (tuple, list)) or len(f.pitch) != 2:
        raise ValueError("finite positive pitch pair required")
    for v in f.pitch:
        if (isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, float, np.integer, np.floating))
                or not math.isfinite(float(v)) or v <= 0):
            raise ValueError("finite positive pitch pair required")
    if not isinstance(f.period_id, np.ndarray) or f.period_id.ndim != 1:
        raise ValueError("aligned period vector required")
    n = len(f.period_id)
    for name, dtype, shape in (("period_id", np.int16, (n,)), ("ball_xy", np.float32, (n, 2)),
            ("ball_observed", np.bool_, (n,)), ("nearest", np.float32, (n, 2)),
            ("tracked_counts", np.int16, (n, 2)), ("collective_speed", np.float32, (n, 2)),
            ("ball_speed", np.float32, (n,))):
        _array(getattr(f, name), dtype, shape, name)
    for name in ("ball_xy", "nearest", "collective_speed", "ball_speed"):
        if np.isinf(getattr(f, name)).any():
            raise ValueError("infinite feature values are malformed")
    observed = np.isfinite(f.ball_xy)
    if np.any(observed.any(axis=1) != observed.all(axis=1)) or not np.array_equal(f.ball_observed, observed.all(axis=1)):
        raise ValueError("ball observation mask/pair mismatch")
    if (f.nearest < 0).any() or (f.tracked_counts < 0).any():
        raise ValueError("distances/counts must be nonnegative")
    return n


def build_boundary_features(features: FeatureSet) -> BoundaryFeatures:
    """Full period-contained [t-k,t)/[t,t+k) summaries, no imputation."""
    n = _validate_features(features)
    f = features
    values = np.full((n, 28), np.nan, dtype=np.float32)
    valid = np.zeros((n, 2), dtype=bool)
    geometry = (reliable_ball_mask(f) & np.isfinite(f.nearest).all(axis=1)
                & np.isfinite(f.ball_xy).all(axis=1) & (f.tracked_counts >= 1).all(axis=1))
    for a, b in period_slices(f.period_id):
        m = b - a
        g = geometry[a:b]
        # Six bases, including signed margin as a non-exported intermediate.
        base = np.full((m, 6), np.nan, dtype=np.float64)
        near = f.nearest[a:b].astype(np.float64)
        base[g, 0] = np.clip(near[g].min(axis=1), 0., 30.)
        base[g, 5] = np.clip(near[g, 1] - near[g, 0], -10., 10.)
        base[g, 1] = np.abs(base[g, 5])
        base[g, 2] = np.clip(f.ball_speed[a:b][g], 0., 40.)
        motion = f.collective_speed[a:b]
        motion_ok = np.isfinite(motion)
        motion_count = motion_ok.sum(axis=1)
        np.divide(np.where(motion_ok, motion, 0.).sum(axis=1, dtype=np.float64), motion_count,
                  out=base[:, 3], where=motion_count > 0)
        base[:, 3] = np.clip(base[:, 3], 0., 12.)
        xy = f.ball_xy[a:b].astype(np.float64)
        distance = np.minimum.reduce((xy[:, 0], float(f.pitch[0]) - xy[:, 0],
                                      xy[:, 1], float(f.pitch[1]) - xy[:, 1]))
        base[g, 4] = np.clip(distance[g], -10., 30.)
        gc = np.r_[0, np.cumsum(g, dtype=np.int64)]
        run_valid = np.ones(m, dtype=bool)
        for window, k in enumerate((5, 15)):
            full = np.arange(k, m-k+1, dtype=np.int64)
            good = np.zeros(m, dtype=bool)
            if len(full):
                before = gc[full] - gc[full-k]
                after = gc[full+k] - gc[full]
                good[full] = (before >= math.ceil(.8*k)) & (after >= math.ceil(.8*k))
                col = window * 14
                values[a+full, col+12] = before / k
                values[a+full, col+13] = after / k
                margins = []
                for c in range(6):
                    x = base[:, c]
                    finite = np.isfinite(x)
                    sums = np.r_[0., np.cumsum(np.where(finite, x, 0.), dtype=np.float64)]
                    counts = np.r_[0, np.cumsum(finite, dtype=np.int64)]
                    means = []
                    for lo, hi in ((full-k, full), (full, full+k)):
                        count = counts[hi] - counts[lo]
                        mean = np.full(len(full), np.nan, dtype=np.float64)
                        np.divide(sums[hi]-sums[lo], count, out=mean, where=count >= math.ceil(.8*k))
                        means.append(mean)
                    if c < 5:
                        values[a+full, col+c] = means[0]
                        values[a+full, col+5+c] = means[1]
                    else:
                        margins = means
                values[a+full, col+10] = margins[0] * margins[1] / 100.
                values[a+full, col+11] = np.abs(margins[1] - margins[0]) / 20.
            run_valid &= good
        valid[a:b, :] = run_valid[:, None]
    if np.isinf(values).any():
        raise ValueError("boundary arithmetic exceeded finite storage")
    # Owned output buffers are frozen before the shared type adopts them.
    values.flags.writeable = False
    valid.flags.writeable = False
    return BoundaryFeatures(values, BOUNDARY_NAMES, valid)


def _validated_batch(batch):
    if not isinstance(batch, BoundaryFeatures) or batch.names != BOUNDARY_NAMES:
        raise ValueError("canonical BoundaryFeatures required")
    if not isinstance(batch.values, np.ndarray) or batch.values.ndim != 2:
        raise ValueError("boundary matrix required")
    n = len(batch.values)
    _array(batch.values, np.float32, (n, 28), "boundary values")
    _array(batch.valid, np.bool_, (n, 2), "boundary valid")
    if np.isinf(batch.values).any():
        raise ValueError("infinite boundary input")
    return n


def boundary_support(head: NumericHead, batch: BoundaryFeatures) -> NDArray[np.float32]:
    """Externally bounded raw logits; never materialize full N-by-3 scores."""
    n = _validated_batch(batch)
    q = np.zeros((n, 2), dtype=np.float32)
    for a in range(0, n, HEAD_BATCH_ROWS):
        b = min(n, a + HEAD_BATCH_ROWS)
        raw = head.raw_scores(batch.values[a:b], batch.names)
        if not isinstance(raw, np.ndarray) or raw.dtype != np.float64 or raw.shape != (b-a, 3) or not np.isfinite(raw).all():
            raise ValueError("head must return finite float64 batch logits")
        try:
            with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
                raw = raw - np.max(raw, axis=1, keepdims=True)
                np.exp(raw, out=raw)
                raw /= raw.sum(axis=1, keepdims=True)
        except FloatingPointError as exc:
            raise ValueError("boundary softmax arithmetic overflow") from exc
        q[a:b] = raw[:, 1:3]
        q[a:b][~batch.valid[a:b]] = 0.
    return q


def flatten_support(q: NDArray[np.float32], period_id: NDArray[np.int16],
                    valid: NDArray[np.bool_]) -> NDArray[np.float32]:
    if not isinstance(q, np.ndarray) or q.ndim != 2:
        raise ValueError("q requires float32[N,2]")
    n = len(q)
    _array(q, np.float32, (n, 2), "q")
    _array(period_id, np.int16, (n,), "period_id")
    _array(valid, np.bool_, (n, 2), "valid")
    if not np.isfinite(q).all() or (q < 0).any() or (q > 1).any():
        raise ValueError("all q entries require finite [0,1]")
    out = np.zeros((n, 2), dtype=np.float32)
    for a, b in period_slices(period_id):
        for c in range(2):
            ids = np.flatnonzero(valid[a+1:b, c]) + a + 1
            if len(ids):
                mean = np.float32(np.mean(q[ids, c], dtype=np.float64))
                if not np.isfinite(mean) or not 0 <= mean <= 1:
                    raise ValueError("flattened support arithmetic failure")
                out[ids, c] = mean
    return out


def _keys(obj, expected, name):
    if type(obj) is not dict or set(obj) != set(expected):
        raise ValueError(f"{name} exact schema keys required")


def _number(x):
    if type(x) not in (int, float):
        return False
    try:
        return math.isfinite(x)
    except OverflowError:
        return False


def _digest_value(x):
    return type(x) is str and _DIGEST.fullmatch(x) is not None


def _provenance(p):
    digests = ("scientific_source_digest", "study_digest", "protocol_digest", "split_digest",
               "metric_digest", "dependency_digest")
    _keys(p, (*digests, "training_input_digests", "weight_recipe", "feature_version", "fps",
              "windows_frames", "coverage", "temperature", "tree_parameters", "random_state"), "provenance")
    if any(not _digest_value(p[k]) for k in digests):
        raise ValueError("provenance digest requires64 lowercase hex")
    if p["weight_recipe"] != WEIGHT_RECIPE or p["feature_version"] != FEATURE_VERSION:
        raise ValueError("boundary provenance feature/weight recipe mismatch")
    for k, v in (("fps", 25.), ("coverage", .8), ("temperature", 1.)):
        if not _number(p[k]) or p[k] != v:
            raise ValueError("boundary numeric provenance mismatch")
    if (type(p["windows_frames"]) is not list or len(p["windows_frames"]) != 2
            or any(type(x) is not int for x in p["windows_frames"]) or p["windows_frames"] != [5, 15]
            or type(p["random_state"]) is not int or p["random_state"] != 20261116):
        raise ValueError("boundary window/seed provenance mismatch")
    params = p["tree_parameters"]
    _keys(params, TREE_PARAMETERS, "tree parameters")
    for k, v in TREE_PARAMETERS.items():
        if type(v) is bool or v is None:
            good = type(params[k]) is type(v) and params[k] == v
        elif type(v) is int:
            good = type(params[k]) is int and params[k] == v
        else:
            good = _number(params[k]) and params[k] == v
        if not good:
            raise ValueError("boundary tree parameters mismatch")
    records = p["training_input_digests"]
    expected = [(f, c) for f in _TRAIN for c in _CONDITIONS]
    if type(records) is not list or len(records) != len(expected):
        raise ValueError("exact eight training input records required")
    for r, (f, c) in zip(records, expected):
        _keys(r, ("fixture_id", "condition", "observation_digest", "target_digest", "sampling_digest"), "training input")
        if r["fixture_id"] != f or r["condition"] != c or any(not _digest_value(r[k]) for k in
                ("observation_digest", "target_digest", "sampling_digest")):
            raise ValueError("training input order/digest mismatch")


def _duplicate_reject(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


class NumericHead:
    """Strict separate wrapper around unchanged numeric-tree primitives."""
    def __init__(self, document: dict):
        _keys(document, ("format", "class_names", "feature_names", "baseline", "trees", "provenance"), "head")
        if (document["format"] != "numeric-boundary-hgb-v1" or document["class_names"] != list(CLASS_NAMES)
                or type(document["class_names"]) is not list or document["feature_names"] != list(BOUNDARY_NAMES)
                or type(document["feature_names"]) is not list):
            raise ValueError("boundary class/feature/format mismatch")
        _provenance(document["provenance"])
        baseline = document["baseline"]
        if type(baseline) is not list or len(baseline) != 3 or any(not _number(v) for v in baseline):
            raise ValueError("baseline requires three finite numbers")
        trees = document["trees"]
        if type(trees) is not list or not 3 <= len(trees) <= 96 or len(trees) % 3:
            raise ValueError("head requires3..96 complete three-class trees")
        node_keys = ("value", "feature_idx", "num_threshold", "missing_go_to_left", "left", "right", "is_leaf")
        for i, tree in enumerate(trees):
            _keys(tree, ("class", "nodes"), "tree")
            if type(tree["class"]) is not int or tree["class"] != i % 3:
                raise ValueError("tree class iteration order must be0,1,2")
            nodes = tree["nodes"]
            _keys(nodes, node_keys, "nodes")
            if any(type(v) is not list for v in nodes.values()):
                raise ValueError("node arrays must be JSON lists")
            lengths = {len(v) for v in nodes.values()}
            if len(lengths) != 1 or not 1 <= len(nodes["value"]) <= 13:
                raise ValueError("node arrays require equal length1..13")
            for k in ("value", "num_threshold"):
                if any(not _number(v) for v in nodes[k]):
                    raise ValueError("finite numeric node values required")
            for k in ("feature_idx", "left", "right", "missing_go_to_left", "is_leaf"):
                if any(type(v) is not int for v in nodes[k]):
                    raise ValueError("integer node indices/flags required; bool forbidden")
            for k in ("missing_go_to_left", "is_leaf"):
                if any(v not in (0, 1) for v in nodes[k]):
                    raise ValueError("binary integer flags required")
            for j, leaf in enumerate(nodes["is_leaf"]):
                if leaf and (nodes["left"][j] != 0 or nodes["right"][j] != 0):
                    raise ValueError("leaf children require integer0 sentinels")
                if not leaf and nodes["left"][j] == nodes["right"][j]:
                    raise ValueError("internal children must differ")
        # Primitive validation supplies range, complete reachability, unique
        # parent, root and cycle checks. It copies arrays and freezes them.
        numeric = {"format": "numeric-hgb-v1", "feature_names": list(BOUNDARY_NAMES),
                   "baseline": baseline, "trees": trees, "provenance": document["provenance"]}
        self._model = TreeModel(numeric)
        self.names = BOUNDARY_NAMES
        self.document = copy.deepcopy(document)

    @classmethod
    def load(cls, path: Path) -> NumericHead:
        with Path(path).open("rb") as source:
            data = source.read(MAX_HEAD_BYTES + 1)
        if len(data) > MAX_HEAD_BYTES:
            raise ValueError("boundary JSON exceeds524288byte limit")
        try:
            document = json.loads(data.decode("utf-8"), object_pairs_hook=_duplicate_reject,
                                  parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
            raise ValueError("malformed strict UTF8 boundary JSON") from exc
        return cls(document)

    def raw_scores(self, values: NDArray[np.float32], names: tuple[str, ...]) -> NDArray[np.float64]:
        if type(names) is not tuple or names != BOUNDARY_NAMES:
            raise ValueError("exact boundary feature tuple required")
        if not isinstance(values, np.ndarray) or values.ndim != 2:
            raise ValueError("float32 boundary matrix required")
        _array(values, np.float32, (len(values), 28), "boundary values")
        if np.isinf(values).any():
            raise ValueError("infinite boundary features forbidden")
        return self._model.raw_scores(values, names, chunk_size=HEAD_BATCH_ROWS)


def export_boundary_sklearn(estimator, provenance: dict) -> dict:
    """Training-side numeric adapter; no sklearn runtime import or implicit fit.

    Caller must perform the required all-retained-row plus synthetic raw parity
    checks and bind those receipts in the postfit model seal.
    """
    _provenance(provenance)
    params = estimator.get_params(deep=False)
    if any(params.get(k) != v for k, v in TREE_PARAMETERS.items()) or params.get("random_state") != 20261116:
        raise ValueError("estimator parameters differ from fixed boundary recipe")
    raw = export_sklearn(estimator, BOUNDARY_NAMES, copy.deepcopy(provenance))
    document = {"format": "numeric-boundary-hgb-v1", "class_names": list(CLASS_NAMES),
                "feature_names": list(BOUNDARY_NAMES), "baseline": raw["baseline"],
                "trees": raw["trees"], "provenance": copy.deepcopy(provenance)}
    NumericHead(document)
    encoded = json.dumps(document, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_HEAD_BYTES:
        raise ValueError("exported boundary JSON exceeds524288bytes")
    return document
