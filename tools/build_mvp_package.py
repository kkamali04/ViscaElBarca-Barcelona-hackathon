"""Build the allowlisted review app export, preserving the frozen estimator ZIP."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from review_app.exporting import build_code_export


if __name__ == "__main__":
    result = build_code_export(ROOT, ROOT / "local/mvp-code.zip")
    # Only aggregate code-package metadata; no private prediction records.
    import json
    (ROOT / "reports/mvp-code-package.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "path"}))
