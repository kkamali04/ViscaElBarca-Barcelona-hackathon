"""Run the frozen candidate locally; never opens possession ground truth or video."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import tempfile
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "more-than-a-hack-2027-main"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(UPSTREAM / "evaluation"))
from possession_model.features import load_atd
from possession_model.schema import FeatureSet
from possession_model.pipeline import predict, load_config, write_submission, tag_support, verify_frozen_sources
import possession_metrics as pm


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for part in iter(lambda: source.read(1024*1024), b""):
            digest.update(part)
    return digest.hexdigest()


def peak_memory_bytes():
    if os.name != "nt":
        return None
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    *[(key, ctypes.c_size_t) for key in ("PeakWorkingSetSize", "WorkingSetSize",
                    "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(counters.PeakWorkingSetSize)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "models/active.json")
    parser.add_argument("--data-dir", type=Path, default=UPSTREAM / "data")
    parser.add_argument("--out", type=Path, default=ROOT / "submissions/candidate.csv")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/candidate-run.json")
    parser.add_argument("--no-cache", action="store_true", help="Do not read or write feature caches")
    parser.add_argument("--experimental-tag-weight", type=float, default=0.)
    args = parser.parse_args()
    args.config, args.data_dir = args.config.resolve(), args.data_dir.resolve()
    args.out, args.report = args.out.resolve(), args.report.resolve()
    if args.out.is_dir() or args.report.is_dir():
        raise ValueError("CSV and report destinations must be files, not directories")
    if args.out in args.report.parents or args.report in args.out.parents:
        raise ValueError("CSV and report destinations cannot contain each other")
    for destination in (args.out, args.report):
        if any(parent.exists() and not parent.is_dir() for parent in destination.parents):
            raise ValueError("Output/report parent must be a directory")
    if not np.isfinite(args.experimental_tag_weight) or not 0 <= args.experimental_tag_weight <= .25:
        raise ValueError("Experimental tag weight must be finite and between 0 and .25")
    start = time.perf_counter()
    config = load_config(args.config)
    verify_frozen_sources(ROOT, config)
    model = ROOT / config["model"]
    if sha(model) != config["model_sha256"]:
        raise ValueError("Trained model differs from frozen configuration")
    meta = args.data_dir / "tactical/BAR-ATH_tactical_atd.xml"
    raw = args.data_dir / "tactical/BAR-ATH_tactical_atd.txt"
    # Preflight destinations before inference; alias/hardlink writes must never
    # replace source data, executable code, model/config or the fallback artifact.
    def aliases(first, second):
        return first == second or (first.exists() and second.exists() and os.path.samefile(first, second))
    protected = [meta, raw, args.config, model.resolve(), ROOT/"submissions/baseline_fallback.csv",
                 ROOT/"local/submission-code.zip"]
    protected.append(args.data_dir/"tactical/BAR-ATH_tactical_smart_tagging.xml")
    protected.extend((ROOT/name).resolve() for name in config.get("source_sha256", {}))
    if aliases(args.out, args.report):
        raise ValueError("CSV and report destinations must be different files")
    for destination in (args.out, args.report):
        if destination.is_relative_to(args.data_dir) or any(aliases(destination, source) for source in protected):
            raise ValueError("Output/report destination aliases a protected input or artifact")
    blocks = [(1, 11185, 90652), (2, 110808, 190198)]  # Official inclusive ranges -> half-open.
    signature = {"metadata_sha256": sha(meta), "tracking_sha256": sha(raw),
                 "extractor_sha256": sha(ROOT / "possession_model/features.py"), "blocks": blocks}
    key = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()[:20]
    cache = ROOT / "local" / f"tactical-features-{key}.npz"
    if any(aliases(destination, cache) for destination in (args.out, args.report)):
        raise ValueError("Output/report destination aliases the feature cache")
    array_names = ("period_id", "ball_xy", "ball_observed", "nearest", "tracked_counts", "collective_speed", "ball_speed")
    cached = cache.exists() and not args.no_cache
    feature_start = time.perf_counter()
    if cached:
        with np.load(cache, allow_pickle=False) as data:
            features = FeatureSet(fps=25., pitch=(105.3, 68.), **{name: data[name] for name in array_names})
    else:
        features = load_atd(meta, raw, 199319, 25., (105.3, 68.), blocks)
        if not args.no_cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=cache.parent, suffix=".npz", delete=False) as temp:
                temporary_cache = Path(temp.name)
            try:
                np.savez(temporary_cache, **{name: getattr(features, name) for name in array_names})
                os.replace(temporary_cache, cache)
            finally:
                temporary_cache.unlink(missing_ok=True)
    feature_seconds = time.perf_counter()-feature_start
    transform_start = time.perf_counter()
    if config.get("feature_transform") == "local-linear-v2":
        from experiments.noise_v2.features import robustify_ball_motion
        features = robustify_ball_motion(features)
    elif config.get("feature_transform") not in (None, "identity"):
        raise ValueError("Unsupported feature transformation")
    transform_seconds = time.perf_counter()-transform_start
    tags = None
    if args.experimental_tag_weight:
        config = {**config, "tag_weight": args.experimental_tag_weight}
        tags = tag_support(args.data_dir / "tactical/BAR-ATH_tactical_smart_tagging.xml", features.n_frames, features.fps)
    inference_start = time.perf_counter()
    codes = predict(features, config, model, tags, forced_dead=[(110808, 113742)])
    inference_seconds = time.perf_counter()-inference_start
    if np.asarray(codes).shape != (199319,):
        raise ValueError("Prediction must contain exactly one code for every tactical frame")
    output_sha = write_submission(args.out, codes)
    # Actual organiser validator, without exposing predictions/records in stdout.
    table = pm.read_label_csv(args.out)
    reason = pm.validate_submission(table, 199319)
    if reason:
        raise ValueError(reason)
    report = {"configuration": str(args.config.relative_to(ROOT)) if args.config.is_relative_to(ROOT) else str(args.config), "config_sha256": sha(args.config),
              "experimental_tag_weight": args.experimental_tag_weight,
              "input_signatures": signature, "frames": len(codes), "fps": 25,
              "cache_hit": cached, "feature_seconds": feature_seconds, "inference_seconds": inference_seconds,
              "feature_transform_seconds": transform_seconds,
              "total_seconds": time.perf_counter()-start, "feature_array_bytes": features.array_bytes,
              "peak_process_working_set_bytes": peak_memory_bytes(), "csv_sha256": output_sha,
              "official_format_validator": "passed", "ground_truth_opened": False,
              "video_opened": False, "private_accuracy_measured": False}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=args.report.parent, encoding="utf-8", suffix=".json.tmp", delete=False) as output:
        temporary_report = Path(output.name)
        output.write(json.dumps(report, indent=2)+"\n")
    try:
        os.replace(temporary_report, args.report)
    finally:
        temporary_report.unlink(missing_ok=True)
    print(f"Official format check passed: {len(codes)} frames")
    print(f"Features: {feature_seconds:.3f}s; inference: {inference_seconds:.3f}s; total: {report['total_seconds']:.3f}s")
    print(f"Peak process working set: {report['peak_process_working_set_bytes']} bytes")
    print(f"CSV SHA256: {output_sha}")


if __name__ == "__main__":
    main()
