"""Fetch fixed, independent Sportec/DFL validation matches with integrity checks.

Only public metadata and raw tracking are fetched, never event-derived labels.
Files stay under ignored local/external; originals are never overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request

MATCH_SPLITS = {"J03WOH": "development", "J03WOY": "validation", "J03WR9": "holdout"}
BASE = "https://huggingface.co/datasets/pysport/idsse-data"
ROOT = Path(__file__).resolve().parents[1]


def filename(match_id, kind):
    prefixes = {"meta": "DFL_02_01_matchinformation", "tracking": "DFL_04_03_positions_raw_observed"}
    return f"{prefixes[kind]}_DFL-COM-000002_DFL-MAT-{match_id}.xml"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_git_blob(path, entry):
    if entry.get("lfs"):
        return
    h = hashlib.sha1()
    h.update(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    if h.hexdigest() != entry["oid"]:
        raise ValueError(f"Non-LFS Git blob integrity check failed: {path}")


def download_one(entry, folder):
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / entry["path"]
    expected_size = entry["size"]
    expected_sha = entry.get("lfs", {}).get("oid")
    if destination.exists():
        actual_sha = digest(destination)
        if destination.stat().st_size != expected_size or (expected_sha and actual_sha != expected_sha):
            raise ValueError(f"Existing file failed integrity; retained without overwrite: {destination}")
        verify_git_blob(destination, entry)
        return {"path": str(destination.relative_to(ROOT)), "bytes": expected_size, "sha256": actual_sha, "reused": True}
    temporary = destination.with_suffix(".xml.part")
    if temporary.exists():
        raise FileExistsError(f"Incomplete download exists; inspect before retry: {temporary}")
    # Cache buster avoids expired signed LFS redirect URLs; credentials are not used.
    url = f"{BASE}/resolve/main/{entry['path']}?download=true&t={int(time.time())}"
    request = urllib.request.Request(url, headers={"User-Agent": "possession-independent-validation/1.0"})
    h = hashlib.sha256()
    total = 0
    with urllib.request.urlopen(request, timeout=120) as response, temporary.open("xb") as target:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            target.write(chunk)
            h.update(chunk)
            total += len(chunk)
    actual_sha = h.hexdigest()
    if total != expected_size or (expected_sha and actual_sha != expected_sha):
        raise ValueError(f"Downloaded file failed integrity; partial retained: {temporary}")
    verify_git_blob(temporary, entry)
    # No overwrite on Windows; another worker writing the target is an error.
    temporary.rename(destination)
    return {"path": str(destination.relative_to(ROOT)), "bytes": total, "sha256": actual_sha, "reused": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matches", nargs="+", choices=MATCH_SPLITS, default=list(MATCH_SPLITS))
    args = parser.parse_args()
    with urllib.request.urlopen("https://huggingface.co/api/datasets/pysport/idsse-data/tree/main", timeout=60) as response:
        listing = {item["path"]: item for item in json.load(response)}
    output = []
    for match_id in args.matches:
        for kind in ("meta", "tracking"):
            result = download_one(listing[filename(match_id, kind)], ROOT / "local" / "external" / match_id)
            result.update(match_id=match_id, split=MATCH_SPLITS[match_id], kind=kind, source=f"{BASE}/resolve/main/{filename(match_id, kind)}")
            output.append(result)
            print(json.dumps(result), flush=True)
    manifest = ROOT / "local" / "external" / "download-manifest.json"
    existing = json.loads(manifest.read_text()) if manifest.exists() else []
    entries = {entry["path"]: entry for entry in existing + output}
    manifest.write_text(json.dumps(list(entries.values()), indent=2) + "\n")


if __name__ == "__main__":
    main()
