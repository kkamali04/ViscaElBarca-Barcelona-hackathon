"""Invented fixtures only: alignment, units, missingness and anonymous motion."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from possession_model.features import FeatureAccumulator, load_atd


def metadata(n=2, order=("p0", "p1"), channel_order=("x", "y", "s")):
    channels = ''.join(f'<Channel id="{c}"><Name>{name}</Name><Unit>{unit}</Unit></Channel>'
                       for c, name, unit in (("x", "position_x", "normalized"),
                                              ("y", "position_y", "normalized"),
                                              ("s", "speed_kph", "kph")))
    links = ''.join(f'<PlayerChannel id="{p}_{c}" playerId="{p}" channelId="{c}"/>'
                    for p in ("p0", "p1") for c in ("x", "y", "s"))
    groups = ''.join('<SplitRegister separator=",">' + ''.join(
        f'<PlayerChannelRef playerChannelId="{p}_{c}"/>' for c in channel_order) + '</SplitRegister>'
        for p in order)
    return (f'<main><FrameRate>25</FrameRate><Teams><Team id="away"/><Team id="home"/></Teams>'
            f'<Score idLocalTeam="home" idVisitingTeam="away"/>'
            f'<Players><Player id="p1" teamId="away"/><Player id="p0" teamId="home"/></Players>'
            f'<Channels>{channels}</Channels><PlayerChannels>{links}</PlayerChannels>'
            f'<DataFormatSpecification separator=":" startFrame="1" endFrame="{n}">'
            f'<StringRegister name="frameCount"/><SplitRegister separator=";">{groups}</SplitRegister>'
            f'<SplitRegister separator=","><BallChannelRef channelId="x"/>'
            f'<BallChannelRef channelId="y"/><BallChannelRef channelId="s"/></SplitRegister>'
            f'</DataFormatSpecification></main>')


class FeatureTests(unittest.TestCase):
    def load(self, raw, meta=None, n=2, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "meta.xml").write_text(meta or metadata(n), encoding="utf-8")
            (root / "raw.txt").write_text(raw, encoding="utf-8")
            return load_atd(root / "meta.xml", root / "raw.txt", n, **kwargs)

    def test_explicit_sides_metres_and_counts(self):
        result = self.load("1:0.1,0.5,999;0.9,0.5,999:0.2,0.5,999\n"
                           "2:nan,nan,nan;0.9,0.5,0:nan,nan,nan\n", pitch=(100, 60))
        np.testing.assert_allclose(result.ball_xy[0], (20, 30))
        np.testing.assert_allclose(result.nearest[0], (10, 70))
        np.testing.assert_array_equal(result.tracked_counts, ((1, 1), (0, 1)))
        self.assertTrue(np.isnan(result.nearest[1]).all())
        self.assertFalse(result.ball_observed[1])
        self.assertTrue(np.isnan(result.ball_speed).all())

    def test_slot_and_channel_permutation(self):
        original = self.load("1:0.1,0.5,0;0.9,0.3,0:0.2,0.5,0\n"
                             "2:0.1,0.5,0;0.9,0.3,0:0.3,0.5,0\n")
        permuted = self.load("1:0,0.3,0.9;0,0.5,0.1:0.2,0.5,0\n"
                             "2:0,0.3,0.9;0,0.5,0.1:0.3,0.5,0\n",
                             metadata(order=("p1", "p0"), channel_order=("s", "y", "x")))
        np.testing.assert_allclose(original.nearest, permuted.nearest)

    def test_nan_pairs_and_pitch_excursion(self):
        result = self.load("1:nan,0.5,0;0.9,nan,0:-0.01,1.01,0\n"
                           "2:0.1,0.5,0;0.9,0.3,0:nan,0.5,0\n")
        self.assertTrue(result.ball_observed[0])
        self.assertTrue(np.isnan(result.nearest[0]).all())
        self.assertTrue(np.isnan(result.ball_xy[1]).all())
        self.assertEqual(result.tracked_counts[0].sum(), 0)

    def test_malformed_records_fail_closed(self):
        good = "1:0.1,0.5,0;0.9,0.5,0:0.2,0.5,0\n"
        tail = "2:0.1,0.5,0;0.9,0.5,0:0.2,0.5,0\n"
        invalid = (good, good + good, tail + good, good + tail + tail,
                   good + tail.replace("0.1", "oops"), good + tail.replace("0.1", "inf"),
                   good + tail.replace("0.1,0.5,0", "0.1,0.5"),
                   good + tail.replace("0.1,0.5,0", "0.1,,0.5"),
                   good + tail.replace("0.1,0.5,0", "0.1,0.5,0,1"),
                   good + tail.replace(":0.2,0.5,0", ":0.2,0.5"), good + "\n" + tail,
                   good + tail.replace("0.2", "1e309"))
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.load(raw)

    def test_invalid_metadata_fails(self):
        raw = "1:0.1,0.5,0;0.9,0.5,0:0.2,0.5,0\n2:0.1,0.5,0;0.9,0.5,0:0.2,0.5,0\n"
        variants = (metadata().replace('teamId="away"', 'teamId="unknown"'),
                    metadata().replace('idVisitingTeam="away"', 'idVisitingTeam="home"'),
                    metadata().replace('<Team id="away"/>', '<Team id="away"/><Team id="away"/>'),
                    metadata().replace('<Unit>normalized</Unit>', '<Unit>metres</Unit>'),
                    metadata().replace('<FrameRate>25</FrameRate>', '<FrameRate>30</FrameRate>'),
                    metadata().replace('playerChannelId="p1_x"', 'playerChannelId="p0_x"'),
                    metadata().replace('endFrame="2"', 'endFrame="3"'))
        for meta in variants:
            with self.subTest(meta=meta), self.assertRaises(ValueError):
                self.load(raw, meta)

    def test_order_and_completion(self):
        acc = FeatureAccumulator(2, (0, 1))
        with self.assertRaises(ValueError):
            acc.push(1, ((0, 0), (1, 1)), (0, 0))
        with self.assertRaises(ValueError):
            acc.finish()
        acc.push(0, ((0, 0), (1, 1)), (0, 0))
        with self.assertRaises(ValueError):
            acc.push(0, ((0, 0), (1, 1)), (0, 0))
        acc.push(1, ((0, 0), (1, 1)), (0, 0))
        acc.finish()
        with self.assertRaises(ValueError):
            acc.push(2, ((0, 0), (1, 1)), (0, 0))

    def test_ball_speed_uninterrupted_and_jump_rejection(self):
        acc = FeatureAccumulator(40, (0, 1))
        for i in range(40):
            ball = (i * 0.04, 0)
            if i == 14:
                ball = (np.nan, np.nan)
            if i == 28:
                ball = (80, 0)
            acc.push(i, ((0, 0), (2, 0)), ball)
        result = acc.finish()
        self.assertTrue(np.isnan(result.ball_speed[:10]).all())
        self.assertAlmostEqual(result.ball_speed[10], 1, places=5)
        self.assertTrue(np.isnan(result.ball_speed[14:25]).all())
        self.assertAlmostEqual(result.ball_speed[25], 1, places=5)
        self.assertTrue(np.isnan(result.ball_speed[28:39]).all())
        self.assertAlmostEqual(result.ball_speed[39], 1, places=5)

    def test_period_reset_half_open_blocks(self):
        acc = FeatureAccumulator(60, (0, 1), blocks=((1, 0, 27), (2, 30, 60)))
        for i in range(60):
            acc.push(i, ((0, 0), (1, 0)), (0.04 * i, 0))
        result = acc.finish()
        np.testing.assert_array_equal(result.period_id[26:31], (1, 0, 0, 0, 2))
        self.assertTrue(np.isnan(result.ball_speed[27:40]).all())
        self.assertAlmostEqual(result.ball_speed[40], 1, places=5)
        with self.assertRaises(ValueError):
            FeatureAccumulator(10, (0, 1), blocks=((1, 0, 6), (2, 5, 10)))

    def test_collective_motion_invariant_to_anonymous_slots(self):
        sides = (0, 0, 0, 1, 1, 1)
        points = np.array(((0, 0), (0, 10), (0, 20), (50, 0), (50, 10), (50, 20)))
        first, second = FeatureAccumulator(60, sides), FeatureAccumulator(60, sides)
        for i in range(60):
            moved = points + (0.04 * i, 0)
            first.push(i, moved, (np.nan, np.nan))
            second.push(i, moved[[2, 0, 1, 4, 5, 3]], (np.nan, np.nan))
        result, shuffled = first.finish(), second.finish()
        self.assertTrue(np.isnan(result.collective_speed[:25]).all())
        np.testing.assert_allclose(result.collective_speed[25:], 1, rtol=1e-5)
        np.testing.assert_allclose(result.collective_speed, shuffled.collective_speed, equal_nan=True)
        self.assertEqual(result.metadata["player_ring_bytes"], 26 * 6 * 2 * 4)
        self.assertLess(result.array_bytes, 60 * 40)

    def test_collective_motion_missingness_and_reset(self):
        acc = FeatureAccumulator(65, (0, 0, 0, 1, 1, 1), blocks=((1, 0, 30), (2, 30, 65)))
        points = np.array(((0, 0), (0, 10), (0, 20), (50, 0), (50, 10), (50, 20)), dtype=float)
        for i in range(65):
            current = points + (i * 0.04, 0)
            if i == 57:
                current[:3] = np.nan
            acc.push(i, current, (np.nan, np.nan))
        result = acc.finish()
        self.assertTrue(np.isnan(result.collective_speed[30:55]).all())
        np.testing.assert_allclose(result.collective_speed[55:57], 1, rtol=1e-5)
        self.assertTrue(np.isnan(result.collective_speed[57:, 0]).all())
        self.assertTrue(np.isfinite(result.collective_speed[57:, 1]).all())


if __name__ == "__main__":
    unittest.main()
