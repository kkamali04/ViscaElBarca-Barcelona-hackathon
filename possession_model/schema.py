"""Shared feature contract; all positions and distances are in metres."""
from dataclasses import dataclass, field
import numpy as np


@dataclass
class FeatureSet:
    fps: float
    pitch: tuple
    period_id: np.ndarray
    ball_xy: np.ndarray
    ball_observed: np.ndarray
    nearest: np.ndarray
    tracked_counts: np.ndarray
    collective_speed: np.ndarray
    ball_speed: np.ndarray
    metadata: dict = field(default_factory=dict)

    @property
    def n_frames(self):
        return len(self.period_id)

    @property
    def array_bytes(self):
        return sum(x.nbytes for x in (
            self.period_id, self.ball_xy, self.ball_observed, self.nearest,
            self.tracked_counts, self.collective_speed, self.ball_speed))
