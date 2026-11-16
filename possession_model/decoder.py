"""Exact three-state penalised decoding without a full score history.

Scores are heuristic evidence, not calibrated probabilities.  The primary
objective is the sum of frame scores minus transition costs.  Equal objectives
prefer fewer transitions, then a transition at the current frame over an older
one, then the lower source-state index.  The second rule places an otherwise
unidentifiable H -> neutral gap -> A boundary at the first A evidence rather
than at the beginning of the gap.  This is a convention, not recovered evidence.
"""
from __future__ import annotations

import numpy as np


_NEG_INF = float("-inf")
_UNREACHABLE = 255


def decode_scores(scores, period_id, transition_costs, initial_state=None):
    """Return int8 H/A/D codes (0/1/2), or -1 outside positive periods.

    Each contiguous run with the same positive ``period_id`` is independent.
    ``initial_state`` optionally fixes the first state of *each* such run; by
    default all three starting states are allowed.  No first-frame dead-ball
    assumption is made.  Known frame constraints belong in ``scores`` as -inf
    for forbidden states.

    ``scores`` has shape (N, 3), contains finite values or -inf, and is maximised.
    ``transition_costs`` has shape (3, 3), nonnegative entries and zero diagonal;
    +inf off the diagonal forbids a transition.  NaN and +inf frame scores are
    rejected, including outside-period rows.  An impossible active frame raises
    ValueError instead of inventing a forbidden path.

    Time is O(N * 9).  Internal persistent numeric storage is N * 3 uint8
    backpointers, N int8 output codes, a 3 * 3 float64 cost matrix, and O(3)
    running scores/counts.  The input is never copied to a wider float dtype.
    This storage arithmetic excludes validation temporaries and process RSS.
    """
    evidence = np.asarray(scores)
    periods = np.asarray(period_id)
    if evidence.ndim != 2 or evidence.shape[1] != 3:
        raise ValueError("scores must have shape (N, 3)")
    if evidence.dtype.kind not in "fiu":
        raise ValueError("scores must be real numeric values")
    if np.isnan(evidence).any() or np.isposinf(evidence).any():
        raise ValueError("scores may contain finite values or -inf, not NaN/+inf")
    if periods.ndim != 1 or len(periods) != len(evidence):
        raise ValueError("period_id must be a one-dimensional array of length N")
    if periods.dtype.kind not in "iu":
        raise ValueError("period_id must contain integers")
    try:
        raw_costs = np.asarray(transition_costs)
        if raw_costs.dtype.kind not in "fiu":
            raise ValueError("not real numeric")
        costs = raw_costs.astype(np.float64, copy=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("transition_costs must be a real numeric (3, 3) matrix") from exc
    if costs.shape != (3, 3):
        raise ValueError("transition_costs must have shape (3, 3)")
    if np.isnan(costs).any() or (costs < 0).any():
        raise ValueError("transition_costs must be nonnegative and contain no NaN")
    if np.any(np.diag(costs) != 0):
        raise ValueError("transition_costs must have an exactly zero diagonal")
    if initial_state is not None:
        if (isinstance(initial_state, (bool, np.bool_))
                or not isinstance(initial_state, (int, np.integer))
                or not 0 <= initial_state < 3):
            raise ValueError("initial_state must be None or integer 0, 1, or 2")
        initial_state = int(initial_state)

    n_frames = len(evidence)
    result = np.full(n_frames, -1, dtype=np.int8)
    pointers = np.full((n_frames, 3), _UNREACHABLE, dtype=np.uint8)
    # Python scalar costs avoid allocating a candidates matrix at every frame.
    cost_values = tuple(tuple(float(v) for v in row) for row in costs)
    start = 0
    while start < n_frames:
        if periods[start] <= 0:
            start += 1
            continue
        end = start + 1
        while end < n_frames and periods[end] == periods[start]:
            end += 1

        running = [float(v) for v in evidence[start]]
        if initial_state is not None:
            running = [v if state == initial_state else _NEG_INF
                       for state, v in enumerate(running)]
        if all(value == _NEG_INF for value in running):
            raise ValueError(f"No feasible state at frame index {start} "
                             f"(period {int(periods[start])})")
        changes = [0, 0, 0]

        for frame in range(start + 1, end):
            next_scores = [_NEG_INF, _NEG_INF, _NEG_INF]
            next_changes = [n_frames + 1, n_frames + 1, n_frames + 1]
            frame_pointers = pointers[frame]
            row = evidence[frame]
            for destination in range(3):
                emission = float(row[destination])
                if emission == _NEG_INF:
                    continue
                best_score = _NEG_INF
                best_changes = n_frames + 1
                best_is_change = False
                best_source = _UNREACHABLE
                for source in range(3):
                    candidate = running[source] - cost_values[source][destination]
                    if candidate == _NEG_INF:
                        continue
                    is_change = source != destination
                    candidate_changes = changes[source] + is_change
                    if (candidate > best_score
                            or (candidate == best_score
                                and (candidate_changes < best_changes
                                     or (candidate_changes == best_changes
                                         and is_change and not best_is_change)))):
                        best_score = candidate
                        best_changes = candidate_changes
                        best_is_change = is_change
                        best_source = source
                if best_source != _UNREACHABLE:
                    next_scores[destination] = best_score + emission
                    next_changes[destination] = best_changes
                    frame_pointers[destination] = best_source
            if all(value == _NEG_INF for value in next_scores):
                raise ValueError(f"No feasible path at frame index {frame} "
                                 f"(period {int(periods[frame])})")
            if any(not np.isfinite(value) and value != _NEG_INF
                   for value in next_scores):
                raise ValueError(f"Score arithmetic overflow at frame index {frame}; "
                                 "use smaller evidence magnitudes")
            running = next_scores
            changes = next_changes

        # Canonical final ties prefer fewer transitions, then H, A, D.
        final_state = max(range(3), key=lambda s: (running[s], -changes[s], -s))
        result[end - 1] = final_state
        for frame in range(end - 1, start, -1):
            result[frame - 1] = pointers[frame, result[frame]]
        start = end
    return result
