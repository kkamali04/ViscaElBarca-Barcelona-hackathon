"""Constructed decoder checks; no challenge assets or labels are read."""
import itertools
import unittest

import numpy as np

from possession_model.decoder import decode_scores


def evidence_for(labels, strength=3.0):
    evidence = np.zeros((len(labels), 3), dtype=np.float32)
    for frame, label in enumerate(labels):
        if label in "HAD":
            evidence[frame, "HAD".index(label)] = strength
    return evidence


def uniform_cost(value=4.0):
    return value * (1.0 - np.eye(3))


def objective(path, scores, costs):
    return (sum(float(scores[i, state]) for i, state in enumerate(path))
            - sum(float(costs[a, b]) for a, b in zip(path[:-1], path[1:])))


class DecoderTests(unittest.TestCase):
    def decode(self, labels, strength=3.0, cost=4.0):
        return decode_scores(evidence_for(labels, strength),
                             np.ones(len(labels), dtype=np.int8), uniform_cost(cost))

    def test_matches_brute_force_optimum_and_minimum_changes(self):
        rng = np.random.default_rng(772)
        for n_frames in range(1, 7):
            for repetition in range(8):
                scores = rng.integers(-3, 4, (n_frames, 3)).astype(float)
                costs = rng.integers(0, 5, (3, 3)).astype(float)
                np.fill_diagonal(costs, 0)
                if repetition % 2:
                    scores[rng.integers(n_frames), rng.integers(3)] = -np.inf
                path = decode_scores(scores, np.ones(n_frames, dtype=int), costs)
                exhaustive = [
                    (objective(candidate, scores, costs),
                     sum(a != b for a, b in zip(candidate[:-1], candidate[1:])))
                    for candidate in itertools.product(range(3), repeat=n_frames)
                ]
                best = max(value for value, _ in exhaustive)
                minimum_changes = min(changes for value, changes in exhaustive if value == best)
                self.assertEqual(objective(path, scores, costs), best)
                self.assertEqual(np.count_nonzero(path[1:] != path[:-1]), minimum_changes)

    def test_neutral_gap_retains_last_confirmed_team_until_new_evidence(self):
        for old_team, new_team in (("H", "A"), ("A", "H")):
            path = self.decode(old_team * 8 + "?" * 20 + new_team * 8)
            np.testing.assert_array_equal(path[:28], "HAD".index(old_team))
            np.testing.assert_array_equal(path[28:], "HAD".index(new_team))

    def test_neutral_missing_gap_does_not_create_dead_ball(self):
        np.testing.assert_array_equal(self.decode("H" * 8 + "?" * 25 + "H" * 8), 0)

    def test_zero_cost_neutral_ties_do_not_oscillate(self):
        np.testing.assert_array_equal(self.decode("?" * 50, cost=0), 0)
        np.testing.assert_array_equal(self.decode("A" * 8 + "?" * 20 + "H" * 8, cost=0),
                                      [1] * 28 + [0] * 8)

    def test_definite_short_possession_is_preserved(self):
        # One frame is valid when evidence exceeds the cost of two changes.
        path = self.decode("H" * 8 + "A" + "H" * 8, strength=20)
        np.testing.assert_array_equal(path, [0] * 8 + [1] + [0] * 8)

    def test_weak_single_frame_flicker_is_suppressed(self):
        np.testing.assert_array_equal(self.decode("H" * 8 + "A" + "H" * 8), 0)

    def test_stoppage_splits_same_team(self):
        path = self.decode("H" * 8 + "D" * 8 + "H" * 8)
        np.testing.assert_array_equal(path, [0] * 8 + [2] * 8 + [0] * 8)

    def test_period_boundary_has_no_prior_half_leakage(self):
        scores = evidence_for("H" * 20 + "A")
        periods = np.array([1] * 20 + [2])
        path = decode_scores(scores, periods, uniform_cost(100))
        np.testing.assert_array_equal(path, [0] * 20 + [1])

    def test_outside_is_x_and_splits_equal_period_runs(self):
        scores = evidence_for("H" * 8 + "?" * 2 + "A")
        scores[8:10] = -np.inf  # Constraints outside scoring do not need a path.
        periods = np.array([1] * 8 + [0, -1, 1])
        path = decode_scores(scores, periods, uniform_cost(100))
        np.testing.assert_array_equal(path, [0] * 8 + [-1, -1, 1])
        self.assertEqual(path.dtype, np.int8)

    def test_first_frame_is_not_forced_dead_and_initial_state_is_explicit(self):
        np.testing.assert_array_equal(self.decode("A"), [1])
        np.testing.assert_array_equal(
            decode_scores(evidence_for("?" * 4), np.ones(4, int),
                          uniform_cost(), initial_state=2), [2] * 4)

    def test_minus_inf_constraints_and_infinite_forbidden_transitions(self):
        scores = np.array([[0., -np.inf, -np.inf], [0., 2., -np.inf]])
        costs = np.full((3, 3), np.inf)
        np.fill_diagonal(costs, 0)
        np.testing.assert_array_equal(decode_scores(scores, np.ones(2, int), costs), [0, 0])
        scores[1, 0] = -np.inf
        with self.assertRaisesRegex(ValueError, "No feasible path at frame index 1"):
            decode_scores(scores, np.ones(2, int), costs)

    def test_impossible_initial_and_later_states_fail(self):
        for scores in (np.full((1, 3), -np.inf),
                       np.array([[1., 0., 0.], [-np.inf, -np.inf, -np.inf]])):
            with self.assertRaisesRegex(ValueError, "No feasible"):
                decode_scores(scores, np.ones(len(scores), int), uniform_cost())
        with self.assertRaisesRegex(ValueError, "No feasible state"):
            decode_scores([[-np.inf, 0., 0.]], np.array([1]),
                          uniform_cost(), initial_state=0)

    def test_empty_and_all_outside(self):
        empty = decode_scores(np.empty((0, 3)), np.empty(0, int), uniform_cost())
        self.assertEqual(empty.shape, (0,))
        self.assertEqual(empty.dtype, np.int8)
        np.testing.assert_array_equal(
            decode_scores(np.full((3, 3), -np.inf), np.zeros(3, int), uniform_cost()), -1)

    def test_nonfinite_scores_are_rejected_even_outside(self):
        for invalid in (np.nan, np.inf):
            scores = np.zeros((3, 3))
            scores[1, 0] = invalid
            with self.assertRaisesRegex(ValueError, "NaN/\\+inf"):
                decode_scores(scores, np.array([1, 0, 1]), uniform_cost())

    def test_shapes_periods_costs_and_initial_state_are_validated(self):
        valid = np.zeros((2, 3))
        bad_cases = (
            (np.zeros((2, 2)), np.ones(2, int), uniform_cost(), None),
            (valid, np.ones(1, int), uniform_cost(), None),
            (valid, np.ones(2, float), uniform_cost(), None),
            (valid, np.ones(2, int), np.zeros((2, 2)), None),
            (valid, np.ones(2, int), -uniform_cost(), None),
            (valid, np.ones(2, int), np.eye(3), None),
            (valid, np.ones(2, int), np.full((3, 3), np.nan), None),
            (valid, np.ones(2, int), uniform_cost().astype(complex), None),
            (valid, np.ones(2, int), uniform_cost(), 3),
            (valid, np.ones(2, int), uniform_cost(), True),
            (valid, np.ones(2, int), uniform_cost(), 1.5),
        )
        for args in bad_cases:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    decode_scores(*args)

    def test_deterministic_and_does_not_mutate_inputs(self):
        scores = evidence_for("H" * 8 + "?" * 20 + "A" * 8)
        periods = np.ones(len(scores), dtype=np.int8)
        costs = uniform_cost()
        copies = [array.copy() for array in (scores, periods, costs)]
        first = decode_scores(scores, periods, costs)
        second = decode_scores(scores, periods, costs)
        self.assertEqual(first.tobytes(), second.tobytes())
        for actual, expected in zip((scores, periods, costs), copies):
            np.testing.assert_array_equal(actual, expected)


if __name__ == "__main__":
    unittest.main()
