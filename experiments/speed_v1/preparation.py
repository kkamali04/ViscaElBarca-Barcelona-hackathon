"""Ephemeral, capability-scoped reuse of the unchanged v3 feature preparation.

No fitting, output publication, persistent cache or loader other than load_match.
The registered v3 training entry point deliberately does not import this module.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, fields
import hashlib
import json
from pathlib import Path
from types import MappingProxyType

import numpy as np

from possession_model.schema import FeatureSet
from experiments.v3 import training as frozen
from experiments.v3.contracts import AccessCapability, TargetBatch
from experiments.v3.corruption import validate_observations


_FEATURE_ARRAYS = ("period_id", "ball_xy", "ball_observed", "nearest",
                   "tracked_counts", "collective_speed", "ball_speed")


@dataclass(frozen=True)
class _Prepared:
    """Private owned values; even ndarray writeability cannot be reenabled."""
    fps: float
    pitch: tuple
    arrays: tuple
    metadata: bytes
    observation_digest: str
    receipt: bytes
    retained_bytes: int

    def features(self):
        # Only this short-lived wrapper is mutable. Its buffers have bytes bases;
        # downstream frozen helpers read them and produce their own output arrays.
        return FeatureSet(fps=self.fps, pitch=self.pitch,
            metadata=json.loads(self.metadata), **dict(zip(_FEATURE_ARRAYS, self.arrays)))


def _cap_identity(cap):
    return tuple(getattr(cap, field.name) for field in fields(AccessCapability))


class TrainingPreparationSession:
    """Prepare frozen v3 strata with a session-local, byte-bounded LRU.

    ``owned_matches`` has the same adapter-owned input mapping semantics as v3's
    ``_source_strata``. It remains caller-visible so replaced/changed inputs are
    revalidated and rehashed. Cache accounting covers retained feature buffers,
    their schema/scalars, diagnostics, receipts and keys, not owned input matches,
    returned strata, transient allocations or Python allocator overhead. Statistics
    are aggregate read-only snapshots, not a process-memory measurement.

    This synchronous session is not shared between threads or capabilities.
    ``clear`` drops prepared entries; ``close`` also drops all input references.
    """

    def __init__(self, study, cap, protocol, owned_matches=None,
                 max_cache_bytes=134217728):
        if (type(cap) is not AccessCapability or cap.role != "train"
                or cap.fixture_ids != frozen.TRAIN_FIXTURES):
            raise frozen.guard.AccessError("exact train capability required")
        if type(max_cache_bytes) is not int or max_cache_bytes < 0:
            raise ValueError("nonnegative exact cache byte cap required")
        if owned_matches is not None and type(owned_matches) is not dict:
            raise ValueError("owned matches must be a dict")
        self._study = Path(study).absolute()
        self._cap = cap
        self._cap_identity = _cap_identity(cap)
        self._protocol = frozen.guard._plain(Path(protocol))
        self._protocol_digest = frozen.guard.sha256(self._protocol)
        self._owned_matches = {} if owned_matches is None else owned_matches
        self._max_cache_bytes = max_cache_bytes
        self._cache = OrderedDict()
        self._closed = False
        self._counts = dict(source_calls=0, fixture_uses=0, hits=0, misses=0,
                            preparations=0, evictions=0, skipped_retention=0,
                            retained_bytes=0, peak_retained_bytes=0)

    @property
    def stats(self):
        return MappingProxyType({**self._counts, "cache_entries": len(self._cache),
            "max_cache_bytes": self._max_cache_bytes, "closed": self._closed})

    def _assert_live(self):
        if self._closed:
            raise RuntimeError("preparation session is closed")
        if (_cap_identity(self._cap) != self._cap_identity
                or self._cap.role != "train"):
            raise frozen.guard.AccessError("session capability identity changed")
        if frozen.guard.sha256(frozen.guard._plain(self._protocol)) != self._protocol_digest:
            raise frozen.guard.IntegrityError("session protocol identity changed")

    def clear(self):
        if self._closed:
            raise RuntimeError("preparation session is closed")
        self._cache.clear()
        self._counts["retained_bytes"] = 0

    def close(self):
        if not self._closed:
            self.clear()
            self._owned_matches = None
            self._closed = True

    def __enter__(self):
        self._assert_live()
        return self

    def __exit__(self, *exc):
        self.close()

    def _prepare(self, obs, fixture, condition, original_digest, seeds):
        # Include the exact recipe and original observation schema/content, never
        # labels or target metadata. Each session already binds one capability.
        key = (self._protocol_digest, original_digest, fixture, condition,
               hashlib.sha256(frozen.guard.canonical(frozen.CONDITIONS[condition])).hexdigest())
        if key in self._cache:
            self._counts["hits"] += 1
            self._cache.move_to_end(key)
            return self._cache[key]
        self._counts["misses"] += 1
        conditioned = frozen.condition_observations(obs, frozen.CONDITIONS[condition], seeds)
        input_hash = frozen.observation_digest(conditioned)
        features = frozen.build_features(conditioned)
        receipt = frozen.condition_receipt(obs, frozen.CONDITIONS[condition], seeds)
        del conditioned
        self._counts["preparations"] += 1
        # Own every retained byte. Read-only arrays backed by immutable bytes do
        # not alias the adapter, temporary feature producer or returned strata.
        arrays = tuple(np.frombuffer(getattr(features, name).tobytes(order="C"),
                       dtype=getattr(features, name).dtype).reshape(getattr(features, name).shape)
                       for name in _FEATURE_ARRAYS)
        # Preserve the helpers' diagnostic key order as well as their values.
        metadata = json.dumps(features.metadata, ensure_ascii=False,
                              separators=(",", ":"), allow_nan=False).encode("utf-8")
        receipt_bytes = json.dumps(receipt, ensure_ascii=False,
                                   separators=(",", ":"), allow_nan=False).encode("utf-8")
        schema = frozen.guard.canonical({"key": list(key), "fps": features.fps,
            "pitch": list(features.pitch), "observation_digest": input_hash,
            "arrays": [{"name": name, "dtype": arr.dtype.str, "shape": list(arr.shape)}
                       for name, arr in zip(_FEATURE_ARRAYS, arrays)]})
        size = sum(arr.nbytes for arr in arrays) + len(metadata) + len(receipt_bytes) + len(schema)
        prepared = _Prepared(features.fps, tuple(features.pitch), arrays, metadata,
                             input_hash, receipt_bytes, size)
        self._assert_live()
        if not self._max_cache_bytes or size > self._max_cache_bytes:
            self._counts["skipped_retention"] += 1
            return prepared
        while self._counts["retained_bytes"] + size > self._max_cache_bytes:
            _, old = self._cache.popitem(last=False)
            self._counts["retained_bytes"] -= old.retained_bytes
            self._counts["evictions"] += 1
        self._cache[key] = prepared
        self._counts["retained_bytes"] += size
        self._counts["peak_retained_bytes"] = max(self._counts["peak_retained_bytes"],
                                                  self._counts["retained_bytes"])
        return prepared

    def source_strata(self, name):
        """Return the exact frozen strata/names, redoing all target-bearing work."""
        self._assert_live()
        if type(name) is not str or name not in frozen.CURRICULA:
            raise ValueError("supported ordered curriculum required")
        self._counts["source_calls"] += 1
        strata = []
        names = None
        for fixture in frozen.TRAIN_FIXTURES:
            self._assert_live()
            # Both checks happen before every fixture use, even all-cache-hit
            # uses and before load_match. The existing loader keeps its own gates.
            frozen.guard.assert_access(self._cap, fixture, "observations")
            frozen.guard.assert_access(self._cap, fixture, "targets")
            self._counts["fixture_uses"] += 1
            if fixture not in self._owned_matches:
                self._owned_matches[fixture] = frozen.load_match(self._study, self._cap, fixture)
            obs, truth = self._owned_matches[fixture]
            if type(truth) is not TargetBatch or len(truth.labels) != len(obs.frame_id):
                raise ValueError("aligned actual targets required")
            if not frozen.guard._hex(truth.observation_digest) or not frozen.guard._hex(obs.source_digest):
                raise ValueError("adapter input identity is not a SHA256")
            validate_observations(obs)
            original_digest = frozen.observation_digest(obs)
            ids = frozen.emitter_rows(truth.labels, obs.period_id) if name != "boundary" else None
            target_hash = frozen.array_digest(truth.labels)
            for condition in frozen.CURRICULA[name]:
                self._assert_live()
                seeds = frozen.seed_streams(self._protocol_digest, "train", fixture, condition)
                prepared = self._prepare(obs, fixture, condition, original_digest, seeds)
                features = prepared.features()
                if name == "boundary":
                    boundary = frozen.build_boundary_features(features)
                    eligible, target = frozen.boundary_population(truth.labels, features.period_id, boundary.valid)
                    chosen, y, inclusion, counts = frozen.sample_boundary(eligible, target, seeds["boundary_none_sampling"])
                    x = boundary.values[chosen].copy()
                    names = frozen.BOUNDARY_NAMES
                    stratum = dict(x=x, y=y, inclusion=inclusion, population_counts=counts)
                    sampling = frozen.array_digest(eligible, target, chosen, y, inclusion, counts)
                else:
                    matrix, names, pairs = frozen.feature_matrix(features)
                    x, y, weights, counts = frozen.emitter_stratum(matrix, truth.labels, ids, pairs)
                    stratum = dict(x=x, y=y, weights=weights, population_counts=counts)
                    sampling = frozen.array_digest(ids, y, weights, counts)
                stratum.update(fixture_id=fixture, condition=condition,
                    observation_digest=prepared.observation_digest, target_digest=target_hash,
                    sampling_digest=sampling, corruption=json.loads(prepared.receipt))
                strata.append(stratum)
        self._assert_live()
        return strata, names
