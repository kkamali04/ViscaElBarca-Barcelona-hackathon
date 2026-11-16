"""Implementation unit tests using invented coordinates, never match records."""
from dataclasses import replace
import unittest
from unittest.mock import patch

import numpy as np

from experiments.noise_v2.features import robustify_ball_motion
from possession_model.schema import FeatureSet


def invented(xy, fps=25., periods=None, observed=None):
    xy = np.asarray(xy, dtype=np.float64)
    n = len(xy)
    return FeatureSet(
        fps=fps, pitch=(105.3, 68.),
        period_id=np.ones(n, dtype=np.int8) if periods is None else np.asarray(periods),
        ball_xy=xy,
        ball_observed=np.ones(n, dtype=bool) if observed is None else np.asarray(observed),
        nearest=np.tile([.5, 7.], (n, 1)).astype(np.float32),
        tracked_counts=np.full((n, 2), 11, dtype=np.uint16),
        collective_speed=np.zeros((n, 2), dtype=np.float32),
        ball_speed=np.full(n, 7., dtype=np.float32),
        metadata={"feature_version": "invented", "ball_speed_method": "old", "nested": {"x": 1}})


def ramp(n=501, velocity=(1., 0.), fps=25.):
    return np.array([30., 34.]) + np.arange(n)[:, None]/fps*np.asarray(velocity)


class NoiseV2FeatureTests(unittest.TestCase):
    def test_noiseless_linear_vector_slope_and_full_window_edges(self):
        f = invented(ramp(velocity=(3., 4.)))
        result = robustify_ball_motion(f)
        self.assertEqual(result.metadata["ball_motion_window_frames"], 31)
        self.assertTrue(np.isnan(result.ball_speed[:15]).all())
        self.assertTrue(np.isnan(result.ball_speed[-15:]).all())
        np.testing.assert_allclose(result.ball_speed[15:-15], 5., rtol=0, atol=1e-6)

    def test_stationary_jitter_and_true_one_mps_are_distinguished(self):
        noise = np.random.default_rng(20261115).normal(0, .2, (2001, 2))
        still = robustify_ball_motion(invented(np.array([50., 34.])+noise))
        moving = robustify_ball_motion(invented(ramp(2001)+noise))
        self.assertLess(float(np.nanmean(still.ball_speed)), .2)
        self.assertLess(abs(float(np.nanmean(moving.ball_speed))-1.), .05)
        self.assertLess(float(np.nanquantile(still.ball_speed, .95)), .35)

    def test_missing_flag_and_nan_coordinates_split_full_windows(self):
        for mode in ("flag", "nan"):
            with self.subTest(mode=mode):
                xy = ramp(201)
                observed = np.ones(201, dtype=bool)
                if mode == "flag":
                    observed[80:100] = False
                else:
                    xy[80:100] = np.nan
                result = robustify_ball_motion(invented(xy, observed=observed))
                # Every complete 31-point window overlapping [80,100) is unknown.
                self.assertTrue(np.isnan(result.ball_speed[65:115]).all())
                np.testing.assert_allclose(result.ball_speed[15:65], 1., atol=1e-6)
                np.testing.assert_allclose(result.ball_speed[115:186], 1., atol=1e-6)

    def test_period_reset_never_creates_a_cross_boundary_slope(self):
        xy = ramp(201)
        xy[100:] += [20., -10.]
        periods = np.r_[np.ones(100, np.int8), np.full(101, 2, np.int8)]
        result = robustify_ball_motion(invented(xy, periods=periods))
        self.assertTrue(np.isnan(result.ball_speed[85:115]).all())
        np.testing.assert_allclose(result.ball_speed[15:85], 1., atol=1e-6)
        np.testing.assert_allclose(result.ball_speed[115:186], 1., atol=1e-6)

    def test_teleport_guard_prevents_outlier_contamination(self):
        xy = ramp(201)
        xy[100] += [20., 0.]
        result = robustify_ball_motion(invented(xy))
        self.assertTrue(np.isnan(result.ball_speed[85:116]).all())
        np.testing.assert_allclose(result.ball_speed[15:75], 1., atol=1e-6)
        np.testing.assert_allclose(result.ball_speed[125:186], 1., atol=1e-6)
        self.assertLessEqual(float(np.nanmax(result.ball_speed)), 1.000001)

    def test_short_runs_and_inactive_periods_remain_unknown(self):
        self.assertTrue(np.isnan(robustify_ball_motion(invented(ramp(30))).ball_speed).all())
        f = invented(ramp(100), periods=np.zeros(100, np.int8))
        self.assertTrue(np.isnan(robustify_ball_motion(f).ball_speed).all())

    def test_speed_safety_limit_is_applied_after_slope(self):
        # Isolate the final safety check from the existing adjacent-jump guard.
        f = invented(ramp(101, velocity=(61., 0.)))
        with patch("experiments.noise_v2.features.reliable_ball_mask", return_value=np.ones(101, bool)):
            self.assertTrue(np.isnan(robustify_ball_motion(f).ball_speed).all())

    def test_original_arrays_metadata_and_values_are_unchanged(self):
        f = invented(ramp())
        arrays = ("period_id", "ball_xy", "ball_observed", "nearest", "tracked_counts",
                  "collective_speed", "ball_speed")
        snapshots = {name: getattr(f, name).copy() for name in arrays}
        before_meta = dict(f.metadata)
        result = robustify_ball_motion(f)
        self.assertIsNot(result, f)
        self.assertIsNot(result.metadata, f.metadata)
        self.assertEqual(f.metadata, before_meta)
        self.assertEqual(f.metadata["ball_speed_method"], "old")
        for name in arrays:
            np.testing.assert_array_equal(getattr(f, name), snapshots[name])
            if name != "ball_speed":
                self.assertIs(getattr(result, name), getattr(f, name))
        self.assertIsNot(result.ball_speed, f.ball_speed)

    def test_invalid_fps_and_alignment_rejected(self):
        f = invented(ramp())
        for fps in (0., -1., np.nan, np.inf):
            with self.subTest(fps=fps), self.assertRaises(ValueError):
                robustify_ball_motion(replace(f, fps=fps))
        with self.assertRaises(ValueError):
            robustify_ball_motion(replace(f, ball_xy=f.ball_xy[:-1]))

    def test_optional_scipy_local_linear_coefficient_parity(self):
        try:
            from scipy.signal import savgol_coeffs
        except ImportError:
            self.skipTest("SciPy is an optional training/test dependency")
        times = np.arange(-15, 16, dtype=np.float64)/25.
        expected_weights = savgol_coeffs(31, 1, deriv=1, delta=1/25., use="dot")
        np.testing.assert_allclose(times/np.dot(times, times), expected_weights, rtol=0, atol=1e-14)
        noise = np.random.default_rng(20261115).normal(0, .2, (101, 2))
        xy = ramp(101)+noise
        result = robustify_ball_motion(invented(xy))
        expected = np.hypot(
            np.convolve(xy[:, 0], expected_weights[::-1], mode="valid"),
            np.convolve(xy[:, 1], expected_weights[::-1], mode="valid"))
        np.testing.assert_allclose(result.ball_speed[15:-15], expected, rtol=1e-6, atol=1e-6)


if __name__ == "__main__":
    unittest.main()
