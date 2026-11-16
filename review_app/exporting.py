"""Deterministic, local-only exports. Restricted label bytes never leave this process.

Only the frozen estimator archive and explicitly named MVP source folders are
eligible for the public-code export. A review pack is PRIVATE and is never a
claim that registration, publication or competition submission has occurred.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import unicodedata
from urllib.parse import urlsplit
import zipfile

MAX_ENTRY_BYTES = 50_000_000
MAX_ARCHIVE_BYTES = 250_000_000
N_FRAMES = 199_319
_STAMP = (2026, 11, 15, 0, 0, 0)
_DEVICES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    prefix + digit for prefix in ("COM", "LPT") for digit in "123456789¹²³"
}
_REMOVED_TIMELINES = frozenset({
    "more-than-a-hack-2027-main/evaluation/gt/BAR-ATH_possession_gt_public.csv",
    "more-than-a-hack-2027-main/evaluation/gt/BAR-ATH_possession_gt_public_meta.json",
    *("more-than-a-hack-2027-main/evaluation/results/" + name for name in (
        "baseline_raw.csv", "baseline_smooth25.csv", "baseline_smooth50.csv", "baseline_smooth125.csv"
    )),
})


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(data: object) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _safe_member(name: str) -> str:
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("Unsafe archive member path")
    parts = name.split("/")
    if any(part in ("", ".", "..") or part[-1:] in (" ", ".") or
           any(ord(c) < 32 or ord(c) == 127 or c in ':<>\"|?*' for c in part) or
           part.split(".", 1)[0].upper() in _DEVICES for part in parts):
        raise ValueError("Unsafe archive member path")
    if PurePosixPath(name).is_absolute():
        raise ValueError("Unsafe archive member path")
    return name


def _root(root: Path) -> Path:
    result = Path(root).resolve(strict=True)
    if not result.is_dir():
        raise ValueError("Project root must be a directory")
    return result


def _inside(root: Path, path: Path, *, must_exist: bool = True) -> Path:
    path = Path(path)
    if not path.is_absolute():
        path = root / path
    if ".." in path.parts:
        raise ValueError("Parent traversal is not allowed")
    # Reject links/reparse points before resolving, including directory junctions.
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ValueError("Path must stay inside the project") from error
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        try:
            entry_stat = cursor.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(entry_stat.st_mode) or (
            getattr(entry_stat, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ):
            raise ValueError("Linked paths are not eligible for export")
    resolved = path.resolve(strict=must_exist)
    if not resolved.is_relative_to(root):
        raise ValueError("Path must stay inside the project")
    return resolved


def _read(root: Path, path: Path) -> tuple[Path, bytes]:
    resolved = _inside(root, path)
    file_stat = resolved.stat()
    if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size > MAX_ENTRY_BYTES:
        raise ValueError("Export source is not a regular file within the size limit")
    with resolved.open("rb") as stream:
        data = stream.read(MAX_ENTRY_BYTES + 1)
    if len(data) > MAX_ENTRY_BYTES or len(data) != file_stat.st_size:
        raise ValueError("Export source size changed or exceeded the limit")
    return resolved, data


def _destination(root: Path, destination: Path, protected: list[Path]) -> Path:
    result = _inside(root, destination, must_exist=False)
    if result.suffix.lower() != ".zip" or not any(
        result.is_relative_to(root / folder) and result != root / folder for folder in ("local", "submissions")
    ):
        raise ValueError("Export destination must be a ZIP under local/ or submissions/")
    for source in protected + [root / "local/submission-code.zip"]:
        if result == source or (result.exists() and source.exists() and os.path.samefile(result, source)):
            raise ValueError("Export destination aliases a protected source")
    if result.exists() and (not result.is_file() or result.stat().st_nlink > 1):
        raise ValueError("Export destination must not be linked or shared")
    return result


def _load_archive(data: bytes) -> dict[str, bytes]:
    members: dict[str, bytes] = {}
    folded: set[str] = set()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            total = 0
            for info in archive.infolist():
                name = _safe_member(info.filename)
                mode = info.external_attr >> 16
                if name.casefold() in folded or info.is_dir() or info.flag_bits & 1 or (
                    stat.S_IFMT(mode) not in (0, stat.S_IFREG)
                ) or info.file_size > MAX_ENTRY_BYTES:
                    raise ValueError("Archive contains a duplicate, linked, encrypted or oversized member")
                total += info.file_size
                if total > MAX_ARCHIVE_BYTES:
                    raise ValueError("Archive exceeds the total expanded size limit")
                folded.add(name.casefold())
                with archive.open(info) as stream:
                    payload = stream.read(MAX_ENTRY_BYTES + 1)
                if len(payload) != info.file_size or len(payload) > MAX_ENTRY_BYTES:
                    raise ValueError("Archive member size check failed")
                members[name] = payload
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as error:
        raise ValueError("Invalid code archive") from error
    return members


def _verify_package_manifest(members: dict[str, bytes]) -> dict:
    try:
        manifest = json.loads(members["PACKAGE_MANIFEST.json"])
        records = manifest["files"]
        expected: set[str] = set()
        for record in records:
            name = _safe_member(record["path"])
            if name in expected or name == "PACKAGE_MANIFEST.json":
                raise ValueError("Duplicate manifest member")
            expected.add(name)
            payload = members[name]
            if type(record["bytes"]) is not int or len(payload) != record["bytes"] or _hash(payload) != record["sha256"]:
                raise ValueError("Code package manifest integrity failed")
        if expected != set(members) - {"PACKAGE_MANIFEST.json"}:
            raise ValueError("Code package manifest does not describe the exact archive")
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("Code package manifest is missing or invalid") from error
    return manifest


def _verify_frozen(members: dict[str, bytes]) -> None:
    description = _verify_package_manifest(members)
    if description.get("restricted_assets_included") is not False:
        raise ValueError("Frozen package does not declare a code-only boundary")
    try:
        upstream = json.loads(members["reports/upstream-manifest.json"])
        seen: set[str] = set()
        for record in upstream["files"]:
            name = "more-than-a-hack-2027-main/" + _safe_member(record["path"])
            if name in seen:
                raise ValueError("Duplicate upstream provenance record")
            seen.add(name)
            payload = members[name]
            blob = b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload
            if len(payload) != record["size"] or hashlib.sha1(blob).hexdigest() != record["sha"]:
                raise ValueError("Frozen upstream provenance integrity failed")
        _verify_active(members)
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("Frozen provenance manifest is missing or invalid") from error


def _verify_active(members: dict[str, bytes]) -> None:
    try:
        active = json.loads(members["models/active.json"])
        if _hash(members[_safe_member(active["model"])]) != active["model_sha256"]:
            raise ValueError("Frozen model integrity failed")
        for name, digest in active["source_sha256"].items():
            if _hash(members[_safe_member(name)]) != digest:
                raise ValueError("Frozen active source integrity failed")
        for key, name in (("experiment_script_sha256", "experiments/noise_v2/run_experiment.py"),
                          ("corruption_script_sha256", "tools/check_robustness.py"),
                          ("protocol_sha256", "research/NOISE_V2_PROTOCOL.md")):
            if key in active and _hash(members[name]) != active[key]:
                raise ValueError("Frozen experiment provenance integrity failed")
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("Frozen active configuration is missing or invalid") from error


def _load_extracted_base(root: Path) -> tuple[dict[str, bytes], str, list[Path]]:
    """Read only members named by a previously exported MVP's exact manifest."""
    manifest_path, manifest_bytes = _read(root, root / "PACKAGE_MANIFEST.json")
    try:
        description = json.loads(manifest_bytes)
        if description.get("format") != "mvp-code-only-v1" or description.get("restricted_assets_included") is not False or description.get("prediction_timelines_included") is not False:
            raise ValueError("Fresh-copy export requires a validated MVP package manifest")
        frozen_hash = description["frozen_code_sha256"]
        if not re.fullmatch(r"[0-9a-f]{64}", frozen_hash):
            raise ValueError("Invalid frozen archive provenance hash")
        members = {"PACKAGE_MANIFEST.json": manifest_bytes}
        protected = [manifest_path]
        for record in description["files"]:
            name = _safe_member(record["path"])
            if name in members:
                raise ValueError("Duplicate extracted package record")
            source, data = _read(root, root / name)
            members[name] = data
            protected.append(source)
        _verify_package_manifest(members)
        _verify_active(members)
        original = json.loads(members["ESTIMATOR_PACKAGE_MANIFEST.json"])
        seen: set[str] = set()
        for record in original["files"]:
            name = _safe_member(record["path"])
            if name in seen:
                raise ValueError("Duplicate original estimator manifest record")
            seen.add(name)
            if name in _REMOVED_TIMELINES:
                continue
            payload = members["ESTIMATOR_README.md" if name == "README.md" else name]
            if len(payload) != record["bytes"] or _hash(payload) != record["sha256"]:
                raise ValueError("Retained estimator source integrity failed")
        retained = (seen - _REMOVED_TIMELINES - {"README.md"}) | {"ESTIMATOR_README.md", "ESTIMATOR_PACKAGE_MANIFEST.json"}
        mvp_names = {"README.md", "PACKAGE_MANIFEST.json", "MVP_TECHNICAL.md", "MVP_REVIEW.md", "review.ps1", "stop-review.ps1", "tools/build_mvp_package.py"}
        if any(name not in retained and name not in mvp_names and not name.startswith("review_app/") for name in members):
            raise ValueError("Extracted manifest contains a file outside the MVP source allowlist")
        return members, frozen_hash, protected
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("Extracted MVP package provenance is missing or invalid") from error


def _add_manifest(members: dict[str, bytes], **metadata: object) -> None:
    members["PACKAGE_MANIFEST.json"] = _json({
        **metadata,
        "manifest_path": "PACKAGE_MANIFEST.json",
        "manifest_self_excluded": True,
        "files": [{"path": name, "bytes": len(payload), "sha256": _hash(payload)}
                  for name, payload in sorted(members.items()) if name != "PACKAGE_MANIFEST.json"],
    })


def _write_zip(root: Path, destination: Path, members: dict[str, bytes], protected: list[Path]) -> dict:
    destination = _destination(root, destination, protected)
    if len({name.casefold() for name in members}) != len(members):
        raise ValueError("Export has conflicting archive member names")
    for name, payload in members.items():
        _safe_member(name)
        if len(payload) > MAX_ENTRY_BYTES:
            raise ValueError("Export member exceeds the size limit")
    if sum(map(len, members.values())) > MAX_ARCHIVE_BYTES:
        raise ValueError("Export exceeds the expanded size limit")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".mvp-export-", suffix=".zip.tmp", dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, payload in sorted(members.items()):
                info = zipfile.ZipInfo(name, date_time=_STAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, payload, compresslevel=9)
        # Recheck link/alias constraints immediately before atomic replacement.
        _destination(root, destination, protected)
        data = temporary.read_bytes()
        result = {"path": str(destination), "sha256": _hash(data), "bytes": len(data), "files": len(members)}
        os.replace(temporary, destination)
        return result
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def build_code_export(root: Path, destination: Path) -> dict:
    """Build an atomic deterministic public-code candidate from the frozen ZIP.

    No data directories are swept. A prior destination survives all validation
    failures. The original estimator ZIP is a protected immutable input.
    """
    root = _root(root)
    frozen = root / "local/submission-code.zip"
    if frozen.exists() or frozen.is_symlink():
        frozen, payload = _read(root, frozen)
        members = _load_archive(payload)
        _verify_frozen(members)
        frozen_hash = _hash(payload)
        excluded = sorted(name for name in members if name in _REMOVED_TIMELINES)
        for name in excluded:
            del members[name]
        members["ESTIMATOR_README.md"] = members.pop("README.md")
        members["ESTIMATOR_PACKAGE_MANIFEST.json"] = members.pop("PACKAGE_MANIFEST.json")
        protected = [frozen]
    else:
        members, frozen_hash, protected = _load_extracted_base(root)
        excluded = sorted(_REMOVED_TIMELINES)
        for name in list(members):
            if name.startswith("review_app/") or name in {"README.md", "PACKAGE_MANIFEST.json", "MVP_TECHNICAL.md", "MVP_REVIEW.md", "review.ps1", "stop-review.ps1", "tools/build_mvp_package.py"}:
                del members[name]
    destination = _destination(root, destination, protected)
    # Full timeline/prediction exports are never eligible, even in a modified base.
    if any((name.lower().endswith((".csv", ".npy", ".npz", ".mp4", ".txt")) and
            not name.rsplit("/", 1)[-1].startswith("requirements")) or
           any(part.lower() in {"local", "submissions", ".venv", "venv", "__pycache__", ".git", "node_modules"} or
               part.lower().startswith((".env", "credentials", "token")) for part in name.split("/"))
           for name in members):
        raise ValueError("Frozen code archive contains a data or prediction artifact")
    required = ["MVP_TECHNICAL.md", "MVP_REVIEW.md", "review.ps1", "stop-review.ps1"]
    review = _inside(root, root / "review_app")
    static_folder = _inside(root, review / "static")
    if not review.is_dir() or not static_folder.is_dir():
        raise ValueError("Required review application/static folder is absent")
    sources = sorted(p for p in review.rglob("*.py") if "__pycache__" not in p.parts)
    static_sources = [static_folder / name for name in ("index.html", "app.css", "app.js")]
    if not sources:
        raise ValueError("Required review application source or static assets are absent")
    sources += static_sources + [root / name for name in required]
    optional = root / "tools/build_mvp_package.py"
    if optional.exists() or optional.is_symlink():
        sources.append(optional)
    for source in sources:
        source, data = _read(root, source)
        name = _safe_member(source.relative_to(root).as_posix())
        if name in members:
            raise ValueError("MVP source collides with a frozen estimator member")
        if any(existing.casefold() == name.casefold() for existing in members):
            raise ValueError("MVP source has a case-insensitive archive collision")
        members[name] = data
        protected.append(source)
    members["README.md"] = members["MVP_REVIEW.md"]
    _add_manifest(members, format="mvp-code-only-v1", release="noise-v2-with-local-review-v1",
                  restricted_assets_included=False, prediction_timelines_included=False,
                  frozen_code_sha256=frozen_hash, excluded_frozen_members=excluded,
                  upstream_manifest_scope="Historical upstream repository provenance; not this archive's member allowlist.")
    return _write_zip(root, destination, members, protected)


def _team(team_name: str) -> tuple[str, str]:
    if not isinstance(team_name, str) or not 1 <= len(team_name) <= 80 or team_name != team_name.strip() or not any(c.isalnum() for c in team_name):
        raise ValueError("A meaningful team name of 1 to 80 characters is required")
    if any(unicodedata.category(c).startswith("C") or c in '/\\:<>\"|?*' for c in team_name) or ".." in team_name or team_name.endswith("."):
        raise ValueError("Team name contains unsafe filename characters")
    if team_name.split(".", 1)[0].upper() in _DEVICES:
        raise ValueError("Team name is a reserved Windows device name")
    ascii_name = unicodedata.normalize("NFKD", team_name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    if not slug:
        slug = "team-" + _hash(team_name.encode("utf-8"))[:12]
    if slug.upper() in _DEVICES:
        slug = "team-" + slug
    return team_name, slug


def _repository(repository_url: str) -> str:
    if not isinstance(repository_url, str):
        raise ValueError("Repository URL must be a string")
    if not repository_url:
        return ""
    if any(c.isspace() or unicodedata.category(c).startswith("C") for c in repository_url):
        raise ValueError("Repository URL must be a public GitHub HTTPS URL")
    try:
        parsed = urlsplit(repository_url)
        if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or "?" in repository_url or "#" in repository_url:
            raise ValueError
        match = re.fullmatch(r"/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/([A-Za-z0-9_.-]{1,100})", parsed.path)
        if not match or match[1].endswith("-") or match[2] in (".", ".."):
            raise ValueError
    except ValueError as error:
        raise ValueError("Repository URL must be a public GitHub HTTPS owner/repository URL without credentials or parameters") from error
    return "https://github.com" + parsed.path


def _markdown(text: str) -> str:
    # Escape user text before replacing either placeholder. One replacement pass
    # prevents a literal placeholder in a team name from being reinterpreted.
    return re.sub(r"([\\`*_{}\[\]<>()!|#])", r"\\\1", text.replace("&", "&amp;"))


def _validate_csv(payload: bytes) -> None:
    try:
        reader = csv.reader(io.StringIO(payload.decode("utf-8"), newline=""), strict=True)
        if next(reader, None) != ["frame", "label"]:
            raise ValueError
        count = 0
        for count, row in enumerate(reader, 1):
            if count > N_FRAMES or len(row) != 2 or row[0] != str(count - 1) or row[1] not in ("H", "A", "D", "X"):
                raise ValueError
        if count != N_FRAMES:
            raise ValueError
    except (UnicodeDecodeError, csv.Error, ValueError) as error:
        # Never echo restricted rows, labels, parser excerpts or label sequences.
        raise ValueError("CSV must have the exact frame,label header and ordered frames 0..199318 with H/A/D/X labels") from None


def build_review_pack(root: Path, csv_path: Path, code_zip: Path, team_name: str,
                      repository_url: str, destination: Path, *, demo: bool = False) -> dict:
    """Build a PRIVATE review ZIP; never publish or mark it submission-ready."""
    if type(demo) is not bool:
        raise ValueError("Demo marker must be a boolean")
    root = _root(root)
    display_name, slug = _team(team_name)
    repository_url = _repository(repository_url)
    csv_path, csv_bytes = _read(root, csv_path)
    code_zip, code_bytes = _read(root, code_zip)
    technical_path, technical_bytes = _read(root, root / "MVP_TECHNICAL.md")
    protected = [csv_path, code_zip, technical_path, root / "MVP_REVIEW.md"]
    destination = _destination(root, destination, protected)
    _validate_csv(csv_bytes)
    code_members = _load_archive(code_bytes)
    code_manifest = _verify_package_manifest(code_members)
    if code_manifest.get("format") != "mvp-code-only-v1" or code_manifest.get("restricted_assets_included") is not False or code_manifest.get("prediction_timelines_included") is not False:
        raise ValueError("Review pack requires an MVP code-only export")
    try:
        template = technical_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Technical document must be UTF-8") from error
    if "{{TEAM_NAME}}" not in template or "{{REPOSITORY_URL}}" not in template:
        raise ValueError("Technical document is missing required team/repository placeholders")
    replacement = {"TEAM_NAME": _markdown(display_name), "REPOSITORY_URL": repository_url or "Pending public repository publication and verification"}
    document = re.sub(r"\{\{(TEAM_NAME|REPOSITORY_URL)\}\}", lambda match: replacement[match[1]], template)
    if demo:
        document = ("# DEMO — synthetic demonstration only\n\n"
                    "This private pack contains an invented synthetic CSV for testing the review workflow. "
                    "It is not the match prediction or a competition deliverable. Training, external-match "
                    "metrics and runtime measurements below describe the historical frozen estimator, "
                    "not this demonstration's accuracy, training or performance.\n\n" + document)
    marker = "DEMO-" if demo else ""
    csv_name, document_name, code_name = marker + slug + ".csv", marker + slug + ".md", marker + slug + "-code-only.zip"
    pending = ["Confirm the exact registered team name and registration/eligibility.",
               "Review the exact CSV and technical document and the organiser email/form requirements.",
               "Explicit owner authorization is required for publication and competition submission.",
               "No publication, form submission or receipt is represented by this pack."]
    if not repository_url:
        pending.insert(1, "Publish an authorized project-only public code repository and supply its URL.")
    else:
        pending.insert(1, "Independently verify that the supplied repository URL is public and reproduces the exact CSV.")
    if demo:
        pending.insert(0, "DEMO: replace the synthetic CSV with an actual algorithmic match output before final review.")
    readme = ("# " + ("DEMO — " if demo else "") + "PRIVATE local review pack\n\n"
              "This ZIP is private because its possession CSV is a reconstructable match prediction. "
              "Never put the CSV, this outer ZIP, restricted inputs, videos or timelines in a public repository. "
              "Only the nested code-only ZIP is a candidate for separately authorized public publication.\n\n"
              + ("DEMO: the CSV is synthetic test data, not actual match results.\n\n" if demo else "")
              + "CSV bytes are copied exactly after checking all 199319 ordered frames and the H/A/D/X contract. "
              "A valid format does not establish accuracy, registration, public repository availability or submission. "
              "Member sizes and SHA256 values are in PACKAGE_MANIFEST.json; the manifest excludes itself.\n\n"
              + "Pending owner review:\n\n" + "".join("- " + item + "\n" for item in pending)).encode("utf-8")
    members = {csv_name: csv_bytes, document_name: document.encode("utf-8"), code_name: code_bytes, "README.md": readme}
    _add_manifest(members, format="private-mvp-review-v1", private=True, submission_ready=False,
                  demo=bool(demo), synthetic_demonstration=bool(demo), team_name=display_name,
                  repository_url=repository_url, repository_publication_verified=False,
                  csv_contract={"rows": N_FRAMES, "first_frame": 0, "last_frame": N_FRAMES - 1, "validation": "strict-independent-complete-contract"},
                  input_sha256={"csv": _hash(csv_bytes), "code_zip": _hash(code_bytes), "technical_template": _hash(technical_bytes)},
                  pending=pending)
    result = _write_zip(root, destination, members, protected)
    return {**result, "filename": destination.name, "files": sorted(members), "submission_ready": False, "pending": pending}
