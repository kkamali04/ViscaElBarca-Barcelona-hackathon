"""Invented SportsCode intervals and format bytes; no supplied match records."""
from pathlib import Path
import tempfile
import unittest
import numpy as np
from possession_model.pipeline import tag_support, write_submission, predict
from test_evidence import invented_features


def event(code, team, start=0, stop=4):
    return f'<instance><code>{code}</code><start>{start}</start><end>{stop}</end><label><group>Team</group><text>{team}</text></label></instance>'


class PipelineTests(unittest.TestCase):
    def test_tags_polarity_duplicates_unknown_and_set_piece(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"tags.xml"
            path.write_text('<root>'+event("BUILD UP", "Home")*20+
                event("Defensive Transition", "Home")+event("SET PIECES", "Away")+
                event("PROGRESSION", "N/A")+'</root>')
            tags = tag_support(path, 20, 5, "Home", "Away")
            np.testing.assert_array_equal(tags[:, 0], 1.)
            np.testing.assert_array_equal(tags[:, 1], .5)

    def test_deterministic_csv_and_invalid_label(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"output.csv"
            one = write_submission(path, [-1, 0, 1, 2])
            self.assertEqual(path.read_bytes(), b'frame,label\n0,X\n1,H\n2,A\n3,D\n')
            self.assertEqual(one, write_submission(path, [-1, 0, 1, 2]))
            with self.assertRaises(ValueError):
                write_submission(path, [3])

    def test_only_explicit_dead_interval_is_forced(self):
        features = invented_features(n=30)
        config = {"emitter": "heuristic", "transition_seconds": .25, "tag_weight": 0}
        codes = predict(features, config, forced_dead=[(10, 15)])
        np.testing.assert_array_equal(codes[10:15], 2)
        self.assertEqual(codes[0], 0)
        self.assertEqual(codes[-1], 0)


if __name__ == "__main__":
    unittest.main()
