"""Invented observations for evidence semantics; reads no match data."""
from dataclasses import replace
import unittest

import numpy as np

from possession_model.evidence import feature_matrix, heuristic_scores, period_slices, rolling_mean
from possession_model.schema import FeatureSet


def invented_features(n=12, fps=5.):
    return FeatureSet(
        fps=fps, pitch=(105.3, 68.), period_id=np.ones(n, dtype=np.int8),
        ball_xy=np.tile(np.array([50., 34.], dtype=np.float32), (n, 1)),
        ball_observed=np.ones(n, dtype=bool),
        nearest=np.tile(np.array([.4, 8.], dtype=np.float32), (n, 1)),
        tracked_counts=np.tile(np.array([11, 10], dtype=np.int16), (n, 1)),
        collective_speed=np.full((n, 2), 2., dtype=np.float32),
        ball_speed=np.ones(n, dtype=np.float32))


class EvidenceTests(unittest.TestCase):
    def test_impossible_ball_jump_cannot_create_full_opposing_control(self):
        f = invented_features(n=30, fps=25.)
        f.ball_xy[15] += [20., 0.]
        f.nearest[15] = [20., 0.]
        f.ball_speed[15:26] = np.nan
        scores = heuristic_scores(f)
        np.testing.assert_array_equal(scores[15, :2], 0.)
        matrix, names, _ = feature_matrix(f)
        self.assertTrue(np.isnan(matrix[15, names.index("distance_m_A")]))

    def test_rolling_windows_do_not_cross_half_or_unscored_gap(self):
        values = np.array([0., 0., 999., 100., 100.])
        for periods in (np.array([1, 1, 0, 2, 2]), np.array([1, 1, 0, 1, 1])):
            actual = rolling_mean(values, periods, radius=20)
            np.testing.assert_allclose(actual, [0., 0., np.nan, 100., 100.], equal_nan=True)

    def test_rolling_uses_finite_observations_and_minimum_count(self):
        values = np.array([1., np.nan, 3.])
        periods = np.ones(3, dtype=int)
        np.testing.assert_allclose(rolling_mean(values, periods, 1), [1., 2., 3.])
        np.testing.assert_allclose(rolling_mean(values, periods, 1, min_count=2),
                                   [np.nan, 2., np.nan], equal_nan=True)
        self.assertTrue(np.isnan(rolling_mean([np.nan] * 3, periods, 2)).all())

    def test_empty_periods_and_rolling_have_empty_result(self):
        self.assertEqual(period_slices(np.empty(0, dtype=int)), [])
        self.assertEqual(rolling_mean([], np.empty(0, dtype=int), 2).shape, (0,))

    def test_unknown_ball_and_unknown_motion_add_no_dead_ball_support(self):
        f = invented_features()
        f.ball_observed[:] = False
        f.ball_xy[:] = np.nan
        f.ball_speed[:] = np.nan
        f.nearest[:] = np.nan
        f.collective_speed[:] = np.nan
        scores = heuristic_scores(f)
        self.assertTrue(np.isfinite(scores).all())
        np.testing.assert_array_equal(scores, 0.)

    def test_live_stationary_ball_alone_does_not_force_dead_ball(self):
        f = invented_features()
        f.ball_speed[:] = 0.
        # Players are moving; a stationary ball alone is insufficient evidence.
        self.assertTrue((heuristic_scores(f)[:, 2] <= 0).all())

    def test_one_unobserved_team_never_defaults_to_home(self):
        f = invented_features()
        for side in (0, 1):
            f.nearest[:] = [.4, 8.]
            f.nearest[:, side] = np.nan
            scores = heuristic_scores(f)
            np.testing.assert_array_equal(scores[:, :2], 0.)

    def test_swapping_team_inputs_swaps_all_pairs_and_control_scores(self):
        f = invented_features(20)
        f.nearest[:, 0] = np.linspace(.2, 10., f.n_frames)
        f.nearest[:, 1] = np.linspace(10., .2, f.n_frames)
        f.collective_speed[:, 0] = np.linspace(0., 3., f.n_frames)
        f.collective_speed[:, 1] = np.linspace(3., 0., f.n_frames)
        f.nearest[3, 0] = np.nan
        swapped = replace(f, nearest=f.nearest[:, ::-1].copy(),
                          tracked_counts=f.tracked_counts[:, ::-1].copy(),
                          collective_speed=f.collective_speed[:, ::-1].copy())
        matrix, names, pairs = feature_matrix(f)
        actual, actual_names, actual_pairs = feature_matrix(swapped)
        self.assertEqual(actual_names, names)
        self.assertEqual(actual_pairs, pairs)
        expected = matrix.copy()
        for h, a in pairs:
            expected[:, [h, a]] = matrix[:, [a, h]]
            self.assertTrue(names[h].endswith("_H"))
            self.assertTrue(names[a].endswith("_A"))
        np.testing.assert_allclose(actual, expected, equal_nan=True)
        np.testing.assert_allclose(heuristic_scores(swapped),
                                   heuristic_scores(f)[:, [1, 0, 2]], equal_nan=True)

    def test_feature_matrix_masks_outside_and_resets_observation_gap(self):
        f = invented_features(5)
        f.period_id[:] = [1, 1, 0, 2, 2]
        f.ball_observed[:] = [True, False, False, False, False]
        matrix, names, _ = feature_matrix(f)
        self.assertTrue(np.isnan(matrix[2]).all())
        gap = matrix[:, names.index("ball_gap_seconds")]
        np.testing.assert_allclose(gap, [0., .2, np.nan, .2, .4], equal_nan=True)

    def test_unknown_distances_stay_unknown_in_matrix(self):
        f = invented_features()
        f.nearest[:] = np.nan
        matrix, names, pairs = feature_matrix(f)
        for name in ("distance_m_H", "distance_m_A", "close_H", "close_A",
                     "close_mean_0.6_H", "close_mean_3.0_A"):
            self.assertTrue(np.isnan(matrix[:, names.index(name)]).all(), name)
        self.assertEqual(matrix.dtype, np.float32)

    def test_evidence_computation_does_not_mutate_features(self):
        f = invented_features()
        arrays = (f.period_id, f.ball_xy, f.ball_observed, f.nearest,
                  f.tracked_counts, f.collective_speed, f.ball_speed)
        originals = [array.copy() for array in arrays]
        feature_matrix(f)
        heuristic_scores(f)
        for actual, expected in zip(arrays, originals):
            np.testing.assert_array_equal(actual, expected)


if __name__ == "__main__":
    unittest.main()
