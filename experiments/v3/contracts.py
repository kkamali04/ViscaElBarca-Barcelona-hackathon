"""Frozen shared v3 types. Arrays are validated, owned, and read-only.

This module imports no study control, parser, model implementation, or training
package. Postponed annotations keep release-only imports independent of sklearn.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from possession_model.trees import TreeModel
    from .boundary import NumericHead
    from .cache import ReadLease

Role = Literal["train", "selection", "test"]


_BOUNDARY_NAMES = tuple(name for prefix in ("w020", "w060") for name in (
    *(f"{prefix}_pre_{base}" for base in ("min_distance_m", "abs_margin_m", "ball_speed_mps",
                                         "set_motion_mps", "boundary_distance_m")),
    *(f"{prefix}_post_{base}" for base in ("min_distance_m", "abs_margin_m", "ball_speed_mps",
                                          "set_motion_mps", "boundary_distance_m")),
    f"{prefix}_margin_product_scaled", f"{prefix}_margin_change_scaled",
    f"{prefix}_reliable_fraction_pre", f"{prefix}_reliable_fraction_post"))


def _array(value, dtype, shape, name):
    if not isinstance(value, np.ndarray) or value.dtype != np.dtype(dtype):
        raise ValueError(f"{name}: exact dtype required")
    if value.ndim != len(shape) or any(s is not None and s != n for s, n in zip(shape, value.shape)):
        raise ValueError(f"{name}: shape mismatch")
    if value.flags.c_contiguous and value.flags.owndata and not value.flags.writeable:
        return value
    result = np.array(value, copy=True, order="C")
    result.flags.writeable = False
    return result


@dataclass(frozen=True)
class ReleaseAccess:
    release_digest: str
    source_manifest_digest: str
    input_kind: Literal["challenge_observations", "synthetic_observations"]
    source_files: tuple[tuple[str, int, str], ...]
    runtime_digest: str
    policy_digest: str
    cache_root: Path
    process_id: int
    process_creation_time: str


@dataclass(frozen=True)
class InferenceContext:
    access: ReleaseAccess
    policy: InferencePolicy
    source_leases: tuple[ReadLease, ...]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        for lease in reversed(self.source_leases):
            lease.__exit__(*exc)


@dataclass(frozen=True)
class PeriodOrigin:
    period_id: int
    source_frame_id: int
    utc_ns: int

    def __post_init__(self):
        if any(type(value) is not int for value in (self.period_id, self.source_frame_id, self.utc_ns)):
            raise ValueError("period origin fields require exact integers")


@dataclass(frozen=True)
class ObservationBatch:
    frame_id: NDArray[np.int64]
    source_frame_id: NDArray[np.int64]
    period_id: NDArray[np.int16]
    positions: NDArray[np.float32]
    ball_xy: NDArray[np.float32]
    team_of_slot: NDArray[np.int8]
    slot_ids: tuple[str, ...]
    slot_ids_digest: str
    source_time_frame_index: NDArray[np.int64]
    source_time_slot: NDArray[np.int32]
    source_time_utc_ns: NDArray[np.int64]
    period_origins: tuple[PeriodOrigin, ...]
    fps: float
    pitch: tuple[float, float]
    fixture_id: str
    source_digest: str

    def __post_init__(self):
        if (type(self.slot_ids) is not tuple or type(self.pitch) is not tuple
                or type(self.period_origins) is not tuple):
            raise ValueError("observation metadata requires immutable tuples")
        if (any(type(origin) is not PeriodOrigin for origin in self.period_origins)
                or len(self.pitch) != 2 or any(type(value) not in (int, float) for value in self.pitch)
                or type(self.fps) not in (int, float)):
            raise ValueError("invalid typed observation metadata")
        if type(self.fixture_id) is not str or not self.fixture_id:
            raise ValueError("fixture identity requires a nonempty string")
        for digest in (self.slot_ids_digest, self.source_digest):
            if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("observation identities require SHA256 hex strings")
        n = len(self.frame_id)
        s = len(self.slot_ids)
        r = len(self.source_time_frame_index)
        for name, dtype, shape in (
            ("frame_id", np.int64, (n,)), ("source_frame_id", np.int64, (n,)),
            ("period_id", np.int16, (n,)), ("positions", np.float32, (n, s, 2)),
            ("ball_xy", np.float32, (n, 2)), ("team_of_slot", np.int8, (s,)),
            ("source_time_frame_index", np.int64, (r,)),
            ("source_time_slot", np.int32, (r,)), ("source_time_utc_ns", np.int64, (r,))):
            object.__setattr__(self, name, _array(getattr(self, name), dtype, shape, name))
        if not np.array_equal(self.frame_id, np.arange(n, dtype=np.int64)):
            raise ValueError("frame_id must be dense zero-based")
        if not np.isfinite(self.fps) or abs(self.fps - 25.) > 1e-6:
            raise ValueError("fps must be 25Hz")
        if len(self.pitch) != 2 or any(not np.isfinite(x) or x <= 0 for x in self.pitch):
            raise ValueError("pitch must be finite positive metres")
        for name in ("positions", "ball_xy"):
            a = getattr(self, name)
            if np.isinf(a).any() or np.any(np.isfinite(a).any(axis=-1) != np.isfinite(a).all(axis=-1)):
                raise ValueError("infinity or partial coordinate pair")
        if any(type(x) is not str or not x for x in self.slot_ids) or len(set(self.slot_ids)) != s:
            raise ValueError("unique nonempty slot IDs required")
        if not np.isin(self.team_of_slot, [0, 1]).all():
            raise ValueError("invalid team slot")
        order = sorted(range(s), key=lambda i: (int(self.team_of_slot[i]), self.slot_ids[i].encode("utf-8")))
        if order != list(range(s)):
            raise ValueError("noncanonical slot order")
        expected = hashlib.sha256(json.dumps(list(self.slot_ids), ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        if self.slot_ids_digest != expected:
            raise ValueError("slot digest mismatch")
        if r and (np.any(self.source_time_frame_index < 0) or np.any(self.source_time_frame_index >= n)
                  or np.any(self.source_time_slot < 0) or np.any(self.source_time_slot > s)):
            raise ValueError("invalid timestamp indices")
        previous_frame = previous_slot = None
        for start in range(0, r, 4096):
            frames = self.source_time_frame_index[start:start + 4096]
            slots = self.source_time_slot[start:start + 4096]
            if start and (frames[0] < previous_frame or
                          (frames[0] == previous_frame and slots[0] <= previous_slot)):
                raise ValueError("timestamp rows must be unique and sorted")
            if (np.any(frames[1:] < frames[:-1]) or
                    np.any((frames[1:] == frames[:-1]) & (slots[1:] <= slots[:-1]))):
                raise ValueError("timestamp rows must be unique and sorted")
            previous_frame, previous_slot = frames[-1], slots[-1]


@dataclass(frozen=True)
class InferencePolicy:
    kind: Literal["external", "challenge"]
    forced_dead: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class CandidateConfig:
    candidate_id: str
    alpha: float
    support: Literal["none", "learned", "flattened_valid_run_mean"]
    transition_seconds: float


@dataclass(frozen=True)
class ModelBundle:
    emitter: TreeModel
    head: NumericHead | None
    manifest_digest: str


@dataclass(frozen=True)
class TargetBatch:
    labels: NDArray[np.int8]
    observation_digest: str

    def __post_init__(self):
        labels = _array(self.labels, np.int8, (None,), "labels")
        if labels is self.labels:
            labels = np.array(labels, copy=True, order="C")
            labels.flags.writeable = False
        if not np.isin(labels, [-1, 0, 1, 2]).all():
            raise ValueError("invalid target code")
        object.__setattr__(self, "labels", labels)


@dataclass(frozen=True)
class BoundaryFeatures:
    values: NDArray[np.float32]
    names: tuple[str, ...]
    valid: NDArray[np.bool_]

    def __post_init__(self):
        if (type(self.names) is not tuple or any(type(name) is not str for name in self.names)
                or self.names != _BOUNDARY_NAMES):
            raise ValueError("boundary names require the exact canonical28 tuple")
        values = _array(self.values, np.float32, (None, 28), "boundary values")
        if np.isinf(values).any():
            raise ValueError("invalid boundary features")
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "valid", _array(self.valid, np.bool_, (len(values), 2), "boundary validity"))


@dataclass(frozen=True)
class AccessCapability:
    study_digest: str
    attempt_id: str
    role: Role
    fixture_ids: tuple[str, ...]
    process_id: int
    process_creation_time: str
    reservation_event_digest: str


CacheAuthority = AccessCapability | ReleaseAccess
