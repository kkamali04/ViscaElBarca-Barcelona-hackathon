"""Local model runs and derived review state; never opens ground-truth files."""
from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time

FRAMES = 199319
FPS = 25
PERIODS = ((11185, 90652), (110808, 190198))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8", delete=False) as out:
        temporary = Path(out.name)
        json.dump(value, out, indent=2, allow_nan=False)
        out.write("\n")
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def inspect_csv(path):
    """Validate streaming row contract; retain only maximal predicted runs."""
    counts = Counter({label: 0 for label in "HADX"})
    segments = []
    with Path(path).open(encoding="utf-8", newline="") as source:
        rows = csv.reader(source, strict=True)
        if next(rows, None) != ["frame", "label"]:
            raise ValueError("The CSV header must be frame,label")
        total = 0
        for frame, row in enumerate(rows):
            if len(row) != 2 or row[0] != str(frame) or row[1] not in counts:
                raise ValueError("The CSV has invalid frame order or label values")
            label = row[1]
            counts[label] += 1
            if not segments or segments[-1]["label"] != label:
                segments.append({"start": frame, "end": frame + 1, "label": label})
            else:
                segments[-1]["end"] = frame + 1
            total += 1
    if total != FRAMES:
        raise ValueError("The CSV must contain exactly 199319 ordered frames")
    live = counts["H"] + counts["A"]
    return {"present": True, "valid": True, "frames": total, "sha256": sha(path),
            "counts": dict(counts),
            "live_possession": {label: round(100 * counts[label] / live, 2) if live else 0.0 for label in "HA"},
            "segments": segments}


def demo_csv(path):
    """Invented timeline, not labels or measurements from any football match."""
    with Path(path).open("w", encoding="utf-8", newline="") as out:
        out.write("frame,label\n")
        for frame in range(FRAMES):
            if not any(start <= frame < stop for start, stop in PERIODS):
                label = "X"
            elif 110808 <= frame < 113742:
                label = "D"
            else:
                block = frame // 625
                label = "D" if block % 7 == 0 else ("H" if block % 5 < 3 else "A")
            out.write(f"{frame},{label}\n")


class ReviewState:
    def __init__(self, root, demo=False):
        self.root = Path(root).resolve()
        self.demo = bool(demo)
        self.mode = "demo" if self.demo else "local"
        self.work = (self.root / "local" / ("review-mvp-demo" if self.demo else "review-mvp")).resolve()
        if not self.work.is_relative_to(self.root):
            raise ValueError("Review workspace must remain inside this project")
        self.work.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.export_lock = threading.Lock()
        self.run = {"status": "idle", "message": "Current candidate ready for review", "started_at": None}
        self.cached = None
        self.cached_key = None
        self.last_error = None
        self.code_zip = self.root / "local/mvp-code.zip"
        self.csv = self.work / "candidate.csv" if self.demo else self.root / "submissions/candidate.csv"
        self.report = None if self.demo else self.root / "reports/final-candidate-run.json"
        if not self.demo and (self.work / "candidate.csv").is_file() and (self.work / "run.json").is_file():
            self.csv, self.report = self.work / "candidate.csv", self.work / "run.json"
        if self.demo:
            demo_csv(self.csv)
        self.bundle = None

    def current(self):
        with self.lock:
            if not self.csv.is_file():
                return {"present": False, "valid": False, "frames": 0, "counts": {x: 0 for x in "HADX"},
                        "live_possession": {"H": 0, "A": 0}, "sha256": None, "segments": []}
            stat = self.csv.stat()
            key = (str(self.csv), stat.st_size, stat.st_mtime_ns, sha(self.csv))
            if not self.demo:
                # These small integrity checks run even when the derived CSV
                # summary is cached. Never show a stale green model binding.
                try:
                    from possession_model.pipeline import load_config, verify_frozen_sources
                    config = load_config(self.root / "models/active.json")
                    verify_frozen_sources(self.root, config)
                    if sha(self.root / config["model"]) != config["model_sha256"]:
                        raise ValueError("Frozen model integrity check failed")
                    if self.report is None or not self.report.is_file():
                        raise ValueError("Candidate provenance report is missing")
                    provenance = json.loads(self.report.read_text(encoding="utf-8"))
                    if (provenance.get("config_sha256") != sha(self.root / "models/active.json")
                            or provenance.get("official_format_validator") != "passed"):
                        raise ValueError("Candidate does not match its validated model/run report")
                    key += (provenance.get("csv_sha256"),)
                except (ValueError, OSError, KeyError) as error:
                    self.last_error = str(error)
                    return {"present": True, "valid": False, "frames": 0, "sha256": None,
                            "counts": {x: 0 for x in "HADX"}, "live_possession": {"H": 0, "A": 0}, "segments": []}
            if key != self.cached_key:
                try:
                    result = inspect_csv(self.csv)
                    if not self.demo:
                        if provenance.get("csv_sha256") != result["sha256"]:
                            raise ValueError("Candidate does not match its validated model/run report")
                    self.cached, self.cached_key, self.last_error = result, key, None
                except (ValueError, OSError, csv.Error, KeyError) as error:
                    self.last_error = str(error)
                    return {"present": True, "valid": False, "frames": 0, "sha256": None,
                            "counts": {x: 0 for x in "HADX"}, "live_possession": {"H": 0, "A": 0}, "segments": []}
            self.last_error = None
            return self.cached

    def state(self):
        with self.lock:
            output = dict(self.current())
            output.pop("segments", None)
            output["source"] = "invented demo" if self.demo else "frozen noise-v2 prediction"
            if self.last_error:
                output["error"] = self.last_error
            runtime = None
            if self.report and self.report.is_file():
                try:
                    data = json.loads(self.report.read_text(encoding="utf-8"))
                    runtime = {k: data.get(k) for k in ("total_seconds", "peak_process_working_set_bytes", "cache_hit")}
                except (OSError, ValueError, AttributeError):
                    pass
            run = dict(self.run)
            run["elapsed_seconds"] = (round(time.monotonic() - run["started_at"], 1)
                                      if run["started_at"] is not None else run.get("elapsed_seconds", 0))
            # Never expose the process-monotonic timestamp as a wall clock.
            run.pop("started_at", None)
            data = self.root / "more-than-a-hack-2027-main/data/tactical"
            return {"app": "touchline-local-review", "version": "1.0", "mode": self.mode, "request_token": self.token,
                    "match": {"title": "Barcelona vs Athletic Club", "frames": FRAMES, "fps": FPS,
                              "home": "Barcelona", "away": "Athletic Club"},
                    "inputs": {"tracking_ready": True if self.demo else all((data / name).is_file() for name in
                              ("BAR-ATH_tactical_atd.xml", "BAR-ATH_tactical_atd.txt")),
                               "video_ready": False if self.demo else (data / "BAR-ATH_tactical.mp4").is_file()},
                    "output": output, "run": run, "runtime": runtime,
                    "model": {"name": "Noise-v2", "description": "Tracking geometry + small tree model + temporal possession decoding"},
                    "external_validation": {"match": "J03WMX", "clean_spell_f1": .4724602203182375,
                                            "occluded_spell_f1": .40137931034482754, "combined_spell_f1": .34654788418708243,
                                            "notice": "One independent provider match with simulated corruptions. Hidden challenge accuracy is unknown."},
                    "code_export_ready": self.code_zip.is_file()}

    def timeline(self):
        result = self.current()
        if not result["valid"]:
            raise ValueError("Generate a valid CSV before reviewing its timeline")
        return {"fps": FPS, "frames": FRAMES, "segments": result["segments"]}

    def start_run(self):
        with self.lock:
            if self.run["status"] == "running":
                return False
            self.run = {"status": "running", "message": "Generating and validating the complete frame CSV", "started_at": time.monotonic()}
            threading.Thread(target=self._run, name="touchline-inference", daemon=True).start()
            return True

    def _run(self):
        directory = None
        start = time.monotonic()
        try:
            directory = Path(tempfile.mkdtemp(prefix="run-", dir=self.work)).resolve()
            if directory.parent != self.work:
                raise ValueError("Run directory escaped review workspace")
            output, report = directory / "candidate.csv", directory / "run.json"
            if self.demo:
                demo_csv(output)
                result = inspect_csv(output)
                # Exercise the same actual official format validator in demo,
                # using invented predictions, never public/private answer keys.
                sys.path.insert(0, str(self.root / "more-than-a-hack-2027-main/evaluation"))
                import possession_metrics as pm
                reason = pm.validate_submission(pm.read_label_csv(output), FRAMES)
                if reason:
                    raise ValueError("Synthetic demonstration failed the official format checker")
                atomic_json(report, {"csv_sha256": result["sha256"], "total_seconds": time.monotonic() - start,
                                     "peak_process_working_set_bytes": None, "cache_hit": False, "synthetic_demo": True})
            else:
                command = [sys.executable, str(self.root / "tools/run_candidate.py"), "--out", str(output), "--report", str(report)]
                with (self.work / "last-run.log").open("w", encoding="utf-8") as log:
                    completed = subprocess.run(command, cwd=self.root, stdout=log, stderr=subprocess.STDOUT, timeout=300)
                if completed.returncode:
                    raise ValueError("Estimator failed. Details are saved locally in local/review-mvp/last-run.log")
                result = inspect_csv(output)
                provenance = json.loads(report.read_text(encoding="utf-8"))
                if (provenance.get("csv_sha256") != result["sha256"]
                        or provenance.get("official_format_validator") != "passed"
                        or provenance.get("config_sha256") != sha(self.root / "models/active.json")):
                    raise ValueError("Generated candidate provenance failed; previous output preserved")
                reference = self.root / "submissions/candidate.csv"
                if reference.is_file() and result["sha256"] != sha(reference):
                    raise ValueError("Regenerated CSV differs from the frozen review candidate; existing output preserved")
            with self.lock:
                os.replace(output, self.work / "candidate.csv")
                os.replace(report, self.work / "run.json")
                self.csv, self.report = self.work / "candidate.csv", self.work / "run.json"
                self.cached_key = None
                self.run = {"status": "complete", "message": "Complete frame CSV generated and validated", "started_at": None,
                            "elapsed_seconds": round(time.monotonic() - start, 3)}
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            with self.lock:
                self.run = {"status": "failed", "message": "The previous validated candidate is preserved", "error": str(error), "started_at": None}
        except Exception:
            with self.lock:
                self.run = {"status": "failed", "message": "The previous validated candidate is preserved", "error": "Generation could not finish; check local setup and retry", "started_at": None}
        finally:
            if directory is not None and directory.is_relative_to(self.work) and directory.parent == self.work:
                shutil.rmtree(directory, ignore_errors=True)

    def export(self, team, repository):
        from .exporting import build_code_export, build_review_pack
        if not self.export_lock.acquire(blocking=False):
            raise ValueError("Another review pack is being prepared; try again shortly")
        try:
            with self.lock:
                if not self.current()["valid"]:
                    raise ValueError("A valid prediction CSV is required before export")
                if not self.code_zip.is_file():
                    build_code_export(self.root, self.code_zip)
                destination = self.work / "review-pack.zip"
                result = build_review_pack(self.root, self.csv, self.code_zip, team, repository, destination, demo=self.demo)
                self.bundle = destination
                return {"download_url": "/download/review-pack", **{k: v for k, v in result.items() if k != "path"}}
        finally:
            self.export_lock.release()
