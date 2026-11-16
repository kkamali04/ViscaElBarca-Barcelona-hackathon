"""Immutable study bindings and one-shot process-bound consumption authority.

Wire format: every JSONL event has the exact keys EVENT_KEYS, schema_version=1,
sequence starting at 1, previous_digest (64 zeroes at genesis), and event_digest
SHA256 of canonical JSON excluding event_digest. A newline is mandatory. Payload
is closed by event kind. register carries study_path; history carries prior_roles;
reserve/first_access/interrupted have empty payload; child carries child_pid and
child_creation_time; finish/finalize carry result path/bytes/SHA256. finalize is
metadata-only recovery of a sealed complete result after interruption; it never
restores authority. All events include
UTC, study/attempt IDs, whole fixture cohort, role, owner PID+creation, and status.

The Windows byte-range OS lock encloses replay, stale-owner interruption,
eligibility, append and fsync. Lock-file existence is never ownership evidence.
There is no tail repair, stale-lock reset, unreserve, retry or parser here.
Raw member hash/identity verification is additionally performed under T03's held
read leases; this module binds their complete catalog before authority is issued.
Private synthetic controls are supported by explicit register/reserve calls;
normal CLI accepts only ROOT/local/v3-control. Loading a study registers its
location for subsequent capability checks in that process. New normal processes
bootstrap lookup from the canonical ledger's durable register event.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import ast
import ctypes
from ctypes import wintypes
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import sys
import time
from typing import Mapping
import uuid

from .contracts import AccessCapability, Role

ROOT = Path(__file__).resolve().parents[2]
ZERO = "0" * 64
_LOCATIONS: dict[str, tuple[Path, Path]] = {}
_CONTROL_BY_PATH: dict[Path, Path] = {}
# Required prefit/runtime science identity, matching the frozen observation-only
# cache verifier's REQUIRED_SCIENTIFIC_PATHS. Never import that verifier merely
# to discover this allowlist (guard/cache have intentionally separate authority).
_REQUIRED_SCIENTIFIC_PATHS = frozenset(
    ["experiments/v3/" + name + ".py" for name in
     ("__init__", "contracts", "guard", "cache", "adapter", "corruption", "fetch", "boundary", "decoder", "training", "evaluate", "resources", "core", "cli")]
    + ["possession_model/" + name + ".py" for name in
       ("__init__", "features", "schema", "evidence", "trees", "decoder", "pipeline")]
    + ["experiments/__init__.py", "experiments/noise_v2/__init__.py", "experiments/noise_v2/features.py",
       "validation/sportec.py", "validation/metrics.py", "tools/train_and_validate.py", "tools/run_candidate.py",
       "more-than-a-hack-2027-main/evaluation/possession_metrics.py",
       "more-than-a-hack-2027-main/evaluation/validate_submission.py",
       "more-than-a-hack-2027-main/games.py", "more-than-a-hack-2027-main/FAQ.md"])
_STUDY_KEYS = {"schema_version", "study_id", "protocol_digest", "catalog_digest",
               "scientific_closure_digest", "environment_digest", "comparator_digest",
               "prior_snapshot_digest", "ledger_checkpoint", "raw_root", "catalog_path",
               "model_seal_path", "artifact_bindings"}
EVENT_KEYS = {"schema_version", "sequence", "previous_digest", "event_digest", "utc",
              "kind", "study_digest", "attempt_id", "fixture_ids", "role", "process_id",
              "process_creation_time", "status", "payload"}


class AccessError(ValueError):
    """Preflight/schema/access failure (CLI exit 2)."""


class IntegrityError(AccessError):
    """Changed or corrupt registered artifact (CLI exit 3)."""


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise IntegrityError("duplicate JSON key")
        out[key] = value
    return out


def read_json(path: Path) -> dict:
    try:
        value = json.loads(Path(path).read_bytes(), object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(IntegrityError("nonfinite JSON")))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IntegrityError("unreadable JSON artifact") from exc
    if type(value) is not dict:
        raise IntegrityError("JSON object required")
    return value


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def _digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _hex(value, length=64):
    return type(value) is str and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None


def _keys(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise IntegrityError("unknown/missing schema keys")


def _identity(value, keys):
    """Closed content identity: JSON bool/float can never masquerade as bytes."""
    _keys(value, keys)
    if type(value["bytes"]) is not int or value["bytes"] < 0 or not _hex(value["sha256"]):
        raise IntegrityError("invalid exact byte-size/SHA256 identity")


def _same(left, right):
    """Structural JSON equality with boolean/number types kept distinct."""
    if type(left) is bool or type(right) is bool:
        return type(left) is type(right) and left == right
    if type(left) in (int, float) or type(right) in (int, float):
        return type(left) in (int, float) and type(right) in (int, float) and left == right
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(_same(left[k], right[k]) for k in left)
    if type(left) is list:
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    return left == right


def _plain(path: Path, *, missing=False) -> Path:
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.exists():
            info = part.lstat()
            if part.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                raise AccessError("symlink/reparse path prohibited")
    if not missing and not path.exists():
        raise AccessError("required path absent")
    if path.exists() and path.is_file() and path.stat().st_nlink != 1:
        raise AccessError("hardlinked artifacts prohibited")
    return path


def _relative(name: str) -> str:
    if type(name) is not str or not name or "\\" in name or ":" in name:
        raise AccessError("normalized relative path required")
    p = PurePosixPath(name)
    if p.is_absolute() or any(x in (".", "..", "") for x in name.split("/")):
        raise AccessError("path traversal prohibited")
    return p.as_posix()


def _under(root: Path, name: str, *, missing=False):
    name = _relative(name)
    path = _plain(root / name, missing=missing)
    if not path.is_relative_to(_plain(root)):
        raise AccessError("path outside registered root")
    return path


def _write_once(path: Path, value):
    path = _plain(path, missing=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    with temporary.open("xb") as stream:
        stream.write(canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    try:
        # Windows rename refuses an existing target; use link on POSIX for the
        # same no-replace guarantee in synthetic portability tests.
        if os.name == "nt":
            temporary.rename(path)
        else:
            os.link(temporary, path)
            temporary.unlink()
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def process_creation_time(pid: int | None = None) -> str:
    pid = os.getpid() if pid is None else pid
    if type(pid) is not int or pid <= 0:
        raise AccessError("invalid PID")
    if os.name == "nt":
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.OpenProcess.restype = wintypes.HANDLE
        k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.WaitForSingleObject.restype = wintypes.DWORD
        handle = k.OpenProcess(0x1000 | 0x100000, False, pid)
        if not handle:
            raise AccessError("process identity unavailable")
        try:
            if k.WaitForSingleObject(handle, 0) != 258:  # WAIT_TIMEOUT = live
                raise AccessError("process is no longer live")
            values = [wintypes.FILETIME() for _ in range(4)]
            if not k.GetProcessTimes(handle, *[ctypes.byref(x) for x in values]):
                raise AccessError("process creation time unavailable")
            return str((values[0].dwHighDateTime << 32) | values[0].dwLowDateTime)
        finally:
            k.CloseHandle(handle)
    try:
        # Linux fixture-only fallback: kernel start ticks, not wall-clock guess.
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError) as exc:
        raise AccessError("process identity unavailable") from exc


def _alive(pid, created):
    try:
        return process_creation_time(pid) == created
    except AccessError:
        return False


def _parent_process_id(pid: int) -> int:
    """Read the kernel's parent PID; never infer ancestry from process names."""
    if os.name != "nt":
        try:
            return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError) as exc:
            raise AccessError("process ancestry unavailable") from exc
    class BasicInformation(ctypes.Structure):
        _fields_ = [(name, ctypes.c_void_p) for name in
                    ("Reserved1", "PebBaseAddress", "Reserved2a", "Reserved2b", "UniqueProcessId", "ParentProcessId")]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    query = ctypes.WinDLL("ntdll").NtQueryInformationProcess
    query.argtypes = [wintypes.HANDLE, wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG, ctypes.POINTER(wintypes.ULONG)]
    query.restype = wintypes.LONG
    handle = kernel.OpenProcess(0x0400, False, pid)
    if not handle:
        raise AccessError("process ancestry unavailable")
    try:
        info, returned = BasicInformation(), wintypes.ULONG()
        if query(handle, 0, ctypes.byref(info), ctypes.sizeof(info), ctypes.byref(returned)) != 0 or info.UniqueProcessId != pid:
            raise AccessError("process ancestry unavailable")
        return int(info.ParentProcessId or 0)
    finally:
        kernel.CloseHandle(handle)


def _assert_descendant(owner_pid: int, owner_created: str, child_pid: int, child_created: str) -> None:
    """Prove a live descendant chain, including launcher intermediaries.

    Each link is read between matching live creation-time observations. A reused
    parent PID cannot identify an ancestor born after its child. Any inaccessible,
    dead, cyclic or stale link fails closed; arbitrary siblings receive no grant.
    """
    if owner_pid == child_pid or not _alive(owner_pid, owner_created) or not _alive(child_pid, child_created):
        raise AccessError("exact live descendant identity required")
    current, created, seen = child_pid, child_created, set()
    try:
        for _ in range(128):
            if current in seen or process_creation_time(current) != created:
                raise AccessError("stale or cyclic process ancestry")
            seen.add(current)
            parent = _parent_process_id(current)
            if type(parent) is not int or parent <= 0 or parent == current or process_creation_time(current) != created:
                raise AccessError("process ancestry unavailable")
            parent_created = process_creation_time(parent)
            if int(parent_created) > int(created):
                raise AccessError("reused parent PID is not an ancestor")
            if parent == owner_pid:
                if parent_created != owner_created or not _alive(owner_pid, owner_created) or not _alive(child_pid, child_created):
                    raise AccessError("process ancestry identity changed")
                return
            current, created = parent, parent_created
    except (OSError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise AccessError("verified live owner ancestry required") from exc
    raise AccessError("owner not in bounded process ancestry")


@contextmanager
def _locked(control: Path):
    control = _plain(control, missing=True)
    control.mkdir(parents=True, exist_ok=True)
    lock = _plain(control / "ledger.lock", missing=True)
    with lock.open("a+b") as stream:
        if stream.seek(0, 2) == 0:
            stream.write(b"\0")
            stream.flush()
            os.fsync(stream.fileno())
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            # LK_NBLCK retry without msvcrt's fixed ten-second timeout.
            deadline = time.monotonic() + 30
            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise AccessError("control lock unavailable")
                    time.sleep(.01)
            try:
                yield control
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield control
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


def _replay(control):
    ledger = _plain(control / "consumption.jsonl", missing=True)
    if not ledger.exists():
        return []
    raw = ledger.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise IntegrityError("partial ledger tail")
    events = []
    for line in raw.splitlines():
        try:
            event = json.loads(line, object_pairs_hook=_pairs)
        except (ValueError, UnicodeError) as exc:
            raise IntegrityError("corrupt ledger") from exc
        _keys(event, EVENT_KEYS)
        if type(event["sequence"]) is not int or event["sequence"] != len(events) + 1:
            raise IntegrityError("nonmonotone ledger")
        previous = events[-1]["event_digest"] if events else ZERO
        body = {k: v for k, v in event.items() if k != "event_digest"}
        if type(event["schema_version"]) is not int or event["schema_version"] != 1 or event["previous_digest"] != previous or event["event_digest"] != _digest(body):
            raise IntegrityError("ledger hash chain mismatch")
        payload_keys = {"history": {"prior_roles"}, "register": {"study_path"}, "reserve": set(),
                        "first_access": set(), "child": {"child_pid", "child_creation_time"},
                        "finish": {"result", "bytes", "sha256"}, "finalize": {"result", "bytes", "sha256"}, "interrupted": set()}
        if event["kind"] not in payload_keys:
            raise IntegrityError("unknown ledger event")
        _keys(event["payload"], payload_keys[event["kind"]])
        if event["kind"] in ("finish", "finalize"):
            _identity(event["payload"], {"result", "bytes", "sha256"})
            if type(event["payload"]["result"]) is not str or not event["payload"]["result"]:
                raise IntegrityError("invalid ledger result path")
        elif event["kind"] == "child":
            if (type(event["payload"]["child_pid"]) is not int or event["payload"]["child_pid"] <= 0
                    or type(event["payload"]["child_creation_time"]) is not str or not event["payload"]["child_creation_time"].isdecimal()):
                raise IntegrityError("invalid ledger child identity")
        if (type(event["fixture_ids"]) is not list or len(set(event["fixture_ids"])) != len(event["fixture_ids"])
                or any(type(x) is not str or not x for x in event["fixture_ids"])):
            raise IntegrityError("invalid ledger cohort")
        if event["role"] not in ("train", "selection", "test", None) or type(event["process_id"]) is not int:
            raise IntegrityError("invalid ledger identity")
        if type(event["process_creation_time"]) is not str or type(event["utc"]) is not str:
            raise IntegrityError("invalid ledger timestamps")
        if not _hex(event["study_digest"]) or type(event["attempt_id"]) is not str:
            raise IntegrityError("invalid ledger provenance")
        if event["kind"] in ("reserve", "first_access", "child") and event["status"] != "active":
            raise IntegrityError("invalid active ledger status")
        if event["kind"] in ("finish", "finalize", "interrupted") and event["status"] not in ("complete", "failed", "interrupted"):
            raise IntegrityError("invalid terminal ledger status")
        if event["kind"] not in ("history", "register", "reserve"):
            reservations = [e for e in events if e["kind"] == "reserve" and e["attempt_id"] == event["attempt_id"]]
            if len(reservations) != 1:
                raise IntegrityError("event without reservation")
            owner = reservations[0]
            for key in ("study_digest", "role", "fixture_ids", "process_id", "process_creation_time"):
                if event[key] != owner[key]:
                    raise IntegrityError("event changed reservation identity")
            terminal = [e for e in events if e["attempt_id"] == owner["attempt_id"] and e["kind"] in ("finish", "interrupted", "finalize")]
            if event["kind"] == "finalize":
                if len(terminal) != 1 or terminal[0]["kind"] != "interrupted" or event["status"] != "complete":
                    raise IntegrityError("invalid metadata-only restart finalization")
            elif terminal:
                raise IntegrityError("event after terminal attempt")
        events.append(event)
    return events


def _append(control, events, kind, *, study=ZERO, attempt="", fixtures=(), role=None,
            pid=None, created=None, status="active", payload=None):
    pid = os.getpid() if pid is None else pid
    event = {"schema_version": 1, "sequence": len(events) + 1,
             "previous_digest": events[-1]["event_digest"] if events else ZERO,
             "utc": datetime.now(timezone.utc).isoformat(), "kind": kind,
             "study_digest": study, "attempt_id": attempt, "fixture_ids": list(fixtures),
             "role": role, "process_id": pid, "process_creation_time": created or process_creation_time(pid),
             "status": status, "payload": {} if payload is None else payload}
    event["event_digest"] = _digest(event)
    with (control / "consumption.jsonl").open("ab") as stream:
        stream.write(canonical(event) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    events.append(event)
    return event


def _append_for(control, events, kind, owner, **kwargs):
    return _append(control, events, kind, study=owner["study_digest"], attempt=owner["attempt_id"],
                   fixtures=owner["fixture_ids"], role=owner["role"], pid=owner["process_id"],
                   created=owner["process_creation_time"], **kwargs)


def _interrupt_dead(control, events):
    for owner in list(events):
        if owner["kind"] != "reserve":
            continue
        terminal = any(e["attempt_id"] == owner["attempt_id"] and e["kind"] in ("finish", "interrupted") for e in events)
        if not terminal and not _alive(owner["process_id"], owner["process_creation_time"]):
            _append_for(control, events, "interrupted", owner, status="interrupted")


def _environment():
    installed = sorted((d.metadata["Name"].lower(), d.version) for d in importlib.metadata.distributions())
    versions = dict(installed)
    if platform.python_version() != "3.13.12" or any(versions.get(k) != v for k, v in
            {"numpy": "2.4.4", "scikit-learn": "1.9.1", "scipy": "1.18.1"}.items()):
        raise AccessError("locked training environment mismatch; no automatic upgrade")
    return {"python": platform.python_version(), "implementation": platform.python_implementation(),
            "platform": sys.platform, "packages": installed}


def _binding(root, path):
    path = _plain(path)
    if not path.is_file() or not path.is_relative_to(root):
        raise AccessError("artifact outside project")
    return {"relative_path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)}


def _catalog(path, protocol, root):
    value = read_json(path)
    _keys(value, {"schema_version", "provider", "raw_root", "metadata_overlap_receipt_digest", "fixtures"})
    if type(value["schema_version"]) is not int or value["schema_version"] != 1 or value["provider"] != "IDSSE" or not _hex(value["metadata_overlap_receipt_digest"]):
        raise IntegrityError("incomplete source catalog")
    raw = _plain(Path(value["raw_root"]), missing=True)
    if str(raw) != value["raw_root"] or raw != root / "local/v3-data/originals":
        raise AccessError("raw_root must be canonical local/v3-data/originals")
    expected = {x: role for role in ("train", "selection", "test") for x in protocol["split"][role]}
    record_map = value["fixtures"]
    if type(record_map) is not dict or set(record_map) != set(expected):
        raise IntegrityError("exact five fixture records required")
    records = list(record_map.values())
    seen, paths = set(), set()
    for record in records:
        _keys(record, {"fixture_id", "canonical_fixture_id", "duplicate_group", "role", "fps", "license", "metadata", "tracking"})
        fixture = record["fixture_id"]
        if fixture in seen or fixture not in expected or record_map.get(fixture) is not record or record["role"] != expected[fixture] or record["fps"] != 25:
            raise IntegrityError("catalog split/fps mismatch")
        seen.add(fixture)
        if not all(type(record[k]) is str and record[k] for k in ("canonical_fixture_id", "duplicate_group")):
            raise IntegrityError("missing metadata identity")
        _keys(record["license"], {"spdx", "attribution_receipt_digest"})
        if record["license"]["spdx"] != "CC-BY-4.0" or not _hex(record["license"]["attribution_receipt_digest"]):
            raise IntegrityError("license/attribution binding required")
        for kind in ("metadata", "tracking"):
            entry = record[kind]
            _identity(entry, {"kind", "relative_path", "source_url", "bytes", "sha256", "md5"})
            relative = _relative(entry["relative_path"])
            if (entry["kind"] != kind or relative.casefold() in paths or type(entry["bytes"]) is not int
                    or entry["bytes"] <= 0 or not _hex(entry["sha256"]) or not _hex(entry["md5"], 32)
                    or type(entry["source_url"]) is not str or not entry["source_url"].startswith("https://")):
                raise IntegrityError("incomplete source member identity")
            paths.add(relative.casefold())
            _plain(raw / relative, missing=True)
    if len({r["canonical_fixture_id"] for r in records}) != len(records) or len({r["duplicate_group"] for r in records}) != len(records):
        raise IntegrityError("overlapping allocated fixtures")
    return value


def _dynamic_import_requests(tree, relative_path, closure):
    """Statically close literal import APIs; refuse computed/escaping importers.

    Importlib/builtins import aliases and simple assignment aliases are supported.
    import_module permits a literal absolute name or literal relative name/package.
    __import__ permits a literal absolute name, literal tuple/list fromlist and
    exact zero level; globals/locals do not affect absolute resolution. Relative
    builtin imports and indirect importer extraction require explicit source
    imports instead. This is dependency discovery, not an arbitrary-code sandbox.

    The only computed request is the reviewed CLI _module helper, checked against
    its exact namespace/body and finite literal/conditional-literal call sites.
    Both protocol target lists close that dispatcher; release implementations
    retain their separate later binding and are not traversed here.
    """
    nodes = list(ast.walk(tree))
    parents = {child: node for node in nodes for child in ast.iter_child_nodes(node)}
    modules, importers = {}, {"__import__": "builtin"}
    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("importlib", "builtins") or (not alias.asname and alias.name.startswith("importlib.")):
                    modules[alias.asname or alias.name.split(".")[0]] = alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and not node.level:
            for alias in node.names:
                if node.module == "importlib" and alias.name == "import_module":
                    importers[alias.asname or alias.name] = "importlib"
                elif node.module == "builtins" and alias.name == "__import__":
                    importers[alias.asname or alias.name] = "builtin"

    def module_kind(node):
        return modules.get(node.id) if isinstance(node, ast.Name) else None

    def importer_kind(node):
        if isinstance(node, ast.Name):
            return importers.get(node.id)
        if isinstance(node, ast.Attribute):
            kind = module_kind(node.value)
            if kind == "importlib" and node.attr == "import_module":
                return "importlib"
            if kind == "builtins" and node.attr == "__import__":
                return "builtin"
        return None

    def assignment(node):
        if isinstance(node, ast.Assign):
            return node.targets, node.value
        if isinstance(node, ast.AnnAssign) and node.value is not None:
            return [node.target], node.value
        return [], None

    # Order-independent finite alias closure also sees imports inside functions.
    # Ambiguous reassignment/escaping APIs refuse rather than guessing a scope.
    for _ in range(len(nodes) + 1):
        changed = False
        for node in nodes:
            targets, value = assignment(node)
            kind, module = importer_kind(value), module_kind(value)
            if kind or module:
                for target in targets:
                    if not isinstance(target, ast.Name):
                        raise AccessError("unsupported dynamic importer alias")
                    table, expected = (importers, kind) if kind else (modules, module)
                    if target.id in table and table[target.id] != expected:
                        raise AccessError("ambiguous dynamic importer alias")
                    if target.id not in table:
                        table[target.id] = expected
                        changed = True
        if not changed:
            break

    dispatch_call = None
    if relative_path == "experiments/v3/cli.py":
        helpers = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_module"]
        if helpers:
            expected = ast.parse('def _module(name):\n return importlib.import_module("experiments.v3." + name)\n').body[0]
            if (len(helpers) != 1 or ast.dump(helpers[0]) != ast.dump(expected)
                    or modules.get("importlib") != "importlib"):
                raise AccessError("unsupported CLI dynamic import dispatcher")
            dispatch_call = helpers[0].body[0].value
            targets = {Path(n).stem for key in ("scientific_new_modules", "release_only_modules") for n in closure[key]}

            def finite_targets(value):
                if isinstance(value, ast.Constant) and type(value.value) is str:
                    return {value.value}
                if isinstance(value, ast.IfExp):
                    return finite_targets(value.body) | finite_targets(value.orelse)
                raise AccessError("computed CLI dispatch target")

            for node in nodes:
                if isinstance(node, ast.Name) and node.id == "_module":
                    parent = parents.get(node)
                    if (not isinstance(node.ctx, ast.Load) or not isinstance(parent, ast.Call)
                            or parent.func is not node or len(parent.args) != 1 or parent.keywords
                            or not finite_targets(parent.args[0]) <= targets):
                        raise AccessError("undeclared or escaping CLI dispatch target")

    def simple_alias_reference(node, parent):
        targets, value = assignment(parent)
        return value is node and targets and all(isinstance(t, ast.Name) for t in targets)

    for node in nodes:
        parent = parents.get(node)
        if importer_kind(node) and isinstance(getattr(node, "ctx", None), ast.Load):
            if not ((isinstance(parent, ast.Call) and parent.func is node) or simple_alias_reference(node, parent)):
                raise AccessError("escaping dynamic importer requires explicit imports")
        if module_kind(node) and isinstance(node.ctx, ast.Load):
            if not ((isinstance(parent, ast.Attribute) and parent.value is node) or simple_alias_reference(node, parent)):
                raise AccessError("indirect import module lookup requires explicit imports")
            if isinstance(parent, ast.Attribute) and parent.attr in ("__dict__", "__getattribute__"):
                raise AccessError("indirect import module lookup requires explicit imports")
        targets, value = assignment(node)
        for target in targets:
            if isinstance(target, ast.Name):
                if target.id in modules and module_kind(value) != modules[target.id]:
                    raise AccessError("reassigned dynamic import module")
                if target.id in importers and importer_kind(value) != importers[target.id]:
                    raise AccessError("reassigned dynamic importer")

    def arguments(call, signature, defaults):
        if len(call.args) > len(signature) or any(isinstance(a, ast.Starred) for a in call.args):
            raise AccessError("unsupported dynamic import arguments")
        values = dict(defaults)
        given = set()
        for key, value in zip(signature, call.args):
            values[key] = value
            given.add(key)
        for keyword in call.keywords:
            if keyword.arg not in signature or keyword.arg in given:
                raise AccessError("unsupported dynamic import keyword")
            values[keyword.arg] = keyword.value
            given.add(keyword.arg)
        if "name" not in given:
            raise AccessError("dynamic import requires literal name")
        return values

    def literal(value):
        if not isinstance(value, ast.Constant):
            raise AccessError("computed dynamic import requires explicit imports")
        return value.value

    def parts(name):
        if type(name) is not str or not name or any(not p.isidentifier() for p in name.split(".")):
            raise AccessError("unsupported dynamic module spelling")
        return name.split(".")

    requests = []
    for node in nodes:
        if not isinstance(node, ast.Call):
            continue
        kind = importer_kind(node.func)
        if kind is None:
            if isinstance(node.func, ast.Attribute) and node.func.attr in ("import_module", "__import__"):
                raise AccessError("unresolved dynamic importer")
            continue
        if node is dispatch_call:
            continue
        if kind == "importlib":
            values = arguments(node, ("name", "package"), {"package": ast.Constant(None)})
            name, package = literal(values["name"]), literal(values["package"])
            if type(name) is not str or not name or (package is not None and type(package) is not str):
                raise AccessError("dynamic import requires literal name/package")
            package_parts = parts(package) if package is not None else []
            level = len(name) - len(name.lstrip("."))
            if level:
                if not package_parts or level > len(package_parts):
                    raise AccessError("relative dynamic import outside literal package")
                base = package_parts[:len(package_parts) - level + 1]
                imported = base + (parts(name[level:]) if name[level:] else [])
            else:
                imported = parts(name)
            requests.append((imported, ()))
        else:
            values = arguments(node, ("name", "globals", "locals", "fromlist", "level"),
                               {"fromlist": ast.Tuple(elts=[], ctx=ast.Load()), "level": ast.Constant(0)})
            level = literal(values["level"])
            if type(level) is not int or level != 0:
                raise AccessError("relative builtin import requires literal import_module package")
            imported = parts(literal(values["name"]))
            members = values["fromlist"]
            if not isinstance(members, (ast.Tuple, ast.List)):
                raise AccessError("dynamic fromlist requires literal tuple/list")
            fromlist = []
            for member in members.elts:
                name = literal(member)
                parts(name)
                fromlist.append(name)
            requests.append((imported, fromlist))
    return requests


def _scientific_paths(root, protocol, roots=()):
    """Resolve local Python modules/packages recursively without importing them.

    Bind parent initializers, relative imported aliases and from-package imported
    submodules and supported literal dynamic imports. Computed/escaping dynamic
    imports fail closed except the validated finite CLI dispatcher. Namespace
    packages have no initializer bytes but their discovered
    local modules still bind. Unsupported local star imports fail closed. Release
    dispatch implementations retain the protocol's explicit later-closure boundary.
    """
    root = _plain(root)
    closure = protocol["fit"]["source_closure"]
    paths = [root / "experiments/v3" / n for n in closure["scientific_new_modules"]]
    paths += [root / name for name in _REQUIRED_SCIENTIFIC_PATHS]
    # Every bound Python root, including catalog preparation and accepted
    # comparator helpers, contributes its transitive imports to the same graph.
    # Other bound artifacts are opaque content identities, never decoded here.
    paths += list(roots)
    for folder in ("possession_model", "validation", "experiments/noise_v2"):
        directory = _plain(root / folder, missing=True)
        if directory.exists():
            paths += list(directory.glob("*.py"))
    paths += [root / "more-than-a-hack-2027-main/evaluation/possession_metrics.py"]
    release = {root / "experiments/v3" / n for n in closure["release_only_modules"]}

    def checked(path):
        path = _plain(path, missing=True)
        if not path.is_relative_to(root):
            raise AccessError("scientific source outside project")
        return path

    def resolve(parts, *, required=False):
        """Return discovered sources, whether local, and whether a package."""
        if not parts or any(not p.isidentifier() for p in parts):
            raise AccessError("unsupported local module spelling")
        sources, local, package = set(), False, False
        for count in range(1, len(parts) + 1):
            directory = checked(root.joinpath(*parts[:count]))
            initializer = checked(directory / "__init__.py")
            module = checked(directory.with_suffix(".py"))
            if initializer.is_file():
                sources.add(initializer)
                local, package = True, True
            elif module.is_file():
                local, package = True, False
                sources.add(module)
                if count != len(parts):
                    raise AccessError("module file cannot contain a local submodule")
            elif directory.is_dir():
                local, package = True, True  # namespace package
            else:
                if local and required:
                    raise AccessError("declared local scientific module absent")
                return sources, local, False
        return sources, local, package

    queue, found = list(paths), set()
    while queue:
        path = checked(queue.pop())
        if path in release:
            continue
        if not path.is_file():
            raise AccessError("scientific source absent")
        if path in found:
            continue
        found.add(path)
        if path.suffix != ".py":
            continue  # explicitly bound public policy bytes, never parsed as code
        # Importing any submodule executes every existing parent __init__.py.
        parent = path.parent
        while parent != root:
            initializer = checked(parent / "__init__.py")
            if initializer.is_file() and initializer not in found:
                queue.append(initializer)
            parent = parent.parent
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except (SyntaxError, UnicodeError) as exc:
            raise AccessError("unparseable scientific source") from exc
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    discovered, _, _ = resolve(alias.name.split("."), required=True)
                    queue.extend(discovered)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    package_parts = list(path.relative_to(root).parent.parts)
                    if node.level > len(package_parts):
                        raise AccessError("relative import outside project")
                    base = package_parts[:len(package_parts) - node.level + 1]
                    parts = base + (node.module.split(".") if node.module else [])
                else:
                    parts = node.module.split(".") if node.module else []
                discovered, local, package = resolve(parts, required=True)
                queue.extend(discovered)
                if local:
                    for alias in node.names:
                        if alias.name == "*":
                            raise AccessError("local star imports require explicit scientific imports")
                        if package:
                            alias_sources, _, _ = resolve(parts + alias.name.split("."))
                            queue.extend(alias_sources)
        for parts, fromlist in _dynamic_import_requests(tree, path.relative_to(root).as_posix(), closure):
            discovered, local, package = resolve(parts, required=True)
            queue.extend(discovered)
            if local and package:
                for member in fromlist:
                    discovered, _, _ = resolve(parts + member.split("."))
                    queue.extend(discovered)
    return found


def study_digest(study: Path) -> str:
    return sha256(_plain(study))


def _checkpoint(events):
    return {"sequence": len(events), "digest": events[-1]["event_digest"] if events else ZERO}


def _prefix(checkpoint, events):
    _keys(checkpoint, {"sequence", "digest"})
    n = checkpoint["sequence"]
    if type(n) is not int or n < 0 or n > len(events) or checkpoint["digest"] != (events[n - 1]["event_digest"] if n else ZERO):
        raise IntegrityError("snapshot is not authentic ledger prefix")


# Closed recursive wire shape of the reviewed revision4 protocol. This is data
# shape/type validation, not a substitute for scientific gates or provenance.
# Generated once from reviewed protocol bytes; no mutable runtime schema lookup.
_PROTOCOL_SHAPE = json.loads(r'''{"access":{"cache_hits":"@str","cache_lifetime":"@str","live_ledger":"@str","prior_snapshot":"@str","release_authority":"@str","retry":"@str","selection_reservation":"@str","test_reservation":"@str","transport_integrity":"@str"},"authority":{"fallback_manifest":"@str","implementation_requires":"@str","new_label_parse_requires":["@str","@str"],"submission_authorized":"@bool"},"candidates":[{"alpha":"@int","emitter":"@str","id":"@str","support":"@str"},{"alpha":"@number","emitter":"@str","id":"@str","support":"@str"},{"alpha":"@number","emitter":"@str","id":"@str","support":"@str"},{"alpha":"@int","emitter":"@str","id":"@str","support":"@str"},{"alpha":"@int","emitter":"@str","id":"@str","support":"@str"},{"alpha":"@number","emitter":"@str","id":"@str","support":"@str"},{"alpha":"@number","emitter":"@str","id":"@str","support":"@str"},{"alpha":"@number","emitter":"@str","id":"@str","support":"@str"},{"alpha":"@number","emitter":"@str","id":"@str","support":"@str"}],"conditions":[{"id":"@str","kind":"@str"},{"block_probability":"@number","block_seconds":"@int","id":"@str","kind":"@str"},{"block_probability":"@number","block_seconds":"@int","id":"@str","kind":"@str"},{"ball_block_probability":"@number","ball_block_seconds":"@int","id":"@str","jitter_std_metres":"@number","kind":"@str","order":["@str","@str","@str","@str"],"player_block_seconds":"@int","player_slot_probability":"@number","teleport_metres":"@int","teleport_probability_per_frame":"@number"},{"anchor":"@str","ball":"@str","block_seconds":"@int","id":"@str","kind":"@str","per_slot_probability":"@number"},{"block_probability":"@number","block_seconds":"@int","channels":["@str","@str"],"id":"@str","kind":"@str"}],"corruption_semantics":{"arithmetic":"@str","ball_gap":"@str","blocks":"@str","boundary_none_sampling":"@str","chunk_equivalence":"@str","coordinates":"@str","jitter":"@str","player_dropout":"@str","row_sampling":"@str","stale_players":"@str","symmetry":"@str","targets_and_timeline":"@str","teleport":"@str","view_gap":"@str"},"decoder":{"alpha_zero":"@str","base_cost":"@str","boundary_head":"@str","classes":["@str","@str","@str"],"edge":"@str","flattened_control":"@str","head_validation":"@str","invalid_support":"@str","modulation":"@str","symmetry":"@str"},"design_revision":"@int","evaluation":{"attribution":"@str","condition_weights":["@int","@int","@int","@int","@int","@int"],"conditions":["@str","@str","@str","@str","@str","@str"],"frame_aggregation":"@str","gate":{"comparison_epsilon":"@number","each_condition_mean_spell_delta_min":"@number","each_match_clean_spell_delta_min":"@number","each_match_primary_delta_min":"@int","mean_clean_spell_delta_min":"@number","mean_each_class_frame_f1_delta_min":"@number","mean_paired_spell_gain_min":"@number"},"primary":"@str","secondary":["@str","@str","@str","@str","@str","@str"],"selection_gate":"@str","selection_order":["@str","@str","@str"],"test_attempts":"@int","test_candidates":"@int","tolerance_inclusive":"@bool","transition_aggregation":"@str","uncertainty":"@str","unknowns":"@str"},"fit":{"C0_conditions":["@str","@str","@str","@str"],"C1_conditions":["@str","@str","@str","@str"],"boundary":{"categorical_features":"@null","early_stopping":"@bool","l2_regularization":"@number","learning_rate":"@number","max_bins":"@int","max_iter":"@int","max_leaf_nodes":"@int","min_samples_leaf":"@int"},"boundary_conditions":["@str","@str","@str","@str"],"boundary_fits":"@int","boundary_none_sample":"@str","boundary_side_swap":"@bool","boundary_targets":"@str","boundary_weights":"@str","emitter":{"categorical_features":"@null","early_stopping":"@bool","l2_regularization":"@number","learning_rate":"@number","max_bins":"@int","max_iter":"@int","max_leaf_nodes":"@int","min_samples_leaf":"@int"},"emitter_fits":"@int","emitter_rows":"@str","emitter_weights":"@str","export_max_raw_error":"@number","head_max_bytes":"@int","max_base_rows_per_match":"@int","max_boundary_rows":"@int","max_emitter_augmented_rows_per_fit":"@int","provenance_stages":{"G08":"@str","postfit":"@str","prefit":"@str","pretest":"@str"},"runtime_environment_binding":"@str","source_closure":{"release_only_modules":["@str","@str","@str","@str"],"rule":"@str","scientific_legacy_modules":"@str","scientific_new_modules":["@str","@str","@str","@str","@str","@str","@str","@str","@str","@str","@str","@str","@str","@str"]},"temperature":"@number","weight_normalization_order":["@str","@str","@str","@str","@str","@str"]},"input":{"class_names":["@str","@str","@str"],"coordinate_units":"@str","fps":"@number","fps_tolerance":"@number","full_timeline":"@bool","labels_in_features":"@bool","masks":"@str","native_unknown_frames_retained":"@bool","outside_positive_period":"@int","slot_identity":"@str","target_lexical":"@str","targets":{"BallStatus=0":"@int","BallStatus=1,BallPossession=1":"@int","BallStatus=1,BallPossession=2":"@int","otherwise":"@int"},"timestamps":"@str","unknown":"@int","unknown_scorer_code":"@int"},"randomness":{"algorithm":"@str","fit_random_state":"@int","fit_replicates":"@int","generator":"@str","root_binding":"@str","seed_encoding":"@str","streams":["@str","@str","@str","@str","@str","@str","@str","@str"]},"release":{"accepted_fallback_files_immutable":"@int","challenge_frames":["@int","@int"],"challenge_header":["@str","@str"],"challenge_rows":"@int","core_equivalence":"@str","forced_dead_authority":{"bytes":"@int","local_path":"@str","meaning":"@str","sha256":"@str","url":"@str"},"labels":["@str","@str","@str","@str"],"member_max_bytes_exclusive":"@int","minimal_environment":"@str","namespace":"@str","output_root":"@str","positive_period_half_open":[["@int","@int","@int"],["@int","@int","@int"]],"promotion":"@str","publication":{"commit":"@str","crash":"@str","paths":"@str","readers":"@str"},"published_forced_dead_half_open":[["@int","@int"]],"review":"@str","scientific_api":"@str","technical_docs":["@str","@str"],"zip_max_bytes":"@int"},"research_cutoff":"@str","resource":{"added_disk_target_bytes":"@int","aggregate_fit_seconds":"@int","benchmark_cache":"@str","benchmark_order":["@str","@str","@str","@str","@str","@str"],"disk_definition":"@str","heavy_workers":"@int","inference_uncached_median_ratio_max":"@number","inference_uncached_median_seconds_max":"@int","measurement_limits":"@str","min_free_disk_bytes":"@int","numeric_threads":"@int","process_tree_peak_bytes":"@int","repeats":"@int","tree_measurement":"@str","worker_peak_absolute_max_bytes":"@int","worker_peak_increment_max_bytes":"@int"},"schedule":{"feasibility":"@str","first_e2e_gate_end":"@str","fit_end":"@str","freeze":"@str","late_policy":"@str","latest_fit_start":"@str","latest_selection_start":"@str","latest_test_start":"@str","test_end":"@str","timezone":"@str"},"schema_version":"@int","split":{"closed":["@str","@str"],"deferred_sources":["@str"],"prior_roles":{"J03WMX":"@str","J03WOH":"@str","J03WOY":"@str","J03WR9":"@str"},"provider":"@str","replacement_policy":"@str","selection":["@str"],"test":["@str","@str"],"train":["@str","@str"]},"status":"@str","study_id":"@str"}''')


def _validate_protocol(config):
    def check(value, shape):
        if type(shape) is dict:
            _keys(value, shape)
            for key, child in shape.items():
                check(value[key], child)
        elif type(shape) is list:
            if type(value) is not list or len(value) != len(shape):
                raise IntegrityError("malformed protocol array")
            for item, child in zip(value, shape):
                check(item, child)
        elif shape == "@int":
            if type(value) is not int:
                raise IntegrityError("protocol requires exact integer")
        elif shape == "@number":
            if type(value) not in (int, float) or not -float("inf") < value < float("inf"):
                raise IntegrityError("protocol requires finite real number")
        elif shape == "@bool":
            if type(value) is not bool:
                raise IntegrityError("protocol requires boolean")
        elif shape == "@str":
            if type(value) is not str or not value.strip() or "\0" in value:
                raise IntegrityError("protocol requires nonempty string")
        elif shape == "@null":
            if value is not None:
                raise IntegrityError("protocol requires null")
        else:
            raise IntegrityError("unsupported protocol schema")
    check(config, _PROTOCOL_SHAPE)
    if config["schema_version"] != 1 or config["design_revision"] != 4 or not re.fullmatch(r"[A-Za-z0-9_-]+", config["study_id"]):
        raise AccessError("unsupported protocol version/identity")
    for names in (config["fit"]["source_closure"]["scientific_new_modules"], config["fit"]["source_closure"]["release_only_modules"]):
        if len(names) != len(set(names)) or any(_relative(name) != name or "/" in name or not name.endswith(".py") for name in names):
            raise AccessError("invalid scientific module allowlist")


def register_study(protocol: Path, catalog: Path, fallback: Path, control: Path) -> Path:
    protocol, catalog, fallback = map(_plain, (protocol, catalog, fallback))
    root = ROOT.resolve()
    config = read_json(protocol)
    _validate_protocol(config)
    _catalog(catalog, config, root)
    comparison = read_json(fallback)
    if type(comparison.get("files")) is not dict or len(comparison["files"]) != 29:
        raise IntegrityError("exact fallback29 manifest required")
    source_paths = set()
    spec = protocol.parent
    source_paths.update([protocol, catalog, fallback, spec / "PRD-TURNOVER.md", spec / "PRD-MULTIMATCH.md", spec / "contracts.md",
                         root / "requirements-lock.txt", root / "requirements-training-lock.txt"])
    complete = read_json(catalog)
    overlap, attribution = root / "reports/v3-metadata-overlap.json", root / "reports/v3-source-attribution.json"
    if sha256(_plain(overlap)) != complete["metadata_overlap_receipt_digest"]:
        raise IntegrityError("metadata overlap receipt mismatch")
    if any(r["license"]["attribution_receipt_digest"] != sha256(_plain(attribution)) for r in complete["fixtures"].values()):
        raise IntegrityError("attribution receipt mismatch")
    source_paths.update([overlap, attribution, root / "tools/v3_prepare_catalog.py"])
    for name, identity in comparison["files"].items():
        _identity(identity, {"bytes", "sha256"})
        path = _under(root, name)
        if path.stat().st_size != identity["bytes"] or sha256(path) != identity["sha256"]:
            raise IntegrityError("accepted fallback changed")
        source_paths.add(path)
    source_paths = _scientific_paths(root, config, source_paths)
    bindings = sorted((_binding(root, p) for p in source_paths), key=lambda x: x["relative_path"].encode())
    environment_digest = _digest(_environment())
    study = _plain(root / "local/v3-studies" / config["study_id"] / "study.json", missing=True)
    if study.parent.exists():
        raise AccessError("study generation already exists")
    with _locked(control) as control:
        events = _replay(control)
        _interrupt_dead(control, events)
        histories = [e["payload"]["prior_roles"] for e in events if e["kind"] == "history"]
        if not histories:
            _append(control, events, "history", payload={"prior_roles": config["split"]["prior_roles"]})
        elif histories[0] != config["split"]["prior_roles"]:
            raise IntegrityError("prior role history changed")
        snapshot = {"schema_version": 1, "ledger_checkpoint": _checkpoint(events), "prior_roles": histories[0] if histories else config["split"]["prior_roles"]}
        study.parent.mkdir(parents=True, exist_ok=False)
        snapshot_path = study.parent / "prior-access-snapshot.json"
        _write_once(snapshot_path, snapshot)
        value = {"schema_version": 1, "study_id": config["study_id"], "protocol_digest": sha256(protocol),
                 "catalog_digest": sha256(catalog), "scientific_closure_digest": _digest(bindings),
                 "environment_digest": environment_digest, "comparator_digest": sha256(fallback),
                 "prior_snapshot_digest": sha256(snapshot_path), "ledger_checkpoint": snapshot["ledger_checkpoint"],
                 "raw_root": str(root / "local/v3-data/originals"), "catalog_path": str(catalog),
                 "model_seal_path": str(study.parent / "models/models.json"), "artifact_bindings": bindings}
        _write_once(study, value)
        digest = study_digest(study)
        _append(control, events, "register", study=digest, payload={"study_path": str(study)})
        _LOCATIONS[digest] = (study, control)
        _CONTROL_BY_PATH[study] = control
    return study


def _find_control(study):
    return _CONTROL_BY_PATH.get(study, ROOT / "local/v3-control")


def load_registered_study(study: Path, verify: bool = True) -> dict:
    study = _plain(study)
    value = read_json(study)
    _keys(value, _STUDY_KEYS)
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise IntegrityError("unsupported study schema")
    if type(value["study_id"]) is not str or not re.fullmatch(r"[A-Za-z0-9_-]+", value["study_id"]):
        raise IntegrityError("invalid study identity")
    for key in ("protocol_digest", "catalog_digest", "scientific_closure_digest", "environment_digest", "comparator_digest", "prior_snapshot_digest"):
        if not _hex(value[key]):
            raise IntegrityError("invalid study digest")
    if type(value["artifact_bindings"]) is not list or not value["artifact_bindings"]:
        raise IntegrityError("empty scientific closure")
    for item in value["artifact_bindings"]:
        _identity(item, {"relative_path", "bytes", "sha256"})
        _relative(item["relative_path"])
    if not verify:
        return value
    if study != ROOT / "local/v3-studies" / value["study_id"] / "study.json":
        raise AccessError("noncanonical study path")
    for key in ("protocol_digest", "catalog_digest", "scientific_closure_digest", "environment_digest", "comparator_digest", "prior_snapshot_digest"):
        if not _hex(value[key]):
            raise IntegrityError("invalid study digest")
    bindings = value["artifact_bindings"]
    if type(bindings) is not list or not bindings:
        raise IntegrityError("empty scientific closure")
    names = []
    for item in bindings:
        _identity(item, {"relative_path", "bytes", "sha256"})
        path = _under(ROOT, item["relative_path"])
        if type(item["bytes"]) is not int or not _hex(item["sha256"]) or path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise IntegrityError("registered scientific artifact changed")
        names.append(item["relative_path"])
    if names != sorted(set(names), key=lambda x: x.encode()) or _digest(bindings) != value["scientific_closure_digest"]:
        raise IntegrityError("invalid scientific closure")
    protocols = [ROOT / x for x in names if x.endswith("/protocol.json")]
    if len(protocols) != 1 or sha256(protocols[0]) != value["protocol_digest"]:
        raise IntegrityError("protocol binding mismatch")
    config = read_json(protocols[0])
    _validate_protocol(config)
    expected_scientific = {p.relative_to(ROOT).as_posix() for p in _scientific_paths(ROOT, config, [ROOT / name for name in names])}
    if not expected_scientific <= set(names):
        raise IntegrityError("scientific import closure changed since registration")
    catalog = _plain(value["catalog_path"])
    if sha256(catalog) != value["catalog_digest"] or not catalog.is_relative_to(ROOT):
        raise IntegrityError("catalog binding mismatch")
    _catalog(catalog, config, ROOT)
    if value["raw_root"] != str(ROOT / "local/v3-data/originals") or value["model_seal_path"] != str(study.parent / "models/models.json"):
        raise IntegrityError("registered source/model path changed")
    if _digest(_environment()) != value["environment_digest"]:
        raise IntegrityError("registered environment changed")
    snapshot_path = study.parent / "prior-access-snapshot.json"
    if sha256(_plain(snapshot_path)) != value["prior_snapshot_digest"]:
        raise IntegrityError("prior access snapshot changed")
    snapshot = read_json(snapshot_path)
    _keys(snapshot, {"schema_version", "ledger_checkpoint", "prior_roles"})
    if type(snapshot["schema_version"]) is not int or snapshot["schema_version"] != 1 or snapshot["ledger_checkpoint"] != value["ledger_checkpoint"] or snapshot["prior_roles"] != config["split"]["prior_roles"]:
        raise IntegrityError("snapshot binding mismatch")
    control = _find_control(study)
    digest = study_digest(study)
    with _locked(control):
        events = _replay(control)
        _prefix(value["ledger_checkpoint"], events)
        if not any(e["kind"] == "register" and e["study_digest"] == digest and e["payload"]["study_path"] == str(study) for e in events):
            raise AccessError("study not registered in canonical control")
    _LOCATIONS[digest] = (study, control)
    return value


def _config(study, value):
    names = [b["relative_path"] for b in value["artifact_bindings"] if b["relative_path"].endswith("/protocol.json")]
    return read_json(ROOT / names[0])


def _location(cap):
    if type(cap) is not AccessCapability:
        raise AccessError("exact study capability required")
    if cap.study_digest not in _LOCATIONS:
        control = ROOT / "local/v3-control"
        with _locked(control):
            events = _replay(control)
        matches = [e for e in events if e["kind"] == "register" and e["study_digest"] == cap.study_digest]
        if len(matches) != 1:
            raise AccessError("unknown study capability")
        path = Path(matches[0]["payload"]["study_path"])
        _CONTROL_BY_PATH[path] = control
        _LOCATIONS[cap.study_digest] = (path, control)
    return _LOCATIONS[cap.study_digest]


def _owner(cap, events, *, caller=True):
    if caller and (cap.process_id != os.getpid() or cap.process_creation_time != process_creation_time()):
        raise AccessError("capability belongs to another process")
    owners = [e for e in events if e["kind"] == "reserve" and e["attempt_id"] == cap.attempt_id]
    if len(owners) != 1:
        raise AccessError("unreserved capability")
    owner = owners[0]
    if (owner["study_digest"] != cap.study_digest or owner["role"] != cap.role
            or tuple(owner["fixture_ids"]) != cap.fixture_ids or owner["event_digest"] != cap.reservation_event_digest):
        raise AccessError("fabricated capability identity")
    if any(e["attempt_id"] == cap.attempt_id and e["kind"] in ("finish", "interrupted") for e in events):
        raise AccessError("attempt already consumed/terminal")
    if not _alive(owner["process_id"], owner["process_creation_time"]):
        raise AccessError("attempt owner is no longer live")
    direct = cap.process_id == owner["process_id"] and cap.process_creation_time == owner["process_creation_time"]
    child = any(e["kind"] == "child" and e["attempt_id"] == cap.attempt_id
                and e["payload"] == {"child_pid": cap.process_id, "child_creation_time": cap.process_creation_time} for e in events)
    if not direct and not child:
        raise AccessError("worker not explicitly authorized")
    return owner


def reserve_attempt(study: Path, role: Role, fixtures: tuple[str, ...], control: Path) -> AccessCapability:
    study, control = _plain(study), _plain(control, missing=True)
    _CONTROL_BY_PATH[study] = control
    value = load_registered_study(study)
    config = _config(study, value)
    if role not in ("train", "selection", "test") or type(fixtures) is not tuple or fixtures != tuple(config["split"][role]):
        raise AccessError("reservation must contain exact ordered whole role cohort")
    if any(f in config["split"]["closed"] for f in fixtures):
        raise AccessError("closed fixtures prohibited")
    if role in ("selection", "test"):
        load_model_seal(study)
    if role == "test":
        _validate_finalist(study, value)
    digest = study_digest(study)
    with _locked(control):
        events = _replay(control)
        _prefix(value["ledger_checkpoint"], events)
        _interrupt_dead(control, events)
        for event in events:
            if event["kind"] == "reserve":
                if event["study_digest"] == digest and event["role"] == role:
                    raise AccessError("declared role attempt already reserved")
                if set(event["fixture_ids"]) & set(fixtures) and (event["role"] != "train" or role != "train"):
                    raise AccessError("fresh cohort already consumed across studies")
            if event["kind"] == "history":
                prior = event["payload"]["prior_roles"]
                if any("closed" in prior.get(f, "") for f in fixtures):
                    raise AccessError("historically closed fixture")
        event = _append(control, events, "reserve", study=digest, attempt=uuid.uuid4().hex, fixtures=fixtures, role=role)
    return AccessCapability(digest, event["attempt_id"], role, fixtures, event["process_id"], event["process_creation_time"], event["event_digest"])


def assert_access(cap: AccessCapability, fixture: str, kind: str) -> None:
    if type(cap) is not AccessCapability or kind not in ("raw", "observations", "targets") or fixture not in cap.fixture_ids:
        raise AccessError("unauthorized access kind/fixture")
    study, control = _location(cap)
    load_registered_study(study)
    with _locked(control):
        events = _replay(control)
        _interrupt_dead(control, events)
        owner = _owner(cap, events)
        if not any(e["kind"] == "first_access" and e["attempt_id"] == cap.attempt_id for e in events):
            _append_for(control, events, "first_access", owner)


def authorize_child(cap: AccessCapability, child_pid: int, creation_time: str) -> AccessCapability:
    study, control = _location(cap)
    load_registered_study(study)
    if child_pid == cap.process_id or not _alive(child_pid, creation_time):
        raise AccessError("exact live child identity required")
    with _locked(control):
        events = _replay(control)
        _interrupt_dead(control, events)
        owner = _owner(cap, events)
        if owner["process_id"] != cap.process_id or owner["process_creation_time"] != cap.process_creation_time:
            raise AccessError("only owner may authorize a child")
        _assert_descendant(owner["process_id"], owner["process_creation_time"], child_pid, creation_time)
        payload = {"child_pid": child_pid, "child_creation_time": creation_time}
        if not any(e["kind"] == "child" and e["attempt_id"] == cap.attempt_id and e["payload"] == payload for e in events):
            _append_for(control, events, "child", owner, payload=payload)
    return AccessCapability(cap.study_digest, cap.attempt_id, cap.role, cap.fixture_ids, child_pid, creation_time, cap.reservation_event_digest)


def finish_attempt(cap: AccessCapability, result: Path, status: str) -> None:
    if status not in ("complete", "failed", "interrupted"):
        raise AccessError("invalid terminal status")
    study, control = _location(cap)
    load_registered_study(study)
    result = _plain(result)
    if not result.is_file() or not result.is_relative_to(study.parent):
        raise AccessError("result must be a sealed study artifact")
    document = read_json(result)
    if "schema_version" in document and (type(document["schema_version"]) is not int or document["schema_version"] != 1):
        raise IntegrityError("unsupported result schema")
    if document.get("study_digest") != cap.study_digest or document.get("attempt_id") != cap.attempt_id:
        raise IntegrityError("result identity mismatch")
    if status == "complete" and document.get("status") != "complete":
        raise IntegrityError("incomplete result cannot finalize success")
    payload = {"result": str(result), "bytes": result.stat().st_size, "sha256": sha256(result)}
    with _locked(control):
        events = _replay(control)
        _interrupt_dead(control, events)
        owner = _owner(cap, events)
        if cap.process_id != owner["process_id"]:
            raise AccessError("only attempt owner may finish")
        _append_for(control, events, "finish", owner, status=status, payload=payload)


def finalize_recorded_result(study: Path, result: Path) -> None:
    """Finish metadata for a dead owner, without a capability or any input read.

    A recoverable result has status='complete', sealed=True, study_digest,
    attempt_id, role, fixture_ids/fixture_count, artifact_count and nonempty
    artifacts:[{relative_path,bytes,sha256}], plus protocol/catalog/scientific/
    environment/comparator digests matching the immutable study. The result
    and every listed output are confined to the study. Restart rehashes complete
    sealed output bytes only; it never constructs arrays, fits, parses, rescans
    inputs, or changes permanent fixture consumption. A missing/incomplete result
    cannot be repaired here. This does not certify scientific quality.
    """
    study = _plain(study)
    value = load_registered_study(study)
    result = _plain(result)
    if not result.is_relative_to(study.parent) or not result.is_file():
        raise AccessError("recovery result must be a study artifact")
    document = read_json(result)
    digest = study_digest(study)
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1 or document.get("study_digest") != digest or document.get("status") != "complete" or document.get("sealed") is not True:
        raise IntegrityError("complete sealed recovery result required")
    if any(document.get(key) != value[key] for key in ("protocol_digest", "catalog_digest", "scientific_closure_digest", "environment_digest", "comparator_digest")):
        raise IntegrityError("recovery result source binding mismatch")
    artifacts = document.get("artifacts")
    if type(artifacts) is not list or not artifacts or type(document.get("artifact_count")) is not int or document["artifact_count"] != len(artifacts):
        raise IntegrityError("complete recovery artifact manifest required")
    seen = set()
    for identity in artifacts:
        _identity(identity, {"relative_path", "bytes", "sha256"})
        path = _under(study.parent, identity["relative_path"])
        if path.suffix != ".json" or Path(identity["relative_path"]).parts[0] not in ("train", "models", "selection", "test"):
            raise AccessError("recovery verifies aggregate/numeric JSON outputs only")
        if (path == result or path in seen or type(identity["bytes"]) is not int or not _hex(identity["sha256"])
                or path.stat().st_size != identity["bytes"] or sha256(path) != identity["sha256"]):
            raise IntegrityError("incomplete/corrupt sealed recovery artifact")
        seen.add(path)
    control = _find_control(study)
    payload = {"result": str(result), "bytes": result.stat().st_size, "sha256": sha256(result)}
    with _locked(control):
        events = _replay(control)
        _interrupt_dead(control, events)
        owners = [e for e in events if e["kind"] == "reserve" and e["study_digest"] == digest and e["attempt_id"] == document.get("attempt_id")]
        if len(owners) != 1:
            raise AccessError("recovery result lacks reservation")
        owner = owners[0]
        if (document.get("role") != owner["role"] or document.get("fixture_ids") != owner["fixture_ids"]
                or type(document.get("fixture_count")) is not int or document["fixture_count"] != len(owner["fixture_ids"])):
            raise IntegrityError("recovery result cohort binding mismatch")
        terminal = [e for e in events if e["attempt_id"] == owner["attempt_id"] and e["kind"] in ("finish", "interrupted", "finalize")]
        if terminal and terminal[-1]["kind"] in ("finish", "finalize"):
            if terminal[-1]["status"] == "complete" and terminal[-1]["payload"] == payload:
                return
            raise AccessError("attempt already finalized with different result")
        if len(terminal) != 1 or terminal[0]["kind"] != "interrupted" or _alive(owner["process_id"], owner["process_creation_time"]):
            raise AccessError("only dead interrupted owners permit metadata finalization")
        _append_for(control, events, "finalize", owner, status="complete", payload=payload)


def seal_fitted_models(study: Path, cap: AccessCapability, models: Mapping[str, Path], parity_receipts: Mapping[str, Path]) -> Path:
    study = _plain(study)
    value = load_registered_study(study)
    if cap.study_digest != study_digest(study) or cap.role != "train" or set(models) != {"C0", "C1", "boundary"} or set(parity_receipts) != set(models):
        raise AccessError("three exact live training model artifacts required")
    assert_access(cap, cap.fixture_ids[0], "observations")
    entries = []
    for name in ("C0", "C1", "boundary"):
        model, receipt = _plain(models[name]), _plain(parity_receipts[name])
        if not model.is_relative_to(study.parent) or not receipt.is_relative_to(study.parent):
            raise AccessError("model artifacts must be confined to study")
        parity = read_json(receipt)
        if (parity.get("study_digest") != cap.study_digest or parity.get("scientific_closure_digest") != value["scientific_closure_digest"]
                or parity.get("model_sha256") != sha256(model) or parity.get("passed") is not True
                or parity.get("numeric_export_passed") is not True or parity.get("parity_passed") is not True):
            raise IntegrityError("missing model provenance/numeric parity proof")
        _validate_numeric_model(study, name, model, parity)
        entries.append({"name": name, "relative_path": model.relative_to(study.parent).as_posix(), "bytes": model.stat().st_size,
                        "sha256": sha256(model), "parity_receipt": {"relative_path": receipt.relative_to(study.parent).as_posix(),
                        "bytes": receipt.stat().st_size, "sha256": sha256(receipt)}})
    seal = {"schema_version": 1, "study_digest": cap.study_digest, "prefit_closure_digest": value["scientific_closure_digest"],
            "train_attempt_digest": cap.reservation_event_digest, "models": entries}
    destination = Path(value["model_seal_path"])
    _write_once(destination, seal)
    load_model_seal(study)
    return destination


def load_model_seal(study: Path, verify: bool = True) -> dict:
    study = _plain(study)
    value = load_registered_study(study, verify=verify)
    seal = read_json(Path(value["model_seal_path"]))
    _keys(seal, {"schema_version", "study_digest", "prefit_closure_digest", "train_attempt_digest", "models"})
    if type(seal["schema_version"]) is not int or seal["schema_version"] != 1:
        raise IntegrityError("unsupported model seal schema")
    if any(not _hex(seal[key]) for key in ("study_digest", "prefit_closure_digest", "train_attempt_digest")):
        raise IntegrityError("invalid model seal digest")
    if type(seal["models"]) is not list or [m.get("name") if type(m) is dict else None for m in seal["models"]] != ["C0", "C1", "boundary"]:
        raise IntegrityError("incomplete three-model seal")
    for entry in seal["models"]:
        _identity(entry, {"name", "relative_path", "bytes", "sha256", "parity_receipt"})
        _relative(entry["relative_path"])
        _identity(entry["parity_receipt"], {"relative_path", "bytes", "sha256"})
        _relative(entry["parity_receipt"]["relative_path"])
    if not verify:
        return seal
    if type(seal["schema_version"]) is not int or seal["schema_version"] != 1 or seal["study_digest"] != study_digest(study) or seal["prefit_closure_digest"] != value["scientific_closure_digest"]:
        raise IntegrityError("postfit seal study mismatch")
    if type(seal["models"]) is not list or [m.get("name") for m in seal["models"]] != ["C0", "C1", "boundary"]:
        raise IntegrityError("incomplete three-model seal")
    with _locked(_find_control(study)) as control:
        events = _replay(control)
        if not any(e["kind"] == "reserve" and e["study_digest"] == seal["study_digest"] and e["role"] == "train"
                   and e["event_digest"] == seal["train_attempt_digest"] for e in events):
            raise IntegrityError("model seal lacks training reservation")
    paths = set()
    for entry in seal["models"]:
        _identity(entry, {"name", "relative_path", "bytes", "sha256", "parity_receipt"})
        for identity in (entry, entry["parity_receipt"]):
            if identity is not entry:
                _identity(identity, {"relative_path", "bytes", "sha256"})
            path = _under(study.parent, identity["relative_path"])
            if path in paths or type(identity["bytes"]) is not int or path.stat().st_size != identity["bytes"] or sha256(path) != identity["sha256"]:
                raise IntegrityError("model/parity artifact changed or aliased")
            paths.add(path)
        parity = read_json(study.parent / entry["parity_receipt"]["relative_path"])
        if (parity.get("study_digest") != seal["study_digest"] or parity.get("scientific_closure_digest") != value["scientific_closure_digest"]
                or parity.get("model_sha256") != entry["sha256"] or parity.get("passed") is not True
                or parity.get("numeric_export_passed") is not True or parity.get("parity_passed") is not True):
            raise IntegrityError("invalid sealed parity receipt")
        _validate_numeric_model(study, entry["name"], study.parent / entry["relative_path"], parity)
    return seal


def expected_model_provenance(study: Path, name: str) -> dict:
    """Common frozen identities and expected input order, never invented digests.

    metric_digest = SHA256 of the exact organizer possession_metrics.py bytes;
    dependency_digest = registered actual environment inventory digest;
    split_digest = canonical compact sorted JSON SHA256 of protocol.split.
    training_input_order contains only fixture_id/condition; the trainer supplies
    actual local observation/target/sampling hashes in training_input_digests.
    """
    if name not in ("C0", "C1", "boundary"):
        raise AccessError("unknown model name")
    value = load_registered_study(study)
    config = _config(study, value)
    conditions = config["fit"][name + "_conditions"]
    return {"study_digest": study_digest(study), "scientific_source_digest": value["scientific_closure_digest"],
            "protocol_digest": value["protocol_digest"], "split_digest": _digest(config["split"]),
            "metric_digest": sha256(ROOT / "more-than-a-hack-2027-main/evaluation/possession_metrics.py"),
            "dependency_digest": value["environment_digest"],
            "training_input_order": [{"fixture_id": fixture, "condition": condition}
                                     for fixture in config["split"]["train"] for condition in conditions]}


def _validate_numeric_model(study, name, path, parity):
    if name == "boundary" and path.stat().st_size > 524288:
        raise IntegrityError("boundary model exceeds bounded parser limit")
    document = read_json(path)  # duplicate keys rejected for both model formats
    try:
        if name == "boundary":
            from .boundary import NumericHead
            NumericHead(document)
        else:
            from possession_model.trees import TreeModel
            _keys(document, {"format", "feature_names", "baseline", "trees", "provenance"})
            TreeModel(document)
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise IntegrityError("invalid strict numeric model") from exc
    provenance = document.get("provenance")
    if type(provenance) is not dict:
        raise IntegrityError("model provenance required")
    expected = expected_model_provenance(study, name)
    for key, digest in expected.items():
        if key != "training_input_order" and provenance.get(key) != digest:
            raise IntegrityError("model prefit provenance mismatch")
    inputs = provenance.get("training_input_digests")
    if type(inputs) is not list or len(inputs) != len(expected["training_input_order"]):
        raise IntegrityError("complete ordered model input provenance required")
    for entry, identity in zip(inputs, expected["training_input_order"]):
        _keys(entry, {"fixture_id", "condition", "observation_digest", "target_digest", "sampling_digest"})
        if any(entry[k] != v for k, v in identity.items()) or any(not _hex(entry[k]) for k in ("observation_digest", "target_digest", "sampling_digest")):
            raise IntegrityError("model input provenance order/digest mismatch")
    if not _same(parity.get("training_input_digests"), inputs):
        raise IntegrityError("model/parity input provenance mismatch")


def _validate_finalist(study, value):
    finalist = read_json(_plain(study.parent / "finalist.json"))
    seal = load_model_seal(study)
    needed = {"schema_version", "study_digest", "model_seal_digest", "protocol_digest", "scientific_closure_digest",
              "comparator_digest", "selection_receipt_digest", "candidate_id", "config", "models"}
    _keys(finalist, needed)
    if any(finalist[k] != value[k] for k in ("protocol_digest", "scientific_closure_digest", "comparator_digest")):
        raise IntegrityError("finalist prefit binding mismatch")
    if type(finalist["schema_version"]) is not int or finalist["schema_version"] != 1 or finalist["study_digest"] != study_digest(study) or finalist["model_seal_digest"] != sha256(Path(value["model_seal_path"])):
        raise IntegrityError("finalist model seal mismatch")
    receipt = _plain(study.parent / "selection/result.json")
    if sha256(receipt) != finalist["selection_receipt_digest"]:
        raise IntegrityError("finalist selection receipt mismatch")
    doc = read_json(receipt)
    if doc.get("study_digest") != study_digest(study) or doc.get("status") != "complete" or doc.get("eligible") is not True:
        raise IntegrityError("finalist lacks eligible selection result")
    candidates = _config(study, value)["candidates"]
    match = [c for c in candidates if c["id"] == finalist["candidate_id"] and c["id"] != "A"]
    for entry in finalist["models"] if type(finalist["models"]) is list else ():
        _identity(entry, {"name", "relative_path", "bytes", "sha256", "parity_receipt"})
        _identity(entry["parity_receipt"], {"relative_path", "bytes", "sha256"})
    if len(match) != 1 or not _same(finalist["config"], match[0]) or not _same(finalist["models"], seal["models"]):
        raise IntegrityError("finalist undeclared configuration/model binding")
    with _locked(_find_control(study)) as control:
        events = _replay(control)
        if not any(e["kind"] in ("finish", "finalize") and e["study_digest"] == study_digest(study) and e["role"] == "selection"
                   and e["status"] == "complete" and e["payload"]["sha256"] == finalist["selection_receipt_digest"] for e in events):
            raise IntegrityError("selection not durably finalized")
