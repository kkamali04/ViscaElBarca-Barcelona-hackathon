"""Fixed v3 command dispatch. Heavy scientific/runtime imports are deferred.

Normal commands always use the one canonical global control; a command cannot
reset consumption by supplying a fresh control directory. No command downloads,
fits, parses or reserves a role merely by importing this module or asking help.
"""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys
import time


def parser():
    p = argparse.ArgumentParser(description="Versioned guarded v3 study and release")
    commands = p.add_subparsers(dest="command", required=True)
    command = commands.add_parser("register")
    command.add_argument("--protocol", type=Path, required=True)
    command.add_argument("--catalog", type=Path, required=True)
    command.add_argument("--fallback", type=Path, required=True)
    command = commands.add_parser("fetch")
    command.add_argument("--study", type=Path, required=True)
    command.add_argument("--fixtures", nargs="+", required=True)
    for name in ("fit", "select", "test"):
        command = commands.add_parser(name)
        command.add_argument("--study", type=Path, required=True)
    command = commands.add_parser("_resource_worker", help=argparse.SUPPRESS)
    command.add_argument("--study", type=Path, required=True)
    command.add_argument("--stage", choices=("train","selection","test"), required=True)
    command = commands.add_parser("package")
    command.add_argument("--study", type=Path, required=True)
    command = commands.add_parser("run")
    command.add_argument("--release", type=Path, required=True)
    command.add_argument("--data-dir", type=Path, required=True)
    command.add_argument("--out", type=Path, required=True)
    command.add_argument("--report", type=Path, required=True)
    command.add_argument("--no-cache", action="store_true")
    command = commands.add_parser("export")
    command.add_argument("--finalist", type=Path, required=True)
    command.add_argument("--destination", type=Path, required=True)
    command = commands.add_parser("review")
    command.add_argument("--release", type=Path, required=True)
    command.add_argument("--data-dir", type=Path, required=True)
    command.add_argument("--demo", action="store_true")
    command = commands.add_parser("promote")
    for name in ("release", "science", "acceptance", "root-verification", "receipt"):
        command.add_argument("--" + name, type=Path, required=True)
    return p


def _module(name):
    return importlib.import_module("experiments.v3." + name)


def validate_generation_paths(out: Path, report: Path):
    """Validate destination transaction before any release/input access."""
    from . import guard
    for supplied in (out, report):
        if ".." in supplied.parts or supplied.name.casefold() == "commit.json":
            raise guard.AccessError("invalid generation filename/path")
    out, report = guard._plain(out, missing=True), guard._plain(report, missing=True)
    if out == report or out.name.casefold() == report.name.casefold() or out.parent != report.parent:
        raise guard.AccessError("CSV/report require distinct names in one absent generation")
    generation = out.parent
    if generation.exists() or out.exists() or report.exists():
        raise guard.AccessError("generation already exists")
    root = guard._plain(generation.parent)
    if not root.is_dir():
        raise guard.AccessError("existing trusted output root required")
    protected = [guard.ROOT / x for x in ("data", "models", "possession_model", "experiments", "validation", "tools", "specs",
                                         "research", "more-than-a-hack-2027-main", "local/v3-data", "local/v3-studies", "local/v3-control")]
    if any(root == p or root.is_relative_to(p) for p in protected):
        raise guard.AccessError("protected output root")
    return out, report


def _budget_path():
    from . import guard
    return guard.ROOT / 'local/v3-control/resource-budget.json'


def _initialize_budget_before_registration():
    from . import guard, resources
    path = _budget_path()
    if path.exists():
        return resources.load_budget(path)
    raw = guard.ROOT / 'local/v3-data/originals'
    if raw.exists() and any(p.is_file() for p in raw.rglob('*')):
        raise guard.IntegrityError('missing original pre-acquisition resource baseline')
    control = guard.ROOT / 'local/v3-control'
    with guard._locked(control):
        if any(e['kind']=='reserve' for e in guard._replay(control)):
            raise guard.IntegrityError('missing resource baseline after an attempt')
    return resources.initialize_budget(path,guard.ROOT,snapshot_unrelated=True)


def _resource_worker(args):
    # This branch is entered before importing guard/contracts/NumPy. The waiting
    # worker opens no study or raw path before its authenticated supervisor grant.
    from . import resources
    grant = resources.worker_handshake()
    from . import guard
    from .contracts import AccessCapability
    cap = AccessCapability(**grant['capability'])
    study = guard._plain(args.study)
    value = guard.load_registered_study(study)
    result = study.parent / args.stage / 'result.json'
    if (cap.role != args.stage or cap.study_digest != guard.study_digest(study)
            or guard._plain(Path(grant['result_path']),missing=True) != result):
        raise guard.AccessError('worker grant role/result mismatch')
    guard.assert_access(cap,cap.fixture_ids[0],'observations')
    implementation = _module("training" if args.stage == "train" else "evaluate")
    from threadpoolctl import threadpool_info, threadpool_limits
    with threadpool_limits(limits=4):
        if any(pool['num_threads'] > 4 for pool in threadpool_info()):
            raise resources.ResourceError('numeric thread ceiling failed')
        if args.stage == 'train':
            implementation.fit_models(study,cap,study.parent/'models')
        elif args.stage == 'selection':
            implementation.select_finalist(study,Path(value['model_seal_path']),cap,result)
        else:
            implementation.run_final_test(study,study.parent/'finalist.json',cap,result)
    return 0


def validate_stage_result(study,cap,path):
    """Owner checks immutable aggregate output; never reparses/retries inputs."""
    from . import guard
    try:
        return _validate_stage_result(study,cap,path)
    except (KeyError,TypeError,ValueError) as exc:
        raise guard.IntegrityError('invalid complete stage result') from exc


def _validate_stage_result(study,cap,path):
    from . import guard
    doc = guard.read_json(path)
    if (type(doc.get('schema_version')) is not int or doc['schema_version'] != 1
            or doc.get('study_digest') != cap.study_digest or doc.get('attempt_id') != cap.attempt_id
            or doc.get('status') != 'complete'):
        raise guard.IntegrityError('complete owner-bound result required')
    if cap.role=='test' and type(doc.get('gate_passed')) is not bool:
        raise guard.IntegrityError('exact test gate_passed boolean required')
    from .training import result_envelope
    from .evaluate import _model_artifacts
    value=guard.load_registered_study(study)
    seal=guard.load_model_seal(study)
    artifacts=_model_artifacts(study,seal)
    if cap.role=='test': artifacts.append(study.parent/'selection/result.json')
    envelope=result_envelope(study,cap,value,artifacts)
    if not guard._same({key:doc.get(key) for key in envelope},envelope):
        raise guard.IntegrityError('complete recovery envelope/artifact mismatch')
    if cap.role == 'train':
        if doc.get('model_seal_digest') != guard.sha256(study.parent/'models/models.json'):
            raise guard.IntegrityError('training result/model seal mismatch')
        return 0
    from .evaluate import choose_finalist, paired_gate
    if cap.role == 'selection':
        if type(doc.get('eligible')) is not bool:
            raise guard.IntegrityError('exact selection eligibility boolean required')
        winner,evaluations = choose_finalist(doc.get('rows'),cap.fixture_ids)
        if (doc['eligible'] != (winner is not None) or doc.get('candidate_id') != winner
                or doc.get('candidates') != evaluations):
            raise guard.IntegrityError('selection arithmetic/result mismatch')
        if winner is not None:
            value=guard.load_registered_study(study); protocol=guard._config(study,value)
            final=guard.read_json(study.parent/'finalist.json'); seal=guard.load_model_seal(study)
            expected={'schema_version':1,'study_digest':cap.study_digest,
                'model_seal_digest':guard.sha256(Path(value['model_seal_path'])),
                'protocol_digest':value['protocol_digest'],'scientific_closure_digest':value['scientific_closure_digest'],
                'comparator_digest':value['comparator_digest'],'selection_receipt_digest':guard.sha256(path),
                'candidate_id':winner,'config':next(r for r in protocol['candidates'] if r['id']==winner),
                'models':seal['models']}
            if not guard._same(final,expected): raise guard.IntegrityError('invalid finalist seal')
        return 0 if doc['eligible'] else 4
    if cap.role != 'test' or type(doc.get('gate_passed')) is not bool:
        raise guard.IntegrityError('exact test gate_passed boolean required')
    final=guard.read_json(study.parent/'finalist.json')
    if doc.get('candidate_id') != final['candidate_id'] or doc.get('finalist_digest') != guard.sha256(study.parent/'finalist.json'):
        raise guard.IntegrityError('test finalist identity mismatch')
    verdict=paired_gate(doc.get('rows'),cap.fixture_ids,final['candidate_id'])
    if doc['gate_passed'] != verdict['gate_passed'] or doc.get('verdict') != verdict:
        raise guard.IntegrityError('test paired arithmetic/result mismatch')
    return 0 if doc['gate_passed'] else 4


def _study_command(args):
    from . import guard, resources
    if Path.cwd().resolve()!=guard.ROOT.resolve():
        raise guard.AccessError('study commands require the registered project-root working directory')
    study = guard._plain(args.study)
    value = guard.load_registered_study(study)
    config = guard._config(study, value)
    protocol_path = next(guard.ROOT/r['relative_path'] for r in value['artifact_bindings']
                         if r['relative_path'].endswith('/protocol.json'))
    policy=resources.policy_from_protocol(protocol_path)
    budget=resources.load_budget(_budget_path())  # Never initialize on fetch/fit.
    if args.command == "fetch":
        allowed = [f for role in ("train", "selection", "test") for f in config["split"][role]]
        if len(set(args.fixtures)) != len(args.fixtures) or any(f not in allowed for f in args.fixtures):
            raise guard.AccessError("unknown or duplicate fetch fixture")
        catalog=guard.read_json(Path(value['catalog_path']))
        forecast=sum(catalog['fixtures'][f][kind]['bytes'] for f in args.fixtures for kind in ('metadata','tracking')
                     if not (Path(value['raw_root'])/catalog['fixtures'][f][kind]['relative_path']).exists())
        resources.check_time(policy,'acquisition',budget)
        resources.check_disk(policy,guard.ROOT,budget,forecast_bytes=forecast)
        receipt=_module("fetch").fetch_registered_sources(study, tuple(args.fixtures), Path(value["raw_root"]))
        resources.check_time(policy,'acquisition',budget)
        resources.check_disk(policy,guard.ROOT,budget)
        return receipt
    role = {"fit": "train", "select": "selection", "test": "test"}[args.command]
    # Fixed source closure is verified before imports as well as reservation.
    # Import errors occur before spending a fresh cohort.
    _module("training" if role == "train" else "evaluate")
    preflight=resources.resource_preflight(policy,guard.ROOT,budget)
    result = study.parent / {"train": "train/result.json", "selection": "selection/result.json", "test": "test/result.json"}[role]
    command=[str(guard.ROOT/'.venv/Scripts/python.exe'),'-m','experiments.v3.cli','_resource_worker',
             '--study',str(study),'--stage',role]
    with resources.prepare_worker(command,policy,guard.ROOT,budget,stage=role,preflight_receipt=preflight) as worker:
        # Another admitted owner may have consumed budget while this process
        # waited for the global heavy-worker mutex. Never reserve on stale state.
        if resources.load_budget(_budget_path()) != budget:
            raise resources.ResourceError('resource budget changed before admission')
        cap=guard.reserve_attempt(study,role,tuple(config['split'][role]),guard.ROOT/'local/v3-control')
        started=time.monotonic(); measured=None; accounted=False
        try:
            worker.authorize(cap,result_path=result)
            measured=worker.wait()
            if role=='train':
                resources.save_budget(_budget_path(),resources.account_fit(budget,measured['wall_seconds']))
                accounted=True
            resource_path=study.parent/role/('resources-'+cap.attempt_id+'.json')
            guard._write_once(resource_path,{'schema_version':1,'study_digest':cap.study_digest,
                'attempt_id':cap.attempt_id,'preflight':preflight,'measurement':measured})
            if (measured['exit_code'] != 0 or measured['termination_reason'] or measured['sampling_errors']
                    or measured['gaps_over_50ms'] or measured['sample_count']<2 or measured['worker_peak_working_set_bytes']<=0
                    or measured['sampled_job_peak_working_set_bytes']>12884901888):
                raise resources.ResourceError('worker/resource acceptance failed')
            code=validate_stage_result(study,cap,result)
            guard.finish_attempt(cap,result,'complete')
            return {'status':'complete' if code==0 else 'ineligible','exit_code':code,'artifact':str(result),
                    'resources':str(resource_path)}
        except BaseException:
            failure=study.parent/role/('failure-'+cap.attempt_id+'.json')
            try:
                guard._write_once(failure,{'schema_version':1,'study_digest':cap.study_digest,
                    'attempt_id':cap.attempt_id,'status':'failed'})
                guard.finish_attempt(cap,failure,'failed')
            except (OSError,ValueError): pass
            raise
        finally:
            if role=='train' and not accounted:
                elapsed=measured['wall_seconds'] if measured is not None else time.monotonic()-started
                resources.save_budget(_budget_path(),resources.account_fit(budget,elapsed))


def dispatch(args):
    from . import guard
    if args.command == "register":
        _initialize_budget_before_registration()
        return guard.register_study(args.protocol, args.catalog, args.fallback, guard.ROOT / "local/v3-control")
    if args.command in ("fetch", "fit", "select", "test"):
        return _study_command(args)
    if args.command == "run":
        out, report = validate_generation_paths(args.out, args.report)
        return _module("runner").run_release(args.release, args.data_dir, out, report, not args.no_cache)
    if args.command == "export":
        destination = guard._plain(args.destination, missing=True)
        if destination.exists() or not destination.parent.is_dir() or not destination.is_relative_to(guard.ROOT / "local/v3-releases"):
            raise guard.AccessError("new destination under existing local/v3-releases required")
        return _module("exporting").build_release(args.finalist, destination, guard.ROOT)
    if args.command == 'package':
        study=guard._plain(args.study); value=guard.load_registered_study(study)
        destination=guard.ROOT/'local/v3-releases'/value['study_id']
        if destination.exists(): raise guard.AccessError('release generation already exists')
        return _module("exporting").build_release(study.parent/'finalist.json',destination,guard.ROOT)
    if args.command == "review":
        return _module("review").main(release=args.release, data_dir=args.data_dir, demo=args.demo)
    if args.command == "promote":
        receipt = guard._plain(args.receipt, missing=True)
        if receipt.exists() or not receipt.is_relative_to(guard.ROOT / "local/v3-releases"):
            raise guard.AccessError("new versioned promotion receipt required")
        return _module("promotion").promote(args.release, args.science, args.acceptance, args.root_verification, receipt)
    raise guard.AccessError("unsupported command")


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == '_resource_worker':
        try:
            return _resource_worker(args)
        except BaseException:
            # Never leak records/tracebacks through the supervised wire.
            print('{"status":"failed","reason":"worker_failure"}',file=sys.stderr)
            return 3
    from . import guard
    from .resources import ResourceError
    try:
        result = dispatch(args)
        if type(result) is dict:
            code = result.get("exit_code", 0)
            print(json.dumps(result, sort_keys=True, allow_nan=False))
            return code
        if result is not None:
            print(json.dumps({"status": "complete", "artifact": str(result)}))
        return 0
    except guard.IntegrityError:
        print('{"status":"failed","reason":"integrity"}', file=sys.stderr)
        return 3
    except (guard.AccessError, FileNotFoundError, ImportError, TypeError, ValueError):
        print('{"status":"failed","reason":"preflight_schema_access"}', file=sys.stderr)
        return 2
    except (OSError, MemoryError, TimeoutError, ResourceError):
        print('{"status":"failed","reason":"resource_or_integrity"}', file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
