"""Synthetic schema fixtures; no restricted challenge records are included."""
import tempfile
from pathlib import Path
import unittest

import numpy as np

from validation.sportec import _build_cache, load_sportec, make_ball_gap_mask, read_metadata, truth_code


META = """<PutDataRequest><MatchInformation>
<General MatchId="fixture" HomeTeamId="home" GuestTeamId="away" />
<Environment PitchX="100" PitchY="60" />
<Teams><Team TeamId="home"><Players><Player PersonId="h" /></Players></Team>
<Team TeamId="away"><Players><Player PersonId="a" /></Players></Team></Teams>
</MatchInformation></PutDataRequest>"""


def raw_fixture(change_truth=False):
    sections = []
    for period, start, timestamp in (("firstHalf", 100, "2020-01-01T10:00:00"), ("secondHalf", 1000, "2020-01-01T11:00:00")):
        for person, team, x in (("a", "away", "10"), ("h", "home", "-10"), ("b", "BALL", "-8")):
            frames = []
            for i in range(3):
                labels = (f' BallStatus="{0 if change_truth else 1}" BallPossession="{1 if i == 0 else 2}"'
                          if team == "BALL" else "")
                frames.append(f'<Frame N="{start + i}" T="{timestamp}.{40*i:03d}+00:00" X="{x}" Y="0"{labels} />')
            sections.append(f'<FrameSet GameSection="{period}" MatchId="fixture" TeamId="{team}" PersonId="{person}">{"".join(frames)}</FrameSet>')
    return f'<PutDataRequest><Positions>{"".join(sections)}</Positions></PutDataRequest>'


class SportecTests(unittest.TestCase):
    def test_truth_mapping_unknown_is_not_away(self):
        self.assertEqual(truth_code({"BallStatus": "0", "BallPossession": "2"}), 2)
        self.assertEqual(truth_code({"BallStatus": "1", "BallPossession": "1"}), 0)
        self.assertEqual(truth_code({"BallStatus": "1", "BallPossession": "2"}), 1)
        self.assertEqual(truth_code({"BallStatus": "1", "BallPossession": "0"}), -1)
        self.assertEqual(truth_code({"BallPossession": "1"}), -1)

    def test_grouped_xml_order_periods_and_center_translation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            meta, raw = root / "meta.xml", root / "raw.xml"
            meta.write_text(META)
            raw.write_text(raw_fixture())
            metadata = read_metadata(meta)
            folder, layout = _build_cache(meta, raw, metadata)
            self.assertEqual(metadata["slots"], ["h", "a"])
            self.assertEqual(layout["n_frames"], 6)
            self.assertEqual(layout["fps"], 25)
            self.assertEqual([(b["start"], b["end"]) for b in layout["blocks"]], [(0, 3), (3, 6)])
            np.testing.assert_array_equal(np.load(folder / "truth.npy"), [0, 1, 1, 0, 1, 1])
            np.testing.assert_allclose(np.load(folder / "ball.npy"), np.tile([42, 30], (6, 1)))
            np.testing.assert_allclose(np.load(folder / "positions.npy")[:, 0], np.tile([40, 30], (6, 1)))

    def test_labels_change_only_truth_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            meta, raw, altered = root / "meta.xml", root / "raw.xml", root / "altered.xml"
            meta.write_text(META)
            raw.write_text(raw_fixture())
            altered.write_text(raw_fixture(change_truth=True))
            metadata = read_metadata(meta)
            folder, layout = _build_cache(meta, raw, metadata)
            changed, other_layout = _build_cache(meta, altered, metadata)
            self.assertEqual(layout["blocks"], other_layout["blocks"])
            for filename in ("positions.npy", "ball.npy"):
                np.testing.assert_array_equal(np.load(folder / filename), np.load(changed / filename))
            self.assertFalse(np.array_equal(np.load(folder / "truth.npy"), np.load(changed / "truth.npy")))

    def test_block_occlusion_deterministic_and_exact_fraction(self):
        blocks = [{"start": 0, "end": 600}, {"start": 600, "end": 1000}]
        one = make_ball_gap_mask(1000, blocks, 25, .4, 4, 19)
        two = make_ball_gap_mask(1000, blocks, 25, .4, 4, 19)
        np.testing.assert_array_equal(one, two)
        self.assertEqual(one.sum(), 400)
        self.assertLessEqual(np.count_nonzero(np.diff(one.astype(int))), 8)

    def test_features_are_label_invariant_and_cache_reproducible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            meta, raw, altered = root / "meta.xml", root / "raw.xml", root / "altered.xml"
            meta.write_text(META)
            raw.write_text(raw_fixture())
            altered.write_text(raw_fixture(change_truth=True))
            features, truth, _ = load_sportec(meta, raw)
            changed, changed_truth, _ = load_sportec(meta, altered)
            cached, _, _ = load_sportec(meta, raw)
            np.testing.assert_array_equal(features.period_id, [1, 1, 1, 2, 2, 2])
            self.assertFalse(np.array_equal(truth, changed_truth))
            for name in ("ball_xy", "ball_observed", "nearest", "tracked_counts", "collective_speed", "ball_speed"):
                np.testing.assert_array_equal(getattr(features, name), getattr(changed, name))
                np.testing.assert_array_equal(getattr(features, name), getattr(cached, name))


if __name__ == "__main__":
    unittest.main()
