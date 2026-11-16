"""Small, period-safe features and a transparent non-learned reference emitter.

No labels, absolute match timestamps, club identity, or exported speed channels
enter these features. Centred windows use future *observations*, allowed offline.
"""
from __future__ import annotations

import numpy as np


def period_slices(period_id):
    periods = np.asarray(period_id)
    if periods.ndim != 1:
        raise ValueError("period_id must be one-dimensional")
    if periods.dtype.kind not in "iu":
        raise ValueError("period_id must contain integer identifiers")
    if len(periods) == 0:
        return []
    starts = np.r_[0, np.flatnonzero(periods[1:] != periods[:-1]) + 1]
    stops = np.r_[starts[1:], len(periods)]
    return [(int(a), int(b)) for a, b in zip(starts, stops) if periods[a] > 0]


def rolling_mean(values, period_id, radius, min_count=1):
    """Finite-only centred means, never crossing a period/gap. O(N)."""
    x = np.asarray(values, dtype=np.float32)
    out = np.full(x.shape, np.nan, dtype=np.float32)
    for start, stop in period_slices(period_id):
        part = x[start:stop]
        ok = np.isfinite(part)
        sums = np.r_[0., np.cumsum(np.where(ok, part, 0), dtype=np.float64)]
        counts = np.r_[0, np.cumsum(ok, dtype=np.int32)]
        i = np.arange(stop - start)
        lo, hi = np.maximum(0, i-radius), np.minimum(len(part), i+radius+1)
        count = counts[hi] - counts[lo]
        np.divide(sums[hi]-sums[lo], count, out=out[start:stop],
                  where=count >= min_count)
    return out


def _finite_side_mean(x):
    finite = np.isfinite(x)
    count = finite.sum(axis=1)
    result = np.full(len(x), np.nan, dtype=np.float32)
    np.divide(np.where(finite, x, 0).sum(axis=1), count, out=result, where=count > 0)
    return result


def reliable_ball_mask(features):
    """Suppress geometry around impossible adjacent jumps, not just its speed.

    Either endpoint can be the tracker error. A 0.2-second guard on both sides
    avoids assigning full control evidence to a teleport, without rejecting
    reacquisition after a genuine observation gap or a different period.
    """
    f = features
    observed = np.asarray(f.ball_observed, dtype=bool)
    jumps = np.zeros(f.n_frames, np.float32)
    if f.n_frames > 1:
        adjacent = observed[1:] & observed[:-1] & (f.period_id[1:] == f.period_id[:-1])
        speed = np.linalg.norm(np.diff(f.ball_xy, axis=0), axis=1)*f.fps
        jumps[1:] = adjacent & (speed > 60.)
    guarded = rolling_mean(jumps, f.period_id, max(1, round(.2*f.fps))) > 0
    return observed & ~guarded


def feature_matrix(features):
    """Return float32 features and ordered names; NaN remains unknown.

    Team-specific features always occur as adjacent H/A pairs. The training
    augmentation swaps these pairs and target H/A together, discouraging side bias.
    """
    f = features
    n = f.n_frames
    if f.nearest.shape != (n, 2) or f.collective_speed.shape != (n, 2):
        raise ValueError("nearest and collective_speed must have shape (N, 2)")
    p = f.period_id
    columns, names, pairs = [], [], []
    def add(name, values):
        names.append(name)
        columns.append(np.asarray(values, dtype=np.float32))
    def pair(name, values):
        pairs.append((len(names), len(names)+1))
        add(name+"_H", values[:, 0])
        add(name+"_A", values[:, 1])
    def smooth(x, seconds):
        return rolling_mean(x, p, int(round(seconds * f.fps / 2)))
    observed = reliable_ball_mask(f)
    distance = np.minimum(f.nearest, 30)
    distance[~observed] = np.nan
    pair("distance_m", distance)
    pair("players_visible", f.tracked_counts)
    pair("set_motion_mps", f.collective_speed)
    close = np.exp(-np.square(distance / 2.5)).astype(np.float32)
    # Unknown team/ball evidence remains NaN, rather than inventing home control.
    pair("close", close)
    for seconds in (.6, 3.):
        pair("close_mean_"+str(seconds), np.column_stack([
            smooth(close[:, side], seconds) for side in range(2)]))
    add("ball_speed_mps", np.minimum(f.ball_speed, 40))
    speed = _finite_side_mean(f.collective_speed)
    add("set_motion_mean_1s", smooth(speed, 1))
    add("set_motion_mean_4s", smooth(speed, 4))
    add("ball_observed", observed)
    add("ball_observed_mean_1s", smooth(observed, 1))
    add("ball_observed_mean_4s", smooth(observed, 4))
    still = np.where(np.isfinite(f.ball_speed), f.ball_speed < .35, np.nan)
    add("ball_still_fraction_2s", smooth(still, 2))
    bx, by = f.ball_xy.T
    boundary = np.minimum.reduce([bx, f.pitch[0]-bx, by, f.pitch[1]-by])
    boundary[~observed] = np.nan
    add("boundary_distance_m", np.clip(boundary, -10, 30))
    outside = np.where(observed, boundary < -.3, np.nan)
    add("outside_fraction_1s", smooth(outside, 1))
    # Time since observation describes missingness only, independent of labels.
    gap = np.zeros(n, dtype=np.float32)
    for start, stop in period_slices(p):
        i = np.arange(stop-start)
        last = np.maximum.accumulate(np.where(observed[start:stop], i, -1))
        gap[start:stop] = np.minimum((i-last)/f.fps, 30)
    add("ball_gap_seconds", gap)
    matrix = np.column_stack(columns).astype(np.float32, copy=False)
    matrix[p <= 0] = np.nan
    return matrix, names, pairs


def heuristic_scores(features):
    """Uncalibrated evidence; a missing ball alone adds no dead-ball support."""
    f = features
    d = f.nearest.copy()
    observed = reliable_ball_mask(f)
    d[~observed] = np.nan
    both = np.isfinite(d).all(axis=1)
    minimum = np.minimum(d[:, 0], d[:, 1])
    margin = np.zeros(f.n_frames, np.float32)
    margin[both] = np.tanh((d[both, 1]-d[both, 0])/2)
    confidence = np.where(both, np.exp(-np.square(minimum/5)), 0)
    confidence *= np.where(np.isfinite(f.ball_speed),
                           np.clip(1-f.ball_speed/30, .15, 1), 1)
    control = margin * confidence
    scores = np.zeros((f.n_frames, 3), np.float32)
    scores[:, 0] = control
    scores[:, 1] = -control
    moving = rolling_mean(_finite_side_mean(f.collective_speed), f.period_id,
                          int(f.fps))
    still = rolling_mean(np.where(np.isfinite(f.ball_speed), f.ball_speed < .35, np.nan),
                         f.period_id, int(f.fps))
    bx, by = f.ball_xy.T
    boundary = np.minimum.reduce([bx, f.pitch[0]-bx, by, f.pitch[1]-by])
    outside = rolling_mean(np.where(observed, boundary < -.3, np.nan),
                           f.period_id, int(f.fps/2))
    # Dead requires motion/context beyond invisibility or a stationary ball alone.
    stationary_stop = np.where(np.isfinite(moving) & np.isfinite(still),
                              np.clip((.65-moving)/.65, 0, 1)*still, 0)
    boundary_stop = np.nan_to_num(outside, nan=0) * np.where(
        np.isfinite(moving), np.clip((1.5-moving)/1.5, 0, 1), 0)
    scores[:, 2] = 1.4*np.maximum(stationary_stop, boundary_stop)
    # Strong observed control favours a live state; nothing is inferred in full gaps.
    scores[:, 2] -= .5*confidence
    return scores
