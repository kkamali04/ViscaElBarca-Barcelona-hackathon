"""Acquire the predeclared fresh holdout by filename/integrity only; no parsing."""
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.fetch_validation_data import BASE, download_one


def main():
    with urllib.request.urlopen(BASE.replace("https://huggingface.co/datasets/", "https://huggingface.co/api/datasets/")+"/tree/main", timeout=60) as response:
        entries = json.load(response)
    wanted = [entry for entry in entries if "J03WMX" in entry["path"] and
              ("matchinformation" in entry["path"] or "positions_raw_observed" in entry["path"])]
    if len(wanted) != 2:
        raise ValueError("Fresh holdout requires exactly metadata and raw observed positions")
    results = []
    for entry in wanted:
        result = download_one(entry, ROOT/"local/external/J03WMX")
        result.update({"split": "noise-v2-fresh-holdout", "match": "J03WMX", "source": BASE+"/resolve/main/"+entry["path"], "labels_parsed": False})
        results.append(result)
        print(json.dumps(result), flush=True)
    (ROOT/"local/external/noise-v2-download-manifest.json").write_text(json.dumps(results, indent=2)+"\n")


if __name__ == "__main__":
    main()
