"""Streaming, metre-based features for the documented Metrica ATD format.

Player slots are anonymous: set motion never treats a slot as a player identity.
Unknown distances and motion remain NaN. Only the output features grow with the
number of frames; player positions live in a one-second ring buffer.
"""
from collections import deque
from pathlib import Path
import warnings
import xml.etree.ElementTree as ET

import numpy as np

from .schema import FeatureSet


def _positive_number(value, name):
    value = float(value)
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def _periods(n_frames, blocks):
    periods = np.ones(n_frames, dtype=np.uint8)
    if blocks is None:
        return periods
    periods.fill(0)
    for period, start, stop in blocks:
        if any(isinstance(x, bool) or int(x) != x for x in (period, start, stop)):
            raise ValueError("Blocks require integer period/start/stop")
        period, start, stop = int(period), int(start), int(stop)
        if period not in (1, 2, 3, 4) or not 0 <= start < stop <= n_frames:
            raise ValueError("Blocks require football period 1..4 and valid half-open bounds")
        if periods[start:stop].any():
            raise ValueError("Period blocks overlap")
        periods[start:stop] = period
    return periods


class FeatureAccumulator:
    """Accept exactly one ordered push per frame, then return compact features.

    ``team_of_slot`` uses 0=home and 1=away. Positions already use metres and a
    pitch-corner origin. Partial-NaN coordinate pairs are unobserved. Motion uses
    uninterrupted same-period observations and never exported speed channels.

    ``collective_speed`` has shape (frames, 2). It is a robust anonymous set-motion
    proxy, not the mean of identified-player speeds. Its nearest-set matching can
    underestimate movement when players cross; use it only as weak context.
    """

    def __init__(self, n_frames, team_of_slot, fps=25, pitch=(105.3, 68), blocks=None):
        if isinstance(n_frames, bool) or int(n_frames) != n_frames or n_frames <= 0:
            raise ValueError("n_frames must be a positive integer")
        self.n_frames = int(n_frames)
        sides = np.asarray(team_of_slot)
        if sides.ndim != 1 or not len(sides) or not np.isin(sides, (0, 1)).all():
            raise ValueError("Every slot must belong to side 0 or 1")
        if not (sides == 0).any() or not (sides == 1).any():
            raise ValueError("Both teams must have at least one slot")
        if len(sides) > np.iinfo(np.uint16).max:
            raise ValueError("Too many slots")
        self.sides = sides.astype(np.uint8)
        self._side_slots = (self.sides == 0, self.sides == 1)
        self.fps = _positive_number(fps, "fps")
        if len(pitch) != 2:
            raise ValueError("pitch requires length and width")
        self.pitch = tuple(_positive_number(x, "pitch dimension") for x in pitch)
        self._blocks_fixed = blocks is not None
        self.period_id = _periods(self.n_frames, blocks)
        self.ball_xy = np.full((self.n_frames, 2), np.nan, dtype=np.float32)
        self.ball_observed = np.zeros(self.n_frames, dtype=bool)
        self.nearest = np.full((self.n_frames, 2), np.nan, dtype=np.float32)
        self.tracked_counts = np.zeros((self.n_frames, 2), dtype=np.uint16)
        self.collective_speed = np.full((self.n_frames, 2), np.nan, dtype=np.float32)
        self.ball_speed = np.full(self.n_frames, np.nan, dtype=np.float32)
        self._lag = max(1, round(self.fps))
        self._ring = np.full((self._lag + 1, len(sides), 2), np.nan, dtype=np.float32)
        self._team_run = np.zeros(2, dtype=np.int32)
        self._motion_stride = max(1, round(self.fps / 5))
        self._last_collective = np.full(2, np.nan, dtype=np.float32)
        self._ball_steps = deque(maxlen=max(1, round(0.4 * self.fps)))
        self._previous_ball = None
        self._previous_period = None
        self._next = 0
        self._finished = False

    @property
    def ring_bytes(self):
        """Bounded player-position storage, excluding output feature arrays."""
        return self._ring.nbytes

    def _reset_motion(self):
        self._ring.fill(np.nan)
        self._team_run.fill(0)
        self._last_collective.fill(np.nan)
        self._ball_steps.clear()
        self._previous_ball = None

    def push(self, index, positions_m, ball_xy_m, period_id=None):
        if self._finished:
            raise ValueError("Accumulator was already finished")
        if isinstance(index, bool) or int(index) != index or index != self._next:
            raise ValueError("Frames must be pushed once in contiguous order from zero")
        index = int(index)
        if index >= self.n_frames:
            raise ValueError("Too many frames")
        positions = np.asarray(positions_m, dtype=np.float64)
        ball = np.asarray(ball_xy_m, dtype=np.float64)
        if positions.shape != (len(self.sides), 2) or ball.shape != (2,):
            raise ValueError("Unexpected position shape")
        if np.isinf(positions).any() or np.isinf(ball).any():
            raise ValueError("Infinite coordinates are invalid")
        max_float = np.finfo(np.float32).max
        if (np.abs(positions) > max_float).any() or (np.abs(ball) > max_float).any():
            raise ValueError("Coordinates exceed float32 storage range")
        period = int(self.period_id[index])
        if period_id is not None:
            if isinstance(period_id, bool) or period_id not in (0, 1, 2, 3, 4):
                raise ValueError("period_id must be 0 or football period 1..4")
            if self._blocks_fixed and period_id != period:
                raise ValueError("period_id disagrees with supplied blocks")
            period = int(period_id)
            self.period_id[index] = period
        if period != self._previous_period:
            self._reset_motion()
        self._previous_period = period
        valid = np.isfinite(positions).all(axis=1)
        positions = positions.astype(np.float32)
        positions[~valid] = np.nan
        ball_valid = bool(np.isfinite(ball).all())
        if ball_valid:
            self.ball_xy[index] = ball
            self.ball_observed[index] = True
        for side, mask in enumerate(self._side_slots):
            points = positions[mask & valid]
            self.tracked_counts[index, side] = len(points)
            if ball_valid and len(points):
                distance = np.sqrt(((points - ball) ** 2).sum(axis=1)).min()
                if not np.isfinite(distance) or distance > max_float:
                    raise ValueError("Nearest distance exceeds finite float32 storage range")
                self.nearest[index, side] = distance
            self._team_run[side] = self._team_run[side] + 1 if len(points) >= 3 and period else 0
            if self._team_run[side] >= self._lag + 1:
                if (self._team_run[side] - self._lag - 1) % self._motion_stride == 0:
                    old = self._ring[(index - self._lag) % len(self._ring)][mask]
                    old = old[np.isfinite(old).all(axis=1)]
                    # Weak motion context is sampled at 5Hz then held causally.
                    # Small per-team matrix; no full-frame pairwise tensor exists.
                    squared = ((points[:, None, :] - old[None, :, :]) ** 2).sum(axis=2)
                    displacement = 0.5 * (np.median(np.sqrt(squared.min(axis=1))) +
                                          np.median(np.sqrt(squared.min(axis=0))))
                    speed = displacement * self.fps / self._lag
                    self._last_collective[side] = speed if speed <= 12.0 else np.nan
                self.collective_speed[index, side] = self._last_collective[side]
            else:
                self._last_collective[side] = np.nan
        self._ring[index % len(self._ring)] = positions
        if period and ball_valid:
            if self._previous_ball is not None:
                speed = float(np.linalg.norm(ball - self._previous_ball) * self.fps)
                if speed <= 60.0:
                    self._ball_steps.append(speed)
                    if len(self._ball_steps) == self._ball_steps.maxlen:
                        self.ball_speed[index] = np.median(self._ball_steps)
                else:
                    # Retain the finite observation, but break its motion chain.
                    self._ball_steps.clear()
            self._previous_ball = ball.copy()
        else:
            self._ball_steps.clear()
            self._previous_ball = None
        self._next += 1

    def finish(self):
        if self._next != self.n_frames:
            raise ValueError("Incomplete frame sequence")
        self._finished = True
        return FeatureSet(
            fps=self.fps, pitch=self.pitch, period_id=self.period_id,
            ball_xy=self.ball_xy, ball_observed=self.ball_observed,
            nearest=self.nearest, tracked_counts=self.tracked_counts,
            collective_speed=self.collective_speed, ball_speed=self.ball_speed,
            metadata={
                "feature_version": "streaming-v1",
                "slots": len(self.sides),
                "player_ring_bytes": self.ring_bytes,
                "collective_lag_frames": self._lag,
                "collective_sample_stride_frames": self._motion_stride,
                "collective_resampling": "causal hold, reset immediately on insufficient observations",
                "collective_motion": "symmetric median nearest-set displacement; anonymous slots",
                "ball_speed_window_frames": self._ball_steps.maxlen,
                "ball_speed_method": "median adjacent speed; uninterrupted observations only",
                "ball_jump_limit_m_s": 60.0,
                "collective_speed_limit_m_s": 12.0,
                "exported_speeds_used": False,
            },
        )


def _name(node):
    return node.tag.rsplit("}", 1)[-1]


def _all(root, tag):
    return [node for node in root.iter() if _name(node) == tag]


def _text(node, tag):
    values = [child.text.strip() for child in node if _name(child) == tag and child.text]
    if len(values) != 1:
        raise ValueError(f"Metadata requires one {tag}")
    return values[0]


def _unique(nodes, key, kind):
    result = {}
    for node in nodes:
        value = node.get(key)
        if not value or value in result:
            raise ValueError(f"Missing or duplicate {kind} identifier")
        result[value] = node
    return result


def _metadata(meta_path, n_frames, fps):
    """Validate reference order and side/channel declarations without raw records."""
    root = ET.parse(meta_path).getroot()
    teams = _unique(_all(root, "Team"), "id", "team")
    scores = _all(root, "Score")
    if len(teams) != 2 or len(scores) != 1:
        raise ValueError("Metadata requires exactly two teams and one explicit home/away Score")
    side_ids = [scores[0].get("idLocalTeam"), scores[0].get("idVisitingTeam")]
    if len(set(side_ids)) != 2 or set(side_ids) != set(teams):
        raise ValueError("Ambiguous home/away team identifiers")
    players = _unique(_all(root, "Player"), "id", "player slot")
    if not players or any(p.get("teamId") not in teams for p in players.values()):
        raise ValueError("Every player slot must reference a known team")
    rates = _all(root, "FrameRate")
    if len(rates) != 1 or not np.isclose(float(rates[0].text), fps, rtol=0, atol=1e-6):
        raise ValueError("Frame rate disagrees with metadata")
    channels = _unique(_all(root, "Channel"), "id", "channel")
    roles = {}
    for channel_id, channel in channels.items():
        name, unit = _text(channel, "Name").lower(), _text(channel, "Unit").lower()
        if name in ("position_x", "position_y") and unit == "normalized":
            roles[channel_id] = name[-1]
        elif name in ("speed_kph", "speed", "speed_mps") and unit in ("kph", "m/s", "mps"):
            roles[channel_id] = "s"
        else:
            raise ValueError("Unsupported channel name or coordinate unit")
    links = _unique(_all(root, "PlayerChannel"), "id", "player channel")
    for link in links.values():
        if link.get("playerId") not in players or link.get("channelId") not in roles:
            raise ValueError("Invalid player-channel reference")
    specifications = _all(root, "DataFormatSpecification")
    if len(specifications) != 1:
        raise ValueError("Exactly one full-timeline data specification is required")
    spec = specifications[0]
    if spec.get("separator") != ":" or spec.get("startFrame") != "1" or spec.get("endFrame") != str(n_frames):
        raise ValueError("Unsupported data separators or declared frame range")
    sections = list(spec)
    if len(sections) != 3 or _name(sections[0]) != "StringRegister" or sections[0].get("name") != "frameCount":
        raise ValueError("Unsupported raw data sections")
    player_section, ball_section = sections[1:]
    if _name(player_section) != "SplitRegister" or player_section.get("separator") != ";":
        raise ValueError("Unsupported player separator")
    if _name(ball_section) != "SplitRegister" or ball_section.get("separator") != ",":
        raise ValueError("Unsupported ball separator")
    slot_ids, indices = [], []
    for group in player_section:
        if _name(group) != "SplitRegister" or group.get("separator") != "," or len(group) != 3:
            raise ValueError("Each slot requires exactly three channels")
        group_roles, player_ids = [], []
        for ref in group:
            if _name(ref) != "PlayerChannelRef" or ref.get("playerChannelId") not in links:
                raise ValueError("Invalid ordered player-channel reference")
            link = links[ref.get("playerChannelId")]
            player_ids.append(link.get("playerId"))
            group_roles.append(roles[link.get("channelId")])
        if len(set(player_ids)) != 1 or set(group_roles) != {"x", "y", "s"}:
            raise ValueError("Each slot must contain x/y/s of a single player slot")
        slot_ids.append(player_ids[0])
        indices.append((group_roles.index("x"), group_roles.index("y")))
    if len(slot_ids) != len(players) or len(set(slot_ids)) != len(slot_ids) or set(slot_ids) != set(players):
        raise ValueError("Ordered slots must reference each declared player exactly once")
    ball_roles = []
    for ref in ball_section:
        if _name(ref) != "BallChannelRef" or ref.get("channelId") not in roles:
            raise ValueError("Invalid ball-channel reference")
        ball_roles.append(roles[ref.get("channelId")])
    if len(ball_roles) != 3 or set(ball_roles) != {"x", "y", "s"}:
        raise ValueError("Ball requires exactly x/y/s channels")
    sides = [side_ids.index(players[slot].get("teamId")) for slot in slot_ids]
    return sides, np.asarray(indices), (ball_roles.index("x"), ball_roles.index("y"))


def _numbers(section, expected):
    # NumPy 2.4 raises on unmatched text; warnings-as-errors preserves the strict
    # behavior on earlier compatible NumPy releases as well.
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        try:
            values = np.fromstring(section, sep=",", dtype=np.float64)
        except (ValueError, DeprecationWarning) as exc:
            raise ValueError("Malformed numeric tracking fields") from exc
    if len(values) != expected or np.isinf(values).any():
        raise ValueError("Invalid channel count or infinite tracking value")
    return values


def load_atd(meta_path, raw_path, n_frames, fps=25, pitch=(105.3, 68), blocks=None):
    """Strict streaming ATD reader; returns features, never a frame/slot tensor.

    Frame IDs must be 1..n_frames in file order. Error messages deliberately do
    not include supplied records. Coordinate values can lie outside [0,1], since
    boundary excursions are useful evidence. NaN denotes missing observations.
    """
    sides, xy_indices, ball_indices = _metadata(meta_path, n_frames, fps)
    accumulator = FeatureAccumulator(n_frames, sides, fps, pitch, blocks)
    scale = np.asarray(pitch, dtype=np.float64)
    slot_indices = np.arange(len(sides))[:, None]
    count = 0
    with Path(raw_path).open("r", encoding="utf-8-sig") as handle:
        for index, line in enumerate(handle):
            parts = line.strip().split(":")
            if len(parts) != 3 or not parts[0].isascii() or not parts[0].isdigit():
                raise ValueError("Malformed tracking record structure")
            if index >= n_frames or int(parts[0]) != index + 1:
                raise ValueError("Tracking IDs must be contiguous 1..n_frames")
            groups = parts[1].split(";")
            if len(groups) != len(sides) or any(g.count(",") != 2 or any(not x.strip() for x in g.split(",")) for g in groups):
                raise ValueError("Invalid player slot/channel count")
            if parts[2].count(",") != 2 or any(not x.strip() for x in parts[2].split(",")):
                raise ValueError("Invalid ball channel count")
            players = _numbers(parts[1].replace(";", ","), len(sides) * 3).reshape(-1, 3)
            ball = _numbers(parts[2], 3)
            positions_m = players[slot_indices, xy_indices] * scale
            ball_m = ball[list(ball_indices)] * scale
            accumulator.push(index, positions_m, ball_m)
            count += 1
    if count != n_frames:
        raise ValueError("Incomplete tracking record sequence")
    features = accumulator.finish()
    features.metadata.update({"input_format": "metrica-epts-normalized", "raw_records": count})
    return features
