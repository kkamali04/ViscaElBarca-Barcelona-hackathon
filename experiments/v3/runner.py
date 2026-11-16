"""Observation-only frozen-core runner and immutable three-file generations.

No training, selection, target lookup or default active-model lookup occurs here.
The public entry uses exactly the challenge frame contract. Small invented ATD
fixtures can exercise extract_features directly under synthetic ReleaseAccess.
"""
from __future__ import annotations

from contextlib import ExitStack
import csv
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import io
import math
import os
from pathlib import Path
import re
import sys
import time
import uuid

import numpy as np

from . import cache

FRAMES = 199319
PERIODS = ((1, 11185, 90652), (2, 110808, 190198))
PITCH = (105.3, 68.0)
COMMIT_KEYS = {'schema_version', 'kind', 'generation_id', 'release_digest',
               'source_manifest_digest', 'policy_digest', 'csv', 'report'}
REPORT_KEYS = {'schema_version','kind','generation_id','release_id','release_digest',
               'source_manifest_digest','policy_digest','csv_filename','csv_sha256','frame_count',
               'official_format_validator','public_bounds','synthetic_demo'}
REPORT_OPTIONAL_KEYS = {'runtime_digest','scientific_digest','model_seal_digest','finalist_digest',
                        'candidate_id','cache_hit','inference_seconds','total_seconds',
                        'peak_process_working_set_bytes','process_id','process_creation_time',
                        'resource_scope','timing_scope'}
RESOURCE_SCOPE = 'OS current worker lifetime high-water; independent process-tree/timing gate required'
TIMING_SCOPE = 'preflight through CSV/official validation; excludes final report/commit serialization and rename'


def _validate_report(value):
    if (type(value) is not dict or not REPORT_KEYS <= set(value)
            or set(value) - REPORT_KEYS - REPORT_OPTIONAL_KEYS
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or value['kind'] != 'v3-inference-report'):
        raise ValueError('closed inference report required')
    if (type(value['frame_count']) is not int or value['frame_count'] != FRAMES
            or value['official_format_validator'] != 'passed' or value['public_bounds'] != 'passed'
            or type(value['synthetic_demo']) is not bool):
        raise ValueError('invalid report frame/validation/mode contract')
    for key in ('release_id','candidate_id'):
        if key in value and (type(value[key]) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',value[key])):
            raise ValueError('invalid report identity')
    for key in ('release_digest','source_manifest_digest','policy_digest','csv_sha256',
                'runtime_digest','scientific_digest','model_seal_digest','finalist_digest'):
        if key in value and (type(value[key]) is not str or not cache.HEX64.fullmatch(value[key])):
            raise ValueError('invalid report digest')
    for key in ('generation_id','csv_filename'):
        if type(value[key]) is not str or not value[key] or Path(value[key]).name != value[key]:
            raise ValueError('invalid report basename')
    if 'cache_hit' in value and type(value['cache_hit']) is not bool:
        raise ValueError('invalid report cache flag')
    for key in ('inference_seconds','total_seconds'):
        if key not in value: continue
        item=value[key]
        if item is None and key=='total_seconds' and value['synthetic_demo']: continue
        if type(item) not in (int,float) or (type(item) is float and not math.isfinite(item)) or item<0:
            raise ValueError('invalid report timing')
    for key in ('peak_process_working_set_bytes','process_id'):
        if key not in value: continue
        item=value[key]
        if item is None and key=='peak_process_working_set_bytes' and value['synthetic_demo']: continue
        if type(item) is not int or item<=0: raise ValueError('invalid report resource integer')
    if 'process_creation_time' in value and (type(value['process_creation_time']) is not str
            or not re.fullmatch(r'[1-9][0-9]{0,19}',value['process_creation_time'])):
        raise ValueError('invalid report process creation identity')
    for key,expected in (('resource_scope',RESOURCE_SCOPE),('timing_scope',TIMING_SCOPE)):
        if key in value and value[key] != expected: raise ValueError('invalid report measurement scope')
    if not value['synthetic_demo'] and not REPORT_OPTIONAL_KEYS <= set(value):
        raise ValueError('complete worker provenance required')


def preflight_paths(out, report, *, protected=()):
    # The fixed CLI's exact protection rules also apply to direct API callers.
    from .cli import validate_generation_paths
    out, report = validate_generation_paths(Path(out), Path(report))
    if out.parent.name.startswith('.'): raise ValueError('scratch name cannot be a final generation')
    for source in protected:
        source = Path(source).absolute()
        cache.reject_reparse(source)
        if out.parent == source or out.parent.is_relative_to(source) or source.is_relative_to(out.parent):
            raise ValueError('generation overlaps a protected release/input')
    for path in (out, report):
        if path.suffix.lower() != ('.csv' if path == out else '.json'):
            raise ValueError('CSV and JSON filenames required')
        if path.name[-1:] in (' ', '.') or any(ord(c)<32 or ord(c)==127 or c in ':<>"|?*' for c in path.name):
            raise ValueError('unsafe generation filename')
        if path.name.split('.',1)[0].upper() in {'CON','PRN','AUX','NUL','CONIN$','CONOUT$',
                *(f'COM{i}' for i in '123456789¹²³'),*(f'LPT{i}' for i in '123456789¹²³')}:
            raise ValueError('reserved generation filename')
    return out, report


def validate_codes(codes):
    if not isinstance(codes, np.ndarray) or codes.dtype != np.int8 or codes.shape != (FRAMES,):
        raise ValueError('exact full-timeline int8 codes required')
    if not np.isin(codes, (0, 1, 2, 3)).all():
        raise ValueError('invalid label alphabet')
    previous = 0
    for _, start, stop in PERIODS:
        if np.any(codes[previous:start] != 3) or np.any(codes[start:stop] == 3):
            raise ValueError('public active/inactive bounds violated')
        previous = stop
    if np.any(codes[previous:] != 3) or np.any(codes[110808:113742] != 2):
        raise ValueError('public bounds/dead interval violated')


def _write(path, payload):
    with Path(path).open('xb') as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _json_file(path, maximum=2097152):
    with cache.ReadLease(path) as held:
        if held.size > maximum:
            raise ValueError('oversized JSON document')
        return cache.strict_json(held.read())


def _record(lease):
    return {'filename': lease.path.name, 'bytes': lease.size, 'sha256': lease.sha256()}


def _official_validate(csv_path, root):
    # Invoke the organizer validator function itself, never a GT/scoring entry.
    source = Path(root)/'more-than-a-hack-2027-main/evaluation/possession_metrics.py'
    with cache.ReadLease(source) as held:
        spec = importlib.util.spec_from_file_location('_v3_official_format_validator', source)
        module = importlib.util.module_from_spec(spec)
        exec(compile(held.read(), str(source), 'exec'), module.__dict__)
        with cache.ReadLease(csv_path) as csv_held:
            reason = module.validate_submission(module.read_label_csv(csv_held.file), FRAMES)
        if reason:
            raise ValueError('official format validation failed')


def publish_generation(out, report, codes, provenance, root, *, started=None):
    """One no-replace directory rename is the sole publication operation.

    Interrupted scratch is deliberately retained and ignored by readers. Every
    output writer is closed/fsynced and the complete pair reverified first.
    """
    out, report = preflight_paths(out, report)
    validate_codes(codes)
    for key in ('release_digest', 'source_manifest_digest', 'policy_digest'):
        if not isinstance(provenance.get(key), str) or not cache.HEX64.fullmatch(provenance[key]):
            raise ValueError('generation provenance digest missing')
    if type(provenance.get('release_id')) is not str or not provenance['release_id']:
        raise ValueError('generation release identity missing')
    stage = out.parent.with_name('.partial-v3-' + uuid.uuid4().hex)
    stage.mkdir()
    staged_csv, staged_report = stage/out.name, stage/report.name
    labels = 'HADX'
    with staged_csv.open('x', encoding='utf-8', newline='') as handle:
        handle.write('frame,label\n')
        for frame, code in enumerate(codes):
            handle.write(f'{frame},{labels[int(code)]}\n')
        handle.flush(); os.fsync(handle.fileno())
    _official_validate(staged_csv, root)
    with cache.ReadLease(staged_csv) as held:
        csv_record = _record(held)
    if started is not None:
        provenance={**provenance,'total_seconds':time.perf_counter()-started,
                    'peak_process_working_set_bytes':peak_working_set(),
                    'timing_scope':TIMING_SCOPE}
    value = {**provenance, 'schema_version': 1, 'kind': 'v3-inference-report',
             'generation_id':out.parent.name,'csv_filename':out.name,
             'csv_sha256': csv_record['sha256'], 'frame_count': FRAMES,
             'official_format_validator': 'passed', 'public_bounds': 'passed'}
    _validate_report(value)
    _write(staged_report, cache.canonical_json(value))
    with cache.ReadLease(staged_report) as held:
        report_record = _record(held)
    commit = {key: value[key] for key in ('generation_id','release_digest','source_manifest_digest','policy_digest')}
    commit.update(schema_version=1, kind='v3-run-generation', csv=csv_record, report=report_record)
    _write(stage/'commit.json', cache.canonical_json(commit))
    _verify_staged_generation(stage,out.parent,value['release_digest'])
    # Windows rename fails if the destination already exists; no replace=True,
    # unlink, per-file move, recovery repair or previous-generation overwrite.
    if os.name != 'nt':
        raise RuntimeError('no-replace Windows publication required')
    stage.rename(out.parent)
    return value


class _GenerationLease:
    def __init__(self, directory, expected_release=None, *, _intended_final=None):
        self.directory = Path(directory).absolute()
        cache.reject_reparse(self.directory)
        if self.directory.name.startswith('.') and _intended_final is None:
            raise ValueError('scratch generations are unavailable')
        generation_id=self.directory.name if _intended_final is None else _intended_final.name
        self.stack = ExitStack()
        try:
            commit_lease = self.stack.enter_context(cache.ReadLease(self.directory/'commit.json'))
            if commit_lease.size > 16384: raise ValueError('oversized generation commit')
            self.commit = cache.strict_json(commit_lease.read())
            if (type(self.commit) is not dict or set(self.commit) != COMMIT_KEYS or type(self.commit['schema_version']) is not int
                    or self.commit['schema_version'] != 1 or self.commit['kind'] != 'v3-run-generation'):
                raise ValueError('closed generation commit required')
            for name in ('release_digest','source_manifest_digest','policy_digest'):
                if type(self.commit[name]) is not str or not cache.HEX64.fullmatch(self.commit[name]):
                    raise ValueError('invalid committed identity')
            if type(self.commit['generation_id']) is not str or self.commit['generation_id'] != generation_id:
                raise ValueError('generation directory identity mismatch')
            if expected_release is not None and self.commit['release_digest'] != expected_release:
                raise ValueError('generation belongs to another release')
            files = {role:self.commit[role] for role in ('csv','report')}
            self.leases = {}
            for role, record in files.items():
                if (type(record) is not dict or set(record) != {'filename','bytes','sha256'} or type(record['bytes']) is not int
                        or not 0 < record['bytes'] < 50000000 or type(record['filename']) is not str
                        or type(record['sha256']) is not str or not cache.HEX64.fullmatch(record['sha256'])):
                    raise ValueError('invalid generation member')
                if Path(record['filename']).name != record['filename'] or record['filename'].casefold() == 'commit.json':
                    raise ValueError('unsafe generation member')
                path = cache.confined_path(self.directory,record['filename'])
                held = self.stack.enter_context(cache.ReadLease(path)); held.verify(record)
                self.leases[role] = held
            if self.leases['csv'].identity[:2] == self.leases['report'].identity[:2]:
                raise ValueError('aliased generation members')
            expected_names = {'commit.json', *(x['filename'] for x in files.values())}
            if len(expected_names) != 3 or set(p.name for p in self.directory.iterdir()) != expected_names:
                raise ValueError('generation member set mismatch')
            held = self.leases['report']
            if held.size > 2097152: raise ValueError('oversized generation report')
            self.report = cache.strict_json(held.read())
            _validate_report(self.report)
            if any(self.report[key] != self.commit[key] for key in ('generation_id','release_digest','source_manifest_digest','policy_digest')):
                raise ValueError('report/commit identity mismatch')
            if (self.report['csv_sha256'] != files['csv']['sha256']
                    or self.report['csv_filename'] != files['csv']['filename']):
                raise ValueError('report/CSV validation binding mismatch')
            self.summary = self._inspect()
        except BaseException:
            self.stack.close(); raise
    def __enter__(self): return self
    def __exit__(self,*exc): self.stack.close()
    def read(self, role):
        held=self.leases[role]; held.seek(0); return held.read()
    def inspect(self):
        self.leases['csv']._check()
        return self.summary
    def _inspect(self):
        held = self.leases['csv']; held.seek(0)
        wrapper = io.TextIOWrapper(held.file,encoding='utf-8',newline='')
        counts = dict.fromkeys('HADX',0); segments=[]; codes=np.empty(FRAMES,dtype=np.int8)
        try:
            reader=csv.reader(wrapper,strict=True)
            if next(reader,None) != ['frame','label']: raise ValueError('invalid CSV header')
            count=0
            for frame,row in enumerate(reader):
                if frame>=FRAMES or len(row)!=2 or row[0]!=str(frame) or row[1] not in counts:
                    raise ValueError('invalid CSV frame/label contract')
                label=row[1]; codes[frame]='HADX'.index(label); counts[label]+=1; count+=1
                if segments and segments[-1]['label']==label: segments[-1]['end']=frame+1
                else: segments.append({'start':frame,'end':frame+1,'label':label})
            if count!=FRAMES: raise ValueError('incomplete CSV')
            validate_codes(codes)
        except (UnicodeError,csv.Error):
            raise ValueError('invalid CSV encoding/structure') from None
        finally:
            wrapper.detach(); held.seek(0)
        live=counts['H']+counts['A']
        return {'present':True,'valid':True,'frames':FRAMES,'counts':counts,'segments':segments,
                'sha256':self.commit['csv']['sha256'],
                'live_possession':{x:round(100*counts[x]/live,2) if live else 0 for x in 'HA'}}


class GenerationLease(_GenerationLease):
    """Public reader: only a committed final directory with its exact basename."""
    def __init__(self,directory,expected_release=None):
        super().__init__(directory,expected_release)


def open_generation(directory, expected_release=None):
    return GenerationLease(directory,expected_release)


def _verify_staged_generation(stage, final_directory, expected_release):
    """Publisher-only check binds this sibling scratch to its intended final ID."""
    stage=Path(stage).absolute(); final_directory=Path(final_directory).absolute()
    cache.reject_reparse(final_directory)
    if (stage.parent != final_directory.parent or final_directory.exists()
            or final_directory.name.startswith('.')
            or not re.fullmatch(r'\.partial-v3-[0-9a-f]{32}',stage.name)):
        raise ValueError('invalid staged publication identity')
    with _GenerationLease(stage,expected_release,_intended_final=final_directory): pass


def extract_features(context, *, n_frames=FRAMES, blocks=PERIODS):
    """Parse the exact already-verified XML/TXT identities; never reopen paths."""
    from possession_model.features import _metadata, _numbers, FeatureAccumulator
    from .corruption import finalize_features
    xml, raw = context.source_leases
    for held in (xml,raw): cache.assert_release_access(context.access,held.path,'raw_observations')
    xml.seek(0)
    sides, xy_indices, ball_indices = _metadata(xml.file,n_frames,25.)
    accumulator = FeatureAccumulator(n_frames,sides,25.,PITCH,blocks)
    scale=np.asarray(PITCH,dtype=np.float64); indices=np.arange(len(sides))[:,None]
    raw.seek(0); count=0
    while True:
        line=raw.file.readline(1048577)
        if not line: break
        if len(line)>1048576: raise ValueError('oversized ATD record')
        try: text=line.decode('utf-8-sig' if count==0 else 'utf-8')
        except UnicodeError: raise ValueError('invalid ATD encoding') from None
        parts=text.strip().split(':')
        if len(parts)!=3 or not parts[0].isascii() or not parts[0].isdigit() or count>=n_frames or parts[0]!=str(count+1):
            raise ValueError('invalid ATD sequence')
        groups=parts[1].split(';')
        if len(groups)!=len(sides) or any(g.count(',')!=2 or any(not x.strip() for x in g.split(',')) for g in groups):
            raise ValueError('invalid ATD player channels')
        if parts[2].count(',')!=2 or any(not x.strip() for x in parts[2].split(',')):
            raise ValueError('invalid ATD ball channels')
        players=_numbers(parts[1].replace(';',','),len(sides)*3).reshape(-1,3)
        ball=_numbers(parts[2],3)
        accumulator.push(count,players[indices,xy_indices]*scale,ball[list(ball_indices)]*scale)
        count+=1
    if count!=n_frames: raise ValueError('incomplete ATD sequence')
    return finalize_features(accumulator.finish(),slot_ids_digest=None)


def peak_working_set():
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in
            ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
    process=ctypes.WinDLL('kernel32').GetCurrentProcess
    process.restype=wintypes.HANDLE
    api=ctypes.WinDLL('psapi').GetProcessMemoryInfo
    api.argtypes=(wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD)
    counters=Counters(); counters.cb=ctypes.sizeof(counters)
    if not api(process(),ctypes.byref(counters),counters.cb): raise OSError('worker memory query failed')
    return int(counters.PeakWorkingSetSize)


def _feature_metadata(context, doc, features=None):
    return {'domain':'release','kind':'features','input_kind':context.access.input_kind,
            'release_digest':context.access.release_digest,'source_manifest_digest':context.access.source_manifest_digest,
            'runtime_digest':context.access.runtime_digest,'policy_digest':context.access.policy_digest,
            'feature_transform_digest':doc['scientific_digest'],'n_frames':FRAMES,
            'fps':25.,'pitch':list(PITCH),'feature_names':list(cache.FEATURE_ARRAYS),
            'feature_metadata':{} if features is None else features.metadata}


def run_release(release, data_dir, out, report, use_cache=True):
    started=time.perf_counter()
    release=Path(release).absolute(); data_dir=Path(data_dir).absolute()
    out,report=preflight_paths(out,report,protected=(release,data_dir))
    if type(use_cache) is not bool: raise ValueError('use_cache must be boolean')
    doc,release_digest=cache._release_document(release)
    preflight_paths(out,report,protected=[release.parent/item['relative_path'] for item in doc['files']])
    cache_root=out.parent.parent/'v3-feature-cache'
    with ExitStack() as stack:
        # Hold the manifest and complete code/model closure throughout loading,
        # inference, official validation and committed publication.
        release_held=stack.enter_context(cache.ReadLease(release))
        if release_held.sha256()!=release_digest: raise ValueError('release changed')
        held_files={}
        for record in doc['files']:
            held=stack.enter_context(cache.ReadLease(cache.confined_path(release.parent,record['relative_path'])))
            held.verify(record); held_files[record['relative_path']]=held
        config_held=held_files[doc['models']['config']]
        if config_held.size>16384: raise ValueError('oversized candidate config')
        config_held.seek(0)
        if cache.canonical_json(cache.strict_json(config_held.read()))!=cache.canonical_json(doc['candidate']):
            raise ValueError('candidate config differs from release')
        from .contracts import CandidateConfig,ModelBundle
        from possession_model.trees import TreeModel
        from .boundary import NumericHead
        from .core import predict_codes
        emitter_held=held_files[doc['models']['emitter']]
        emitter_held.seek(0); emitter=TreeModel(cache.strict_json(emitter_held.read()))
        head=None
        if doc['models']['head'] is not None:
            held=held_files[doc['models']['head']]
            if held.size>524288: raise ValueError('oversized boundary head')
            held.seek(0); head=NumericHead(cache.strict_json(held.read()))
        models=ModelBundle(emitter,head,doc['provenance']['model_seal_digest'])
        config=CandidateConfig(**doc['candidate'])
        _verify_loaded_code(stack,doc)
        context=stack.enter_context(cache.open_inference_context(release,data_dir,cache_root,'challenge_observations'))
        metadata=_feature_metadata(context,doc)
        key=cache.digest_json({k:v for k,v in metadata.items() if k!='feature_metadata'})
        target=cache_root/key; hit=False
        if use_cache and target.exists():
            # Expected transform metadata is read under its own immutable lease,
            # then the complete closed cache verifier checks every member.
            with cache.ReadLease(target/'cache.json') as held:
                if held.size>2097152: raise ValueError('oversized cache manifest')
                cached=cache.strict_json(held.read())
                metadata['feature_metadata']=cached['metadata']['feature_metadata']
            lease=stack.enter_context(cache.verify_cache(target,metadata,context.access))
            from possession_model.schema import FeatureSet
            features=FeatureSet(fps=25.,pitch=PITCH,metadata=dict(metadata['feature_metadata']),**lease.arrays)
            hit=True
        else:
            features=extract_features(context)
            if use_cache:
                cache_root.mkdir(exist_ok=True)
                metadata=_feature_metadata(context,doc,features)
                cache.write_cache_atomic(target,{name:getattr(features,name) for name in cache.FEATURE_ARRAYS},metadata,context.access)
        _verify_loaded_code(stack,doc)
        codes=predict_codes(features,models,config,context.policy)
        validate_codes(codes)
        provenance={'release_id':doc['release_id'],'release_digest':release_digest,
                    'source_manifest_digest':context.access.source_manifest_digest,'policy_digest':doc['policy_digest'],
                    'runtime_digest':doc['runtime_digest'],'scientific_digest':doc['scientific_digest'],
                    'model_seal_digest':doc['provenance']['model_seal_digest'],'finalist_digest':doc['provenance']['finalist_digest'],
                    'candidate_id':config.candidate_id,'cache_hit':hit,'synthetic_demo':False,
                    'inference_seconds':time.perf_counter()-started,'peak_process_working_set_bytes':peak_working_set(),
                    'process_id':os.getpid(),'process_creation_time':cache.process_creation_time(),
                    'resource_scope':RESOURCE_SCOPE}
        return publish_generation(out,report,codes,provenance,release.parent,started=started)


def _verify_loaded_code(stack,doc):
    """An explicit manifest cannot silently execute different imported sources."""
    by_name={record['relative_path']:record for record in doc['files']}
    for name,module in tuple(sys.modules.items()):
        if not name.startswith(('experiments.','possession_model.','review_app.','validation.')): continue
        source=getattr(module,'__file__',None)
        if not source: continue
        relative=name.replace('.','/')+('.py' if Path(source).name!='__init__.py' else '/__init__.py')
        record=by_name.get(relative)
        if record is None: continue
        held=stack.enter_context(cache.ReadLease(Path(source)))
        held.verify(record)


if __name__=='__main__':
    from .cli import main
    raise SystemExit(main(['run',*sys.argv[1:]]))
