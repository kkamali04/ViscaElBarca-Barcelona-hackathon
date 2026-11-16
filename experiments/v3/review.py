"""Versioned loopback review. Synthetic demo never checks tracking/video paths."""
from __future__ import annotations

import argparse
import hashlib
from http.server import ThreadingHTTPServer
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
import uuid

import numpy as np

from review_app.server import Handler
from . import cache
from .runner import FRAMES,PERIODS,open_generation,publish_generation


def _empty(present=False):
    return {'present':present,'valid':False,'frames':0,'counts':dict.fromkeys('HADX',0),
            'live_possession':{'H':0,'A':0},'segments':[],'sha256':None}


class ReviewStateV3:
    def __init__(self,root,release,data_dir,demo=False,*,work=None):
        if type(demo) is not bool: raise ValueError('demo must be boolean')
        self.root=Path(root).absolute(); cache.reject_reparse(self.root)
        self.demo=demo; self.mode='demo' if demo else 'local'
        self.release=Path(release).absolute() if release is not None else None
        self.data_dir=Path(data_dir).absolute()
        if self.release is None:
            if not demo: raise ValueError('explicit verified release required')
            self.release_id='synthetic-v3-demo'
            self.release_digest=cache.digest_json({'kind':'synthetic-v3-demo','schema_version':1})
            self.doc={'policy_digest':cache.digest_json({'kind':'challenge','forced_dead':[[110808,113742]]})}
        else:
            self.doc,self.release_digest=cache._release_document(self.release)
            self.release_id=self.doc['release_id']
            if self.root.resolve()!=self.release.parent.resolve():
                raise ValueError('review root must be the explicit release root')
        self.work=Path(work).absolute() if work is not None else self.root/'local'/('v3-review-demo' if demo else 'v3-review')/self.release_digest[:16]
        cache.reject_reparse(self.work)
        if not self.work.resolve().is_relative_to(self.root.resolve()): raise ValueError('review work escapes root')
        self.runs=self.work/'runs'; self.runs.mkdir(parents=True,exist_ok=True)
        self.token=secrets.token_urlsafe(32); self.lock=threading.RLock(); self.export_lock=threading.Lock()
        self.run={'status':'idle','message':'Generate this explicit v3 release for local review','started_at':None}
        self.generation=None; self.bundle=None; self.worker=None
        self.code_zip=self.work/'v3-code-only.zip'
        self.bundle_digest=None
        # Only complete immutable generations are candidates. No partial repair.
        for path in sorted(self.runs.iterdir(),key=lambda path:path.name.encode('utf-8'),reverse=True):
            if not path.is_dir() or path.name.startswith('.'): continue
            try:
                with open_generation(path,self.release_digest) as pair:
                    if pair.report.get('synthetic_demo') is not self.demo: continue
                    if pair.report['release_id'] != self.release_id: continue
                self.generation=path; break
            except (ValueError,OSError): continue

    @property
    def csv(self):
        if self.generation is None: return self.runs/'absent'/'candidate.csv'
        with open_generation(self.generation,self.release_digest) as pair:
            return self.generation/pair.commit['csv']['filename']
    @property
    def report(self):
        if self.generation is None: return None
        with open_generation(self.generation,self.release_digest) as pair:
            return self.generation/pair.commit['report']['filename']

    def current(self):
        with self.lock:
            if self.generation is None: return _empty()
            try:
                if self.release is not None:
                    _,digest=cache._release_document(self.release)
                    if digest!=self.release_digest: raise ValueError('release identity changed')
                with open_generation(self.generation,self.release_digest) as pair:
                    if pair.report.get('synthetic_demo') is not self.demo: raise ValueError('demo identity mismatch')
                    if pair.report['release_id'] != self.release_id: raise ValueError('release identity mismatch')
                    return pair.inspect()
            except (OSError,ValueError):
                return {**_empty(True),'error':'Generation integrity failed; unavailable for review or export'}

    def state(self):
        with self.lock:
            output=dict(self.current()); output.pop('segments',None)
            output['source']='invented demo' if self.demo else 'explicit v3 release '+self.release_id
            runtime=None
            if output['valid']:
                with open_generation(self.generation,self.release_digest) as pair:
                    runtime={k:pair.report.get(k) for k in ('total_seconds','peak_process_working_set_bytes','cache_hit')}
            run=dict(self.run); start=run.pop('started_at',None)
            run['elapsed_seconds']=round(time.monotonic()-start,2) if start is not None else run.get('elapsed_seconds',0)
            if self.demo: tracking_ready=True; video_ready=False
            else:
                tracking_ready=all((self.data_dir/name).is_file() for name in cache.SOURCE_NAMES)
                video_ready=(self.data_dir/'tactical/BAR-ATH_tactical.mp4').is_file()
            return {'app':'touchline-v3-review','version':'3','mode':self.mode,'request_token':self.token,
                    'release_id':self.release_id,'release_digest':self.release_digest,
                    'match':{'title':'Synthetic demonstration' if self.demo else 'Barcelona vs Athletic Club',
                             'frames':FRAMES,'fps':25,'home':'Home' if self.demo else 'Barcelona','away':'Away' if self.demo else 'Athletic Club'},
                    'inputs':{'tracking_ready':tracking_ready,'video_ready':video_ready},'output':output,'runtime':runtime,'run':run,
                    'model':{'name':self.release_id,'description':'Synthetic workflow demonstration' if self.demo else 'Frozen v3 core; explicit selected release'},
                    'external_validation':{'notice':'Synthetic workflow only; no accuracy or release acceptance is established.' if self.demo else
                                          'See the exact versioned technical report. N=2 engineering evidence does not establish hidden-match performance.'},
                    'code_export_ready':self.release is not None and self.code_zip.is_file()}

    def timeline(self):
        result=self.current()
        if not result['valid']: raise ValueError('A verified generation is required')
        return {'fps':25,'frames':FRAMES,'segments':result['segments'],'release_id':self.release_id,'release_digest':self.release_digest}

    def start_run(self):
        with self.lock:
            if self.run['status']=='running': return False
            self.run={'status':'running','message':'Generating and validating the complete v3 CSV','started_at':time.monotonic()}
            self.worker=threading.Thread(target=self._run,name='v3-release-generation',daemon=True)
            self.worker.start(); return True

    def _run(self):
        started=time.monotonic(); generation=self.runs/('run-'+str(time.time_ns())+'-'+uuid.uuid4().hex[:8])
        try:
            if self.demo:
                codes=np.full(FRAMES,3,dtype=np.int8)
                for _,a,b in PERIODS:
                    for frame in range(a,b): codes[frame]=2 if frame//625%7==0 else (0 if frame//625%5<3 else 1)
                codes[110808:113742]=2
                provenance={'release_id':self.release_id,'release_digest':self.release_digest,
                    'source_manifest_digest':cache.digest_json({'invented':'v3-demo-v1'}),'policy_digest':self.doc['policy_digest'],
                    'synthetic_demo':True,'cache_hit':False,'total_seconds':None,'peak_process_working_set_bytes':None}
                publish_generation(generation/'candidate.csv',generation/'run.json',codes,provenance,self.root)
            else:
                result=subprocess.run([sys.executable,'-m','experiments.v3.cli','run','--release',str(self.release),
                    '--data-dir',str(self.data_dir),'--out',str(generation/'candidate.csv'),'--report',str(generation/'run.json')],
                    cwd=self.root,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=180)
                if result.returncode: raise ValueError('Release inference failed')
            with open_generation(generation,self.release_digest) as pair:
                if pair.report.get('synthetic_demo') is not self.demo: raise ValueError('generation mode mismatch')
            with self.lock:
                self.generation=generation; self.bundle=None; self.bundle_digest=None
                self.run={'status':'complete','message':'Complete immutable v3 generation validated','started_at':None,
                          'elapsed_seconds':round(time.monotonic()-started,3)}
        except Exception:
            with self.lock:
                self.run={'status':'failed','message':'Generation failed; previous complete generation preserved',
                          'error':'Review the explicit release and input configuration','started_at':None}

    def export(self,team,repository):
        from .exporting import export_release,build_review_pack,verify_code_zip
        if not self.export_lock.acquire(blocking=False): raise ValueError('An export is already running')
        try:
            with self.lock:
                if self.release is None: raise ValueError('An explicit synthetic package is required for demo export')
                if not self.current()['valid']: raise ValueError('A verified generation is required')
                if not self.code_zip.exists(): export_release(self.release,self.code_zip)
                with cache.ReadLease(self.code_zip) as held: verify_code_zip(held,self.release)
                destination=self.work/('private-review-'+uuid.uuid4().hex+'.zip')
                result=build_review_pack(self.release,self.generation,self.code_zip,team,repository,destination,demo=self.demo)
                self.bundle=destination; self.bundle_digest=result['sha256']
                return {**{k:v for k,v in result.items() if k!='path'},'download_url':'/download/review-pack'}
        finally: self.export_lock.release()


class HandlerV3(Handler):
    server_version='TouchlineV3Local/1'

    def file(self,path,*,name=None,video=False):
        """Inherited static routes use held verified identities too."""
        app=self.server.app; path=Path(path).absolute()
        allowed={app.root/'review_app/static'/filename for filename in ('index.html','app.js','app.css')}
        if path not in allowed: raise ValueError('unregistered static route')
        import mimetypes
        with cache.ReadLease(path) as held:
            if app.release is not None:
                relative=path.relative_to(app.root).as_posix()
                records=[record for record in app.doc['files'] if record['relative_path']==relative]
                if len(records)!=1: raise ValueError('static source not bound')
                held.verify(records[0])
            return self.held_file(held,name=name,mime=mimetypes.guess_type(path.name)[0] or 'application/octet-stream')

    def held_file(self,held,*,name=None,video=False,mime='application/octet-stream'):
        size=held.size; start,end,status=0,size-1,200
        if video and self.headers.get('Range'):
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',self.headers['Range'])
            if not match or not any(match.groups()): return self.range_error(size)
            first,last=match.groups()
            if first:
                start=int(first); end=min(int(last),size-1) if last else size-1
            else:
                count=int(last)
                if count<=0: return self.range_error(size)
                start=max(0,size-count)
            if start>end or start>=size: return self.range_error(size)
            status=206
        extra={'Accept-Ranges':'bytes'} if video else {}
        if status==206: extra['Content-Range']=f'bytes {start}-{end}/{size}'
        self.reply_headers(status,'video/mp4' if video else mime,max(0,end-start+1),attachment=name,extra=extra)
        if self.command=='HEAD': return
        held.seek(start); remaining=end-start+1
        try:
            while remaining>0:
                block=held.read(min(65536,remaining))
                if not block: raise ValueError('held file truncated')
                self.wfile.write(block); remaining-=len(block)
        except (BrokenPipeError,ConnectionResetError,TimeoutError): pass

    def do_GET(self):
        if not self.origin_ok(): return self.json({'error':'Use the local v3 review address'},403)
        app=self.server.app; route=urlsplit(self.path).path
        try:
            if route=='/api/health':
                return self.json({'app':'touchline-v3-review','mode':app.mode,'status':'ready','release_id':app.release_id,'release_digest':app.release_digest})
            if route=='/download/candidate':
                with app.lock:
                    if app.generation is None: return self.json({'error':'No committed generation'},404)
                    if not app.current()['valid']: raise ValueError('generation/release integrity failed')
                    with open_generation(app.generation,app.release_digest) as pair:
                        name=('DEMO-' if app.demo else '')+pair.commit['csv']['filename']
                        return self.held_file(pair.leases['csv'],name=name,mime='text/csv')
            if route=='/download/code':
                if app.release is None or not app.code_zip.exists(): return self.json({'error':'No versioned code export'},404)
                from .exporting import verify_code_zip
                with cache.ReadLease(app.code_zip) as held:
                    verify_code_zip(held,app.release)
                    return self.held_file(held,name='v3-code-only.zip',mime='application/zip')
            if route=='/download/technical':
                with cache.ReadLease(app.root/'experiments/v3/TECHNICAL.md') as held:
                    if app.release is not None:
                        records=[r for r in app.doc['files'] if r['relative_path']=='experiments/v3/TECHNICAL.md']
                        if len(records)!=1: raise ValueError('technical document not bound')
                        held.verify(records[0])
                    return self.held_file(held,name='v3-technical.md',mime='text/markdown; charset=utf-8')
            if route=='/download/review-pack':
                with app.lock:
                    if app.bundle is None: return self.json({'error':'No private v3 bundle'},404)
                    if not app.current()['valid']: raise ValueError('generation/release integrity failed')
                    with cache.ReadLease(app.bundle) as held:
                        if held.sha256()!=app.bundle_digest: raise ValueError('bundle changed')
                        return self.held_file(held,name='DEMO-private-v3.zip' if app.demo else 'private-v3.zip',mime='application/zip')
            if route=='/media/tactical.mp4':
                if app.demo: return self.json({'error':'Synthetic demo has no match video'},404)
                with cache.ReadLease(cache.confined_path(app.data_dir,'tactical/BAR-ATH_tactical.mp4')) as held:
                    return self.held_file(held,video=True)
            return super().do_GET()
        except (ValueError,OSError,KeyError):
            return self.json({'error':'Versioned artifact unavailable or integrity check failed'},400)


class ServerV3(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True
    def __init__(self,app,port=8766):
        if type(app) is not ReviewStateV3: raise ValueError('explicit v3 state required')
        self.app=app
        super().__init__(('127.0.0.1',port),HandlerV3)


def main(release=None,data_dir=None,demo=False,port=8766):
    if release is None and not demo: raise ValueError('explicit release required')
    root=Path(release).absolute().parent if release is not None else Path(__file__).resolve().parents[2]
    app=ReviewStateV3(root,release,data_dir or root/'unused-demo-input',demo)
    server=ServerV3(app,port)
    try: server.serve_forever()
    finally: server.server_close()
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release',type=Path); parser.add_argument('--data-dir',type=Path)
    parser.add_argument('--demo',action='store_true'); parser.add_argument('--port',type=int,default=8766)
    args=parser.parse_args(); raise SystemExit(main(**vars(args)))
