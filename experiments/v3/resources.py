"""Windows-only bounded study worker supervision. No numerical imports at bootstrap."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import msvcrt
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time

MAX_WIRE = 16384
HANDSHAKE_SECONDS = 20
DISK_MONITOR_SHUTDOWN_SECONDS = 60
_LOCAL_LOCK = threading.Lock()
_ORIGINAL_HASH_LOCK = threading.Lock()
_ORIGINAL_HASH_CACHE = {}
THREAD_VARS = ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','BLIS_NUM_THREADS','VECLIB_MAXIMUM_THREADS')
class ResourceError(RuntimeError): pass

def _hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def _original_record(path, expected=None):
    """Verify an original through one deny-write/delete handle.

    The persisted ctime field records Windows creation time. Native ChangeTime
    invalidates a cached SHA when bytes/metadata change and mtime is restored.
    No digest cache survives process restart or changes the durable baseline.
    """
    handle=k.CreateFileW(str(path),0x80000000,0x1,None,3,0x08000000|0x00200000,None)
    if handle==ctypes.c_void_p(-1).value: raise ResourceError('cannot lock exempt original')
    try: fd=msvcrt.open_osfhandle(handle,os.O_RDONLY|os.O_BINARY)
    except BaseException:
        k.CloseHandle(handle); raise
    with os.fdopen(fd,'rb') as stream:
        native=msvcrt.get_osfhandle(stream.fileno())
        def snapshot():
            st=os.fstat(stream.fileno()); basic=FILE_BASIC_INFO()
            _win(k.GetFileInformationByHandleEx(native,0,ctypes.byref(basic),ctypes.sizeof(basic)),'original change token')
            if basic.FileAttributes & (0x400|0x10) or basic.ChangeTime<=0: raise ResourceError('invalid original file')
            # Derive times from this handle: Python's path stat and fstat can
            # expose different ctime semantics on Windows.
            epoch=116444736000000000
            metadata={'size':st.st_size,'dev':st.st_dev,'ino':st.st_ino,'ctime_ns':(basic.CreationTime-epoch)*100,'mtime_ns':(basic.LastWriteTime-epoch)*100}
            token=tuple(metadata.values())+(basic.CreationTime,basic.LastWriteTime,basic.ChangeTime)
            return metadata,token
        metadata,token=snapshot()
        if expected is not None and any(metadata[name]!=expected.get(name) for name in metadata):
            raise ResourceError('original exemption content metadata changed')
        wanted=None if expected is None else expected.get('sha256')
        if expected is not None and (type(wanted) is not str or len(wanted)!=64 or any(c not in '0123456789abcdef' for c in wanted)):
            raise ResourceError('invalid original exemption SHA256')
        with _ORIGINAL_HASH_LOCK:
            digest=_ORIGINAL_HASH_CACHE.get(token)
            if digest is None:
                h=hashlib.sha256()
                for block in iter(lambda:stream.read(1024*1024),b''): h.update(block)
                digest=h.hexdigest()
            if snapshot()!=(metadata,token): raise ResourceError('original changed during verification')
            if wanted is not None and digest!=wanted: raise ResourceError('original exemption SHA256 changed')
            # Bounded process-local optimization; a miss always verifies bytes.
            if len(_ORIGINAL_HASH_CACHE)>=256: _ORIGINAL_HASH_CACHE.clear()
            _ORIGINAL_HASH_CACHE[token]=digest
        return dict(metadata,sha256=digest)
def policy_from_protocol(protocol):
    p = Path(protocol).resolve(); raw = p.read_bytes(); d = json.loads(raw)
    r, s = d['resource'], d['schedule']
    required = {'heavy_workers':1,'numeric_threads':4,'process_tree_peak_bytes':12884901888,'aggregate_fit_seconds':28800,'added_disk_target_bytes':10737418240,'min_free_disk_bytes':42949672960}
    if any(r.get(k) != v for k,v in required.items()): raise ResourceError('unsupported protocol resource policy')
    return {'protocol_path':str(p),'protocol_sha256':hashlib.sha256(raw).hexdigest(),'resource':required,'schedule':{k:s[k] for k in ('latest_fit_start','fit_end','latest_selection_start','latest_test_start','test_end','freeze')}}

def _validate_policy(p):
    if policy_from_protocol(p['protocol_path']) != p: raise ResourceError('policy changed')

def _safe_path(path, *, allow_missing=False):
    """Reject unresolved reparse components before canonicalizing an entry path."""
    import stat
    raw=Path(path)
    if not raw.is_absolute(): raw=Path.cwd()/raw
    cursor=Path(raw.anchor)
    for part in raw.parts[1:]:
        if part=='..': cursor=cursor.parent; continue
        cursor=cursor/part
        try: st=cursor.lstat()
        except FileNotFoundError as error:
            if allow_missing: continue
            raise ResourceError('resource path missing') from error
        if stat.S_ISLNK(st.st_mode) or getattr(st,'st_file_attributes',0)&0x400:
            raise ResourceError('resource path contains reparse component')
    return raw.resolve()

def _files(root):
    import stat
    root=_safe_path(root); result={}
    def walk_error(error):
        if isinstance(error,FileNotFoundError) and error.filename:
            missing=Path(os.path.abspath(error.filename))
            if missing!=root and missing.is_relative_to(root): return
        raise error
    for base, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        for d in tuple(dirs):
            try: st=(Path(base)/d).lstat()
            except FileNotFoundError:
                dirs.remove(d); continue
            if stat.S_ISLNK(st.st_mode) or getattr(st,'st_file_attributes',0)&0x400: raise ResourceError('disk scope contains directory link')
        for f in files:
            p=Path(base)/f
            try: st=p.lstat()
            except FileNotFoundError:
                # Atomic writers may have removed a reservation or renamed a
                # completed regular file since os.walk enumerated its name.
                continue
            if stat.S_ISLNK(st.st_mode) or getattr(st,'st_file_attributes',0)&0x400: raise ResourceError('disk scope contains file link')
            if not stat.S_ISREG(st.st_mode): raise ResourceError('disk scope contains non-regular file')
            result[str(p.relative_to(root))]=st.st_size
    return result

def _campaign_path(name):
    name=name.replace('\\','/')
    return ('/' not in name or (name.startswith('local/root_') and name.endswith('.py')) or name.startswith(('local/v3-', 'experiments/v3/', 'specs/003-possession-improvements/', 'research/v3/', 'tests/test_v3_', 'reports/v3-')) or name in ('reports/agentic-progress.jsonl','PROJECT_STATE.md','AGENTIC_GOAL.md'))

def new_budget_state(campaign_root, *, exempt_paths=(), snapshot_unrelated=False):
    root=_safe_path(campaign_root,allow_missing=True); root.mkdir(parents=True,exist_ok=True)
    # Explicitly preexisting original paths are exempt; all other present files count.
    exempts={}
    for item in exempt_paths:
        p=_safe_path(item)
        if not p.is_relative_to(root) or not p.is_file(): raise ResourceError('invalid original exemption')
        exempts[str(p.relative_to(root))]=_original_record(p)
    baseline={name:size for name,size in _files(root).items() if not _campaign_path(name)} if snapshot_unrelated else {}
    return {'schema_version':1,'campaign_root':str(root),'exempt_original_sizes':exempts,'baseline_unrelated_sizes':baseline,'scope':'root-loose; local/root_*.py; local/v3-*; experiments/v3; specs/003-possession-improvements; research/v3; tests/test_v3_*; reports/v3-*; reports/agentic-progress.jsonl; all other new/growth','fit_seconds':0.0}

def _baseline_digest(b):
    values={k:b[k] for k in ('schema_version','campaign_root','exempt_original_sizes','baseline_unrelated_sizes','scope')}
    return hashlib.sha256(json.dumps(values,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def initialize_budget(path,campaign_root,*,exempt_paths=(),snapshot_unrelated=True):
    _safe_path(campaign_root,allow_missing=True)
    p=_safe_path(path,allow_missing=True); p.parent.mkdir(parents=True,exist_ok=True)
    b=new_budget_state(campaign_root,exempt_paths=exempt_paths,snapshot_unrelated=snapshot_unrelated)
    b['baseline_sha256']=_baseline_digest(b)
    try: raw=json.dumps(b,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n'
    except (ValueError,TypeError) as e: raise ResourceError('invalid budget serialization') from e
    with p.open('x',encoding='utf-8') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    return b

def _valid_fit(value):
    if type(value) not in (int,float): return False
    try: return math.isfinite(value) and value>=0
    except OverflowError: return False

def _bad_json_constant(value):
    raise ValueError('non-finite JSON constant')

def load_budget(path):
    try:
        b=json.loads(Path(path).read_text(encoding='utf-8'),parse_constant=_bad_json_constant)
        if type(b) is not dict or b.get('baseline_sha256')!=_baseline_digest(b) or b.get('schema_version')!=1 or not _valid_fit(b.get('fit_seconds')): raise ResourceError('budget integrity failure')
        return b
    except (OSError,ValueError,TypeError,KeyError,OverflowError) as e: raise ResourceError('missing or invalid durable budget') from e

def save_budget(path,budget_state):
    p=Path(path); previous=load_budget(p)
    try:
        value=budget_state['fit_seconds']
        if not _valid_fit(value) or value<previous['fit_seconds'] or _baseline_digest(budget_state)!=previous['baseline_sha256'] or budget_state.get('baseline_sha256')!=previous['baseline_sha256']:
            raise ResourceError('budget baseline or accounting changed')
        raw=json.dumps(budget_state,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n'
    except (ValueError,TypeError,KeyError,OverflowError) as e: raise ResourceError('invalid budget serialization') from e
    tmp=p.with_name(p.name+'.pending-'+str(os.getpid())); created=False
    try:
        with tmp.open('x',encoding='utf-8') as f:
            created=True; f.write(raw); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,p); created=False
    finally:
        if created: tmp.unlink(missing_ok=True)

def check_time(policy,stage,budget_state):
    _validate_policy(policy)
    if stage=='acquisition':
        if datetime.now(timezone.utc)>datetime.fromisoformat(policy['schedule']['freeze']).astimezone(timezone.utc): raise ResourceError('freeze passed')
        return policy['schedule']['freeze']
    return _deadline(policy,stage,budget_state).isoformat()

def check_disk(policy,campaign_root,budget_state,forecast_bytes=0):
    _validate_policy(policy); root=_safe_path(campaign_root)
    if str(root)!=budget_state.get('campaign_root') or type(forecast_bytes) is not int or forecast_bytes<0: raise ResourceError('invalid disk budget')
    files=_files(root); exempt=budget_state['exempt_original_sizes']
    # Identity survives a contained same-volume rename. Each original gets one
    # discount; any other hardlink or copy is charged in full.
    identities={}
    for original, record in exempt.items():
        key=(record['dev'],record['ino'])
        if key in identities: raise ResourceError('duplicate exempt original identity')
        identities[key]=(original,record)
    aliases={key:[] for key in identities}
    for name in tuple(files):
        try: st=(root/name).stat()
        except FileNotFoundError:
            # The inventory is a concurrent snapshot. Missing exempt identities
            # are still rejected below; vanished transient files get no charge.
            del files[name]; continue
        key=(st.st_dev,st.st_ino)
        if key in aliases: aliases[key].append((name,st))
    discounts={}; alias_names=set(); mappings=[]
    for key,(original,record) in identities.items():
        matches=aliases[key]
        if original in files and not any(name==original for name,_ in matches):
            raise ResourceError('original exemption identity changed')
        if not matches: raise ResourceError('exempt original identity missing')
        for name,st in matches:
            if (st.st_size,st.st_ctime_ns,st.st_mtime_ns)!=(record['size'],record['ctime_ns'],record['mtime_ns']):
                raise ResourceError('original exemption content metadata changed')
            alias_names.add(name)
        chosen=original if original in files else min(name for name,_ in matches)
        _original_record(root/chosen,record)
        discounts[chosen]=record['size']
        if chosen!=original: mappings.append({'original':original,'current':chosen})
    added=0
    for name,n in files.items():
        # Never apply the unrelated snapshot to additional hardlinks of an exempt
        # identity: the exemption is allowed exactly once.
        baseline=0 if name in alias_names else budget_state.get('baseline_unrelated_sizes',{}).get(name,0)
        added+=max(0,n-discounts.get(name,baseline))
    free=shutil.disk_usage(root).free; r=policy['resource']
    if added+forecast_bytes>r['added_disk_target_bytes'] or free-forecast_bytes<r['min_free_disk_bytes']: raise ResourceError('disk budget exceeded')
    return {'added_bytes':added,'free_bytes':free,'forecast_bytes':forecast_bytes,'relocated_originals':mappings}

def account_fit(budget_state,elapsed_seconds):
    if not _valid_fit(elapsed_seconds): raise ResourceError('invalid fit duration')
    b=dict(budget_state); b['fit_seconds']=float(b['fit_seconds'])+elapsed_seconds
    if b['fit_seconds']>28800: raise ResourceError('fit budget exceeded')
    return b

def _deadline(policy,stage,budget):
    now=datetime.now(timezone.utc); s=policy['schedule']; parse=lambda x:datetime.fromisoformat(x).astimezone(timezone.utc)
    starts={'train':'latest_fit_start','selection':'latest_selection_start','test':'latest_test_start'}
    ends={'train':'fit_end','selection':'freeze','test':'test_end','synthetic':'freeze'}
    if stage not in ends: raise ResourceError('invalid stage')
    if now>parse(s['freeze']) or now>parse(s[ends[stage]]): raise ResourceError('stage end deadline passed')
    if stage in starts and now>parse(s[starts[stage]]): raise ResourceError('stage start deadline passed')
    if stage=='train' and float(budget['fit_seconds'])>=28800: raise ResourceError('fit budget exhausted')
    return parse(s[ends[stage]])

k=ctypes.WinDLL('kernel32',use_last_error=True); ps=ctypes.WinDLL('psapi',use_last_error=True)
HANDLE=wintypes.HANDLE; DWORD=wintypes.DWORD; SIZE=ctypes.c_size_t
class FILETIME(ctypes.Structure): _fields_=[('low',DWORD),('high',DWORD)]
class FILE_BASIC_INFO(ctypes.Structure): _fields_=[('CreationTime',ctypes.c_longlong),('LastAccessTime',ctypes.c_longlong),('LastWriteTime',ctypes.c_longlong),('ChangeTime',ctypes.c_longlong),('FileAttributes',DWORD)]
class BASIC(ctypes.Structure): _fields_=[('PerProcessUserTimeLimit',ctypes.c_longlong),('PerJobUserTimeLimit',ctypes.c_longlong),('LimitFlags',DWORD),('MinimumWorkingSetSize',SIZE),('MaximumWorkingSetSize',SIZE),('ActiveProcessLimit',DWORD),('Affinity',SIZE),('PriorityClass',DWORD),('SchedulingClass',DWORD)]
class IO(ctypes.Structure): _fields_=[(x,ctypes.c_ulonglong) for x in ('ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount')]
class EXTENDED(ctypes.Structure): _fields_=[('BasicLimitInformation',BASIC),('IoInfo',IO),('ProcessMemoryLimit',SIZE),('JobMemoryLimit',SIZE),('PeakProcessMemoryUsed',SIZE),('PeakJobMemoryUsed',SIZE)]
class STARTUP(ctypes.Structure): _fields_=[('cb',DWORD),('lpReserved',wintypes.LPWSTR),('lpDesktop',wintypes.LPWSTR),('lpTitle',wintypes.LPWSTR),('dwX',DWORD),('dwY',DWORD),('dwXSize',DWORD),('dwYSize',DWORD),('dwXCountChars',DWORD),('dwYCountChars',DWORD),('dwFillAttribute',DWORD),('dwFlags',DWORD),('wShowWindow',wintypes.WORD),('cbReserved2',wintypes.WORD),('lpReserved2',ctypes.c_void_p),('hStdInput',HANDLE),('hStdOutput',HANDLE),('hStdError',HANDLE)]
class PROCINFO(ctypes.Structure): _fields_=[('hProcess',HANDLE),('hThread',HANDLE),('dwProcessId',DWORD),('dwThreadId',DWORD)]
class MEM(ctypes.Structure): _fields_=[('cb',DWORD),('PageFaultCount',DWORD)]+[(x,SIZE) for x in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
for name,restype,args in [('CreateJobObjectW',HANDLE,[ctypes.c_void_p,wintypes.LPCWSTR]),('SetInformationJobObject',wintypes.BOOL,[HANDLE,ctypes.c_int,ctypes.c_void_p,DWORD]),('QueryInformationJobObject',wintypes.BOOL,[HANDLE,ctypes.c_int,ctypes.c_void_p,DWORD,ctypes.POINTER(DWORD)]),('AssignProcessToJobObject',wintypes.BOOL,[HANDLE,HANDLE]),('IsProcessInJob',wintypes.BOOL,[HANDLE,HANDLE,ctypes.POINTER(wintypes.BOOL)]),('OpenProcess',HANDLE,[DWORD,wintypes.BOOL,DWORD]),('GetProcessTimes',wintypes.BOOL,[HANDLE,ctypes.POINTER(FILETIME),ctypes.POINTER(FILETIME),ctypes.POINTER(FILETIME),ctypes.POINTER(FILETIME)]),('CloseHandle',wintypes.BOOL,[HANDLE]),('ResumeThread',DWORD,[HANDLE]),('WaitForSingleObject',DWORD,[HANDLE,DWORD]),('TerminateJobObject',wintypes.BOOL,[HANDLE,DWORD]),('TerminateProcess',wintypes.BOOL,[HANDLE,DWORD]),('CreateMutexW',HANDLE,[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR]),('ReleaseMutex',wintypes.BOOL,[HANDLE]),('GetExitCodeProcess',wintypes.BOOL,[HANDLE,ctypes.POINTER(DWORD)]),('CreateProcessW',wintypes.BOOL,[wintypes.LPCWSTR,wintypes.LPWSTR,ctypes.c_void_p,ctypes.c_void_p,wintypes.BOOL,DWORD,ctypes.c_void_p,wintypes.LPCWSTR,ctypes.POINTER(STARTUP),ctypes.POINTER(PROCINFO)])]:
    f=getattr(k,name); f.restype=restype; f.argtypes=args
ps.GetProcessMemoryInfo.argtypes=[HANDLE,ctypes.POINTER(MEM),DWORD]; ps.GetProcessMemoryInfo.restype=wintypes.BOOL
k.CreateFileW.argtypes=[wintypes.LPCWSTR,DWORD,DWORD,ctypes.c_void_p,DWORD,DWORD,HANDLE]; k.CreateFileW.restype=HANDLE
k.GetFileInformationByHandleEx.argtypes=[HANDLE,ctypes.c_int,ctypes.c_void_p,DWORD]; k.GetFileInformationByHandleEx.restype=wintypes.BOOL
k.GetCurrentThread.argtypes=[]; k.GetCurrentThread.restype=HANDLE
k.SetThreadPriority.argtypes=[HANDLE,ctypes.c_int]; k.SetThreadPriority.restype=wintypes.BOOL

def _win(ok,what):
    if not ok: raise ResourceError(what+' (winerror '+str(ctypes.get_last_error())+')')

def _created(h):
    t=[FILETIME() for _ in range(4)]; _win(k.GetProcessTimes(h,*[ctypes.byref(x) for x in t]),'GetProcessTimes')
    return str((t[0].high<<32)|t[0].low)

def _line(stream):
    line=stream.readline(MAX_WIRE+1)
    if not line.endswith(b'\n') or len(line)>MAX_WIRE: raise ResourceError('invalid wire line')
    obj=json.loads(line)
    if type(obj) is not dict: raise ResourceError('invalid wire object')
    return obj

def worker_handshake():
    h=k.OpenProcess(0x1000|0x100000,False,os.getpid()); _win(h,'open self')
    try: hello={'schema_version':1,'type':'ready','process_id':os.getpid(),'process_creation_time':_created(h)}
    finally: k.CloseHandle(h)
    sys.stdout.buffer.write(json.dumps(hello,separators=(',',':')).encode()+b'\n'); sys.stdout.buffer.flush()
    msg=_line(sys.stdin.buffer)
    if set(msg)!={'schema_version','type','capability','result_path'} or msg['schema_version']!=1 or msg['type']!='grant' or type(msg['result_path']) is not str or type(msg['capability']) is not dict: raise ResourceError('invalid grant')
    fields={'study_digest','attempt_id','role','fixture_ids','process_id','process_creation_time','reservation_event_digest'}
    c=msg['capability']
    if set(c)!=fields or type(c['fixture_ids']) is not list or not all(type(x) is str for x in c['fixture_ids']) or type(c['process_id']) is not int or any(type(c[x]) is not str for x in fields-{'fixture_ids','process_id'}): raise ResourceError('invalid capability')
    if c['process_id']!=hello['process_id'] or c['process_creation_time']!=hello['process_creation_time']: raise ResourceError('grant identity mismatch')
    c['fixture_ids']=tuple(c['fixture_ids']); return msg

def _memory(h):
    m=MEM(); m.cb=ctypes.sizeof(m)
    _win(ps.GetProcessMemoryInfo(h,ctypes.byref(m),m.cb),'GetProcessMemoryInfo')
    return int(m.WorkingSetSize),int(m.PeakWorkingSetSize)

def _job_pids(job):
    # JOBOBJECT_BASIC_PROCESS_ID_LIST has DWORD header and pointer-sized entries.
    class IDS(ctypes.Structure): _fields_=[('assigned',DWORD),('count',DWORD),('pids',SIZE*256)]
    v=IDS(); _win(k.QueryInformationJobObject(job,3,ctypes.byref(v),ctypes.sizeof(v),None),'job process list')
    if v.assigned>256 or v.count>256: raise ResourceError('job process list overflow')
    return list(v.pids[:v.count])

class PreparedWorker:
    def __init__(self,command,policy,campaign_root,budget_state,stage,preflight_receipt,*,_preflight=False):
        self.command=list(map(str,command)); self.policy=policy; self.root=_safe_path(campaign_root); self.budget=budget_state; self.stage=stage; self.receipt=preflight_receipt; self.probe=_preflight
        self.job=None; self.proc=None; self.assigned=False; self.worker=None; self.thread=None; self.lock=None; self.lock_owned=False; self.local_lock_owned=False; self.stdin=None; self.stdout=None; self.start=0; self.stop=threading.Event(); self.samples=[]; self.errors=[]; self.max_processes=0; self.peak=0; self.tree_peak=0; self.authorized=False; self.waited=False; self.reason=None
        self._disk_shutdown_deadline=None
    def __enter__(self):
        try:
            _validate_policy(self.policy); self.deadline=_deadline(self.policy,self.stage,self.budget); check_disk(self.policy,self.root,self.budget)
            if not self.probe:
                if type(self.receipt) is not dict or self.receipt.get('protocol_sha256')!=self.policy['protocol_sha256'] or self.receipt.get('resource_source_sha256')!=_hash(__file__) or self.receipt.get('campaign_root')!=str(self.root) or self.receipt.get('passed') is not True: raise ResourceError('missing current preflight')
            if not _LOCAL_LOCK.acquire(blocking=False): raise ResourceError('another heavy worker is active')
            self.local_lock_owned=True
            self.lock=k.CreateMutexW(None,False,'Local\\BarcelonaV3HeavyWorker'); _win(self.lock,'CreateMutex')
            lock_status=k.WaitForSingleObject(self.lock,0)
            if lock_status not in (0,0x80): raise ResourceError('another heavy worker is active')
            self.lock_owned=True
            self.job=k.CreateJobObjectW(None,None); _win(self.job,'CreateJobObject')
            lim=EXTENDED(); lim.BasicLimitInformation.LimitFlags=0x2000|0x200; lim.JobMemoryLimit=self.policy['resource']['process_tree_peak_bytes']
            _win(k.SetInformationJobObject(self.job,9,ctypes.byref(lim),ctypes.sizeof(lim)),'SetInformationJobObject')
            actual=EXTENDED(); _win(k.QueryInformationJobObject(self.job,9,ctypes.byref(actual),ctypes.sizeof(actual),None),'query job limits')
            if actual.JobMemoryLimit!=lim.JobMemoryLimit or (actual.BasicLimitInformation.LimitFlags & 0x2200)!=0x2200: raise ResourceError('job limits not active')
            # Pipe handles are inherited before the initial thread is resumed.
            ir,iw=os.pipe(); or_,ow=os.pipe(); null=os.open(os.devnull,os.O_WRONLY)
            try:
                for fd in (ir,ow,null): os.set_handle_inheritable(msvcrt.get_osfhandle(fd),True)
                si=STARTUP(); si.cb=ctypes.sizeof(si); si.dwFlags=0x100; si.hStdInput=msvcrt.get_osfhandle(ir); si.hStdOutput=msvcrt.get_osfhandle(ow); si.hStdError=msvcrt.get_osfhandle(null)
                pi=PROCINFO(); env=dict(os.environ)
                for key in THREAD_VARS: env[key]='4'
                env['OMP_DYNAMIC']='FALSE'; env['MKL_DYNAMIC']='FALSE'
                envblock='\0'.join(f'{x}={y}' for x,y in sorted(env.items(),key=lambda p:p[0].upper()))+'\0\0'
                eb=ctypes.create_unicode_buffer(envblock); cmd=ctypes.create_unicode_buffer(subprocess.list2cmdline(self.command))
                _win(k.CreateProcessW(None,cmd,None,None,True,0x4|0x400|0x08000000,ctypes.cast(eb,ctypes.c_void_p),None,ctypes.byref(si),ctypes.byref(pi)),'CreateProcessW')
                self.proc=pi.hProcess; self.thread=pi.hThread; self.start=time.monotonic()
                _win(k.AssignProcessToJobObject(self.job,self.proc),'AssignProcessToJobObject'); self.assigned=True
                if k.ResumeThread(self.thread)==0xffffffff: raise ResourceError('ResumeThread failed')
                self.stdin=os.fdopen(iw,'wb',buffering=0); iw=None; self.stdout=os.fdopen(or_,'rb',buffering=0); or_=None
            finally:
                for fd in (ir,iw,or_,ow,null):
                    if fd is not None: os.close(fd)
            q=queue.Queue(maxsize=1)
            def read_hello():
                try: q.put((_line(self.stdout),None))
                except BaseException as e: q.put((None,e))
            threading.Thread(target=read_hello,daemon=True).start()
            try: hello,err=q.get(timeout=HANDSHAKE_SECONDS)
            except queue.Empty: raise ResourceError('worker handshake timed out')
            if err: raise ResourceError('worker handshake failed') from err
            if set(hello)!={'schema_version','type','process_id','process_creation_time'} or hello['schema_version']!=1 or hello['type']!='ready' or type(hello['process_id']) is not int or type(hello['process_creation_time']) is not str: raise ResourceError('invalid worker identity')
            self.pid=hello['process_id']; self.creation=hello['process_creation_time']
            self.worker=k.OpenProcess(0x1000|0x0010|0x0400|0x100000,False,self.pid); _win(self.worker,'open worker')
            member=wintypes.BOOL(); _win(k.IsProcessInJob(self.worker,self.job,ctypes.byref(member)),'IsProcessInJob')
            if not member.value or _created(self.worker)!=self.creation or k.WaitForSingleObject(self.worker,0)!=258: raise ResourceError('worker identity or job mismatch')
            self.output_monitor=threading.Thread(target=self._monitor_output,daemon=True); self.output_monitor.start()
            self.monitor=threading.Thread(target=self._monitor,daemon=True); self.monitor.start()
            self.disk_monitor=threading.Thread(target=self._monitor_disk,daemon=True); self.disk_monitor.start()
            return self
        except BaseException:
            self.__exit__(*sys.exc_info()); raise
    def _monitor_output(self):
        try:
            if self.stdout.read(1):
                self.reason='unexpected worker stdout'; k.TerminateJobObject(self.job,1)
        except (OSError,ValueError): pass
    def _monitor_disk(self):
        while not self.stop.is_set():
            try: check_disk(self.policy,self.root,self.budget)
            except Exception as e:
                self.reason=str(e); k.TerminateJobObject(self.job,1); return
            self.stop.wait(1)
    def _monitor(self):
        # A modest priority increase and 10 ms cadence reduce scheduler jitter;
        # this is not a real-time guarantee. Actual gaps remain admission data.
        try: _win(k.SetThreadPriority(k.GetCurrentThread(),1),'SetThreadPriority sampler')
        except ResourceError as e:
            self.errors.append(str(e)); self.reason=str(e); k.TerminateJobObject(self.job,1); return
        while not self.stop.is_set():
            t=time.monotonic()
            try:
                pids=_job_pids(self.job); self.max_processes=max(self.max_processes,len(pids)); total=0
                for pid in pids:
                    h=k.OpenProcess(0x1000|0x0010|0x0400|0x100000,False,pid)
                    if not h:
                        # A process can exit between enumeration and opening; coverage is incomplete.
                        self.errors.append('process disappeared before sample'); continue
                    try:
                        current,peak=_memory(h); total+=current
                        if pid==self.pid: self.peak=max(self.peak,peak)
                    except ResourceError: self.errors.append('memory read failed')
                    finally: k.CloseHandle(h)
                self.tree_peak=max(self.tree_peak,total); self.samples.append(t)
                if total>self.policy['resource']['process_tree_peak_bytes']: raise ResourceError('sampled working-set ceiling exceeded')
                if datetime.now(timezone.utc)>self.deadline: raise ResourceError('stage deadline exceeded')
                if self.stage=='train' and float(self.budget['fit_seconds'])+t-self.start>28800: raise ResourceError('aggregate fit limit exceeded')
            except Exception as e:
                self.reason=str(e); k.TerminateJobObject(self.job,1); break
            self.stop.wait(max(0,.01-(time.monotonic()-t)))
    def authorize(self,owner_cap,result_path):
        if self.authorized: raise ResourceError('already authorized')
        from .guard import authorize_child
        child=authorize_child(owner_cap,self.pid,self.creation)
        self._grant(asdict(child),result_path)
    def _grant(self,cap,result_path):
        msg={'schema_version':1,'type':'grant','capability':cap,'result_path':str(result_path)}
        raw=json.dumps(msg,separators=(',',':')).encode()+b'\n'
        if len(raw)>MAX_WIRE: raise ResourceError('grant too large')
        self.stdin.write(raw); self.stdin.flush(); self.authorized=True
    def _join_disk_monitor(self):
        disk=getattr(self,'disk_monitor',None)
        if disk is None or not disk.is_alive(): return True
        if self._disk_shutdown_deadline is None:
            self._disk_shutdown_deadline=time.monotonic()+DISK_MONITOR_SHUTDOWN_SECONDS
        disk.join(timeout=max(0,self._disk_shutdown_deadline-time.monotonic()))
        return not disk.is_alive()
    def wait(self):
        if not self.authorized: raise ResourceError('worker not authorized')
        while k.WaitForSingleObject(self.worker,100)==258:
            if self.reason: break
        self.stop.set(); self.monitor.join(timeout=5)
        if self.monitor.is_alive(): raise ResourceError('monitor did not stop')
        if not self._join_disk_monitor(): raise ResourceError('disk monitor did not stop')
        try: self.peak=max(self.peak,_memory(self.worker)[1])
        except ResourceError: pass
        exitcode=DWORD(); _win(k.GetExitCodeProcess(self.worker,ctypes.byref(exitcode)),'worker exit code')
        gaps=[b-a for a,b in zip(self.samples,self.samples[1:])]; self.waited=True
        return {'exit_code':int(exitcode.value),'worker_pid':self.pid,'worker_creation_time':self.creation,'wall_seconds':time.monotonic()-self.start,'worker_peak_working_set_bytes':self.peak,'sampled_job_peak_working_set_bytes':self.tree_peak,'sample_count':len(self.samples),'max_job_processes':self.max_processes,'max_sample_gap_seconds':max(gaps,default=0),'gaps_over_50ms':sum(x>.05 for x in gaps),'sampling_errors':list(self.errors),'termination_reason':self.reason,'job_commit_limit_bytes':self.policy['resource']['process_tree_peak_bytes'],'measurement_note':'Sampled concurrent working-set peak is a lower bound; job ceiling limits committed memory, not resident working set.'}
    def __exit__(self,*exc):
        self.stop.set()
        if self.job: k.TerminateJobObject(self.job,1)
        if self.proc and not self.assigned: k.TerminateProcess(self.proc,1)
        if getattr(self,'monitor',None): self.monitor.join(timeout=5)
        disk_stopped=self._join_disk_monitor()
        if getattr(self,'output_monitor',None): self.output_monitor.join(timeout=2)
        for f in (self.stdin,self.stdout):
            if f:
                try: f.close()
                except OSError: pass
        for h in (self.worker,self.thread,self.proc):
            if h: k.CloseHandle(h)
        if disk_stopped:
            if self.job: k.CloseHandle(self.job)
        elif self.job:
            # The disk thread can still report an error through this Job handle.
            # Retain it until that thread ends; report incomplete cleanup below.
            job=self.job; disk=self.disk_monitor
            def close_job_after_disk():
                disk.join(); k.CloseHandle(job); self.job=None
            self._deferred_job_cleanup=threading.Thread(target=close_job_after_disk,daemon=True)
            self._deferred_job_cleanup.start()
        if self.lock:
            if self.lock_owned: k.ReleaseMutex(self.lock)
            k.CloseHandle(self.lock)
        if self.local_lock_owned: _LOCAL_LOCK.release(); self.local_lock_owned=False
        if not disk_stopped: raise ResourceError('disk monitor did not stop; job handle cleanup deferred until scan ends')
        return False

def prepare_worker(command,policy,campaign_root,budget_state,*,stage,preflight_receipt):
    return PreparedWorker(command,policy,campaign_root,budget_state,stage,preflight_receipt)

def resource_preflight(policy,campaign_root,budget_state):
    _validate_policy(policy); check_disk(policy,campaign_root,budget_state)
    # Same containment and worker handshake path as the study, with only invented values.
    code=("from experiments.v3.resources import worker_handshake; worker_handshake(); "
          "import ctypes,subprocess,sys,time; "
          "a=ctypes.WinDLL('kernel32',use_last_error=True).VirtualAlloc; "
          "a.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_ulong,ctypes.c_ulong]; a.restype=ctypes.c_void_p; "
          "p=a(None,13*1024**3,0x3000,4); "
          "sys.exit(3) if p else None; "
          "c=subprocess.Popen([sys.executable,'-c','import time; x=bytearray(1048576); time.sleep(.25)']); "
          "time.sleep(.35); c.wait()")
    with PreparedWorker([sys.executable,'-c',code],policy,campaign_root,budget_state,'synthetic',None,_preflight=True) as w:
        cap={'study_digest':'synthetic','attempt_id':'synthetic','role':'train','fixture_ids':[],'process_id':w.pid,'process_creation_time':w.creation,'reservation_event_digest':'synthetic'}
        w._grant(cap,str(Path(campaign_root)/'synthetic-unused.json')); evidence=w.wait()
    if evidence['exit_code']!=0 or evidence['worker_peak_working_set_bytes']<=0 or evidence['sample_count']<2 or evidence['max_job_processes']<2 or evidence['sampling_errors'] or evidence['termination_reason'] or evidence['gaps_over_50ms']: raise ResourceError('synthetic resource preflight failed')
    return {'passed':True,'campaign_root':str(Path(campaign_root).resolve()),'protocol_sha256':policy['protocol_sha256'],'resource_source_sha256':_hash(__file__),'evidence':evidence}
