"""Stream supplied ATD observations into a content-checked disk cache.

Only one raw record and one 250-frame block are resident while preparing. Input
files and optional predictions are read-only. No inference, feature accumulator,
video reader, player identity or tracking repair is involved.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Callable
import xml.etree.ElementTree as ET

import numpy as np

from possession_model.features import _metadata, _numbers


PITCH = (105.3, 68.0)
CHUNK_FRAMES = 250
LABEL_CODES = ("X", "H", "A", "D")
CACHE_FORMAT = "replay-v2-observed-xy-f32-le-1"
MAX_METADATA_BYTES = 16 * 1024 * 1024
MAX_SLOTS = 128
MAX_CACHE_BYTES = 32 * 1024 ** 3
Progress = Callable[[dict], None]


class ReplayError(ValueError):
    """A fixed, safe explanation suitable for local aggregate status."""


_OWNED_TEMPORARY = re.compile(r"\.replay-([1-9][0-9]{0,9})-[a-z0-9_]{8}\.(?:f32\.)?tmp\Z")


def _process_exited(pid: int) -> bool:
    """Delete nothing unless the owning process is positively known to be gone."""
    if pid == os.getpid() or not 0 < pid <= 2 ** 31 - 1:
        return False
    if os.name == "nt":
        # os.kill(pid, 0) is not a liveness probe on Windows: it can terminate.
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only
        if not handle:
            # Access denied and other unknown states preserve the file.
            return ctypes.get_last_error() == 87  # nonexistent process ID
        try:
            return kernel.WaitForSingleObject(handle, 0) == 0
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except (OSError, OverflowError):
        return False
    return False


def _cleanup_abandoned_temporaries(cache_dir: Path, protected: tuple[Path, ...]) -> None:
    """Reap only recognized generated files whose process has exited.

    No recursion, symbolic links, input files, live/unknown owners or legacy
    anonymous files are removed. PID reuse conservatively retains an old file.
    """
    protected_paths = {path.resolve() for path in protected}
    exited = {}
    with os.scandir(cache_dir) as entries:
        for entry in entries:
            match = _OWNED_TEMPORARY.fullmatch(entry.name)
            if match is None:
                continue
            try:
                if not entry.is_file(follow_symlinks=False):
                    continue
                path = Path(entry.path)
                if path.is_symlink() or path.resolve() in protected_paths:
                    continue
                if path.parent.resolve() != cache_dir:
                    continue
                pid = int(match[1])
                if pid not in exited:
                    exited[pid] = _process_exited(pid)
                if exited[pid]:
                    path.unlink(missing_ok=True)
            except OSError:
                # A locked/disappeared file must not break another viewer.
                continue


def _digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _private_directory(path: Path) -> Path:
    # Refuse a symlink cache destination rather than following an unexpected
    # target during atomic cache writes. Parent directories are user-selected.
    if path.is_symlink():
        raise ReplayError("The cache directory must not be a symbolic link.")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.is_dir():
        raise ReplayError("The cache directory is unavailable.")
    try:
        path.chmod(0o700)
    except OSError:
        pass  # Windows uses the parent directory's current-user ACL.
    return path.resolve()


def atomic_private_json(path: Path, value: dict) -> None:
    """Replace only the caller's named state file, never a followed symlink."""
    if path.is_symlink():
        raise ReplayError("The local state destination is not a regular file.")
    handle = tempfile.NamedTemporaryFile(prefix=f".replay-{os.getpid()}-", suffix=".tmp",
                                         dir=path.parent, delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            os.chmod(temporary, 0o600)
            handle.write(_canonical(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _inputs(data_dir: Path) -> tuple[Path, Path]:
    tactical = data_dir / "tactical"
    pairs = [(xml, xml.with_suffix(".txt")) for xml in tactical.glob("*.xml")
             if xml.with_suffix(".txt").is_file()]
    if len(pairs) != 1:
        raise ReplayError("Expected one matching ATD XML/TXT pair in tactical/.")
    return pairs[0]


def _describe(meta: Path) -> dict:
    if meta.stat().st_size > MAX_METADATA_BYTES:
        raise ReplayError("Tracking metadata exceeds the supported size.")
    content = meta.read_bytes()
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise ReplayError("Tracking metadata contains unsupported declarations.")
    root = ET.fromstring(content)
    specifications = [node for node in root.iter()
                      if node.tag.rsplit("}", 1)[-1] == "DataFormatSpecification"]
    rates = [node for node in root.iter()
             if node.tag.rsplit("}", 1)[-1] == "FrameRate"]
    if len(specifications) != 1 or len(rates) != 1:
        raise ReplayError("Tracking metadata requires one frame range and frame rate.")
    declared = specifications[0].get("endFrame", "")
    if not declared.isascii() or not declared.isdigit() or len(declared) > 10:
        raise ReplayError("Tracking metadata has an invalid frame range.")
    frames = int(declared)
    fps = float(rates[0].text or "nan")
    if not 0 < frames <= 2 ** 31 - 1 or not math.isfinite(fps) or fps <= 0:
        raise ReplayError("Tracking metadata has an invalid frame range or frame rate.")
    sides, xy_indices, ball_indices = _metadata(meta, frames, fps)
    if not 0 < len(sides) <= MAX_SLOTS:
        raise ReplayError("The declared tracking slot count is unsupported.")
    row_floats = 2 * (len(sides) + 1) + 1
    if frames * row_floats * 4 > MAX_CACHE_BYTES:
        raise ReplayError("The declared tracking cache exceeds the supported size.")
    return {"frames": frames, "fps": fps, "sides": sides,
            "xy_indices": xy_indices, "ball_indices": ball_indices,
            "row_floats": row_floats}


def _prediction_rows(path: Path | None, frames: int):
    if path is None:
        for _ in range(frames):
            yield math.nan
        return
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        # Bounded physical lines also prevent csv.reader from accumulating an
        # arbitrarily large quoted field. The public contract has no quoting.
        if handle.readline(128).rstrip("\r\n") != "frame,label":
            raise ReplayError("Predictions require the exact frame,label header.")
        for index in range(frames):
            line = handle.readline(128)
            if not line or len(line) >= 128 or '"' in line:
                raise ReplayError("Predictions contain an invalid row or row count.")
            fields = line.rstrip("\r\n").split(",")
            if len(fields) != 2 or fields[0] != str(index) or fields[1] not in LABEL_CODES:
                raise ReplayError("Predictions require ordered zero-based frames and X/H/A/D labels.")
            yield float(LABEL_CODES.index(fields[1]))
        if handle.read(1):
            raise ReplayError("Predictions contain an invalid row count.")


def _local_rows(raw: Path, description: dict, predictions: Path | None,
                progress: Progress):
    frames, sides = description["frames"], description["sides"]
    xy = description["xy_indices"]
    ball_xy = list(description["ball_indices"])
    slot_indices = np.arange(len(sides))[:, None]
    scale = np.asarray(PITCH, dtype=np.float64)
    max_float = np.finfo(np.float32).max
    labels = _prediction_rows(predictions, frames)
    line_limit = max(4096, (len(sides) * 3 + 4) * 256)
    count = 0
    with raw.open("r", encoding="utf-8-sig") as handle:
        while True:
            line = handle.readline(line_limit + 1)
            if not line:
                break
            if len(line) > line_limit:
                raise ReplayError("A tracking record exceeds the supported size.")
            parts = line.strip().split(":")
            if len(parts) != 3 or not parts[0].isascii() or not parts[0].isdigit():
                raise ReplayError("Tracking records have an invalid structure.")
            if count >= frames or len(parts[0]) > 10 or int(parts[0]) != count + 1:
                raise ReplayError("Tracking frame IDs must be contiguous from one.")
            groups = parts[1].split(";")
            if (len(groups) != len(sides)
                    or any(group.count(",") != 2 or any(not item.strip() for item in group.split(","))
                           for group in groups)
                    or parts[2].count(",") != 2
                    or any(not item.strip() for item in parts[2].split(","))):
                raise ReplayError("Tracking records have an invalid channel count.")
            players = _numbers(parts[1].replace(";", ","), len(sides) * 3).reshape(-1, 3)
            ball = _numbers(parts[2], 3)
            with np.errstate(over="ignore", invalid="ignore"):
                positions_m = players[slot_indices, xy] * scale
                ball_m = ball[ball_xy] * scale
            if (np.isinf(positions_m).any() or np.isinf(ball_m).any()
                    or (np.abs(positions_m) > max_float).any()
                    or (np.abs(ball_m) > max_float).any()):
                raise ReplayError("Tracking coordinates exceed finite float32 storage.")
            positions_m[~np.isfinite(positions_m).all(axis=1)] = np.nan
            if not np.isfinite(ball_m).all():
                ball_m[:] = np.nan
            row = np.full(description["row_floats"], np.nan, dtype="<f4")
            row[:len(sides) * 2] = positions_m.reshape(-1)
            row[len(sides) * 2:len(sides) * 2 + 2] = ball_m
            row[-1] = next(labels)
            yield row
            count += 1
            if count % CHUNK_FRAMES == 0:
                progress({"phase": "preparing", "records": count, "total": frames})
    if count != frames:
        raise ReplayError("Tracking records do not match the declared frame range.")
    # Exhaust the generator to check that an optional CSV has no extra rows.
    try:
        next(labels)
    except StopIteration:
        pass


def _triangle(value: float) -> float:
    return 1.0 - abs((value % 2.0) - 1.0)


def _demo_rows(description: dict, progress: Progress):
    """Invented moving slot trajectories and scripted passes, with visible gaps."""
    slots = len(description["sides"])
    for frame in range(description["frames"]):
        seconds = frame / description["fps"]
        row = np.full(description["row_floats"], np.nan, dtype="<f4")
        positions = row[:slots * 2].reshape(slots, 2)
        for slot in range(slots):
            side, lane = divmod(slot, 11)
            positions[slot] = (8 + 88 * _triangle(seconds / 42 + slot * 0.071 + side * .35),
                               5 + (lane % 6) * 10.5 + 2 * _triangle(seconds / 8 + slot * .2))
        # Ball travels between changing moving slot positions, with a sharp
        # source discontinuity and two intervals where it is unobserved.
        pass_id, pass_frame = divmod(frame, 100)
        source = (pass_id * 3) % slots
        destination = (source + 7) % slots
        ratio = pass_frame / 99
        row[slots * 2:slots * 2 + 2] = positions[source] * (1 - ratio) + positions[destination] * ratio
        if 275 <= frame % 900 < 300:
            row[slots * 2:slots * 2 + 2] = np.nan
        if 420 <= frame % 700 < 465:
            positions[3] = np.nan
        if 630 <= frame % 1100 < 650:
            positions[15] = np.nan
        if 1200 <= frame < 1250:
            positions[0, 0] = -3.0  # Finite off-pitch observations stay off pitch.
        yield row
        if (frame + 1) % CHUNK_FRAMES == 0:
            progress({"phase": "preparing", "records": frame + 1, "total": description["frames"]})


@dataclass(frozen=True)
class ReplayStore:
    payload: Path
    manifest: dict
    preparation_seconds: float
    reused_cache: bool

    def metadata(self) -> dict:
        item = self.manifest
        return {"mode": item["mode"], "status": "ready", "frames": item["frames"],
                "fps": item["fps"], "pitch": list(PITCH), "slots": item["slots"],
                "chunk_frames": CHUNK_FRAMES, "row_floats": item["row_floats"],
                "initial_frame": item["initial_frame"], "predictions_ready": item["predictions_ready"],
                "label_codes": list(LABEL_CODES), "source_hashes": item["source_hashes"],
                "cache_sha256": item["payload_sha256"], "reused_cache": self.reused_cache,
                "preparation_seconds": round(self.preparation_seconds, 6)}

    def read_window(self, start: int, count: int) -> bytes:
        frames, width = self.manifest["frames"], self.manifest["row_floats"]
        if type(start) is not int or type(count) is not int or not 0 <= start < frames or not 1 <= count <= CHUNK_FRAMES:
            raise ReplayError("Frame window is outside the bounded replay range.")
        stop = min(start + count, frames)
        row_bytes = width * 4
        result = bytearray()
        if self.payload.is_symlink():
            raise ReplayError("The replay cache changed; restart to rebuild it.")
        with self.payload.open("rb") as handle:
            if os.fstat(handle.fileno()).st_size != frames * row_bytes:
                raise ReplayError("The replay cache changed; restart to rebuild it.")
            for chunk in range(start // CHUNK_FRAMES, (stop - 1) // CHUNK_FRAMES + 1):
                chunk_start = chunk * CHUNK_FRAMES
                chunk_stop = min(chunk_start + CHUNK_FRAMES, frames)
                handle.seek(chunk_start * row_bytes)
                content = handle.read((chunk_stop - chunk_start) * row_bytes)
                if hashlib.sha256(content).hexdigest() != self.manifest["chunk_sha256"][chunk]:
                    raise ReplayError("The replay cache changed; restart to rebuild it.")
                left, right = max(start, chunk_start) - chunk_start, min(stop, chunk_stop) - chunk_start
                result.extend(content[left * row_bytes:right * row_bytes])
        return bytes(result)


def _cached(payload: Path, index: Path, expected: dict) -> dict | None:
    if payload.is_symlink() or index.is_symlink() or not payload.is_file() or not index.is_file():
        return None
    try:
        if index.stat().st_size > MAX_METADATA_BYTES:
            return None
        manifest = json.loads(index.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            return None
        if any(manifest.get(key) != value for key, value in expected.items()):
            return None
        row_bytes = expected["row_floats"] * 4
        expected_bytes = expected["frames"] * row_bytes
        hashes = manifest.get("chunk_sha256")
        if (payload.stat().st_size != expected_bytes or not isinstance(hashes, list)
                or len(hashes) != math.ceil(expected["frames"] / CHUNK_FRAMES)
                or type(manifest.get("initial_frame")) is not int
                or not 0 <= manifest["initial_frame"] < expected["frames"]):
            return None
        whole = hashlib.sha256()
        with payload.open("rb") as handle:
            for expected_hash in hashes:
                block = handle.read(CHUNK_FRAMES * row_bytes)
                whole.update(block)
                if hashlib.sha256(block).hexdigest() != expected_hash:
                    return None
            if handle.read(1):
                return None
        if whole.hexdigest() != manifest.get("payload_sha256"):
            return None
        return manifest
    except (OSError, ValueError, TypeError):
        return None


def prepare_store(*, data_dir: Path | None, predictions: Path | None,
                  cache_dir: Path, demo: bool = False,
                  progress: Progress = lambda _: None) -> ReplayStore:
    started = time.perf_counter()
    selected_cache = Path(cache_dir).resolve()
    if not demo and data_dir is not None:
        selected_data = Path(data_dir).resolve()
        if selected_cache == selected_data or selected_data in selected_cache.parents:
            raise ReplayError("Choose a cache directory outside the supplied input directory.")
    cache_dir = _private_directory(Path(cache_dir))
    parser_hash = hashlib.sha256(Path(__file__).read_bytes() +
                                 (Path(__file__).resolve().parents[1] / "possession_model" / "features.py").read_bytes()).hexdigest()
    inputs = []
    first_non_x = None
    if demo:
        if predictions is not None or data_dir is not None:
            raise ReplayError("Demo mode cannot also select supplied tracking or predictions.")
        description = {"frames": 3000, "fps": 25.0, "sides": [0] * 11 + [1] * 11,
                       "row_floats": 47}
        source_hashes = {"invented_demo": hashlib.sha256(b"moving-slots-scripted-passes-gaps-v1").hexdigest()}
    else:
        if data_dir is None:
            raise ReplayError("Choose a data directory containing tactical/, or choose demo mode.")
        data_dir = Path(data_dir).resolve()
        if cache_dir == data_dir or data_dir in cache_dir.parents:
            raise ReplayError("Choose a cache directory outside the supplied input directory.")
        meta, raw = _inputs(data_dir)
        inputs = [("metadata", meta), ("tracking", raw)]
        if predictions is not None:
            predictions = Path(predictions).resolve()
            inputs.append(("predictions", predictions))
        progress({"phase": "hashing", "records": 0})
        source_hashes = {name: _digest(path) for name, path in inputs}
        description = _describe(meta)
        # Predictions are validated afresh even when coordinate/payload cache
        # bytes can be reused. Labels can never affect the XY reader.
        if predictions is not None:
            progress({"phase": "checking_predictions", "records": 0, "total": description["frames"]})
            for frame, code in enumerate(_prediction_rows(predictions, description["frames"])):
                if first_non_x is None and code > 0:
                    first_non_x = frame
    _cleanup_abandoned_temporaries(cache_dir, tuple(path for _, path in inputs))
    expected = {"format": CACHE_FORMAT, "parser_sha256": parser_hash,
                "mode": "demo" if demo else "local", "pitch": list(PITCH), "frames": description["frames"],
                "fps": description["fps"], "row_floats": description["row_floats"],
                "slots": [{"slot": slot, "side": "H" if side == 0 else "A"}
                          for slot, side in enumerate(description["sides"])],
                "predictions_ready": predictions is not None, "source_hashes": source_hashes}
    identity = hashlib.sha256(_canonical(expected)).hexdigest()
    payload, index = cache_dir / (identity + ".f32"), cache_dir / (identity + ".json")
    selected_paths = {path.resolve() for _, path in inputs}
    if selected_paths.intersection({payload.resolve(), index.resolve()}):
        raise ReplayError("A cache destination conflicts with a supplied input. Choose a different cache directory; the input was not changed.")
    progress({"phase": "checking_cache", "records": 0, "total": description["frames"]})
    manifest = _cached(payload, index, expected)
    if manifest is not None:
        # Hashes are always recomputed above, even when size/mtime are unchanged.
        if inputs and {name: _digest(path) for name, path in inputs} != source_hashes:
            raise ReplayError("Supplied inputs changed during preparation; restart to retry.")
        if first_non_x is not None and manifest["initial_frame"] != first_non_x:
            manifest = None
    if manifest is not None:
        return ReplayStore(payload, manifest, time.perf_counter() - started, True)
    if payload.is_symlink() or index.is_symlink():
        raise ReplayError("The cache destination must not be a symbolic link.")
    rows = _demo_rows(description, progress) if demo else _local_rows(raw, description, predictions, progress)
    handle = tempfile.NamedTemporaryFile(prefix=f".replay-{os.getpid()}-", suffix=".f32.tmp", dir=cache_dir, delete=False)
    temporary = Path(handle.name)
    hashes, block, whole = [], bytearray(), hashlib.sha256()
    count, first_observed = 0, None
    try:
        with handle:
            os.chmod(temporary, 0o600)
            for row in rows:
                if first_observed is None and np.isfinite(row[:-1]).any():
                    first_observed = count
                block.extend(row.tobytes())
                count += 1
                if count % CHUNK_FRAMES == 0:
                    handle.write(block)
                    whole.update(block)
                    hashes.append(hashlib.sha256(block).hexdigest())
                    block.clear()
            if block:
                handle.write(block)
                whole.update(block)
                hashes.append(hashlib.sha256(block).hexdigest())
            handle.flush()
            os.fsync(handle.fileno())
        if count != description["frames"]:
            raise ReplayError("Prepared frames disagree with the declared frame range.")
        if inputs:
            progress({"phase": "checking_sources", "records": count, "total": count})
            if {name: _digest(path) for name, path in inputs} != source_hashes:
                raise ReplayError("Supplied inputs changed during preparation; restart to retry.")
        initial = first_non_x if first_non_x is not None else (first_observed if first_observed is not None else 0)
        manifest = dict(expected, identity=identity, payload_sha256=whole.hexdigest(),
                        chunk_sha256=hashes, initial_frame=initial)
        os.replace(temporary, payload)
        atomic_private_json(index, manifest)
        return ReplayStore(payload, manifest, time.perf_counter() - started, False)
    finally:
        temporary.unlink(missing_ok=True)
