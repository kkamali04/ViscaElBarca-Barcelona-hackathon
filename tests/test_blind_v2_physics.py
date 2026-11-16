"""Independent physical acceptance on invented observations, never match data.

Preinspection expectations (declared to root before source inspection): exact
stationarity/linear speed; rigid-motion invariance; reduced zero-mean jitter
derivative energy; gaps/periods isolate finite support; outliers have local
effects; stable empty/short shapes; no input mutation; bounded invalid-input
handling; NumPy-only inference. Physical stationarity is not a class label.

Oracle: a coordinate OLS slope has variance sigma**2 / sum(centered_t**2).
The speed error cannot exceed the Euclidean velocity-vector error. A 25%
allowance covers finite-sample variation for the seeded long noise fixtures.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
import numpy as np
from possession_model.schema import FeatureSet
from experiments.noise_v2.features import robustify_ball_motion

METRICS = {}
SOURCES = [ROOT / 'experiments/noise_v2/features.py',
           ROOT / 'possession_model/schema.py', ROOT / 'possession_model/evidence.py']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(xy, fps=25., observed=None, periods=None):
    n = len(xy)
    return FeatureSet(fps, (105., 68.),
        np.ones(n, dtype=np.int16) if periods is None else periods,
        xy, np.ones(n, dtype=bool) if observed is None else observed,
        np.full((n, 2), 4., np.float32), np.full((n, 2), 11, np.int16),
        np.zeros((n, 2), np.float32), np.full(n, 7., np.float32),
        {'independent_fixture': True})


def linear(n, fps=25., velocity=(3., 4.), start=(2., -8.)):
    return np.asarray(start) + np.arange(n)[:, None] / fps * np.asarray(velocity)


def full_support(observed, periods, half):
    """Slow independent window oracle, deliberately not production segmentation."""
    result = np.zeros(len(observed), bool)
    for i in range(half, len(observed)-half):
        sl = slice(i-half, i+half+1)
        result[i] = bool(observed[sl].all() and np.isfinite(periods[sl]).all()
                         and (periods[sl] > 0).all()
                         and (periods[sl] == periods[i]).all())
    return result


class BlindPhysics(unittest.TestCase):
    def test_exact_stationary(self):
        out = robustify_ball_motion(fixture(np.tile([17.25, -4.5], (301, 1))))
        self.assertTrue(np.isnan(out.ball_speed[:15]).all())
        self.assertTrue(np.isnan(out.ball_speed[-15:]).all())
        self.assertLess(float(np.max(out.ball_speed[15:-15])), 1e-10)

    def test_exact_linear_at_multiple_sample_rates(self):
        for fps in (5., 12.5, 25., 50.):
            with self.subTest(fps=fps):
                f = fixture(linear(501, fps), fps)
                out = robustify_ball_motion(f)
                half = max(1, round(.6 * fps))
                finite = np.isfinite(out.ball_speed)
                np.testing.assert_array_equal(finite, full_support(f.ball_observed, f.period_id, half))
                np.testing.assert_allclose(out.ball_speed[finite], 5., atol=1e-5, rtol=0)

    def test_jitter_analytic_physical_bound(self):
        rng = np.random.default_rng(208411)
        sigma, fps, n = .04, 25., 12001
        noise = rng.normal(0., sigma, (n, 2))
        noise -= noise.mean(axis=0)
        t = np.arange(-15, 16) / fps
        vector_rms_bound = np.sqrt(2 * sigma**2 / np.sum(t*t))
        for velocity in ((0., 0.), (3., 4.)):
            with self.subTest(velocity=velocity):
                xy = linear(n, fps, velocity) + noise
                out = robustify_ball_motion(fixture(xy, fps)).ball_speed
                v = np.linalg.norm(velocity)
                err = float(np.sqrt(np.mean((out[15:-15]-v)**2)))
                raw = np.linalg.norm(np.diff(xy, axis=0) * fps, axis=1)
                raw_err = float(np.sqrt(np.mean((raw-v)**2)))
                self.assertLess(err, 1.25*vector_rms_bound)
                self.assertLess(err, raw_err/10)
                METRICS[f'jitter_speed_{v:g}_rms_error'] = err
                METRICS[f'raw_speed_{v:g}_rms_error'] = raw_err
        METRICS['analytic_vector_rms_bound_mps'] = float(vector_rms_bound)

    def test_rigid_translation_rotation(self):
        rng = np.random.default_rng(3001)
        xy = linear(1001, velocity=(1., -2.)) + rng.normal(0., .02, (1001, 2))
        angle = .731
        rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
        a = robustify_ball_motion(fixture(xy)).ball_speed
        b = robustify_ball_motion(fixture(xy @ rotation.T + [10000., -7000.])).ball_speed
        np.testing.assert_allclose(a, b, atol=2e-5, rtol=0, equal_nan=True)

    def test_gaps_isolate_runs(self):
        n = 360
        xy = linear(n, velocity=(2., 0.))
        observed = np.ones(n, bool)
        observed[90:96] = False
        observed[210] = False
        xy[96:] += [500., -20.]
        xy[211:] += [-900., 30.]
        f = fixture(xy, observed=observed)
        out = robustify_ball_motion(f).ball_speed
        mask = full_support(observed, f.period_id, 15)
        np.testing.assert_array_equal(np.isfinite(out), mask)
        np.testing.assert_allclose(out[mask], 2., atol=1e-5, rtol=0)

    def test_period_resets_and_unavailable_period(self):
        n = 390
        periods = np.repeat(np.array([1, 0, 2], np.int16), [170, 30, 190])
        xy = linear(n, velocity=(0., 6.))
        xy[200:] += [800., -170.]
        f = fixture(xy, periods=periods)
        out = robustify_ball_motion(f).ball_speed
        mask = full_support(f.ball_observed, periods, 15)
        np.testing.assert_array_equal(np.isfinite(out), mask)
        np.testing.assert_allclose(out[mask], 6., atol=1e-5, rtol=0)

    def test_outlier_has_local_bounded_effect(self):
        xy = linear(501, velocity=(2., 1.))
        xy[250] += [300., -400.]
        speed = robustify_ball_motion(fixture(xy)).ball_speed
        self.assertFalse(np.isinf(speed).any())
        self.assertTrue(np.isnan(speed[250]))
        distant = np.r_[np.arange(15, 225), np.arange(276, 486)]
        np.testing.assert_allclose(speed[distant], np.sqrt(5.), atol=1e-5, rtol=0)

    def test_no_mutation_dtype_strides_and_storage(self):
        xy = linear(301).astype(np.float32)[::-1]
        f = fixture(xy)
        fields = ('period_id', 'ball_xy', 'ball_observed', 'nearest',
                  'tracked_counts', 'collective_speed', 'ball_speed')
        snapshots = {k: getattr(f, k).copy() for k in fields}
        strides = f.ball_xy.strides
        for k in fields:
            getattr(f, k).flags.writeable = False
        metadata = dict(f.metadata)
        out = robustify_ball_motion(f)
        for k in fields:
            np.testing.assert_array_equal(getattr(f, k), snapshots[k])
            self.assertEqual(getattr(f, k).dtype, snapshots[k].dtype)
            if k != 'ball_speed':
                self.assertIs(getattr(out, k), getattr(f, k))
        self.assertEqual(f.ball_xy.strides, strides)
        self.assertEqual(out.ball_speed.dtype, np.float32)
        self.assertFalse(np.shares_memory(out.ball_speed, f.ball_speed))
        self.assertEqual(f.metadata, metadata)
        self.assertIsNot(f.metadata, out.metadata)

    def test_empty_and_short_trajectories(self):
        for n in (0, 1, 2, 15, 30, 31, 32):
            with self.subTest(n=n):
                out = robustify_ball_motion(fixture(linear(n)))
                self.assertEqual(out.ball_speed.shape, (n,))
                self.assertEqual(np.isfinite(out.ball_speed).sum(), max(0, n-30))

    def test_nonfinite_coordinates_invalidate_support(self):
        for bad in (np.nan, np.inf, -np.inf):
            with self.subTest(bad=bad):
                xy = linear(151)
                xy[75, 0] = bad
                out = robustify_ball_motion(fixture(xy)).ball_speed
                self.assertFalse(np.isinf(out).any())
                self.assertTrue(np.isnan(out[60:91]).all())
                np.testing.assert_allclose(out[15:50], 5., atol=1e-5, rtol=0)

    def test_nonfinite_periods_rejected_or_unavailable(self):
        for bad in (np.nan, np.inf, -np.inf):
            with self.subTest(bad=bad):
                periods = np.ones(211, np.float64)
                periods[65:146] = bad
                f = fixture(linear(211), periods=periods)
                try:
                    out = robustify_ball_motion(f).ball_speed
                except (ValueError, TypeError):
                    continue
                if np.isposinf(bad):
                    METRICS['positive_infinite_period_finite_outputs'] = int(np.isfinite(out[65:146]).sum())
                self.assertTrue(np.isnan(out[50:161]).all())

    def test_invalid_fps_and_shape_fail_safely(self):
        for fps in (0., -1., np.nan, np.inf, -np.inf):
            with self.subTest(fps=fps):
                with self.assertRaises(ValueError):
                    robustify_ball_motion(fixture(linear(40), fps))
        for field, value in [('ball_xy', np.zeros((40, 3))),
                             ('ball_observed', np.ones(39, bool)),
                             ('period_id', np.ones((40, 1), np.int16))]:
            with self.subTest(field=field):
                f = fixture(linear(40))
                setattr(f, field, value)
                with self.assertRaises((ValueError, TypeError)):
                    robustify_ball_motion(f)

    def test_repeat_is_deterministic(self):
        rng = np.random.default_rng(19013)
        f = fixture(linear(501) + rng.normal(0, .02, (501, 2)))
        a = robustify_ball_motion(f).ball_speed
        b = robustify_ball_motion(f).ball_speed
        self.assertEqual(a.tobytes(), b.tobytes())
        METRICS['deterministic_output_sha256'] = hashlib.sha256(a.tobytes()).hexdigest()

    def test_inference_without_training_or_scipy(self):
        program = r'''
import sys
class NoTraining:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'scipy','sklearn','torch','pandas','matplotlib','joblib','xgboost'}:
            raise ImportError('dependency intentionally unavailable')
sys.meta_path.insert(0, NoTraining())
import numpy as np
from possession_model.schema import FeatureSet
from experiments.noise_v2.features import robustify_ball_motion
n=101
t=np.arange(n)/25
f=FeatureSet(25., (105.,68.), np.ones(n,np.int16), np.column_stack([3*t,4*t]),
np.ones(n,bool), np.zeros((n,2)), np.ones((n,2)), np.zeros((n,2)), np.zeros(n))
s=robustify_ball_motion(f).ball_speed
assert s.shape==(n,) and np.allclose(s[15:-15],5)
assert not any(k.split('.')[0] in {'scipy','sklearn','torch','pandas','matplotlib','joblib','xgboost'} for k in sys.modules)
print('numpy_only_inference_pass')
'''
        result = subprocess.run([sys.executable, '-c', program], cwd=ROOT,
                                capture_output=True, text=True, timeout=20,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'numpy_only_inference_pass')


if __name__ == '__main__':
    source_before = {str(p.relative_to(ROOT)): digest(p) for p in SOURCES}
    started = time.perf_counter()
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BlindPhysics)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    source_after = {str(p.relative_to(ROOT)): digest(p) for p in SOURCES}
    report = {
        'scope': 'invented physical motion fixtures; no classifier accuracy claim',
        'python': sys.executable, 'tests_run': result.testsRun,
        'failures': [{'test': str(t), 'detail': detail} for t, detail in result.failures],
        'errors': [{'test': str(t), 'detail': detail} for t, detail in result.errors],
        'passed': result.wasSuccessful(), 'duration_seconds': time.perf_counter()-started,
        'source_frozen': source_before == source_after,
        'source_sha256': source_after, 'test_sha256': digest(Path(__file__)),
        'metrics': METRICS, 'test_output': stream.getvalue(),
        'command': '.venv\\Scripts\\python.exe tests\\test_blind_v2_physics.py',
        'limitations': ['No challenge/match data or GT inspected.',
            'No learned classifier accuracy assessed.',
            'This physical API acceptance is not a full exported-package E2E acceptance.']}
    (ROOT / 'reports/blind-v2-physics.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(stream.getvalue())
    print(json.dumps({k: report[k] for k in ['tests_run','passed','duration_seconds','source_frozen','metrics']}))
    sys.exit(0 if result.wasSuccessful() and source_before == source_after else 1)
