"""Stable Windows identities, closed numeric caches and standalone authority.

Wire formats are deliberately declarative. Cache JSON has exactly
schema_version, metadata, members; metadata keys are META_* below. Member records
have filename,bytes,sha256,dtype,shape,order. Release JSON has RELEASE_KEYS below;
files are canonical sorted relative-path records with bytes/sha256/role. The
runtime digest is SHA256(canonical JSON(files)); scientific_digest binds the
subset role=scientific. No verifier callback or study lookup is used in release.

Mappings may only be used inside CacheLease. Consumers needing longer lifetime
must make owned copies before exit. The arrays property refuses access on exit.

Feature diagnostic metadata is a closed optional-key object: string identities
FEATURE_DIAGNOSTIC_IDENTITIES, integer counters FEATURE_DIAGNOSTIC_INTS, finite
positive measurements FEATURE_DIAGNOSTIC_NUMBERS, exact producer booleans, and an
optional slot_ids_digest. Empty is valid. Observation normalization_counts has
exactly coordinate_pairs, a nonnegative native integer bounded by sparse rows.
Accepted load_atd additionally supplies optional input_format (the exact ATD
identity) and raw_records (a native positive integer equal to cache n_frames).
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import ExitStack
import ctypes
from ctypes import wintypes
import hashlib
import json
import math
import mmap
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import time
import uuid
import weakref
from types import MappingProxyType
import numpy as np

from .contracts import AccessCapability, ReleaseAccess, InferenceContext, InferencePolicy

HEX64=re.compile(r'[0-9a-f]{64}\Z')
OBSERVATION_ARRAYS={'frame_id':'int64','source_frame_id':'int64','period_id':'int16','positions':'float32',
                    'ball_xy':'float32','team_of_slot':'int8','source_time_frame_index':'int64',
                    'source_time_slot':'int32','source_time_utc_ns':'int64'}
FEATURE_ARRAYS={'period_id':'int16','ball_xy':'float32','ball_observed':'bool','nearest':'float32',
                'tracked_counts':'int16','collective_speed':'float32','ball_speed':'float32'}
META_STUDY={'domain','kind','fixture_id','role','attempt_id','study_digest','source_digest','protocol_digest',
            'dependency_digest','environment_digest','config_digest','condition','seeds','n_frames'}
META_RELEASE={'domain','kind','input_kind','release_digest','source_manifest_digest','runtime_digest',
              'policy_digest','feature_transform_digest','n_frames'}
OBS_META={'n_slots','slot_ids','slot_ids_digest','period_origins','fps','pitch','normalization_counts'}
FEATURE_META={'fps','pitch','feature_names','feature_metadata'}
FEATURE_DIAGNOSTIC_IDENTITIES={
    'input_format':frozenset({'metrica-epts-normalized'}),
    'feature_version':frozenset({'streaming-v1'}),
    'collective_resampling':frozenset({'causal hold, reset immediately on insufficient observations'}),
    'collective_motion':frozenset({'symmetric median nearest-set displacement; anonymous slots'}),
    'ball_speed_method':frozenset({'median adjacent speed; uninterrupted observations only','centred full-window local-linear x/y slope magnitude'}),
    'ball_motion_transform':frozenset({'noise-v2-local-linear-1.2s'}),
    'ball_motion_method':frozenset({'magnitude of centred full-window x/y linear slopes'}),
    'ball_motion_observation_policy':frozenset({'reliable same-period runs; no gap interpolation'}),
    'v3_feature_transform':frozenset({'accepted-streaming-v1+noise-v2-local-linear-1.2s'})}
FEATURE_DIAGNOSTIC_INTS={'raw_records':1,'slots':1,'player_ring_bytes':0,'collective_lag_frames':1,
    'collective_sample_stride_frames':1,'ball_speed_window_frames':1,'ball_motion_window_frames':1}
FEATURE_DIAGNOSTIC_NUMBERS=frozenset({'ball_jump_limit_m_s','collective_speed_limit_m_s',
    'ball_motion_nominal_window_seconds','ball_motion_window_span_seconds','ball_motion_jump_limit_m_s'})
FEATURE_DIAGNOSTIC_BOOLS={'exported_speeds_used':False,'ball_motion_offline':True}
RELEASE_KEYS={'schema_version','kind','release_id','scientific_digest','runtime_digest','files','policy',
              'policy_digest','candidate','models','provenance'}
RELEASE_FILE_ROLES={'scientific','runtime','config','emitter','head','notice'}
REQUIRED_SCIENTIFIC_PATHS=frozenset(
    ['experiments/v3/'+name+'.py' for name in ('__init__','contracts','guard','cache','adapter','corruption','fetch','boundary','decoder','training','evaluate','resources','core','cli')]
    +['possession_model/'+name+'.py' for name in ('__init__','features','schema','evidence','trees','decoder','pipeline')]
    +['experiments/__init__.py','experiments/noise_v2/__init__.py','experiments/noise_v2/features.py',
      'validation/sportec.py','validation/metrics.py','tools/train_and_validate.py','tools/run_candidate.py',
      'more-than-a-hack-2027-main/evaluation/possession_metrics.py',
      'more-than-a-hack-2027-main/evaluation/validate_submission.py',
      'more-than-a-hack-2027-main/games.py','more-than-a-hack-2027-main/FAQ.md'])
REQUIRED_RUNTIME_PATHS=frozenset(['requirements-lock.txt']+
    ['experiments/v3/'+name+'.py' for name in ('runner','exporting','review','promotion')])
SOURCE_NAMES=('tactical/BAR-ATH_tactical_atd.xml','tactical/BAR-ATH_tactical_atd.txt')
_RELEASE_GRANTS={}


def canonical_json(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')


def digest_json(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


def strict_json(data):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: raise ValueError('duplicate JSON key')
            result[key]=value
        return result
    def nonfinite(value): raise ValueError('nonfinite JSON constant')
    return json.loads(data,object_pairs_hook=pairs,parse_constant=nonfinite)


def confined_path(root: Path, relative: str) -> Path:
    if type(relative) is not str or not relative or '\\' in relative:
        raise ValueError('normalized relative path required')
    rel=PurePosixPath(relative)
    if rel.is_absolute() or str(rel)!=relative or any(x in ('','..','.') or ':' in x for x in rel.parts):
        raise ValueError('unsafe relative path')
    root=Path(root).absolute()
    path=root.joinpath(*rel.parts)
    reject_reparse(path)
    if not path.resolve().is_relative_to(root.resolve()): raise ValueError('path escapes root')
    return path


def reject_reparse(path: Path):
    path=Path(path).absolute()
    for part in (path,*path.parents):
        try: info=part.lstat()
        except FileNotFoundError: continue
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
            raise ValueError('symlink/reparse path refused')


def process_creation_time(pid=None):
    if os.name!='nt': raise RuntimeError('v3 stable identity requires Windows')
    pid=os.getpid() if pid is None else pid
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=(wintypes.DWORD,wintypes.BOOL,wintypes.DWORD); kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.GetProcessTimes.argtypes=(wintypes.HANDLE,ctypes.POINTER(wintypes.FILETIME),ctypes.POINTER(wintypes.FILETIME),ctypes.POINTER(wintypes.FILETIME),ctypes.POINTER(wintypes.FILETIME))
    kernel.CloseHandle.argtypes=(wintypes.HANDLE,)
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle: raise OSError(ctypes.get_last_error(),'process identity unavailable')
    try:
        times=[wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle,*[ctypes.byref(x) for x in times]):
            raise OSError(ctypes.get_last_error(),'process times unavailable')
        return str((times[0].dwHighDateTime<<32)|times[0].dwLowDateTime)
    finally: kernel.CloseHandle(handle)


class ReadLease:
    """One file identity, FILE_SHARE_READ only, from hashing through final use."""
    def __init__(self,path: Path):
        if os.name!='nt': raise RuntimeError('Windows immutable read handles required')
        import msvcrt
        self.path=Path(path).absolute(); reject_reparse(self.path); self.closed=True
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=(wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE)
        kernel.CreateFileW.restype=wintypes.HANDLE
        kernel.CloseHandle.argtypes=(wintypes.HANDLE,)
        handle=kernel.CreateFileW(str(self.path),0x80000000,0x1,None,3,0x08000000,None)
        if handle==ctypes.c_void_p(-1).value: raise OSError(ctypes.get_last_error(),'stable read acquisition failed')
        try: fd=msvcrt.open_osfhandle(handle,os.O_RDONLY|os.O_BINARY)
        except BaseException:
            kernel.CloseHandle(handle); raise
        self.file=os.fdopen(fd,'rb',buffering=0); self.closed=False
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
            self.close(); raise ValueError('regular unaliased file required')
        self.identity=(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)
    def __enter__(self): self._check(); return self
    def __exit__(self,*exc): self.close()
    def _check(self):
        if self.closed: raise RuntimeError('ReadLease is closed')
        i=os.fstat(self.file.fileno())
        if (i.st_dev,i.st_ino,i.st_size,i.st_mtime_ns)!=self.identity: raise ValueError('held file identity changed')
    def read(self,size=-1): self._check(); return self.file.read(size)
    def seek(self,*args): self._check(); return self.file.seek(*args)
    def fileno(self): self._check(); return self.file.fileno()
    @property
    def size(self): self._check(); return self.identity[2]
    def hashes(self):
        self._check(); self.seek(0); sha=hashlib.sha256(); md5=hashlib.md5()
        for block in iter(lambda:self.read(1024*1024),b''): sha.update(block); md5.update(block)
        self.seek(0); self._check(); return sha.hexdigest(),md5.hexdigest()
    def sha256(self): return self.hashes()[0]
    def verify(self,record):
        if type(record) is not dict or type(record.get('bytes')) is not int or record['bytes']<0 or type(record.get('sha256')) is not str or not HEX64.fullmatch(record['sha256']):
            raise ValueError('exact source integrity types required')
        if 'md5' in record and (type(record['md5']) is not str or not re.fullmatch(r'[0-9a-f]{32}',record['md5'])):
            raise ValueError('exact MD5 string required')
        sha,md5=self.hashes()
        if self.size!=record['bytes'] or sha!=record['sha256'] or ('md5' in record and md5!=record['md5']):
            raise ValueError('source integrity mismatch')
        return sha
    def close(self):
        if not self.closed: self.file.close(); self.closed=True


def assert_release_access(access: ReleaseAccess, source: Path, kind: str) -> None:
    if type(access) is not ReleaseAccess or kind not in ('raw_observations','observations','features'):
        raise PermissionError('invalid release authority/kind')
    grant=_RELEASE_GRANTS.get(id(access))
    if grant is None or grant['access']() is not access or access.process_id!=os.getpid() or access.process_creation_time!=process_creation_time():
        raise PermissionError('unminted/stale process release authority')
    if any(lease.closed for lease in grant['leases']): raise PermissionError('release context closed')
    source=Path(source).absolute()
    if kind=='raw_observations':
        found=[lease for lease in grant['leases'] if lease.path==source]
        if len(found)!=1: raise PermissionError('unregistered observation source')
        found[0]._check()
    else:
        reject_reparse(source)
        if not source.resolve().is_relative_to(access.cache_root): raise PermissionError('release cache escapes root')


def assert_cache_authority(authority,domain,kind):
    if type(domain) is not str or type(kind) is not str or domain not in ('study','release') or kind not in ('observations','features','targets'):
        raise PermissionError('invalid cache domain/kind')
    if type(authority) is AccessCapability:
        if domain!='study': raise PermissionError('study capability cannot authorize release')
        for fixture in authority.fixture_ids:
            _assert_study_access(authority,fixture,'observations' if kind=='features' else kind)
    elif type(authority) is ReleaseAccess:
        if domain!='release' or kind=='targets': raise PermissionError('release cannot authorize study/targets')
        assert_release_access(authority,authority.cache_root,kind)
    else: raise PermissionError('exact cache authority required')


def _assert_study_access(cap,fixture,kind):
    # Lazy import is necessary: extracted observation-only releases do not ship
    # or consult the original study/control implementation at all.
    from .guard import assert_access
    return assert_access(cap,fixture,kind)


def _metadata(metadata,authority,path=None):
    if type(metadata) is not dict: raise ValueError('cache metadata required')
    domain=metadata.get('domain'); kind=metadata.get('kind')
    assert_cache_authority(authority,domain,kind)
    base=META_STUDY if domain=='study' else META_RELEASE
    extra=OBS_META if kind=='observations' else FEATURE_META if kind=='features' else set()
    if set(metadata)!=base|extra: raise ValueError('closed cache metadata keys required')
    n=metadata['n_frames']
    if type(n) is not int or n<=0: raise ValueError('positive n_frames required')
    for k,v in metadata.items():
        if k.endswith('_digest') and (type(v) is not str or not HEX64.fullmatch(v)):
            raise ValueError('invalid cache digest '+k)
    if domain=='study':
        if any(type(metadata[key]) is not str or not metadata[key] for key in ('fixture_id','role','attempt_id','condition')) or metadata['role'] not in ('train','selection','test'):
            raise ValueError('exact study identity strings required')
        if metadata['fixture_id'] not in authority.fixture_ids or metadata['study_digest']!=authority.study_digest or metadata['attempt_id']!=authority.attempt_id or metadata['role']!=authority.role:
            raise PermissionError('cache study binding mismatch')
        if metadata['fixture_id'] in ('J03WR9','J03WMX'): raise PermissionError('closed fixture')
        from .corruption import CONDITIONS,validate_condition_inputs
        if metadata['condition'] not in CONDITIONS or type(metadata['seeds']) is not dict: raise ValueError('invalid condition/seed metadata')
        validate_condition_inputs(CONDITIONS[metadata['condition']],metadata['seeds'])
    else:
        for k in ('input_kind','release_digest','source_manifest_digest','runtime_digest','policy_digest'):
            if metadata[k]!=getattr(authority,k): raise PermissionError('release cache binding mismatch')
        if path is not None: assert_release_access(authority,path,kind)
    if kind in ('observations','features'):
        if type(metadata['fps']) not in (float,int) or not np.isfinite(metadata['fps']) or abs(metadata['fps']-25)>1e-6 or type(metadata['pitch']) is not list or len(metadata['pitch'])!=2 or any(type(x) not in (float,int) or not np.isfinite(x) or x<=0 for x in metadata['pitch']):
            raise ValueError('invalid cache fps/pitch')
    if kind=='observations':
        slots=metadata['slot_ids']; count=metadata['n_slots']
        if type(count) is not int or count<=0 or type(slots) is not list or len(slots)!=count or any(type(x) is not str or not x for x in slots) or len(set(slots))!=count:
            raise ValueError('exact ordered slot string list required')
        try: slot_digest=hashlib.sha256(json.dumps(slots,ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest()
        except UnicodeError: raise ValueError('invalid UTF8 slot identity') from None
        if slot_digest!=metadata['slot_ids_digest']: raise ValueError('slot identity digest mismatch')
        origins=metadata['period_origins']
        if type(origins) is not list: raise ValueError('origin metadata must be a list')
        for origin in origins:
            if type(origin) is not dict or set(origin)!={'period_id','source_frame_id','utc_ns'} or any(type(v) is not int for v in origin.values()) or origin['period_id'] not in (1,2,3,4) or not 0<=origin['source_frame_id']<2**63 or not -(2**63)<=origin['utc_ns']<2**63:
                raise ValueError('closed exact integer period origins required')
        normalization=metadata['normalization_counts']
        if type(normalization) is not dict or set(normalization)!={'coordinate_pairs'} or type(normalization['coordinate_pairs']) is not int or normalization['coordinate_pairs']<0:
            raise ValueError('closed exact integer normalization count required')
    if kind=='features':
        if type(metadata['feature_names']) is not list or any(type(x) is not str for x in metadata['feature_names']) or metadata['feature_names']!=list(FEATURE_ARRAYS):
            raise ValueError('exact feature name list required')
        _feature_diagnostics(metadata['feature_metadata'])
        if 'raw_records' in metadata['feature_metadata'] and metadata['feature_metadata']['raw_records']!=n:
            raise ValueError('ATD raw record count must equal cache frame count')
    canonical_json(metadata)


def _feature_diagnostics(metadata):
    from .corruption import plain_diagnostic_metadata
    plain_diagnostic_metadata(metadata)
    allowed=set(FEATURE_DIAGNOSTIC_IDENTITIES)|set(FEATURE_DIAGNOSTIC_INTS)|set(FEATURE_DIAGNOSTIC_NUMBERS)|set(FEATURE_DIAGNOSTIC_BOOLS)|{'slot_ids_digest'}
    if set(metadata)-allowed: raise ValueError('unknown feature diagnostic metadata key')
    for key,value in metadata.items():
        if key in FEATURE_DIAGNOSTIC_IDENTITIES:
            if type(value) is not str or value not in FEATURE_DIAGNOSTIC_IDENTITIES[key]: raise ValueError('malformed feature transform identity')
        elif key in FEATURE_DIAGNOSTIC_INTS:
            if type(value) is not int or value<FEATURE_DIAGNOSTIC_INTS[key]: raise ValueError('exact feature counter required')
        elif key in FEATURE_DIAGNOSTIC_NUMBERS:
            if type(value) not in (int,float) or not np.isfinite(value) or value<=0: raise ValueError('finite positive feature measurement required')
        elif key in FEATURE_DIAGNOSTIC_BOOLS:
            if type(value) is not bool or value is not FEATURE_DIAGNOSTIC_BOOLS[key]: raise ValueError('exact feature producer boolean required')
        elif type(value) is not str or not HEX64.fullmatch(value): raise ValueError('feature slot digest required')


def _schemas(metadata):
    n=metadata['n_frames']; kind=metadata['kind']
    if kind=='targets': return {'labels':('int8',(n,))}
    if kind=='features': return {name:(dtype,(n,2) if name in ('ball_xy','nearest','tracked_counts','collective_speed') else (n,)) for name,dtype in FEATURE_ARRAYS.items()}
    s=metadata['n_slots']
    if type(s) is not int or s<=0: raise ValueError('positive slot count required')
    return {name:(dtype,(n,s,2) if name=='positions' else (n,2) if name=='ball_xy' else (s,) if name=='team_of_slot' else (None,) if name.startswith('source_time_') else (n,)) for name,dtype in OBSERVATION_ARRAYS.items()}


def _validate_arrays(arrays,metadata):
    schemas=_schemas(metadata)
    if set(arrays)!=set(schemas): raise ValueError('exact allowlisted cache members required')
    for name,(dtype,shape) in schemas.items():
        arr=arrays[name]
        if not isinstance(arr,np.ndarray) or arr.dtype!=np.dtype(dtype) or arr.ndim!=len(shape) or any(x is not None and x!=y for x,y in zip(shape,arr.shape)) or not arr.flags.c_contiguous:
            raise ValueError('cache member dtype/shape/order mismatch: '+name)
        if arr.dtype.kind=='f' and np.isinf(arr).any(): raise ValueError('infinite cache member')
    kind=metadata['kind']
    if kind=='targets':
        if not np.isin(arrays['labels'],[-1,0,1,2]).all(): raise ValueError('invalid target member')
    elif kind=='observations':
        from .contracts import ObservationBatch,PeriodOrigin
        from .corruption import validate_observations
        origins=tuple(PeriodOrigin(**x) for x in metadata['period_origins'])
        obs=ObservationBatch(**arrays,slot_ids=tuple(metadata['slot_ids']),slot_ids_digest=metadata['slot_ids_digest'],period_origins=origins,
            fps=metadata['fps'],pitch=tuple(metadata['pitch']),fixture_id=metadata.get('fixture_id','release'),source_digest=metadata.get('source_digest',metadata.get('source_manifest_digest')))
        validate_observations(obs)
        if metadata['normalization_counts']['coordinate_pairs']>len(arrays['source_time_slot']):
            raise ValueError('normalization count exceeds observed records')
        for name in ('positions','ball_xy'):
            arr=arrays[name]
            if np.any(arr.view(np.uint32)[np.isnan(arr)]!=0x7fc00000): raise ValueError('noncanonical coordinate NaN payload')
    else:
        if not np.isin(arrays['period_id'],[0,1,2,3,4]).all() or (arrays['tracked_counts']<0).any(): raise ValueError('invalid features')
        finite=np.isfinite(arrays['ball_xy'])
        if np.any(finite.any(axis=-1)!=finite.all(axis=-1)) or not np.array_equal(finite.all(axis=-1),arrays['ball_observed']):
            raise ValueError('feature coordinate/mask mismatch')
        if metadata['feature_names']!=list(FEATURE_ARRAYS): raise ValueError('feature order mismatch')
        if any(np.any(arrays[name][np.isfinite(arrays[name])]<0) for name in ('nearest','collective_speed','ball_speed')):
            raise ValueError('negative distance/speed feature')


class _LeaseArray(np.ndarray):
    """Normal array access fails explicitly after its mapping lease expires.

    Deliberately stripping subclass/retaining raw pointers is outside the API;
    consumers must copy under the lease rather than keep escaped mapped views.
    """
    def __array_finalize__(self,source): self._lease_state=getattr(source,'_lease_state',None)
    def _check(self):
        state=getattr(self,'_lease_state',None)
        if state is not None and state['closed']: raise RuntimeError('mapped array lease is closed')
    def __getitem__(self,key): self._check(); return super().__getitem__(key)
    def __iter__(self): self._check(); return super().__iter__()
    def tobytes(self,*args,**kwargs): self._check(); return super().tobytes(*args,**kwargs)
    def copy(self,order='C'): self._check(); return np.array(self.view(np.ndarray),copy=True,order=order)
    def item(self,*args): self._check(); return super().item(*args)
    def astype(self,*args,**kwargs): self._check(); return super().astype(*args,**kwargs)
    def __array_ufunc__(self,ufunc,method,*inputs,**kwargs):
        def unwrap(value):
            if isinstance(value,_LeaseArray): value._check(); return value.view(np.ndarray)
            return value
        if 'out' in kwargs: kwargs['out']=tuple(unwrap(x) for x in kwargs['out'])
        return getattr(ufunc,method)(*[unwrap(x) for x in inputs],**kwargs)
    def __array_function__(self,func,types,args,kwargs):
        def unwrap(value):
            if isinstance(value,_LeaseArray): value._check(); return value.view(np.ndarray)
            if isinstance(value,tuple): return tuple(unwrap(x) for x in value)
            if isinstance(value,list): return [unwrap(x) for x in value]
            if isinstance(value,dict): return {k:unwrap(v) for k,v in value.items()}
            return value
        return func(*unwrap(args),**unwrap(kwargs))


class CacheLease:
    def __init__(self,manifest,arrays,leases,mappings):
        self.manifest=manifest; self._leases=leases; self._mappings=mappings; self.closed=False
        self._state={'closed':False}
        wrapped={}
        for name,arr in arrays.items():
            view=arr.view(_LeaseArray); view._lease_state=self._state; wrapped[name]=view
        self._arrays=MappingProxyType(wrapped)
    def __enter__(self):
        if self.closed: raise RuntimeError('CacheLease closed')
        return self
    @property
    def arrays(self):
        if self.closed: raise RuntimeError('CacheLease closed')
        return self._arrays
    def __exit__(self,*exc): self.close()
    def close(self):
        if not self.closed:
            self.closed=True; self._state['closed']=True; self._arrays=MappingProxyType({})
            for mapping in reversed(self._mappings): mapping.close()
            for lease in reversed(self._leases): lease.close()


def _npy_layout(lease,record):
    lease.seek(0)
    version=np.lib.format.read_magic(lease.file)
    if version not in ((1,0),(2,0)): raise ValueError('unsupported numeric NPY version')
    reader=np.lib.format.read_array_header_1_0 if version==(1,0) else np.lib.format.read_array_header_2_0
    shape,fortran,dtype=reader(lease.file,max_header_size=16384)
    offset=lease.file.tell()
    if dtype.hasobject or dtype.fields or dtype.subdtype or dtype.str!=record['dtype'] or list(shape)!=record['shape'] or fortran or record['order']!='C':
        raise ValueError('NPY header does not match manifest')
    if any(type(x) is not int or x<0 for x in shape) or offset+math.prod(shape)*dtype.itemsize!=lease.size:
        raise ValueError('NPY payload length mismatch')
    return shape,dtype,offset


def verify_cache(path: Path,expected: dict,authority) -> CacheLease:
    _metadata(expected,authority,path)
    path=Path(path); reject_reparse(path)
    leases=[]; mappings=[]
    try:
        manifest_lease=ReadLease(path/'cache.json'); leases.append(manifest_lease)
        if manifest_lease.size>1_048_576: raise ValueError('oversized cache manifest')
        document=strict_json(manifest_lease.read())
        if type(document) is not dict or set(document)!={'schema_version','metadata','members'} or type(document['schema_version']) is not int or document['schema_version']!=1:
            raise ValueError('cache manifest binding/schema mismatch')
        _metadata(document['metadata'],authority,path)
        if canonical_json(document['metadata'])!=canonical_json(expected): raise ValueError('exact cache metadata binding mismatch')
        records=document['members']; schemas=_schemas(expected)
        if type(records) is not dict or set(records)!=set(schemas): raise ValueError('cache exact member set mismatch')
        files={'cache.json'}; held={}; identities=set()
        for name,record in records.items():
            if type(record) is not dict or set(record)!={'filename','bytes','sha256','dtype','shape','order'} or type(record['filename']) is not str or record['filename']!=name+'.npy' or type(record['bytes']) is not int or record['bytes']<=0 or type(record['sha256']) is not str or not HEX64.fullmatch(record['sha256']) or type(record['dtype']) is not str or type(record['order']) is not str or record['order']!='C' or type(record['shape']) is not list or any(type(x) is not int or x<0 for x in record['shape']):
                raise ValueError('invalid cache member record')
            dtype,shape=schemas[name]
            if record['dtype']!=np.dtype(dtype).str or len(record['shape'])!=len(shape) or any(x is not None and x!=y for x,y in zip(shape,record['shape'])):
                raise ValueError('cache member schema mismatch before opening')
            member=confined_path(path,record['filename']); files.add(record['filename'])
            lease=ReadLease(member); leases.append(lease)
            if lease.identity[:2] in identities: raise ValueError('aliased cache members')
            identities.add(lease.identity[:2]); held[name]=lease
        if {p.name for p in path.iterdir()}!=files: raise ValueError('extra/missing cache directory entries')
        arrays={}
        # All hashes, byte sizes and headers are checked before the first mmap.
        layouts={}
        for name,lease in held.items():
            record=records[name]; lease.verify(record); layouts[name]=_npy_layout(lease,record)
            dtype,shape=schemas[name]
            if np.dtype(record['dtype'])!=np.dtype(dtype) or len(record['shape'])!=len(shape) or any(x is not None and x!=y for x,y in zip(shape,record['shape'])):
                raise ValueError('cache dtype/shape policy mismatch')
        for name,lease in held.items():
            shape,dtype,offset=layouts[name]
            mapping=mmap.mmap(lease.fileno(),0,access=mmap.ACCESS_READ); mappings.append(mapping)
            arrays[name]=np.ndarray(shape,dtype=dtype,buffer=mapping,offset=offset,order='C'); arrays[name].flags.writeable=False
        _validate_arrays(arrays,expected)
        return CacheLease(document,arrays,leases,mappings)
    except BaseException:
        for mapping in reversed(mappings): mapping.close()
        for lease in reversed(leases): lease.close()
        raise


def write_cache_atomic(path: Path,arrays: Mapping,metadata: dict,authority) -> dict:
    _metadata(metadata,authority,path); _validate_arrays(arrays,metadata)
    path=Path(path); reject_reparse(path); path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        with verify_cache(path,metadata,authority) as existing:
            for name,arr in arrays.items():
                if existing.arrays[name].tobytes()!=arr.tobytes(): raise ValueError('immutable cache differs')
            return existing.manifest
    reservation=path.with_name('.'+path.name+'.writer-reservation')
    try: lockfd=os.open(reservation,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:
        if path.exists():
            with verify_cache(path,metadata,authority) as existing:
                for name,arr in arrays.items():
                    if existing.arrays[name].tobytes()!=arr.tobytes(): raise ValueError('racing immutable cache differs')
                return existing.manifest
        raise FileExistsError('cache identity already reserved; no stale reset') from None
    try:
        os.write(lockfd,canonical_json({'pid':os.getpid(),'nonce':uuid.uuid4().hex})); os.fsync(lockfd)
        return _write_reserved_cache(path,arrays,metadata,authority)
    finally:
        os.close(lockfd); reservation.unlink()


def _write_reserved_cache(path,arrays,metadata,authority):
    temporary=path.with_name('.'+path.name+'.partial-'+uuid.uuid4().hex); temporary.mkdir()
    records={}
    for name,arr in arrays.items():
        member=temporary/(name+'.npy')
        with member.open('xb') as target:
            np.lib.format.write_array(target,arr,allow_pickle=False); target.flush(); os.fsync(target.fileno())
        with ReadLease(member) as lease:
            records[name]={'filename':member.name,'bytes':lease.size,'sha256':lease.sha256(),'dtype':arr.dtype.str,'shape':list(arr.shape),'order':'C'}
    document={'schema_version':1,'metadata':metadata,'members':records}
    with (temporary/'cache.json').open('xb') as target:
        target.write(canonical_json(document)); target.flush(); os.fsync(target.fileno())
    with verify_cache(temporary,metadata,authority): pass
    _publish_reserved_cache(temporary,path)
    return document


def _publication_identity(directory):
    """Stat the already verified staging tree without following reparse points."""
    reject_reparse(directory)
    def identity(path):
        reject_reparse(path); info=path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
            raise ValueError('cache publication reparse path refused')
        return (info.st_dev,info.st_ino,info.st_mode,info.st_size,info.st_mtime_ns,
                info.st_ctime_ns,info.st_nlink,getattr(info,'st_file_attributes',0))
    parent=identity(directory)
    if not stat.S_ISDIR(parent[2]): raise ValueError('cache staging directory required')
    members=[]
    for member in directory.iterdir():
        info=identity(member)
        if not stat.S_ISREG(info[2]) or info[6]!=1:
            raise ValueError('regular unaliased cache staging member required')
        members.append((member.name,info))
    return parent,tuple(sorted(members))


def _publish_reserved_cache(temporary,path):
    """Retry one no-replace publication, never a cache/model/cohort operation."""
    original=_publication_identity(temporary); deadline=time.monotonic()+1.0
    for attempt in range(50):
        if attempt and time.monotonic()>=deadline: raise last_error
        reject_reparse(path)
        try: path.lstat()
        except FileNotFoundError: pass
        else: raise FileExistsError('cache publication destination appeared')
        if _publication_identity(temporary)!=original:
            raise ValueError('cache staging identity changed during publication')
        try:
            # Windows os.rename (Path.rename) refuses an existing destination.
            temporary.rename(path)
            return
        except OSError as error:
            if (os.name!='nt' or isinstance(error,FileExistsError)
                    or getattr(error,'winerror',None) not in (5,32,33)):
                raise
            last_error=error
            remaining=deadline-time.monotonic()
            if attempt==49 or remaining<=0: raise
            time.sleep(min(.02,remaining))


def _release_document(release: Path):
    """Frozen wire verifier reused by T09; no raw inputs are accessed here."""
    with ReadLease(release) as held:
        if held.size>2_097_152: raise ValueError('oversized release manifest')
        raw=held.read(); doc=strict_json(raw)
    if type(doc) is not dict or set(doc)!=RELEASE_KEYS or type(doc['schema_version']) is not int or doc['schema_version']!=1 or doc['kind']!='v3-observation-release' or type(doc['release_id']) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',doc['release_id']):
        raise ValueError('closed release schema required')
    if any(type(doc[k]) is not str or not HEX64.fullmatch(doc[k]) for k in ('scientific_digest','runtime_digest','policy_digest')):
        raise ValueError('release digests require exact SHA256 strings')
    files=doc['files']
    if type(files) is not list or not files: raise ValueError('release closure required')
    names=[]; roles=set(); identities=set()
    for item in files:
        if type(item) is not dict or set(item)!={'relative_path','bytes','sha256','role'} or type(item['bytes']) is not int or not 0<=item['bytes']<50_000_000 or type(item['sha256']) is not str or not HEX64.fullmatch(item['sha256']) or type(item['role']) is not str or item['role'] not in RELEASE_FILE_ROLES:
            raise ValueError('invalid release closure member')
        name=item['relative_path']; path=confined_path(release.parent,name)
        if name==release.name or (name.lower().endswith('.txt') and name not in ('requirements-lock.txt','requirements-training-lock.txt')) or name.lower().endswith(('.xml','.npy','.npz','.csv','.mp4','.pkl','.pickle')) or any(x.lower() in ('local','data','targets','raw','study','control') for x in PurePosixPath(name).parts):
            raise ValueError('private/recursive release member refused')
        with ReadLease(path) as lease:
            lease.verify(item)
            if lease.identity[:2] in identities: raise ValueError('aliased closure members')
            identities.add(lease.identity[:2])
        names.append(name); roles.add(item['role'])
    if names!=sorted(set(names)) or not {'scientific','runtime','config','emitter'}.issubset(roles):
        raise ValueError('missing/unsorted release closure roles')
    by_name={item['relative_path']:item for item in files}
    for expected_role,required in (('scientific',REQUIRED_SCIENTIFIC_PATHS),('runtime',REQUIRED_RUNTIME_PATHS)):
        if any(name not in by_name or by_name[name]['role']!=expected_role for name in required):
            raise ValueError('incomplete frozen runtime/scientific closure')
    # Bind the executing verifier and shared type implementation, preventing a
    # declarative manifest from verifying a different cache/authority module.
    for name,loaded in (('experiments/v3/cache.py',Path(__file__)),
                        ('experiments/v3/contracts.py',Path(sys.modules[ReleaseAccess.__module__].__file__))):
        with ReadLease(loaded) as lease:
            if lease.sha256()!=by_name[name]['sha256']: raise ValueError('executing verifier/type closure mismatch')
    if digest_json(files)!=doc['runtime_digest'] or digest_json([x for x in files if x['role']=='scientific'])!=doc['scientific_digest']:
        raise ValueError('release closure digest mismatch')
    policy=doc['policy']
    if type(policy) is not dict or set(policy)!={'kind','forced_dead'} or policy['kind']!='challenge' or type(policy['forced_dead']) is not list or any(type(pair) is not list or len(pair)!=2 or any(type(frame) is not int for frame in pair) for pair in policy['forced_dead']) or policy['forced_dead']!=[[110808,113742]] or digest_json(policy)!=doc['policy_digest']:
        raise ValueError('exact public challenge policy required')
    candidate=doc['candidate']
    if type(candidate) is not dict or set(candidate)!={'candidate_id','alpha','support','transition_seconds'} or type(candidate['candidate_id']) is not str or type(candidate['support']) is not str or candidate['candidate_id'] not in ('A','F080','B080','C0','C1','D0050','D0080','D1050','D1080') or type(candidate['alpha']) not in (int,float) or type(candidate['transition_seconds']) not in (int,float) or not np.isfinite(candidate['alpha']) or candidate['transition_seconds']!=.5:
        raise ValueError('invalid release candidate')
    allowed={'A':(0,'none'),'F080':(.8,'flattened_valid_run_mean'),'B080':(.8,'learned'),'C0':(0,'none'),'C1':(0,'none'),'D0050':(.5,'learned'),'D0080':(.8,'learned'),'D1050':(.5,'learned'),'D1080':(.8,'learned')}
    if (candidate['alpha'],candidate['support'])!=allowed[candidate['candidate_id']]: raise ValueError('candidate policy mismatch')
    models=doc['models']
    if type(models) is not dict or set(models)!={'emitter','head','config'}: raise ValueError('closed release model paths required')
    for role in ('emitter','config','head'):
        if role=='head' and candidate['alpha']==0 and models[role] is None: continue
        if type(models[role]) is not str or not models[role]: raise ValueError('model paths require exact strings')
        if len([x for x in files if x['relative_path']==models[role] and x['role']==role])!=1: raise ValueError('model path role mismatch')
    provenance=doc['provenance']
    if type(provenance) is not dict or set(provenance)!={'study_digest','model_seal_digest','finalist_digest','protocol_digest'} or any(type(v) is not str or not HEX64.fullmatch(v) for v in provenance.values()):
        raise ValueError('release provenance digests required')
    return doc,hashlib.sha256(raw).hexdigest()


def open_inference_context(release: Path,data_dir: Path,cache_root: Path,input_kind: str) -> InferenceContext:
    if input_kind not in ('challenge_observations','synthetic_observations'): raise PermissionError('observation input kind required')
    doc,release_digest=_release_document(Path(release))
    root=Path(data_dir).absolute(); cache_root=Path(cache_root).absolute(); reject_reparse(root); reject_reparse(cache_root)
    if cache_root.resolve().is_relative_to(root.resolve()) or root.resolve().is_relative_to(cache_root.resolve()):
        raise ValueError('source and cache roots must be disjoint')
    leases=[]
    try:
        sources=[]
        for name in SOURCE_NAMES:
            lease=ReadLease(confined_path(root,name)); leases.append(lease)
            sources.append((name,lease.size,lease.sha256()))
        # .xml is accepted public ATD metadata. .txt is the observation-only ATD
        # numeric frame stream. Header validation belongs to the accepted ATD
        # parser under this same identity; Sportec/targets are never admissible.
        _validate_atd_schema(leases,input_kind)
        source_digest=digest_json([{'relative_path':n,'bytes':b,'sha256':s} for n,b,s in sources])
        access=ReleaseAccess(release_digest,source_digest,input_kind,tuple(sources),doc['runtime_digest'],doc['policy_digest'],cache_root.resolve(),os.getpid(),process_creation_time())
        policy=InferencePolicy('challenge',((110808,113742),))
        context=InferenceContext(access,policy,tuple(leases))
        grant_id=id(access)
        _RELEASE_GRANTS[grant_id]={'access':weakref.ref(access,lambda ref,key=grant_id:_RELEASE_GRANTS.pop(key,None)),
                                   'leases':tuple(leases),'release':doc}
        return context
    except BaseException:
        for lease in reversed(leases): lease.close()
        raise


def _validate_atd_schema(leases,input_kind):
    import xml.etree.ElementTree as ET
    from possession_model.features import _metadata, _numbers
    xml,raw=leases
    xml.seek(0)
    if xml.size>2_097_152: raise ValueError('oversized ATD metadata')
    tree=ET.parse(xml.file)
    forbidden={'frameset','frame','ballpossession','ballstatus','smarttag','smarttagging','event','possession','target','targets','groundtruth'}
    for node in tree.iter():
        if node.tag.rsplit('}',1)[-1].lower() in forbidden or any(k.lower() in forbidden for k in node.attrib):
            raise ValueError('target-bearing ATD metadata refused')
    specifications=[node for node in tree.iter() if node.tag.rsplit('}',1)[-1]=='DataFormatSpecification']
    if len(specifications)!=1: raise ValueError('one ATD format declaration required')
    end=specifications[0].get('endFrame','')
    if not re.fullmatch(r'[1-9][0-9]*',end): raise ValueError('positive ATD frame count required')
    count=int(end)
    if count>1_000_000 or (input_kind=='challenge_observations' and count!=199319): raise ValueError('ATD frame count contract mismatch')
    xml.seek(0); sides,_,_=_metadata(xml.file,count,25.)
    raw.seek(0); first=raw.file.readline(1_048_577)
    if len(first)>1_048_576: raise ValueError('oversized ATD record')
    try: parts=first.decode('utf-8-sig').strip().split(':')
    except UnicodeDecodeError: raise ValueError('ATD text encoding') from None
    if len(parts)!=3 or parts[0]!='1' or len(parts[1].split(';'))!=len(sides): raise ValueError('ATD observation schema required')
    if any(group.count(',')!=2 or any(not x.strip() for x in group.split(',')) for group in parts[1].split(';')) or parts[2].count(',')!=2:
        raise ValueError('ATD x/y/s channels required')
    _numbers(parts[1].replace(';',','),3*len(sides)); _numbers(parts[2],3)
    xml.seek(0); raw.seek(0)
