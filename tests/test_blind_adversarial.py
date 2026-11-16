r"""Independent synthetic adversarial checks. No challenge assets or answer files.

Run: .venv\Scripts\python.exe tests/test_blind_adversarial.py
The JSON report records failures as evidence; this file never repairs production.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import itertools
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LOCAL = ROOT / "local" / "blind-adversarial"
LOCAL.mkdir(parents=True, exist_ok=True)

from possession_model.features import FeatureAccumulator, load_atd
from possession_model.schema import FeatureSet
from possession_model.evidence import feature_matrix, heuristic_scores, rolling_mean, reliable_ball_mask
from possession_model.decoder import decode_scores
from possession_model.trees import TreeModel, export_sklearn
from possession_model.pipeline import write_submission, tag_support, source_fingerprints, verify_frozen_sources
from validation.metrics import measure
from validation.sportec import load_sportec, make_ball_gap_mask


def invented_features(n=12, periods=None, fps=25):
    periods = np.ones(n, np.uint8) if periods is None else np.array(periods, np.uint8)
    acc = FeatureAccumulator(n, [0, 0, 0, 1, 1, 1], fps=fps)
    for i in range(n):
        acc.push(i, [[10, 10], [20, 10], [30, 10], [70, 40], [80, 40], [90, 40]],
                 [11, 10], period_id=int(periods[i]))
    return acc.finish()


def atd_pair(folder, rows, *, fps=25, slot_order=("away", "home"),
             channel_orders=(("s", "y", "x"), ("y", "x", "s")),
             ball_order=("y", "s", "x")):
    """Invented EPTS declaration: element order deliberately disagrees with sides.

    Rows contain semantic metre-independent normalized home/away/ball coordinates.
    Oracles never derive expected positions from the parser's returned mappings.
    """
    root = ET.Element("Tracking")
    ET.SubElement(root, "Team", id="visitors")
    ET.SubElement(root, "Team", id="hosts")
    ET.SubElement(root, "Score", idLocalTeam="hosts", idVisitingTeam="visitors")
    ET.SubElement(root, "Player", id="home", teamId="hosts")
    ET.SubElement(root, "Player", id="away", teamId="visitors")
    ET.SubElement(root, "FrameRate").text = str(fps)
    for role in ("x", "y", "s"):
        ch = ET.SubElement(root, "Channel", id=role)
        ET.SubElement(ch, "Name").text = {"x": "position_x", "y": "position_y", "s": "speed_kph"}[role]
        ET.SubElement(ch, "Unit").text = "kph" if role == "s" else "normalized"
    for player in ("home", "away"):
        for role in ("x", "y", "s"):
            ET.SubElement(root, "PlayerChannel", id=player + role, playerId=player, channelId=role)
    spec = ET.SubElement(root, "DataFormatSpecification", separator=":", startFrame="1", endFrame=str(len(rows)))
    ET.SubElement(spec, "StringRegister", name="frameCount")
    players = ET.SubElement(spec, "SplitRegister", separator=";")
    for player, roles in zip(slot_order, channel_orders):
        group = ET.SubElement(players, "SplitRegister", separator=",")
        for role in roles:
            ET.SubElement(group, "PlayerChannelRef", playerChannelId=player + role)
    ball = ET.SubElement(spec, "SplitRegister", separator=",")
    for role in ball_order:
        ET.SubElement(ball, "BallChannelRef", channelId=role)
    meta, raw = folder / "invented.xml", folder / "invented.txt"
    ET.ElementTree(root).write(meta, encoding="utf-8")
    lines = []
    for i, record in enumerate(rows, 1):
        def channels(name, order):
            values = dict(zip(("x", "y", "s"), record[name]))
            return ",".join(str(values[role]) for role in order)
        lines.append(f"{i}:" + ";".join(channels(player, roles) for player, roles in zip(slot_order, channel_orders))
                     + ":" + channels("ball", ball_order))
    raw.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return meta, raw


def sportec_pair(folder, *, label="1", ball_x="1", periods=("firstHalf", "secondHalf")):
    meta = folder / "sportec-meta.xml"
    raw = folder / "sportec-raw.xml"
    meta.write_text('<Match><General MatchId="invented-game" HomeTeamId="H-club" GuestTeamId="A-club"/>'
                    '<Environment PitchX="100" PitchY="60"/><Team TeamId="A-club"><Player PersonId="a"/></Team>'
                    '<Team TeamId="H-club"><Player PersonId="h"/></Team></Match>', encoding="utf-8")
    root = ET.Element("Positions")
    for period in periods:
        for team, person, x in (("BALL", None, ball_x), ("A-club", "a", "20"), ("H-club", "h", "0")):
            attr = {"MatchId": "invented-game", "GameSection": period, "TeamId": team}
            if person:
                attr["PersonId"] = person
            fs = ET.SubElement(root, "FrameSet", **attr)
            for n in range(3):
                ET.SubElement(fs, "Frame", N=str(100 + n), T=f"2020-01-01T12:00:00.{n * 40:03d}",
                              X=x, Y="0", BallStatus="1", BallPossession=label)
    ET.ElementTree(root).write(raw, encoding="utf-8")
    return meta, raw


class BlindAdversarial(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="case-", dir=LOCAL)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def test_atd_mapping_channels_sides_frame_and_units(self):
        rows = [{"home": (.1, .2, 999), "away": (.8, .7, 0), "ball": (.11, .2, 123)},
                {"home": (.3, .4, 100), "away": (.9, .8, 999), "ball": (.9, .8, 0)}]
        meta, raw = atd_pair(self.folder, rows)
        f = load_atd(meta, raw, 2, pitch=(100, 50))
        np.testing.assert_allclose(f.ball_xy, [[11, 10], [90, 40]])
        np.testing.assert_allclose(f.nearest, [[1, np.hypot(69, 25)], [np.hypot(60, 20), 0]], rtol=1e-6)
        self.assertEqual(np.argmin(f.nearest, axis=1).tolist(), [0, 1])
        np.testing.assert_equal(f.tracked_counts, [[1, 1], [1, 1]])
        self.assertTrue(np.isnan(f.ball_speed).all())

    def test_atd_rejects_duplicate_skipped_reordered_and_malformed_rows(self):
        row = {"home": (.1, .2, 0), "away": (.8, .7, 0), "ball": (.11, .2, 0)}
        meta, raw = atd_pair(self.folder, [row, row])
        good = raw.read_text()
        variants = [good.replace("2:", "1:"), good.replace("1:", "0:"), good.splitlines()[1] + "\n" + good.splitlines()[0] + "\n",
                    good.replace("0.11", "0.11junk"), good.replace("0.11", "inf"), good + "\n", good.splitlines()[0] + "\n"]
        for bad in variants:
            with self.subTest(raw=bad[:70]):
                raw.write_text(bad)
                with self.assertRaises(ValueError):
                    load_atd(meta, raw, 2)

    def test_partial_nan_and_absent_team_never_become_zero_distance(self):
        acc = FeatureAccumulator(2, [0, 1])
        acc.push(0, [[np.nan, 10], [2, 3]], [2, 3])
        acc.push(1, [[1, 2], [2, 3]], [np.nan, 3])
        f = acc.finish()
        self.assertTrue(np.isnan(f.nearest[0, 0]))
        self.assertEqual(f.nearest[0, 1], 0)
        self.assertEqual(f.tracked_counts[0].tolist(), [0, 1])
        self.assertTrue(np.isnan(f.nearest[1]).all())
        self.assertFalse(f.ball_observed[1])
        self.assertTrue(np.isnan(f.ball_xy[1]).all())

    def test_motion_resets_on_period_and_observation_gap(self):
        acc = FeatureAccumulator(16, [0, 1], fps=5)
        for i in range(16):
            ball = [i * .2, 5] if i != 7 else [np.nan, np.nan]
            acc.push(i, [[0, 0], [20, 20]], ball, 1 if i < 11 else 2)
        f = acc.finish()
        self.assertAlmostEqual(float(f.ball_speed[6]), 1., places=5)
        self.assertTrue(np.isnan(f.ball_speed[[7, 8, 11, 12]]).all())
        self.assertAlmostEqual(float(f.ball_speed[10]), 1., places=5)
        self.assertAlmostEqual(float(f.ball_speed[13]), 1., places=5)

    def test_anonymous_slot_permutation_preserves_motion(self):
        sides = [0, 0, 0, 1, 1, 1]
        a, b = FeatureAccumulator(14, sides, fps=5), FeatureAccumulator(14, sides, fps=5)
        base = np.array([[10, 10], [20, 10], [30, 10], [60, 30], [70, 30], [80, 30]], float)
        for i in range(14):
            positions = base + [i * .2, 0]
            a.push(i, positions, [12 + i * .2, 10])
            b.push(i, positions[[i % 3, (i + 1) % 3, (i + 2) % 3, 3 + (i + 2) % 3, 3 + i % 3, 3 + (i + 1) % 3]], [12 + i * .2, 10])
        fa, fb = a.finish(), b.finish()
        np.testing.assert_allclose(fa.collective_speed, fb.collective_speed, equal_nan=True)
        np.testing.assert_allclose(fa.nearest, fb.nearest, equal_nan=True)
        np.testing.assert_allclose(fa.collective_speed[5:], 1., atol=2e-5)

    def test_rolling_mean_against_direct_window_oracle(self):
        rng = np.random.default_rng(473)
        for radius in (0, 1, 4, 30):
            values = rng.normal(size=23)
            values[[1, 3, 11]] = np.nan
            values[20] = np.inf
            periods = np.array([0] * 2 + [1] * 7 + [0] * 3 + [2] * 6 + [1] * 5)
            expected = np.full(23, np.nan)
            for i in range(23):
                if periods[i] == 0:
                    continue
                lo = i
                while lo and periods[lo - 1] == periods[i]:
                    lo -= 1
                hi = i + 1
                while hi < 23 and periods[hi] == periods[i]:
                    hi += 1
                subset = values[max(lo, i - radius):min(hi, i + radius + 1)]
                subset = subset[np.isfinite(subset)]
                if len(subset) >= 2:
                    expected[i] = subset.mean()
            np.testing.assert_allclose(rolling_mean(values, periods, radius, min_count=2), expected, equal_nan=True, atol=1e-6)

    def test_full_missing_ball_does_not_invent_team_or_dead_support(self):
        f = invented_features(40)
        f.ball_observed[:] = False
        f.ball_xy[:] = np.nan
        f.nearest[:] = np.nan
        f.ball_speed[:] = np.nan
        f.collective_speed[:] = np.nan
        matrix, names, _ = feature_matrix(f)
        self.assertFalse(np.isinf(matrix).any())
        for name in ("distance_m_H", "distance_m_A", "close_H", "close_A"):
            self.assertTrue(np.isnan(matrix[:, names.index(name)]).all())
        np.testing.assert_equal(heuristic_scores(f), np.zeros((40, 3)))

    def test_feature_team_swap_and_period_isolation(self):
        f = invented_features(18, [1] * 8 + [0] * 2 + [2] * 8)
        before, names, pairs = feature_matrix(f)
        for key in ("nearest", "tracked_counts", "collective_speed"):
            setattr(f, key, getattr(f, key)[:, ::-1].copy())
        swapped, _, _ = feature_matrix(f)
        expected = before.copy()
        for h, a in pairs:
            expected[:, [h, a]] = expected[:, [a, h]]
        np.testing.assert_allclose(swapped, expected, equal_nan=True)
        f.ball_xy[10:] = [200, 200]
        f.nearest[10:] = [20, 25]
        after, _, _ = feature_matrix(f)
        np.testing.assert_allclose(after[:8], swapped[:8], equal_nan=True)
        self.assertTrue(np.isnan(after[8:10]).all())

    def test_tag_support_case_defense_unknown_duplicate_and_rounding(self):
        root = ET.Element("tags")
        def event(code, team, start, end):
            inst = ET.SubElement(root, "instance")
            for key, value in (("code", code), ("start", start), ("end", end)):
                ET.SubElement(inst, key).text = str(value)
            label = ET.SubElement(inst, "label")
            ET.SubElement(label, "group").text = " tEaM "
            ET.SubElement(label, "text").text = team
        event(" BuIlD Up ", " HOsTS ", .2, .6)
        event("BUILD UP", "hosts", .2, .6)
        event("DEFENSIVE TRANSITION", "Visitors", .6, 1.)
        event("BUILD UP", "N/A", 0, 2.)
        event("SET PIECES", "Hosts", 0, 2.)
        event("GOALS", "Visitors", 0, 2.)
        event("BUILD UP", "Visitors", -4, .2)
        path = self.folder / "invented-tags.xml"
        ET.ElementTree(root).write(path)
        expected = np.zeros((12, 2), np.float32)
        expected[:2, 1] = 1
        expected[2:6, 0] = 1
        expected[6:10, 0] = .5
        np.testing.assert_equal(tag_support(path, 12, 10, "Hosts", "Visitors"), expected)

    def test_impossible_jump_guard_and_gap_reacquisition(self):
        f = invented_features(40)
        f.ball_xy[:] = [10, 10]
        f.ball_xy[20:] = [90, 60]
        self.assertFalse(reliable_ball_mask(f)[19:22].any())
        f.ball_observed[19] = False
        f.ball_xy[19] = np.nan
        mask = reliable_ball_mask(f)
        self.assertTrue(mask[18])
        self.assertTrue(mask[20])
        f.period_id[20:] = 2
        f.ball_observed[:] = True
        f.ball_xy[19] = [10, 10]
        self.assertTrue(reliable_ball_mask(f)[19:22].all())

    def test_extreme_finite_coordinates_cannot_emit_infinite_features(self):
        acc = FeatureAccumulator(1, [0, 1])
        try:
            with np.errstate(over="ignore", invalid="ignore"):
                acc.push(0, [[3e38, 3e38], [0, 0]], [-3e38, -3e38])
        except ValueError:
            return
        f = acc.finish()
        self.assertFalse(np.isinf(f.nearest).any(), "Accepted finite coordinates produced infinite nearest distance")

    def test_decoder_global_objective_against_exhaustive_paths(self):
        rng = np.random.default_rng(2981)
        for case in range(65):
            n = int(rng.integers(1, 8))
            scores = rng.integers(-3, 4, size=(n, 3)).astype(float)
            scores[rng.random((n, 3)) < .12] = -np.inf
            costs = rng.choice([0., .5, 2., np.inf], size=(3, 3))
            np.fill_diagonal(costs, 0)
            initial = None if case % 3 else 1
            candidates = []
            for path in itertools.product(range(3), repeat=n):
                if initial is not None and path[0] != initial:
                    continue
                value = sum(scores[i, state] for i, state in enumerate(path)) - sum(costs[path[i - 1], path[i]] for i in range(1, n))
                if np.isfinite(value):
                    candidates.append((value, -sum(path[i - 1] != path[i] for i in range(1, n)), path))
            with self.subTest(case=case):
                if not candidates:
                    with self.assertRaises(ValueError):
                        decode_scores(scores, np.ones(n, int), costs, initial)
                    continue
                actual = decode_scores(scores, np.ones(n, int), costs, initial)
                value = sum(scores[i, state] for i, state in enumerate(actual)) - sum(costs[actual[i - 1], actual[i]] for i in range(1, n))
                changes = sum(actual[i - 1] != actual[i] for i in range(1, n))
                self.assertEqual((value, -changes), max((c[0], c[1]) for c in candidates))

    def test_decoder_independent_periods_and_negative_gap(self):
        scores = np.array([[6, 0, 0], [0, 0, 0], [0, 6, 0], [100, 0, 0], [0, 0, 5], [0, 0, 5]], float)
        periods = np.array([1, 1, 2, 0, 2, 2])
        costs = np.full((3, 3), 4.)
        np.fill_diagonal(costs, 0)
        np.testing.assert_equal(decode_scores(scores, periods, costs), [0, 0, 1, -1, 2, 2])

    def test_decoder_rejects_nonfinite_evidence_and_impossible_paths(self):
        costs = np.full((3, 3), np.inf)
        np.fill_diagonal(costs, 0)
        for invalid in (np.nan, np.inf):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                decode_scores([[invalid, 0, 0]], np.array([0]), costs)
        with self.assertRaises(ValueError):
            decode_scores([[0, -np.inf, -np.inf], [-np.inf, 0, -np.inf]], np.ones(2, int), costs)

    def test_decoder_neutral_gap_keeps_previous_team_until_new_evidence(self):
        scores = np.array([[4, 0, -4], [0, 0, -4], [0, 0, -4], [0, 4, -4]], float)
        costs = np.full((3, 3), 1.)
        np.fill_diagonal(costs, 0)
        np.testing.assert_equal(decode_scores(scores, np.ones(4, int), costs), [0, 0, 0, 1])

    def test_metric_abstentions_and_unknown_frames_have_distinct_costs(self):
        result = measure([0, 0, 1, 1, 2, 2, -1], [0, -1, 1, -1, 2, 2, 0], [1] * 7)
        self.assertAlmostEqual(result["macro_f1"], (2 / 3 + 2 / 3 + 1) / 3)
        self.assertEqual(result["spell_f1"], 1.)
        self.assertEqual(result["graded_frames"], 6)
        self.assertEqual(result["n_truth_spells"], 2)
        self.assertEqual(result["n_predicted_spells"], 2)

    def test_metric_cannot_pair_transitions_between_compact_halves(self):
        # A true H->A in half one and a predicted H->A in half two are only
        # two compact frames apart, but must produce zero matched events.
        result = measure([0, 1, 0, 0], [0, 0, 0, 1], [1, 1, 2, 2])
        self.assertEqual(result["transitions_1s"]["n_gt"], 1)
        self.assertEqual(result["transitions_1s"]["n_pred"], 1)
        self.assertEqual(result["transitions_1s"]["n_matched"], 0)
        self.assertEqual(result["n_truth_spells"], 3)

    def test_metric_rejects_out_of_domain_codes_instead_of_wrapping_int8(self):
        for code in (256, 257, 258, 259, .9):
            with self.subTest(code=code), self.assertRaises(ValueError):
                measure([0, 1, 2], [code, 1, 2], [1, 1, 1])

    def test_tree_explicit_threshold_nan_and_chunk_routing(self):
        nodes = {"is_leaf": [0, 1, 1], "value": [0, 7, -4], "feature_idx": [0, 0, 0],
                 "num_threshold": [1., 0, 0], "missing_go_to_left": [0, 0, 0], "left": [1, 0, 0], "right": [2, 0, 0]}
        model = TreeModel({"format": "numeric-hgb-v1", "feature_names": ["invented"], "baseline": [1, 2, 3],
                           "trees": [{"class": 0, "nodes": nodes}]})
        matrix = np.array([[np.nan], [1], [np.nextafter(np.float32(1), np.float32(2))], [-8]], np.float32)
        expected = [[-3, 2, 3], [8, 2, 3], [-3, 2, 3], [8, 2, 3]]
        for chunk in (1, 3, 8192):
            np.testing.assert_equal(model.raw_scores(matrix, ["invented"], chunk), expected)

    def test_tree_export_matches_independent_sklearn_raw_predictions(self):
        try:
            from sklearn.ensemble import HistGradientBoostingClassifier
        except ModuleNotFoundError as error:
            if error.name != "sklearn":
                raise
            self.skipTest("scikit-learn is optional and used for export verification only")
        rng = np.random.default_rng(641)
        x = rng.normal(size=(210, 4)).astype(np.float32)
        y = np.arange(210) % 3
        x[:, 0] += 2 * y
        x[rng.random(x.shape) < .2] = np.nan
        estimator = HistGradientBoostingClassifier(max_iter=6, max_leaf_nodes=5, min_samples_leaf=4, random_state=19).fit(x, y)
        model = TreeModel(export_sklearn(estimator, ["a", "b", "c", "d"], {"invented": True}))
        test = np.vstack([x, np.zeros((1, 4), np.float32), np.full((1, 4), np.nan, np.float32)])
        np.testing.assert_allclose(model.raw_scores(test, ["a", "b", "c", "d"], 7), estimator._raw_predict(test), atol=1e-12)

    def test_tree_rejects_negative_class_that_silently_targets_dead(self):
        doc = {"format": "numeric-hgb-v1", "feature_names": ["x"], "baseline": [0, 0, 0],
               "trees": [{"class": -1, "nodes": {"is_leaf": [1], "value": [7], "feature_idx": [0],
                          "num_threshold": [0], "missing_go_to_left": [0], "left": [0], "right": [0]}}]}
        try:
            model = TreeModel(doc)
        except ValueError:
            return
        result = model.raw_scores([[0]], ["x"]).tolist()
        self.fail(f"Invalid tree class -1 accepted and silently applied: {result}")

    def test_standalone_runtime_imports_require_no_training_framework(self):
        script = '''import sys, importlib.abc
class BlockTraining(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('sklearn','scipy','joblib','cloudpickle','torch'):
            raise ImportError('training dependency blocked by independent test')
sys.meta_path.insert(0, BlockTraining())
from possession_model import features, evidence, decoder, trees, pipeline
print('standalone inference imports succeeded')
'''
        result = subprocess.run([sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("standalone inference imports succeeded", result.stdout)

    def test_csv_failure_preserves_preexisting_file(self):
        path = self.folder / "synthetic.csv"
        original = b"must preserve existing artifact\n"
        path.write_bytes(original)
        with self.assertRaises(ValueError):
            write_submission(path, [0, 1, 99])
        self.assertEqual(path.read_bytes(), original, "Invalid later code truncated and partially rewrote existing file")

    def test_csv_bytes_and_utf8_lf_are_platform_independent(self):
        path = self.folder / "synthetic.csv"
        digest = write_submission(path, np.array([-1, 0, 1, 2], np.int8))
        expected = b"frame,label\n0,X\n1,H\n2,A\n3,D\n"
        self.assertEqual(path.read_bytes(), expected)
        self.assertEqual(digest, hashlib.sha256(expected).hexdigest())

    def test_sportec_label_isolation_and_roster_mapping(self):
        first, second = self.folder / "first", self.folder / "second"
        first.mkdir(); second.mkdir()
        fa, ta, pa = load_sportec(*sportec_pair(first, label="1"))
        fb, tb, pb = load_sportec(*sportec_pair(second, label="2"))
        np.testing.assert_equal(ta, 0)
        np.testing.assert_equal(tb, 1)
        for key in ("ball_xy", "ball_observed", "nearest", "tracked_counts", "collective_speed", "ball_speed", "period_id"):
            np.testing.assert_allclose(getattr(fa, key), getattr(fb, key), equal_nan=True)
        np.testing.assert_allclose(fa.ball_xy, [[51, 30]] * 6)
        np.testing.assert_allclose(fa.nearest, [[1, 19]] * 6)
        self.assertFalse(pa["inference_uses_labels"])

    def test_sportec_same_size_preserved_mtime_source_edit_invalidates_cache(self):
        meta, raw = sportec_pair(self.folder, ball_x="1")
        first, _, _ = load_sportec(meta, raw)
        stat = raw.stat()
        raw.write_bytes(raw.read_bytes().replace(b'X="1"', b'X="9"'))
        self.assertEqual(raw.stat().st_size, stat.st_size)
        os.utime(raw, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        second, _, _ = load_sportec(meta, raw)
        self.assertEqual(first.ball_xy[0, 0], 51)
        self.assertEqual(second.ball_xy[0, 0], 59, "Edited source reused old geometry when size/mtime were unchanged")

    def test_ball_gap_mask_exact_count_and_period_independence(self):
        blocks = [{"start": 0, "end": 13}, {"start": 13, "end": 29}]
        for fraction in (0, .27, .41, 1):
            mask = make_ball_gap_mask(29, blocks, 5, fraction, 1, seed=31)
            self.assertEqual(int(mask.sum()), round(29 * fraction))
            np.testing.assert_equal(mask, make_ball_gap_mask(29, blocks, 5, fraction, 1, seed=31))

    def test_source_freeze_includes_cli_that_sets_inference_constraints(self):
        from possession_model.pipeline import FROZEN_SOURCES
        for name in (*FROZEN_SOURCES, "tools/run_candidate.py"):
            target = self.folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("synthetic executable source", encoding="utf-8")
        frozen = source_fingerprints(self.folder)
        (self.folder / "tools/run_candidate.py").write_text("modified forced_dead or frame indexing", encoding="utf-8")
        with self.assertRaises(ValueError, msg="CLI inference constraints can change without invalidating frozen source provenance"):
            verify_frozen_sources(self.folder, {"source_sha256": frozen})

    def _cli_module(self):
        spec = importlib.util.spec_from_file_location("blind_synthetic_cli", ROOT / "tools" / "run_candidate.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _sandbox_cli(self, *, no_cache=False, collide=False, overwrite_source=False):
        """Exercise the actual CLI flow with synthetic data and injected inference.

        No challenge/model/config file is opened. The inference and XML load are
        isolated so path/cache behavior is tested without expensive predictions.
        """
        cli = self._cli_module()
        cli.ROOT = self.folder
        config = self.folder / "config.json"
        model = self.folder / "invented-model.json"
        model.write_text("synthetic model bytes")
        config.write_text(json.dumps({"model": model.name, "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest()}))
        data = self.folder / "data" / "tactical"
        data.mkdir(parents=True)
        (data / "BAR-ATH_tactical_atd.xml").write_text("invented metadata stub")
        (data / "BAR-ATH_tactical_atd.txt").write_text("invented tracking stub")
        extractor = self.folder / "possession_model" / "features.py"
        extractor.parent.mkdir()
        extractor.write_text("synthetic extractor stub")
        out = data / "BAR-ATH_tactical_atd.txt" if overwrite_source else self.folder / "invented-output.csv"
        report = out if collide else self.folder / "invented-report.json"
        args = ["run_candidate.py", "--config", str(config), "--data-dir", str(data.parent), "--out", str(out), "--report", str(report)]
        if no_cache:
            args.append("--no-cache")
        with patch.object(sys, "argv", args), patch.object(cli, "verify_frozen_sources"), \
             patch.object(cli, "load_atd", return_value=invented_features(1)), \
             patch.object(cli, "predict", return_value=np.zeros(199319, np.int8)), \
             contextlib.redirect_stdout(io.StringIO()):
            cli.main()
        return out, report

    def test_cli_output_report_alias_cannot_destroy_successful_csv(self):
        try:
            out, _ = self._sandbox_cli(collide=True)
        except ValueError:
            return
        self.assertTrue(out.read_bytes().startswith(b"frame,label\n"),
                        "CLI returned success after report JSON overwrote the validated CSV at identical --out/--report path")

    def test_cli_no_cache_does_not_write_a_feature_cache(self):
        self._sandbox_cli(no_cache=True)
        self.assertEqual(list((self.folder / "local").glob("*.npz")), [],
                         "--no-cache bypasses reads but still persists feature cache; cache behavior is writeful")

    def test_cli_output_cannot_overwrite_tracking_source(self):
        try:
            out, _ = self._sandbox_cli(overwrite_source=True)
        except ValueError:
            return
        self.assertEqual(out.read_bytes()[:80], b"invented tracking stub",
                         "CLI returned success after --out overwrote its raw input file with a CSV")

    def test_cli_changed_model_fails_before_reading_data_or_writing_output(self):
        cli = self._cli_module()
        config = self.folder / "synthetic-config.json"
        model = self.folder / "invented-model.json"
        model.write_text("modified synthetic model")
        config.write_text(json.dumps({"model": str(model), "model_sha256": "0" * 64}))
        out = self.folder / "existing.csv"
        out.write_bytes(b"preserve me")
        args = ["run_candidate.py", "--config", str(config), "--data-dir", str(self.folder / "missing"), "--out", str(out)]
        with patch.object(sys, "argv", args), patch.object(cli, "verify_frozen_sources"), patch.object(cli, "load_atd") as loader:
            with self.assertRaisesRegex(ValueError, "Trained model differs"):
                cli.main()
            loader.assert_not_called()
        self.assertEqual(out.read_bytes(), b"preserve me")


ISSUES = {
    "test_extreme_finite_coordinates_cannot_emit_infinite_features": {"severity": "low", "fixture": "One frame, ball [-3e38,-3e38], home [3e38,3e38], away [0,0]. All coordinates finite and within accepted float32 range.", "actual": "Distance cast emits +inf; finite accepted observations can become infinite feature values."},
    "test_metric_rejects_out_of_domain_codes_instead_of_wrapping_int8": {"severity": "medium", "fixture": "truth=[0,1,2], prediction=[256,1,2], period=[1,1,1]. Also 257,258,259 and .9.", "actual": "measure casts to int8 without domain checking; 256 becomes H=0 and .9 becomes H=0, silently producing plausible incorrect metrics."},
    "test_tree_rejects_negative_class_that_silently_targets_dead": {"severity": "medium", "fixture": "Single leaf numeric-hgb-v1 tree: class=-1, leaf value=7, baseline=[0,0,0].", "actual": "TreeModel accepts class=-1 and NumPy indexing silently applies its contribution to class D: [[0,0,7]]."},
    "test_csv_failure_preserves_preexisting_file": {"severity": "medium", "fixture": "Existing output contains sentinel bytes; call write_submission(path,[0,1,99]).", "actual": "ValueError occurs after existing file is truncated and replaced with partial CSV header/H/A rows."},
    "test_sportec_same_size_preserved_mtime_source_edit_invalidates_cache": {"severity": "medium", "fixture": "Invented Sportec source, change ball X=1 to X=9, preserving byte length and mtime_ns.", "actual": "Second load reuses stale ball X=51 instead of updated X=59 because raw cache signature has no content hash."},
    "test_source_freeze_includes_cli_that_sets_inference_constraints": {"severity": "medium", "fixture": "Freeze source fingerprints in synthetic root; alter tools/run_candidate.py only.", "actual": "verify_frozen_sources succeeds because the executable that defines fixed dead intervals, input mapping and CSV orchestration is outside FROZEN_SOURCES."},
    "test_cli_output_report_alias_cannot_destroy_successful_csv": {"severity": "high", "fixture": "Sandboxed actual main(), invented sources/config/model, injected invented 199319-frame predictions; identical --out and --report.", "actual": "Official CSV validation passes, then report JSON overwrites CSV. CLI returns success with invalid final deliverable.", "isolation": "Main CLI flow real; load_atd, predict and source-freeze verification stubbed. Real model hash check, CSV writer and organiser validator used."},
    "test_cli_no_cache_does_not_write_a_feature_cache": {"severity": "low", "fixture": "Sandboxed actual main(), --no-cache, invented inputs and injected invented predictions.", "actual": "CLI writes local/tactical-features-*.npz despite --no-cache. Flag currently means bypass reading, not disable cache writes.", "contract_caveat": "Flag name is ambiguous: documentation may explicitly intend read bypass. Treat as behavior requiring clarification, not model correctness defect."},
    "test_cli_output_cannot_overwrite_tracking_source": {"severity": "high", "fixture": "Sandboxed actual main(), --out points to the supplied raw tracking input, invented sources and injected invented predictions.", "actual": "CLI returns success after overwriting the tracking source with a synthetic submission CSV. No collision guard protects input assets.", "isolation": "CLI orchestration real; source verification, feature extraction and inference injected. No challenge input file was accessed."},
}


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []
        self._started = {}

    def startTest(self, test):
        self._started[test.id()] = time.perf_counter()
        super().startTest(test)

    def _record(self, test, status, detail=None):
        method = test._testMethodName
        item = {"test": method, "status": status, "seconds": round(time.perf_counter() - self._started[test.id()], 6)}
        if detail:
            item["detail"] = detail
        if status != "passed" and method in ISSUES:
            item["finding"] = ISSUES[method]
        self.records.append(item)

    def addSuccess(self, test):
        self._record(test, "passed")
        super().addSuccess(test)

    def addFailure(self, test, err):
        self._record(test, "failed", self._exc_info_to_string(err, test))
        super().addFailure(test, err)

    def addError(self, test, err):
        self._record(test, "error", self._exc_info_to_string(err, test))
        super().addError(test, err)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            self._record(test, "failed-subtest", self._exc_info_to_string(err, test))
        super().addSubTest(test, subtest, err)


if __name__ == "__main__":
    started = time.perf_counter()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BlindAdversarial)
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    report = {"report_format": "blind-adversarial-v1", "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "scope": "Independent synthetic adversarial checks; no challenge assets/GT/CSV, prior reports/results/tests, model/config artifacts or solution documents read.",
              "public_contract_sources": ["more-than-a-hack-2027-main/" + x for x in ("CHALLENGE.md", "DATA.md", "SUBMISSION.md", "RULES.md", "evaluation/possession_metrics.py")],
              "command": ".\\.venv\\Scripts\\python.exe tests/test_blind_adversarial.py",
              "python": sys.version, "platform": platform.platform(), "numpy": np.__version__,
              "tested_source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                    ("possession_model/features.py", "possession_model/evidence.py", "possession_model/decoder.py",
                     "possession_model/trees.py", "possession_model/pipeline.py", "possession_model/schema.py",
                     "validation/metrics.py", "validation/sportec.py", "tools/run_candidate.py")},
              "tests_run": result.testsRun, "failure_events": len(result.failures), "errors": len(result.errors),
              "failed_test_methods": sorted({item["test"] for item in result.records if item["status"] != "passed"}),
              "passed_test_methods": len({item["test"] for item in result.records if item["status"] == "passed"}),
              "seconds": round(time.perf_counter() - started, 3), "records": result.records,
              "boundary": "Only synthetic fixtures written under ignored local/blind-adversarial, this test, and reports/blind-adversarial.json. No implementation or model changes; no Git mutations.",
              "limitations": ["CLI successful-path tests inject synthetic feature loading/inference and source verification, but run the actual CLI orchestration, model-byte hash, writer and organiser format validator.",
                              "No score or quality claim for the actual match or frozen model.", "No Linux execution; CSV LF byte contract checked on Windows."]}
    path = ROOT / "reports" / "blind-adversarial.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    sys.exit(not result.wasSuccessful())
