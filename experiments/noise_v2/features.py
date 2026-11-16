"""Gap-safe local-linear ball motion for the isolated noise-v2 experiment.

This is an offline coordinate-trend estimator. It smooths turning motion and
does not identify tracking error or make the residual speed magnitude unbiased.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from possession_model.evidence import reliable_ball_mask
from possession_model.schema import FeatureSet


def robustify_ball_motion(features: FeatureSet) -> FeatureSet:
    """Return a new FeatureSet with only ball_speed and metadata replaced.

    A fixed nominal 1.2 s odd window fits x/y linear slopes before computing
    their magnitude. Full windows must lie inside one uninterrupted reliable
    same-period run. At 25 Hz the 31-point window has 15 unknown edge frames
    on each side. All original arrays other than ball_speed are shared without
    mutation; metadata is shallow-copied. NumPy only, O(N) for fixed fps/window.
    """
    fps = float(features.fps)
    if not np.isfinite(fps) or fps <= 0:
        raise ValueError("fps must be finite and positive")
    n = features.n_frames
    xy = np.asarray(features.ball_xy, dtype=np.float64)
    observed = np.asarray(features.ball_observed, dtype=bool)
    periods = np.asarray(features.period_id)
    if xy.shape != (n, 2) or observed.shape != (n,) or periods.shape != (n,):
        raise ValueError("ball positions, observations and periods must align")
    half = max(1, round(.6 * fps))
    window = 2 * half + 1
    times = np.arange(-half, half+1, dtype=np.float64) / fps
    weights = times / np.dot(times, times)
    valid = (observed & np.isfinite(xy).all(axis=1) & (periods > 0)
             & reliable_ball_mask(features))
    speed = np.full(n, np.nan, dtype=np.float32)
    # Split on both missing observations and period changes. No dense N x W
    # windows, interpolation, adjacent-speed smoothing or cross-gap slope.
    previous = np.r_[False, valid[:-1] & (periods[:-1] == periods[1:])]
    following = np.r_[valid[1:] & (periods[:-1] == periods[1:]), False]
    starts = np.flatnonzero(valid & ~previous)
    stops = np.flatnonzero(valid & ~following) + 1
    for start, stop in zip(starts, stops):
        if stop-start < window:
            continue
        part = xy[start:stop]
        vx = np.convolve(part[:, 0], weights[::-1], mode="valid")
        vy = np.convolve(part[:, 1], weights[::-1], mode="valid")
        motion = np.hypot(vx, vy)
        motion[~np.isfinite(motion) | (motion > 60.)] = np.nan
        speed[start+half:stop-half] = motion
    metadata = dict(features.metadata)
    metadata.update({
        "ball_speed_method": "centred full-window local-linear x/y slope magnitude",
        "ball_speed_window_frames": window,
        "ball_motion_transform": "noise-v2-local-linear-1.2s",
        "ball_motion_nominal_window_seconds": 1.2,
        "ball_motion_window_frames": window,
        "ball_motion_window_span_seconds": (window-1)/fps,
        "ball_motion_method": "magnitude of centred full-window x/y linear slopes",
        "ball_motion_observation_policy": "reliable same-period runs; no gap interpolation",
        "ball_motion_jump_limit_m_s": 60.,
        "ball_motion_offline": True,
    })
    return replace(features, ball_speed=speed, metadata=metadata)
