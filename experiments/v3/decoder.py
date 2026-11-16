"""Exact three-state, incoming-edge modulation in the isolated v3 closure.

The accepted decoder's objective and canonical tie convention are preserved.
Unlike the accepted implementation, every allowed finite arithmetic alternative
is checked for both signs of overflow, even if that alternative loses.
"""
from __future__ import annotations

import math
import numpy as np
from numpy.typing import NDArray


def decode_change_aware(scores: np.ndarray, period_id: np.ndarray,
                        base_costs: np.ndarray, q: np.ndarray, alpha: float,
                        initial_state: int | None = None) -> NDArray[np.int8]:
    evidence = np.asarray(scores)
    periods = np.asarray(period_id)
    support = np.asarray(q)
    if evidence.ndim != 2 or evidence.shape[1] != 3 or evidence.dtype.kind not in "fiu":
        raise ValueError("scores must be real numeric (N,3)")
    if np.isnan(evidence).any() or np.isposinf(evidence).any():
        raise ValueError("scores require finite values or explicit -inf")
    n = len(evidence)
    if periods.shape != (n,) or periods.dtype.kind not in "iu":
        raise ValueError("period_id requires an aligned integer vector")
    if support.shape != (n, 2) or support.dtype.kind not in "fiu":
        raise ValueError("q requires real numeric (N,2)")
    if not np.isfinite(support).all() or (support < 0).any() or (support > 1).any():
        raise ValueError("q requires finite support in [0,1]")
    if (isinstance(alpha, (bool, np.bool_)) or not np.isscalar(alpha)
            or not isinstance(alpha, (float, int, np.floating, np.integer))):
        raise ValueError("alpha requires a real scalar in [0,1)")
    alpha = float(alpha)
    if not math.isfinite(alpha) or not 0 <= alpha < 1:
        raise ValueError("alpha requires a finite scalar in [0,1)")
    raw_costs = np.asarray(base_costs)
    if raw_costs.shape != (3, 3) or raw_costs.dtype.kind not in "fiu":
        raise ValueError("base_costs requires a real (3,3) matrix")
    costs = raw_costs.astype(np.float64, copy=False)
    if np.isnan(costs).any() or (costs < 0).any() or (np.diag(costs) != 0).any():
        raise ValueError("base_costs requires nonnegative entries and exact zero diagonal")
    if initial_state is not None:
        if (isinstance(initial_state, (bool, np.bool_))
                or not isinstance(initial_state, (int, np.integer)) or not 0 <= initial_state < 3):
            raise ValueError("initial_state requires None or integer0/1/2")
        initial_state = int(initial_state)

    result = np.full(n, -1, dtype=np.int8)
    pointers = np.full((n, 3), 255, dtype=np.uint8)
    cost_values = tuple(tuple(float(v) for v in row) for row in costs)
    start = 0
    while start < n:
        if periods[start] <= 0:
            start += 1
            continue
        stop = start + 1
        while stop < n and periods[stop] == periods[start]:
            stop += 1
        running = [float(v) for v in evidence[start]]
        if initial_state is not None:
            running = [v if s == initial_state else -math.inf for s, v in enumerate(running)]
        if all(v == -math.inf for v in running):
            raise ValueError("No feasible initial state in positive run")
        changes = [0, 0, 0]
        for t in range(start + 1, stop):
            factors = (1. - alpha * float(support[t, 0]),
                       1. - alpha * float(support[t, 1]))
            next_scores = [-math.inf] * 3
            next_changes = [n + 1] * 3
            for dest in range(3):
                emission = float(evidence[t, dest])
                if emission == -math.inf:
                    continue
                best = -math.inf
                best_changes = n + 1
                best_is_change = False
                best_source = 255
                for source in range(3):
                    previous = running[source]
                    base = cost_values[source][dest]
                    if previous == -math.inf or base == math.inf:
                        continue
                    is_change = source != dest
                    cost = 0. if not is_change else base * factors[0 if source < 2 and dest < 2 else 1]
                    candidate = previous - cost
                    if not math.isfinite(candidate) or not math.isfinite(candidate + emission):
                        raise ValueError("Score arithmetic overflow in allowed finite alternative")
                    count = changes[source] + is_change
                    # Compare before adding common emission, as the accepted
                    # decoder does. Ascending sources resolve the final tie.
                    if (candidate > best or (candidate == best and
                            (count < best_changes or
                             (count == best_changes and is_change and not best_is_change)))):
                        best, best_changes = candidate, count
                        best_is_change, best_source = is_change, source
                if best_source != 255:
                    next_scores[dest] = best + emission
                    next_changes[dest] = best_changes
                    pointers[t, dest] = best_source
            if all(v == -math.inf for v in next_scores):
                raise ValueError("No feasible path in positive run")
            running, changes = next_scores, next_changes
        state = max(range(3), key=lambda s: (running[s], -changes[s], -s))
        result[stop - 1] = state
        for t in range(stop - 1, start, -1):
            result[t - 1] = pointers[t, result[t]]
        start = stop
    return result
