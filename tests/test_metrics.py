"""Metric adapter preserves independent halves without inserting fake labels."""
import unittest
import numpy as np
from validation.metrics import measure


class MetricTests(unittest.TestCase):
    def test_same_team_across_adjacent_halves_is_two_spells(self):
        labels = np.zeros(40, np.int8)
        periods = np.repeat([1, 2], 20)
        report = measure(labels, labels, periods)
        self.assertEqual(report["n_truth_spells"], 2)
        self.assertEqual(report["n_predicted_spells"], 2)
        self.assertEqual(report["spell_f1"], 1.)

    def test_outside_period_ignored_and_unknown_truth_excluded(self):
        truth = np.array([0, 0, -1, 1, 1], np.int8)
        predicted = np.array([1, 0, 2, 1, 0], np.int8)
        periods = np.array([0, 1, 1, 2, 0])
        report = measure(truth, predicted, periods)
        self.assertEqual(report["graded_frames"], 2)
        self.assertEqual(report["spell_f1"], 1.)


if __name__ == "__main__":
    unittest.main()
