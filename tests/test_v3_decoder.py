"""Invented-only implementation checks; independent G04 acceptance is separate."""
import itertools
import unittest

import numpy as np

from possession_model.decoder import decode_scores
from experiments.v3.decoder import decode_change_aware


def objective(path, scores, costs, q, alpha):
    value = sum(float(scores[t, s]) for t, s in enumerate(path))
    for t, (a, b) in enumerate(zip(path, path[1:]), 1):
        if a != b:
            channel = 0 if {a, b} == {0, 1} else 1
            value -= costs[a, b] * (1 - alpha * float(q[t, channel]))
    return value


class DecoderChecks(unittest.TestCase):
    def test_exhaustive_objective_and_unique_swap(self):
        rng = np.random.default_rng(304)
        for n in range(1, 8):
            scores = rng.normal(size=(n, 3))
            q = rng.random((n, 2)).astype(np.float32)
            costs = np.array([[0., .25, 1.5], [.75, 0., .5], [1., .4, 0.]])
            paths = list(itertools.product(range(3), repeat=n))
            values = np.array([objective(p, scores, costs, q, .8) for p in paths])
            got = decode_change_aware(scores, np.ones(n, np.int16), costs, q, .8)
            self.assertAlmostEqual(objective(got, scores, costs, q, .8), values.max(), places=12)
            swap = np.array([1, 0, 2])
            other = decode_change_aware(scores[:, swap], np.ones(n, np.int16),
                                        costs[np.ix_(swap, swap)], q, .8)
            np.testing.assert_array_equal(other, swap[got])

    def test_canonical_alpha_zero_and_runs(self):
        rng = np.random.default_rng(50)
        for trial in range(100):
            n = 25
            scores = rng.integers(-2, 3, size=(n, 3)).astype(float)
            p = np.array([0] + [1] * 7 + [0] + [1] * 8 + [2] * 8, np.int16)
            costs = rng.integers(0, 4, size=(3, 3)).astype(float)
            np.fill_diagonal(costs, 0.)
            q = rng.random((n, 2)).astype(np.float32)
            for initial in (None, 0, 1, 2):
                np.testing.assert_array_equal(
                    decode_change_aware(scores, p, costs, q, 0., initial),
                    decode_scores(scores, p, costs, initial))
        scores = np.array([[2, 0, -1], [0, 0, -1], [0, 2, -1]], float)
        np.testing.assert_array_equal(decode_change_aware(scores, [1, 1, 1],
            np.ones((3, 3))-np.eye(3), np.zeros((3, 2), np.float32), 0), [0, 0, 1])

    def test_edge_channels_short_spell_and_period_reset(self):
        scores = np.array([[5, 0, -np.inf], [0, 3, -np.inf], [5, 0, -np.inf]], float)
        costs = np.full((3, 3), 3.); np.fill_diagonal(costs, 0)
        q = np.zeros((3, 2), np.float32); q[1:, 0] = 1
        np.testing.assert_array_equal(decode_change_aware(scores, [1, 1, 1], costs, q, .8), [0, 1, 0])
        q[:, 0] = 0; q[:, 1] = 1
        np.testing.assert_array_equal(decode_change_aware(scores, [1, 1, 1], costs, q, .8), [0, 0, 0])
        np.testing.assert_array_equal(decode_change_aware(scores, [1, 0, 1], costs, q, .8), [0, -1, 0])

    def test_prohibitions_and_initial_state(self):
        scores = np.array([[0., -np.inf, -np.inf], [0., 100., -np.inf]])
        costs = np.full((3, 3), np.inf); np.fill_diagonal(costs, 0)
        q = np.ones((2, 2), np.float32)
        np.testing.assert_array_equal(decode_change_aware(scores, [1, 1], costs, q, .8), [0, 0])
        with self.assertRaises(ValueError):
            decode_change_aware(scores, [1, 1], costs, q, .8, 1)
        scores[1, 0] = -np.inf
        with self.assertRaises(ValueError):
            decode_change_aware(scores, [1, 1], costs, q, .8)

    def test_exhaustive_constrained_paths_and_tied_optimal_sets(self):
        scores = np.array([[2., 3., 0.], [2., 3., 1.], [4., -np.inf, 2.], [1., 4., 3.]])
        costs = np.array([[0., np.inf, 1.], [2., 0., .5], [1., 2., 0.]])
        q = np.array([[1., 1.], [.2, .8], [.9, .1], [.3, .7]], np.float32)
        for initial in (None, 0, 1, 2):
            paths = [p for p in itertools.product(range(3), repeat=4)
                     if (initial is None or p[0] == initial)
                     and all(np.isfinite(scores[t, s]) for t, s in enumerate(p))
                     and all(np.isfinite(costs[a, b]) for a, b in zip(p, p[1:]))]
            optimum = max(objective(p, scores, costs, q, .8) for p in paths)
            got = decode_change_aware(scores, np.ones(4, np.int16), costs, q, .8, initial)
            self.assertAlmostEqual(objective(got, scores, costs, q, .8), optimum, places=12)
        # Two constant team paths tie. Canonical output is H-first, whereas the
        # complete maximizing set (and objective) is invariant under H/A swap.
        scores = np.tile([0., 0., -np.inf], (4, 1))
        costs = np.ones((3, 3)) - np.eye(3)
        q = np.zeros((4, 2), np.float32)
        paths = list(itertools.product(range(3), repeat=4))
        values = [objective(p, scores, costs, q, .8) for p in paths]
        best = {p for p, v in zip(paths, values) if v == max(values)}
        swap = (1, 0, 2)
        self.assertEqual(best, {tuple(swap[s] for s in p) for p in best})
        np.testing.assert_array_equal(decode_change_aware(scores, [1]*4, costs, q, .8), [0]*4)

    def test_both_sign_overflow_in_losing_alternatives(self):
        for scores, costs in (
            (np.array([[-1e308, 1., 0.], [-1e308, 0., 0.]]), np.zeros((3, 3))),
            (np.array([[1e308, 1., 0.], [1e308, 0., 0.]]), np.zeros((3, 3))),
            (np.array([[-1e308, 1., 0.], [0., 0., 0.]]),
             np.array([[0., 1e308, 0.], [0., 0., 0.], [0., 0., 0.]])),
        ):
            with self.assertRaisesRegex(ValueError, "overflow"):
                decode_change_aware(scores, [1, 1], costs, np.zeros((2, 2), np.float32), .8)

    def test_empty_and_malformed(self):
        got = decode_change_aware(np.empty((0, 3)), np.empty(0, np.int16),
                                 np.zeros((3, 3)), np.empty((0, 2), np.float32), 0.)
        self.assertEqual(got.dtype, np.int8); self.assertEqual(got.shape, (0,))
        for q in (np.array([[np.nan, 0]]), np.array([[1.1, 0]]), np.ones((1, 3))):
            with self.assertRaises(ValueError):
                decode_change_aware(np.zeros((1, 3)), [0], np.zeros((3, 3)), q, .8)
        for alpha in (True, np.nan, 1., -1.):
            with self.assertRaises(ValueError):
                decode_change_aware(np.zeros((1, 3)), [1], np.zeros((3, 3)), np.zeros((1, 2)), alpha)
        with self.assertRaises(ValueError):
            decode_change_aware([[np.inf, 0., 0.]], [0], np.zeros((3, 3)), np.zeros((1, 2)), .8)
        for periods in ([True], [1.], [[1]]):
            with self.assertRaises(ValueError):
                decode_change_aware(np.zeros((1, 3)), periods, np.zeros((3, 3)), np.zeros((1, 2)), .8)
        for initial in (True, 1., 3):
            with self.assertRaises(ValueError):
                decode_change_aware(np.zeros((1, 3)), [1], np.zeros((3, 3)), np.zeros((1, 2)), .8, initial)


if __name__ == "__main__":
    unittest.main()
