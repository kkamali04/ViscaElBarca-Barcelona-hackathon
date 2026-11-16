"""Bounded-memory adapter for independent IDSSE Sportec/DFL matches.

BallStatus/BallPossession are read into the scoring target only. Features use
coordinates, roster membership, frame IDs and GameSection, never these labels.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

PERIODS = {"firstHalf": 1, "secondHalf": 2, "firstHalfExtra": 3, "secondHalfExtra": 4}
PAPER = "https://www.nature.com/articles/s41597-025-04505-y"
PARSER_VERSION = 2


def _tag(element):
    return element.tag.rsplit("}", 1)[-1]


def _frames(path):
    """Yield (frameset attributes, frame attributes), without retaining XML nodes."""
    current = None
    stack = []
    for event, elem in ET.iterparse(path, events=("start", "end")):
        tag = _tag(elem)
        if event == "start":
            stack.append(elem)
            if tag == "FrameSet":
                current = dict(elem.attrib)
        else:
            if tag == "Frame" and current is not None:
                yield current, elem.attrib
            if tag == "FrameSet":
                current = None
            # Removing each child on its end event prevents empty nodes growing
            # to the multi-million-frame size of the original XML.
            if len(stack) > 1:
                stack[-2].remove(elem)
            elem.clear()
            stack.pop()


def read_metadata(path):
    """Read the small public roster document; officials are deliberately excluded."""
    root = ET.parse(path).getroot()
    general = next(e for e in root.iter() if _tag(e) == "General")
    environment = next(e for e in root.iter() if _tag(e) == "Environment")
    slots = []
    membership = []
    for team in (e for e in root.iter() if _tag(e) == "Team"):
        team_id = team.get("TeamId")
        if team_id == general.get("HomeTeamId"):
            side = 0
        elif team_id == general.get("GuestTeamId"):
            side = 1
        else:
            continue
        for player in (e for e in team.iter() if _tag(e) == "Player"):
            person_id = player.get("PersonId")
            if not person_id or person_id in slots:
                raise ValueError("Missing or duplicated roster PersonId")
            slots.append(person_id)
            membership.append(side)
    if not slots or not {0, 1}.issubset(membership):
        raise ValueError("Both team rosters are required")
    return {
        "match_id": general.get("MatchId"),
        "match_title": general.get("MatchTitle"),
        "kickoff": general.get("KickoffTime"),
        "pitch": [float(environment.get("PitchX")), float(environment.get("PitchY"))],
        "slots": slots,
        "team_of_slot": membership,
        "home_team_id": general.get("HomeTeamId"),
        "away_team_id": general.get("GuestTeamId"),
    }


def truth_code(frame):
    """Scoring-only mapping: -1 unknown, 0 home, 1 away, 2 referee stoppage."""
    status = frame.get("BallStatus")
    if status == "0":
        return 2
    if status == "1":
        return {"1": 0, "2": 1}.get(frame.get("BallPossession"), -1)
    return -1


def _xy(frame, offset):
    try:
        x, y = float(frame["X"]), float(frame["Y"])
    except (KeyError, ValueError):
        return (np.nan, np.nan)
    return (x + offset[0], y + offset[1]) if np.isfinite(x) and np.isfinite(y) else (np.nan, np.nan)


def _scan_layout(raw_path, metadata):
    """Find timeline solely from raw N and GameSection, independently of truth."""
    limits = {}
    samples = {}
    frame_count = 0
    for frame_set, frame in _frames(raw_path):
        period = PERIODS.get(frame_set.get("GameSection"))
        if period is None:
            continue
        if frame_set.get("MatchId") != metadata["match_id"]:
            raise ValueError("Tracking/metadata match IDs disagree")
        n = int(frame["N"])
        lo, hi = limits.get(period, (n, n))
        limits[period] = (min(lo, n), max(hi, n))
        pair = samples.setdefault(period, [])
        if len(pair) < 2 and frame.get("T") and (not pair or n != pair[0][0]):
            pair.append((n, datetime.fromisoformat(frame["T"])))
        frame_count += 1
    if not limits:
        raise ValueError("No supported GameSection frames")
    rates = []
    for pair in samples.values():
        if len(pair) == 2:
            dt = (pair[1][1] - pair[0][1]).total_seconds()
            if dt > 0:
                rates.append((pair[1][0] - pair[0][0]) / dt)
    if not rates or not np.allclose(rates, rates[0], atol=1e-6):
        raise ValueError("Could not establish one consistent frame rate from timestamps")
    blocks = []
    offset = 0
    for period, (lo, hi) in sorted(limits.items()):
        size = hi - lo + 1
        blocks.append({"period": period, "raw_start": lo, "raw_end": hi, "start": offset, "end": offset + size})
        offset += size
    return {"n_frames": offset, "blocks": blocks, "fps": rates[0], "xml_frame_records": frame_count}


def _sha256(path):
    """Hash large raw sources without retaining their contents in memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _build_cache(meta_path, raw_path, metadata):
    # Content identity remains valid when a replacement preserves size/mtime.
    # First acquisition is separately verified by fetch_validation_data.py.
    signature = {"version": PARSER_VERSION, "raw_name": raw_path.name, "raw_size": raw_path.stat().st_size,
                 "raw_mtime_ns": raw_path.stat().st_mtime_ns,
                 "raw_sha256": _sha256(raw_path),
                 "meta_sha256": hashlib.sha256(meta_path.read_bytes()).hexdigest()}
    key = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()[:16]
    folder = raw_path.parent / f"cache-sportec-{key}"
    manifest = folder / "cache.json"
    if manifest.exists():
        return folder, json.loads(manifest.read_text())
    layout = _scan_layout(raw_path, metadata)
    n_frames, n_slots = layout["n_frames"], len(metadata["slots"])
    folder.mkdir(parents=True, exist_ok=True)
    positions = np.lib.format.open_memmap(folder / "positions.npy", mode="w+", dtype=np.float32, shape=(n_frames, n_slots, 2))
    positions[:] = np.nan
    ball = np.lib.format.open_memmap(folder / "ball.npy", mode="w+", dtype=np.float32, shape=(n_frames, 2))
    ball[:] = np.nan
    # Truth is stored in a separate file and never given to FeatureAccumulator.
    truth = np.lib.format.open_memmap(folder / "truth.npy", mode="w+", dtype=np.int8, shape=(n_frames,))
    truth[:] = -1
    player_seen = np.zeros((n_frames, n_slots), dtype=bool)
    ball_seen = np.zeros(n_frames, dtype=bool)
    slot_lookup = {person: i for i, person in enumerate(metadata["slots"])}
    blocks = {block["period"]: block for block in layout["blocks"]}
    center_offset = np.asarray(metadata["pitch"]) / 2
    for frame_set, frame in _frames(raw_path):
        period = PERIODS.get(frame_set.get("GameSection"))
        if period is None:
            continue
        block = blocks[period]
        index = block["start"] + int(frame["N"]) - block["raw_start"]
        if frame_set.get("TeamId") == "BALL":
            if ball_seen[index]:
                raise ValueError("Duplicated ball frame in one period")
            ball_seen[index] = True
            ball[index] = _xy(frame, center_offset)
            truth[index] = truth_code(frame)
        elif frame_set.get("PersonId") in slot_lookup:
            slot = slot_lookup[frame_set["PersonId"]]
            if player_seen[index, slot]:
                raise ValueError("Duplicated player frame in one period")
            player_seen[index, slot] = True
            positions[index, slot] = _xy(frame, center_offset)
    for array in (positions, ball, truth):
        array.flush()
    layout.update(signature=signature, n_slots=n_slots, ball_records=int(ball_seen.sum()),
                  coordinate_transform="centered metres + (pitch_x/2,pitch_y/2), no orientation flip")
    manifest.write_text(json.dumps(layout, indent=2) + "\n")
    return folder, layout


def make_ball_gap_mask(n_frames, blocks, fps, fraction=0.0, block_seconds=4.0, seed=20261115):
    """Deterministic coordinate-independent contiguous gaps, never crossing halves.

    The fraction selects exactly round(fraction*n_frames) timeline frames. It is
    independent of possession, play status and natural ball visibility. Blocks
    are sampled in random order without replacement, then the final block is
    clipped to meet the requested fraction. Adjacent blocks may merge.
    """
    if not 0 <= fraction <= 1 or block_seconds <= 0:
        raise ValueError("fraction must be in [0,1], block_seconds must be positive")
    width = max(1, round(block_seconds * fps))
    segments = [(start, min(start + width, block["end"])) for block in blocks
                for start in range(block["start"], block["end"], width)]
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(segments))
    remaining = round(n_frames * fraction)
    mask = np.zeros(n_frames, dtype=bool)
    for which in order:
        if remaining == 0:
            break
        start, end = segments[which]
        stop = start + min(end - start, remaining)
        mask[start:stop] = True
        remaining -= stop - start
    return mask


def load_sportec(meta_path, raw_path, corruption=None):
    """Return (FeatureSet, separate truth codes, source provenance).

    corruption may be {ball_missing_fraction: .4, block_seconds: 4, seed: 123}.
    No XML labels, provider speed, events or human annotations enter features.
    """
    from possession_model.features import FeatureAccumulator
    from possession_model.schema import FeatureSet

    meta_path, raw_path = Path(meta_path), Path(raw_path)
    metadata = read_metadata(meta_path)
    folder, layout = _build_cache(meta_path, raw_path, metadata)
    positions = np.load(folder / "positions.npy", mmap_mode="r")
    ball = np.load(folder / "ball.npy", mmap_mode="r")
    # A small owned copy avoids returning a Windows file lock to the caller.
    truth = np.load(folder / "truth.npy")
    settings = corruption or {}
    mask = make_ball_gap_mask(layout["n_frames"], layout["blocks"], layout["fps"],
                              settings.get("ball_missing_fraction", 0.0), settings.get("block_seconds", 4.0),
                              settings.get("seed", 20261115))
    blocks = [(block["period"], block["start"], block["end"]) for block in layout["blocks"]]
    extractor_source = Path(__file__).resolve().parents[1] / "possession_model" / "features.py"
    source_hash = hashlib.sha256(extractor_source.read_bytes()).hexdigest()
    cache_key = hashlib.sha256((source_hash + json.dumps(settings, sort_keys=True)).encode()).hexdigest()[:16]
    feature_cache = folder / f"features-{cache_key}.npz"
    array_names = ("period_id", "ball_xy", "ball_observed", "nearest", "tracked_counts", "collective_speed", "ball_speed")
    if feature_cache.exists():
        with np.load(feature_cache, allow_pickle=False) as cached:
            features = FeatureSet(fps=layout["fps"], pitch=tuple(metadata["pitch"]),
                                  **{name: cached[name] for name in array_names})
    else:
        accumulator = FeatureAccumulator(layout["n_frames"], np.asarray(metadata["team_of_slot"], dtype=np.int8),
                                         layout["fps"], tuple(metadata["pitch"]), blocks)
        absent = np.full(2, np.nan, dtype=np.float32)
        for block in layout["blocks"]:
            for index in range(block["start"], block["end"]):
                accumulator.push(index, positions[index], absent if mask[index] else ball[index], block["period"])
        features = accumulator.finish()
        np.savez(feature_cache, **{name: getattr(features, name) for name in array_names})
    provenance = {"source": "IDSSE Sportec/DFL raw observed tracking", "paper": PAPER,
                  "license": "CC-BY-4.0", "metadata": metadata, "layout": layout,
                  "corruption": {**settings, "masked_timeline_frames": int(mask.sum())},
                  "target": "BallStatus=0 -> D; status=1 and possession=1 -> H, 2 -> A; otherwise X",
                  "label_limit": "Provider control semantics; not corrected Metrica challenge ground truth",
                  "inference_uses_labels": False}
    features.metadata.update({"source": "sportec", "match_id": metadata["match_id"],
                              "blocks": blocks, "corruption": provenance["corruption"]})
    return features, truth, provenance
