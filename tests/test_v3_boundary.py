"""Invented-only implementation checks; does not establish empirical improvement."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from possession_model.schema import FeatureSet
from experiments.v3.boundary import (
    BOUNDARY_NAMES, NumericHead, build_boundary_features, boundary_support,
    export_boundary_sklearn, flatten_support,
)


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = json.loads((ROOT / "specs/003-possession-improvements/protocol.json").read_text())
PARITY_EVIDENCE = {}


def provenance():
    digest = "a" * 64
    return dict(scientific_source_digest=digest, study_digest=digest,
        protocol_digest=hashlib.sha256((ROOT / "specs/003-possession-improvements/protocol.json").read_bytes()).hexdigest(),
        split_digest=hashlib.sha256(json.dumps(PROTOCOL["split"], ensure_ascii=False,
            sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
        metric_digest=digest, dependency_digest=digest,
        training_input_digests=[dict(fixture_id=f, condition=c, observation_digest=digest,
            target_digest=digest, sampling_digest=digest) for f in PROTOCOL["split"]["train"]
            for c in PROTOCOL["fit"]["boundary_conditions"]],
        weight_recipe=PROTOCOL["fit"]["boundary_weights"], feature_version="v3-boundary-28-v1",
        fps=25., windows_frames=[5, 15], coverage=.8, temperature=1.,
        tree_parameters=PROTOCOL["fit"]["boundary"], random_state=20261116)


def document():
    node = dict(value=[0.], feature_idx=[0], num_threshold=[0.],
                missing_go_to_left=[0], left=[0], right=[0], is_leaf=[1])
    return dict(format="numeric-boundary-hgb-v1", class_names=["NONE", "TEAM_CHANGE", "LIVE_DEAD"],
        feature_names=list(BOUNDARY_NAMES), baseline=[0., 0., 0.],
        trees=[{"class": c, "nodes": copy.deepcopy(node)} for c in range(3)], provenance=provenance())


def full_tree(count=13):
    """Invented full binary graph, with integer leaf sentinels."""
    internal = (count-1)//2
    return dict(value=[.1]*count, feature_idx=[0]*count, num_threshold=[0.]*count,
        missing_go_to_left=[0]*count,
        left=[2*i+1 if i < internal else 0 for i in range(count)],
        right=[2*i+2 if i < internal else 0 for i in range(count)],
        is_leaf=[0 if i < internal else 1 for i in range(count)])


def features(n=70):
    return FeatureSet(25., (100., 60.), np.ones(n, np.int16),
        np.tile(np.array([20., 20.], np.float32), (n, 1)), np.ones(n, bool),
        np.tile(np.array([2., 8.], np.float32), (n, 1)), np.ones((n, 2), np.int16),
        np.tile(np.array([2., 4.], np.float32), (n, 1)), np.full(n, 6., np.float32))


class BoundaryChecks(unittest.TestCase):
    def test_shared_constructor_names_and_ownership(self):
        from dataclasses import FrozenInstanceError
        from experiments.v3.contracts import BoundaryFeatures
        # Explicit independent spelling from the PRD column table, not the
        # constructor's private schema constant or a shared name generator.
        expected = (
            "w020_pre_min_distance_m", "w020_pre_abs_margin_m", "w020_pre_ball_speed_mps",
            "w020_pre_set_motion_mps", "w020_pre_boundary_distance_m",
            "w020_post_min_distance_m", "w020_post_abs_margin_m", "w020_post_ball_speed_mps",
            "w020_post_set_motion_mps", "w020_post_boundary_distance_m",
            "w020_margin_product_scaled", "w020_margin_change_scaled",
            "w020_reliable_fraction_pre", "w020_reliable_fraction_post",
            "w060_pre_min_distance_m", "w060_pre_abs_margin_m", "w060_pre_ball_speed_mps",
            "w060_pre_set_motion_mps", "w060_pre_boundary_distance_m",
            "w060_post_min_distance_m", "w060_post_abs_margin_m", "w060_post_ball_speed_mps",
            "w060_post_set_motion_mps", "w060_post_boundary_distance_m",
            "w060_margin_product_scaled", "w060_margin_change_scaled",
            "w060_reliable_fraction_pre", "w060_reliable_fraction_post")
        self.assertEqual(BOUNDARY_NAMES, expected)
        x = np.zeros((2, 28), np.float32); mask = np.ones((2, 2), bool)
        mutable = list(expected)
        invalid = (mutable, tuple("invalid_"+str(i) for i in range(28)),
                   expected[::-1], expected[:-1], None, ("same",)*28)
        for names in invalid:
            with patch("experiments.v3.contracts._array", side_effect=AssertionError("allocated first")):
                with self.assertRaises(ValueError):
                    BoundaryFeatures(x, names, mask)
        self.assertEqual(mutable, list(expected))
        np.testing.assert_array_equal(x, 0.); self.assertTrue(x.flags.writeable)
        np.testing.assert_array_equal(mask, True); self.assertTrue(mask.flags.writeable)
        bf = BoundaryFeatures(x, expected, mask)
        self.assertEqual(bf.names, expected); self.assertIs(type(bf.names), tuple)
        self.assertFalse(np.shares_memory(bf.values, x)); self.assertFalse(np.shares_memory(bf.valid, mask))
        self.assertFalse(bf.values.flags.writeable); self.assertFalse(bf.valid.flags.writeable)
        with self.assertRaises(FrozenInstanceError): bf.names = expected[::-1]
        x[:] = 9; mask[:] = False
        np.testing.assert_array_equal(bf.values, 0.); np.testing.assert_array_equal(bf.valid, True)
        owned = np.zeros((2, 28), np.float32); owned_mask = np.ones((2, 2), bool)
        owned.flags.writeable = False; owned_mask.flags.writeable = False
        adopted = BoundaryFeatures(owned, expected, owned_mask)
        self.assertIs(adopted.values, owned); self.assertIs(adopted.valid, owned_mask)
        for value in (np.zeros((3, 28), np.float32)[1:], np.asfortranarray(np.zeros((2, 28), np.float32))):
            old = value.copy(); value.flags.writeable = False
            copied = BoundaryFeatures(value, expected, owned_mask)
            self.assertFalse(np.shares_memory(copied.values, value))
            self.assertTrue(copied.values.flags.owndata); self.assertTrue(copied.values.flags.c_contiguous)
            self.assertFalse(copied.values.flags.writeable); np.testing.assert_array_equal(value, old)

    def test_exact_names_analytic_step_windows_and_symmetry(self):
        f = features()
        f.nearest[35:] = [8., 2.]
        before = [x.copy() for x in (f.nearest, f.ball_xy, f.ball_speed)]
        bf = build_boundary_features(f)
        self.assertEqual(bf.values.dtype, np.float32)
        self.assertEqual(bf.values.shape, (70, 28))
        expected = [2., 6., 6., 3., 20.] * 2 + [-.36, .6, 1., 1.]
        np.testing.assert_allclose(bf.values[35], expected * 2, rtol=1e-7)
        self.assertFalse(bf.valid[14].any()); self.assertTrue(bf.valid[15].all())
        self.assertTrue(bf.valid[55].all()); self.assertFalse(bf.valid[56].any())
        swapped = copy.deepcopy(f); swapped.nearest = f.nearest[:, ::-1].copy()
        swapped.tracked_counts = f.tracked_counts[:, ::-1].copy()
        swapped.collective_speed = f.collective_speed[:, ::-1].copy()
        other = build_boundary_features(swapped)
        np.testing.assert_array_equal(other.values, bf.values)
        np.testing.assert_array_equal(other.valid, bf.valid)
        for x, old in zip((f.nearest, f.ball_xy, f.ball_speed), before):
            np.testing.assert_array_equal(x, old)

    def test_all_columns_against_direct_ramp_window_oracle(self):
        f = features(100)
        ix = np.arange(100, dtype=np.float32)
        f.nearest[:, 0] = 1 + ix/5; f.nearest[:, 1] = 15 - ix/12
        f.ball_speed[:] = ix/2
        f.collective_speed[:, 0] = ix/8; f.collective_speed[:, 1] = ix/10
        f.collective_speed[41, 0] = np.nan
        f.ball_xy[:, 0] = 20 + ix/10
        f.ball_xy[:, 1] = 15 + ix/20
        bf = build_boundary_features(f)
        names = []
        bases = ("min_distance_m", "abs_margin_m", "ball_speed_mps", "set_motion_mps", "boundary_distance_m")
        for prefix in ("w020", "w060"):
            names += [prefix+"_"+side+"_"+name for side in ("pre", "post") for name in bases]
            names += [prefix+"_"+name for name in ("margin_product_scaled", "margin_change_scaled",
                                                    "reliable_fraction_pre", "reliable_fraction_post")]
        self.assertEqual(tuple(names), bf.names)
        for t in (15, 40, 50, 85):
            row = []
            for k in (5, 15):
                windows = []
                margins = []
                for lo, hi in ((t-k, t), (t, t+k)):
                    vals = []
                    margin = []
                    for u in range(lo, hi):
                        h, a = map(float, f.nearest[u]); x, y = map(float, f.ball_xy[u])
                        motion = [float(v) for v in f.collective_speed[u] if np.isfinite(v)]
                        vals.append([min(30., min(h, a)), abs(max(-10., min(10., a-h))),
                            min(40., float(f.ball_speed[u])), min(12., sum(motion)/len(motion)),
                            max(-10., min(30., x, 100-x, y, 60-y))])
                        margin.append(max(-10., min(10., a-h)))
                    windows.append(np.mean(vals, axis=0)); margins.append(sum(margin)/k)
                row += list(windows[0]) + list(windows[1])
                row += [margins[0]*margins[1]/100, abs(margins[1]-margins[0])/20, 1., 1.]
            np.testing.assert_allclose(bf.values[t], row, rtol=1e-7, atol=1e-7)

    def test_coverage_gap_motion_missing_and_period_boundaries(self):
        f = features(); f.ball_observed[31:33] = False; f.ball_xy[31:33] = np.nan
        bf = build_boundary_features(f)
        self.assertFalse(bf.valid[35].any())  # k5 pre has only3/5 observations
        f = features(); f.collective_speed[:] = np.nan; f.ball_speed[:] = np.nan
        bf = build_boundary_features(f)
        self.assertTrue(bf.valid[35].all()); self.assertTrue(np.isnan(bf.values[35, 2:4]).all())
        f.period_id[35:] = 2; bf = build_boundary_features(f)
        self.assertFalse(bf.valid[35].any()); self.assertTrue(bf.valid[50].all())
        f = features(); f.nearest[0, 0] = -1
        with self.assertRaises(ValueError): build_boundary_features(f)
        f = features(); f.ball_observed[:] = False; f.ball_xy[:] = np.nan; f.nearest[:] = np.nan
        self.assertFalse(build_boundary_features(f).valid.any())
        f = features(); f.ball_xy[34] = [90., 50.]
        self.assertFalse(build_boundary_features(f).valid[35].any())
        for mutate in (lambda f: setattr(f, "fps", 24.),
                lambda f: setattr(f, "nearest", f.nearest.astype(np.float64)),
                lambda f: f.ball_xy.__setitem__((0, 0), np.nan),
                lambda f: f.collective_speed.__setitem__((0, 0), np.inf)):
            f = features(); mutate(f)
            with self.assertRaises(ValueError): build_boundary_features(f)

    def test_flatten_exact_mean_type_run_nonmutation_and_refusals(self):
        rng = np.random.default_rng(90)
        q = rng.random((16, 2)).astype(np.float32); saved = q.copy()
        p = np.array([0, 1, 1, 1, 1, 0, 1, 1, 1, 2, 2, 2, 2, 0, -1, 3], np.int16)
        valid = rng.random((16, 2)) > .3
        got = flatten_support(q, p, valid); expected = np.zeros_like(q)
        for a, b in ((1, 5), (6, 9), (9, 13), (15, 16)):
            for c in range(2):
                ix = np.array([t for t in range(a+1, b) if valid[t, c]], dtype=int)
                if len(ix): expected[ix, c] = np.float32(np.mean(q[ix, c], dtype=np.float64))
        np.testing.assert_array_equal(got, expected); np.testing.assert_array_equal(q, saved)
        np.testing.assert_array_equal(got, flatten_support(q, p, valid))
        for bad in (q.astype(np.float64), np.full_like(q, np.nan), np.full_like(q, 1.1)):
            with self.assertRaises(ValueError): flatten_support(bad, p, valid)
        with self.assertRaises(ValueError): flatten_support(q, p.astype(np.int32), valid)
        empty = flatten_support(np.empty((0, 2), np.float32), np.empty(0, np.int16), np.empty((0, 2), bool))
        self.assertEqual(empty.shape, (0, 2))
        constant = np.full_like(q, .3)
        got = flatten_support(constant, p, valid)
        self.assertTrue(np.all((got == 0.) | (got == np.float32(.3))))

    def test_head_support_external_batching_and_invalid_zeros(self):
        from experiments.v3.contracts import BoundaryFeatures
        calls = []
        class Spy:
            def raw_scores(self, values, names):
                calls.append(len(values))
                return np.tile([1000., 1001., 999.], (len(values), 1))
        valid = np.ones((8200, 2), bool); valid[1, 1] = False
        bf = BoundaryFeatures(np.zeros((8200, 28), np.float32), BOUNDARY_NAMES, valid)
        q = boundary_support(Spy(), bf)
        self.assertEqual(calls, [4096, 4096, 8]); self.assertEqual(q.dtype, np.float32)
        expected = np.exp(np.array([-1., 0., -2.])); expected /= expected.sum()
        self.assertAlmostEqual(float(q[0, 0]), expected[1], places=7)
        self.assertEqual(q[1, 1], 0.)

    def test_strict_loader_schema_graph_and_size(self):
        doc = document(); head = NumericHead(doc)
        np.testing.assert_array_equal(head.raw_scores(np.zeros((2, 28), np.float32), BOUNDARY_NAMES), 0.)
        changes = [lambda d: d.update(extra=1), lambda d: d["class_names"].reverse(),
            lambda d: d["trees"][0]["nodes"]["left"].__setitem__(0, True),
            lambda d: d["trees"][0]["nodes"]["left"].__setitem__(0, 1),
            lambda d: d["trees"].append(copy.deepcopy(d["trees"][0])),
            lambda d: d["provenance"].update(extra="x"),
            lambda d: d["provenance"]["training_input_digests"].reverse()]
        for change in changes:
            bad = copy.deepcopy(doc); change(bad)
            with self.assertRaises(ValueError): NumericHead(bad)
        with tempfile.TemporaryDirectory(prefix="v3-t04-", dir=ROOT / "local") as scratch:
            p = Path(scratch) / "head.json"
            text = json.dumps(doc)
            p.write_text(text.replace('"format":', '"format":"x","format":', 1))
            with self.assertRaises(ValueError): NumericHead.load(p)
            p.write_bytes(b" " * 524289)
            with patch("experiments.v3.boundary.json.loads", side_effect=AssertionError("parsed oversized")):
                with self.assertRaises(ValueError): NumericHead.load(p)
            p.write_bytes(text.encode() + b" " * (524288 - len(text.encode())))
            NumericHead.load(p)
            p.write_text(text[:-3])
            with self.assertRaises(ValueError): NumericHead.load(p)
            p.write_text(text.replace('"fps":', '"fps":25,"fps":', 1))
            with self.assertRaises(ValueError): NumericHead.load(p)

    def test_head_limits_and_malicious_graphs_and_numeric_types(self):
        doc = document(); doc["trees"] = [{"class": i % 3, "nodes": full_tree()} for i in range(96)]
        NumericHead(doc)
        doc["trees"].append(copy.deepcopy(doc["trees"][0]))
        with self.assertRaises(ValueError): NumericHead(doc)
        node_variants = []
        #14 nodes is rejected before graph traversal.
        node_variants.append(full_tree(14))
        node = full_tree(); node["left"][1] = 0; node_variants.append(node)  #cycle/root parent
        node = full_tree(); node["left"][1] = node["right"][1]; node_variants.append(node)  #shared
        node = full_tree(); node["is_leaf"][1] = 1; node["left"][1] = node["right"][1] = 0
        node_variants.append(node)  #unreachable stored descendants
        node = full_tree(); node["feature_idx"][0] = 28; node_variants.append(node)
        node = full_tree(); node["num_threshold"][0] = np.inf; node_variants.append(node)
        node = full_tree(); node["missing_go_to_left"][0] = True; node_variants.append(node)
        node = full_tree(); node["value"][0] = 10**400; node_variants.append(node)
        for node in node_variants:
            doc = document(); doc["trees"][0]["nodes"] = node
            with self.assertRaises(ValueError): NumericHead(doc)
        for key in ("study_digest", "protocol_digest", "split_digest", "metric_digest"):
            doc = document(); doc["provenance"][key] = "A"*64
            with self.assertRaises(ValueError): NumericHead(doc)

    def test_toy_sklearn_numeric_export_raw_parity(self):
        from sklearn.ensemble import HistGradientBoostingClassifier
        rng = np.random.default_rng(405)
        x = rng.normal(size=(900, 28)).astype(np.float32); x[::7, 0] = np.nan
        y = np.arange(900) % 3
        model = HistGradientBoostingClassifier(**PROTOCOL["fit"]["boundary"], random_state=20261116)
        model.fit(x, y)
        doc = export_boundary_sklearn(model, provenance()); head = NumericHead(doc)
        self.assertLessEqual(len(json.dumps(doc, allow_nan=False).encode()), 524288)
        probe = np.r_[x, np.full((1, 28), np.nan, np.float32), np.zeros((1, 28), np.float32)]
        expected = model._raw_predict(probe)
        actual = head.raw_scores(probe, BOUNDARY_NAMES)
        raw_error = float(np.max(np.abs(actual - expected)))
        self.assertLessEqual(raw_error, 1e-10)
        # Every retained row and exact threshold/missing routing probes.
        split_probes = []
        for tree in doc["trees"]:
            nodes = tree["nodes"]
            for i, leaf in enumerate(nodes["is_leaf"]):
                if not leaf:
                    threshold = np.float32(nodes["num_threshold"][i])
                    if not np.isfinite(threshold): continue
                    for value in (threshold, np.nextafter(threshold, np.float32(-np.inf)),
                                  np.nextafter(threshold, np.float32(np.inf)), np.float32(np.nan)):
                        row = np.zeros(28, np.float32); row[nodes["feature_idx"][i]] = value
                        split_probes.append(row)
        if split_probes:
            probe = np.asarray(split_probes, np.float32)
            split_error = float(np.max(np.abs(head.raw_scores(probe, BOUNDARY_NAMES) - model._raw_predict(probe))))
            self.assertLessEqual(split_error, 1e-10)
        else:
            split_error = 0.
        PARITY_EVIDENCE.update(retained_invented_rows=len(x), additional_initial_probes=2,
            threshold_missing_probes=len(split_probes), maximum_raw_error=max(raw_error, split_error),
            tree_count=len(doc["trees"]), maximum_nodes=max(len(t["nodes"]["value"]) for t in doc["trees"]),
            compact_json_bytes=len(json.dumps(doc, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False).encode("utf-8")))


if __name__ == "__main__":
    unittest.main()
