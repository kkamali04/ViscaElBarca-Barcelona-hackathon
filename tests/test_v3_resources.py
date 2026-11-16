import json
from pathlib import Path
import sys
import time
import unittest
from experiments.v3 import resources as r

ROOT=Path(__file__).resolve().parents[1]
SCRATCH=ROOT/'local/v3-t05-resources-r6-shutdown'
class ResourcesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SCRATCH.mkdir(parents=True,exist_ok=True)
        cls.policy=r.policy_from_protocol(ROOT/'specs/003-possession-improvements/protocol.json')
        cls.budget=r.new_budget_state(SCRATCH)
        cls.receipt=r.resource_preflight(cls.policy,SCRATCH,cls.budget)
    def command(self, body):
        return [sys.executable,'-c',"from experiments.v3.resources import worker_handshake; x=worker_handshake(); "+body]
    def grant(self,w):
        c={'study_digest':'synthetic','attempt_id':'synthetic','role':'train','fixture_ids':[],'process_id':w.pid,'process_creation_time':w.creation,'reservation_event_digest':'synthetic'}
        w._grant(c,SCRATCH/'unused-result.json')
    def test_real_job_worker_and_child(self):
        code="import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; x=bytearray(32*1024*1024); time.sleep(0.6)']); x=bytearray(16*1024*1024); time.sleep(0.8); p.wait()"
        with r.prepare_worker(self.command(code),self.policy,SCRATCH,self.budget,stage='synthetic',preflight_receipt=self.receipt) as w:
            self.grant(w); result=w.wait()
        self.assertEqual(result['exit_code'],0); self.assertGreaterEqual(result['worker_peak_working_set_bytes'],16*1024*1024)
        self.assertGreater(result['sampled_job_peak_working_set_bytes'],result['worker_peak_working_set_bytes'])
        self.assertGreater(result['sample_count'],3); self.assertFalse(result['termination_reason'])
        self.assertFalse(result['sampling_errors']); self.assertEqual(result['gaps_over_50ms'],0)

    def test_wait_allows_completed_disk_scan_over_five_seconds(self):
        import threading
        from unittest.mock import patch
        real_check=r.check_disk; entered=threading.Event(); finished=threading.Event()
        def delayed(*args,**kwargs):
            if threading.current_thread() is not threading.main_thread():
                entered.set(); time.sleep(5.35)
                try: return real_check(*args,**kwargs)
                finally: finished.set()
            return real_check(*args,**kwargs)
        with patch.object(r,'check_disk',delayed):
            with r.prepare_worker(self.command('import time; time.sleep(.2)'),self.policy,SCRATCH,self.budget,stage='synthetic',preflight_receipt=self.receipt) as worker:
                self.assertTrue(entered.wait(2)); self.grant(worker); evidence=worker.wait()
        self.assertTrue(finished.is_set()); self.assertFalse(worker.disk_monitor.is_alive())
        self.assertGreater(evidence['wall_seconds'],5)
        self.assertEqual(evidence['exit_code'],0); self.assertIsNone(evidence['termination_reason'])
        self.assertEqual(evidence['sampling_errors'],[]); self.assertEqual(evidence['gaps_over_50ms'],0)
        type(self).last_delayed_wait_evidence=evidence

    def test_cleanup_allows_completed_disk_scan_over_five_seconds(self):
        import threading
        from unittest.mock import patch
        real_check=r.check_disk; entered=threading.Event(); finished=threading.Event()
        def delayed(*args,**kwargs):
            if threading.current_thread() is not threading.main_thread():
                entered.set(); time.sleep(5.35)
                try: return real_check(*args,**kwargs)
                finally: finished.set()
            return real_check(*args,**kwargs)
        began=time.monotonic()
        with patch.object(r,'check_disk',delayed):
            with r.prepare_worker(self.command('import time; time.sleep(60)'),self.policy,SCRATCH,self.budget,stage='synthetic',preflight_receipt=self.receipt) as worker:
                self.assertTrue(entered.wait(2)); self.grant(worker); pid=worker.pid
        elapsed=time.monotonic()-began
        self.assertGreater(elapsed,5); self.assertTrue(finished.is_set()); self.assertFalse(worker.disk_monitor.is_alive())
        handle=r.k.OpenProcess(0x100000,False,pid)
        if handle:
            try: self.assertEqual(r.k.WaitForSingleObject(handle,2000),0)
            finally: r.k.CloseHandle(handle)
        type(self).last_delayed_cleanup_evidence={'wall_seconds':elapsed,'disk_finished':True,'worker_terminated':True}

    def test_disk_shutdown_timeout_refuses_and_defers_handle_until_late_error(self):
        import threading
        from unittest.mock import patch
        real_check=r.check_disk; entered=threading.Event(); release=threading.Event(); finished=threading.Event()
        def blocked(*args,**kwargs):
            if threading.current_thread() is not threading.main_thread():
                entered.set()
                try:
                    if not release.wait(5): raise r.ResourceError('invented release timeout')
                    raise r.ResourceError('invented late disk error')
                finally: finished.set()
            return real_check(*args,**kwargs)
        began=time.monotonic(); worker=None
        try:
            with patch.object(r,'check_disk',blocked), patch.object(r,'DISK_MONITOR_SHUTDOWN_SECONDS',.03):
                with self.assertRaisesRegex(r.ResourceError,'cleanup deferred'):
                    with r.prepare_worker(self.command('import time; time.sleep(.2)'),self.policy,SCRATCH,self.budget,stage='synthetic',preflight_receipt=self.receipt) as worker:
                        self.assertTrue(entered.wait(2)); self.grant(worker)
                        with self.assertRaisesRegex(r.ResourceError,'disk monitor did not stop'): worker.wait()
                self.assertTrue(worker.disk_monitor.is_alive()); self.assertTrue(worker._deferred_job_cleanup.is_alive())
                info=r.EXTENDED()
                self.assertTrue(r.k.QueryInformationJobObject(worker.job,9,r.ctypes.byref(info),r.ctypes.sizeof(info),None))
                self.assertLess(time.monotonic()-began,3)
        finally:
            release.set()
            if worker is not None and getattr(worker,'_deferred_job_cleanup',None): worker._deferred_job_cleanup.join(timeout=2)
        self.assertTrue(finished.is_set()); self.assertFalse(worker.disk_monitor.is_alive())
        self.assertFalse(worker._deferred_job_cleanup.is_alive()); self.assertIsNone(worker.job)
        self.assertEqual(worker.reason,'invented late disk error'); self.assertFalse(worker.waited)
        type(self).last_shutdown_refusal_evidence={'wall_seconds':time.monotonic()-began,'temporary_bound_seconds':.03,
                                                 'refused':True,'late_error_preserved':worker.reason,'deferred_cleanup_finished':True}
    def test_bad_handshake_fails_closed(self):
        with self.assertRaises(r.ResourceError):
            with r.prepare_worker([sys.executable,'-c','print("{}")'],self.policy,SCRATCH,self.budget,stage='synthetic',preflight_receipt=self.receipt): pass
    def test_single_worker_and_kill(self):
        with r.prepare_worker(self.command('import time; time.sleep(60)'),self.policy,SCRATCH,self.budget,stage='synthetic',preflight_receipt=self.receipt) as first:
            self.grant(first)
            with self.assertRaises(r.ResourceError):
                with r.prepare_worker(self.command('pass'),self.policy,SCRATCH,self.budget,stage='synthetic',preflight_receipt=self.receipt): pass
            pid=first.pid
        h=r.k.OpenProcess(0x100000,False,pid)
        if h:
            try: self.assertEqual(r.k.WaitForSingleObject(h,2000),0)
            finally: r.k.CloseHandle(h)
    def test_limits_and_forecast(self):
        with self.assertRaises(r.ResourceError): r.check_disk(self.policy,SCRATCH,self.budget,forecast_bytes=10737418241)
        with self.assertRaises(r.ResourceError): r.account_fit(self.budget,28801)
        self.assertEqual(r.account_fit(self.budget,2)['fit_seconds'],2)
        with self.assertRaises(r.ResourceError):
            with r.prepare_worker(self.command('pass'),self.policy,SCRATCH,self.budget,stage='synthetic',preflight_receipt={}): pass

    def test_snapshot_accounts_v3_and_new_or_grown_unrelated(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=SCRATCH) as t:
            root=Path(t); (root/'unrelated').mkdir(); (root/'local').mkdir(); (root/'local/v3-example').mkdir()
            (root/'unrelated/old').write_bytes(b'a'*100)
            (root/'local/v3-example/initial').write_bytes(b'b'*7)
            b=r.new_budget_state(root,snapshot_unrelated=True)
            self.assertEqual(r.check_disk(self.policy,root,b)['added_bytes'],7)
            (root/'unrelated/old').write_bytes(b'a'*105)
            (root/'unrelated/new').write_bytes(b'x'*11)
            self.assertEqual(r.check_disk(self.policy,root,b)['added_bytes'],23)

    def test_inventory_ignores_file_vanished_after_enumeration(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(dir=SCRATCH) as t:
            root=Path(t); transient=root/'.observations.writer-reservation'
            transient.write_bytes(b'invented reservation'); (root/'stable').write_bytes(b'1234567')
            real_lstat=Path.lstat; removed=[]
            def raced(path,*args,**kwargs):
                if path==transient and not removed:
                    transient.unlink(); removed.append(True)
                return real_lstat(path,*args,**kwargs)
            with patch.object(Path,'lstat',raced): result=r._files(root)
            self.assertEqual(removed,[True]); self.assertEqual(result,{'stable':7})

    def test_inventory_ignores_directory_vanished_after_enumeration(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(dir=SCRATCH) as t:
            root=Path(t); folder=root/'volatile'; folder.mkdir(); (root/'stable').write_bytes(b'1234567')
            real_lstat=Path.lstat; removed=[]
            def raced(path,*args,**kwargs):
                if path==folder and not removed:
                    folder.rmdir(); removed.append(True)
                return real_lstat(path,*args,**kwargs)
            with patch.object(Path,'lstat',raced): result=r._files(root)
            self.assertEqual(removed,[True]); self.assertEqual(result,{'stable':7})

    def test_inventory_ignores_directory_vanished_at_walk_entry(self):
        import os, tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(dir=SCRATCH) as t:
            root=Path(t); folder=root/'volatile'; folder.mkdir(); (root/'stable').write_bytes(b'1234567')
            real_scandir=os.scandir; removed=[]
            def raced(path):
                if Path(path)==folder and not removed:
                    folder.rmdir(); removed.append(True)
                    raise FileNotFoundError(2,'invented vanished descendant',str(folder))
                return real_scandir(path)
            with patch.object(r.os,'scandir',raced): result=r._files(root)
            self.assertEqual(removed,[True]); self.assertEqual(result,{'stable':7})

    def test_missing_root_walk_error_and_directory_permissions_refuse(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(dir=SCRATCH) as t:
            root=Path(t)
            for error in (FileNotFoundError(2,'missing root',str(root)),PermissionError(13,'denied',str(root/'descendant'))):
                def failed_walk(path,*,followlinks,onerror): onerror(error); return iter(())
                with self.subTest(error=type(error).__name__), patch.object(r.os,'walk',failed_walk), self.assertRaises(type(error)):
                    r._files(root)

    def test_vanished_directory_with_exempt_original_still_refuses(self):
        import os, tempfile
        from unittest.mock import patch
        for point in ('enumeration','walk-entry'):
            with self.subTest(point=point), tempfile.TemporaryDirectory(dir=SCRATCH) as t:
                root=Path(t); folder=root/'volatile'; folder.mkdir()
                original=folder/'original'; original.write_bytes(b'invented original')
                budget=r.new_budget_state(root,exempt_paths=[original]); removed=[]
                def remove(): original.unlink(); folder.rmdir(); removed.append(True)
                if point=='enumeration':
                    real_lstat=Path.lstat
                    def raced(path,*args,**kwargs):
                        if path==folder and not removed: remove()
                        return real_lstat(path,*args,**kwargs)
                    target=patch.object(Path,'lstat',raced)
                else:
                    real_scandir=os.scandir
                    def raced(path):
                        if Path(path)==folder and not removed:
                            remove(); raise FileNotFoundError(2,'invented vanished descendant',str(folder))
                        return real_scandir(path)
                    target=patch.object(r.os,'scandir',raced)
                with target, self.assertRaisesRegex(r.ResourceError,'identity missing'):
                    r.check_disk(self.policy,root,budget)
                self.assertEqual(removed,[True])

    def test_unresolved_reparse_roots_ancestors_and_exemptions_refuse(self):
        import subprocess, tempfile
        with tempfile.TemporaryDirectory(dir=SCRATCH) as t:
            parent=Path(t); root=parent/'real'; root.mkdir(); (root/'child').mkdir()
            original=root/'original'; original.write_bytes(b'invented original')
            budget=r.new_budget_state(root); link=parent/'junction'
            result=subprocess.run(['cmd.exe','/c','mklink','/J',str(link),str(root)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            for entry in (link,link/'child',link/'..'/'real'):
                with self.subTest(entry=str(entry)):
                    with self.assertRaisesRegex(r.ResourceError,'reparse'): r.new_budget_state(entry)
                    with self.assertRaisesRegex(r.ResourceError,'reparse'): r._files(entry)
                    with self.assertRaisesRegex(r.ResourceError,'reparse'): r.check_disk(self.policy,entry,budget)
                    with self.assertRaisesRegex(r.ResourceError,'reparse'):
                        r.prepare_worker(self.command('pass'),self.policy,entry,budget,stage='synthetic',preflight_receipt={})
            with self.assertRaisesRegex(r.ResourceError,'reparse'):
                r.new_budget_state(parent,exempt_paths=[link/'original'])
            with self.assertRaisesRegex(r.ResourceError,'reparse'):
                r.initialize_budget(link/'budget.json',root)
            self.assertFalse((root/'budget.json').exists())

    def test_actual_worker_full_cache_directory_churn_under_disk_monitor(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=SCRATCH) as t:
            folder=Path(t); completed=folder/'completed.json'
            script=("from pathlib import Path\nimport hashlib,json,os,time\n"
                    f"root=Path({str(folder)!r})\npublications=0\nretries=0\nretry_seconds=0.0\nretry_winerrors=[]\n"
                    "def staging_identity(path):\n"
                    " st=path.lstat()\n"
                    " if st.st_file_attributes&0x400: raise RuntimeError('reparse staging')\n"
                    " return (st.st_dev,st.st_ino,tuple(sorted((p.name,p.stat().st_size,hashlib.sha256(p.read_bytes()).hexdigest()) for p in path.iterdir())))\n"
                    "def publish(source,destination):\n"
                    " global retries,retry_seconds\n"
                    " identity=staging_identity(source); deadline=time.monotonic()+1.0\n"
                    " while True:\n"
                    "  try: source.rename(destination); return\n"
                    "  except OSError as error:\n"
                    "   began=time.monotonic()\n"
                    "   if getattr(error,'winerror',None) not in (5,32,33): raise\n"
                    "   if os.path.lexists(destination) or not source.is_dir() or staging_identity(source)!=identity: raise\n"
                    "   remaining=min(deadline-time.monotonic(),1.0-retry_seconds)\n"
                    "   if remaining<=0: raise\n"
                    "   time.sleep(min(.01,remaining)); retries+=1; retry_winerrors.append(error.winerror)\n"
                    "   retry_seconds+=time.monotonic()-began\n"
                    "for j in range(160):\n"
                    " partial=root/('.cache-'+str(j)+'.partial'); partial.mkdir()\n"
                    " reservation=root/('.cache-'+str(j)+'.reservation'); reservation.write_bytes(b'pending')\n"
                    " for i in range(4):\n"
                    "  with (partial/(str(i)+'.bin')).open('xb') as f:\n"
                    "   f.write(bytes([j%251])*4096); f.flush(); os.fsync(f.fileno())\n"
                    " (partial/'cache.json').write_text(json.dumps({'members':4,'bytes':16384}))\n"
                    " publish(partial,root/('cache-'+str(j))); reservation.unlink()\n"
                    " transient=root/('transient-'+str(j)); transient.mkdir(); (transient/'x').write_bytes(b'x'*127)\n"
                    " moved=root/('moved-'+str(j)); publish(transient,moved); (moved/'x').unlink(); moved.rmdir()\n"
                    " publications+=1; time.sleep(.015)\n"
                    f"Path({str(completed)!r}).write_text(json.dumps({{'publications':publications,'publication_retries':retries,'retry_seconds':retry_seconds,'retry_winerrors':retry_winerrors}}))\n")
            error_path=folder/'worker-error.txt'
            wrapped=("try:\n exec("+repr(script)+")\nexcept BaseException:\n import traceback\n"
                     f" from pathlib import Path\n Path({str(error_path)!r}).write_text(traceback.format_exc())\n raise\n")
            with r.prepare_worker(self.command('exec('+repr(wrapped)+')'),self.policy,SCRATCH,self.budget,stage='synthetic',preflight_receipt=self.receipt) as worker:
                self.grant(worker); evidence=worker.wait()
            type(self).last_directory_churn_evidence=dict(evidence)
            details=dict(evidence,worker_error=error_path.read_text() if error_path.exists() else None)
            self.assertEqual(evidence['exit_code'],0,details); self.assertIsNone(evidence['termination_reason'],details)
            publication_result=json.loads(completed.read_text()); publications=publication_result['publications']
            self.assertEqual(publications,160); self.assertEqual(evidence['exit_code'],0)
            self.assertIsNone(evidence['termination_reason']); self.assertEqual(evidence['sampling_errors'],[])
            self.assertEqual(evidence['gaps_over_50ms'],0); self.assertGreater(evidence['sample_count'],100)
            type(self).last_directory_churn_evidence=dict(evidence,**publication_result)

    def test_disk_ignores_file_vanished_before_identity_rescan(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(dir=SCRATCH) as t:
            root=Path(t); transient=root/'.observations.writer-reservation'
            transient.write_bytes(b'invented reservation'); (root/'stable').write_bytes(b'1234567')
            budget=r.new_budget_state(root); real_files=r._files
            def raced(path):
                files=real_files(path); transient.unlink(); return files
            with patch.object(r,'_files',raced): result=r.check_disk(self.policy,root,budget)
            self.assertEqual(result['added_bytes'],7)

    def test_vanished_exempt_original_still_refuses_at_both_race_points(self):
        import tempfile
        from unittest.mock import patch
        for point in ('enumeration','rescan'):
            with self.subTest(point=point), tempfile.TemporaryDirectory(dir=SCRATCH) as t:
                root=Path(t); original=root/'original'; original.write_bytes(b'invented original')
                budget=r.new_budget_state(root,exempt_paths=[original])
                if point=='enumeration':
                    real_lstat=Path.lstat; removed=[]
                    def raced(path,*args,**kwargs):
                        if path==original and not removed:
                            original.unlink(); removed.append(True)
                        return real_lstat(path,*args,**kwargs)
                    target=patch.object(Path,'lstat',raced)
                else:
                    real_files=r._files
                    def raced(path):
                        files=real_files(path); original.unlink(); return files
                    target=patch.object(r,'_files',raced)
                with target, self.assertRaisesRegex(r.ResourceError,'identity missing'):
                    r.check_disk(self.policy,root,budget)

    def test_inventory_permission_and_reparse_errors_still_refuse(self):
        import stat, tempfile
        from types import SimpleNamespace
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(dir=SCRATCH) as t:
            root=Path(t); item=root/'item'; item.write_bytes(b'invented')
            real_lstat=Path.lstat
            def denied(path,*args,**kwargs):
                if path==item: raise PermissionError('invented denied metadata')
                return real_lstat(path,*args,**kwargs)
            with patch.object(Path,'lstat',denied), self.assertRaises(PermissionError): r._files(root)
            def reparse(path,*args,**kwargs):
                if path==item: return SimpleNamespace(st_mode=stat.S_IFREG|0o600,st_file_attributes=0x400,st_size=8)
                return real_lstat(path,*args,**kwargs)
            with patch.object(Path,'lstat',reparse), self.assertRaisesRegex(r.ResourceError,'file link'): r._files(root)
            def denied_walk(path,*,followlinks,onerror):
                onerror(PermissionError('invented denied directory')); return iter(())
            with patch.object(r.os,'walk',denied_walk), self.assertRaises(PermissionError): r._files(root)

    def test_actual_worker_atomic_file_churn_under_disk_monitor(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=SCRATCH) as t:
            folder=Path(t); completed=folder/'completed.json'
            script=("from pathlib import Path\nimport json,time\n"
                    f"root=Path({str(folder)!r})\n"
                    "reservation=root/'.observations.writer-reservation'\n"
                    "pending=root/'.observations.pending'\nfinal=root/'observations.bin'\n"
                    "until=time.monotonic()+3.3\ncycles=0\n"
                    "while time.monotonic()<until:\n"
                    " reservation.write_bytes(b'invented reservation')\n"
                    " pending.write_bytes(b'0'*64)\n pending.replace(final)\n"
                    " reservation.unlink()\n final.unlink()\n cycles+=1\n time.sleep(.0005)\n"
                    f"Path({str(completed)!r}).write_text(json.dumps({{'cycles':cycles}}))\n")
            with r.prepare_worker(self.command('exec('+repr(script)+')'),self.policy,SCRATCH,self.budget,stage='synthetic',preflight_receipt=self.receipt) as worker:
                self.grant(worker); evidence=worker.wait()
            cycles=json.loads(completed.read_text())['cycles']
            self.assertGreater(cycles,100)
            self.assertEqual(evidence['exit_code'],0); self.assertIsNone(evidence['termination_reason'])
            self.assertEqual(evidence['sampling_errors'],[]); self.assertEqual(evidence['gaps_over_50ms'],0)
            self.assertGreater(evidence['sample_count'],100)
            type(self).last_churn_evidence=dict(evidence,cycles=cycles)
    def test_stdout_violation_is_not_emitted(self):
        with r.prepare_worker(self.command("print('unexpected',flush=True); import time; time.sleep(2)"),self.policy,SCRATCH,self.budget,stage='synthetic',preflight_receipt=self.receipt) as w:
            self.grant(w); result=w.wait()
        self.assertEqual(result['termination_reason'],'unexpected worker stdout')

    def test_budget_baseline_is_create_once_and_immutable(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=SCRATCH) as t:
            root=Path(t); path=root/'budget.json'
            b=r.initialize_budget(path,root)
            with self.assertRaises(FileExistsError): r.initialize_budget(path,root)
            self.assertEqual(r.load_budget(path),b)
            changed=r.account_fit(b,3.5); r.save_budget(path,changed)
            self.assertEqual(r.load_budget(path)['fit_seconds'],3.5)
            with self.assertRaises(r.ResourceError): r.save_budget(path,b)
            changed['scope']='tampered'
            with self.assertRaises(r.ResourceError): r.save_budget(path,changed)
            with self.assertRaises(r.ResourceError): r.load_budget(root/'missing.json')
    def test_original_exemption_identity(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=SCRATCH) as t:
            root=Path(t); source=root/'original'; source.write_bytes(b'original')
            b=r.new_budget_state(root,exempt_paths=[source]); self.assertEqual(r.check_disk(self.policy,root,b)['added_bytes'],0)
            self.assertEqual(b['exempt_original_sizes']['original']['sha256'],r._hash(source))
            source.write_bytes(b'changed!')
            with self.assertRaises(r.ResourceError): r.check_disk(self.policy,root,b)

    def test_original_rename_copy_alias_and_immutable_baseline(self):
        import os, shutil, tempfile
        with tempfile.TemporaryDirectory(dir=SCRATCH) as t:
            root=Path(t); (root/'old').mkdir(); (root/'new').mkdir()
            old=root/'old/original'; old.write_bytes(b'invented-original-contents')
            state_path=root/'budget.json'; b=r.initialize_budget(state_path,root,exempt_paths=[old])
            digest=b['baseline_sha256']; before=r.check_disk(self.policy,root,b)['added_bytes']
            moved=root/'new/renamed'; os.rename(old,moved)
            info=r.check_disk(self.policy,root,b)
            self.assertEqual(info['added_bytes'],before)
            self.assertEqual(info['relocated_originals'],[{'original':str(old.relative_to(root)),'current':str(moved.relative_to(root))}])
            self.assertEqual(r.load_budget(state_path)['baseline_sha256'],digest)
            copied=root/'new/copy'; shutil.copyfile(moved,copied)
            self.assertEqual(r.check_disk(self.policy,root,b)['added_bytes'],before+moved.stat().st_size)
            alias=root/'new/alias'; os.link(moved,alias)
            self.assertEqual(r.check_disk(self.policy,root,b)['added_bytes'],before+2*moved.stat().st_size)
            alias.unlink(); copied.unlink()
            os.rename(moved,old); alias=root/'new/alias'; os.link(old,alias)
            info=r.check_disk(self.policy,root,b)
            self.assertEqual(info['added_bytes'],before+old.stat().st_size)
            self.assertEqual(info['relocated_originals'],[])
            self.assertEqual(r.load_budget(state_path)['baseline_sha256'],digest)
            old.write_bytes(b'modified-original-content')
            with self.assertRaises(r.ResourceError): r.check_disk(self.policy,root,b)
    def test_removed_or_replaced_original_fails_closed(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=SCRATCH) as t:
            root=Path(t); old=root/'original'; old.write_bytes(b'original')
            b=r.new_budget_state(root,exempt_paths=[old]); old.unlink()
            with self.assertRaises(r.ResourceError): r.check_disk(self.policy,root,b)
            old.write_bytes(b'original')
            with self.assertRaises(r.ResourceError): r.check_disk(self.policy,root,b)

    def test_restored_mtime_edit_invalidates_cached_original_digest(self):
        import os, tempfile
        with tempfile.TemporaryDirectory(dir=SCRATCH) as t:
            root=Path(t); source=root/'original'; source.write_bytes(b'abcdefgh')
            budget=r.new_budget_state(root,exempt_paths=[source]); st=source.stat()
            self.assertEqual(r.check_disk(self.policy,root,budget)['added_bytes'],0)
            source.write_bytes(b'ABCDEFGH'); os.utime(source,ns=(st.st_atime_ns,st.st_mtime_ns))
            self.assertEqual(source.stat().st_ino,st.st_ino)
            self.assertEqual(source.stat().st_mtime_ns,st.st_mtime_ns)
            with self.assertRaisesRegex(r.ResourceError,'SHA256 changed'):
                r.check_disk(self.policy,root,budget)
            # A fresh process/cache has no permission to trust persisted metadata.
            r._ORIGINAL_HASH_CACHE.clear()
            with self.assertRaisesRegex(r.ResourceError,'SHA256 changed'):
                r.check_disk(self.policy,root,budget)

    def test_unchanged_original_checks_reuse_verified_change_token(self):
        import tempfile
        from unittest.mock import patch
        original_sha256=r.hashlib.sha256; byte_hashes=[]
        def counted(*args,**kwargs):
            if not args and not kwargs: byte_hashes.append(1)
            return original_sha256(*args,**kwargs)
        with tempfile.TemporaryDirectory(dir=SCRATCH) as t:
            root=Path(t); source=root/'original'; source.write_bytes(b'unchanged-original')
            r._ORIGINAL_HASH_CACHE.clear()
            with patch.object(r.hashlib,'sha256',counted):
                budget=r.new_budget_state(root,exempt_paths=[source])
                for _ in range(4): r.check_disk(self.policy,root,budget)
                self.assertEqual(len(byte_hashes),1)
                r._ORIGINAL_HASH_CACHE.clear(); r.check_disk(self.policy,root,budget)
                self.assertEqual(len(byte_hashes),2)

    def test_original_digest_handle_denies_write_and_rename(self):
        import os, tempfile
        from unittest.mock import patch
        original_sha256=r.hashlib.sha256; attempted=[]
        with tempfile.TemporaryDirectory(dir=SCRATCH) as t:
            source=Path(t)/'original'; source.write_bytes(b'invented-original')
            class Hash:
                def __init__(self): self.inner=original_sha256()
                def update(inner,block):
                    if not attempted:
                        with self.assertRaises(PermissionError):
                            with source.open('r+b'): pass
                        with self.assertRaises(PermissionError): os.rename(source,source.with_name('renamed'))
                        attempted.append(True)
                    inner.inner.update(block)
                def hexdigest(inner): return inner.inner.hexdigest()
            r._ORIGINAL_HASH_CACHE.clear()
            with patch.object(r.hashlib,'sha256',Hash): record=r._original_record(source)
            self.assertEqual(attempted,[True]); self.assertEqual(record['sha256'],r._hash(source))
            with source.open('r+b'): pass

    def test_invalid_fit_values_leave_persisted_budget_unchanged(self):
        import decimal, tempfile
        with tempfile.TemporaryDirectory(dir=SCRATCH) as t:
            root=Path(t); path=root/'budget.json'; b=r.initialize_budget(path,root)
            good=r.account_fit(b,2); r.save_budget(path,good); original=path.read_bytes()
            for value in (True, False, float('nan'), float('inf'), float('-inf'), -1, 1, '3', None, decimal.Decimal('3')):
                bad=dict(good); bad['fit_seconds']=value
                with self.subTest(value=value):
                    with self.assertRaises(r.ResourceError): r.save_budget(path,bad)
                    self.assertEqual(path.read_bytes(),original)
                    self.assertEqual(list(root.glob('budget.json.pending-*')),[])
            bad=dict(good); bad['extra']={'nested':float('nan')}
            with self.assertRaises(r.ResourceError): r.save_budget(path,bad)
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(list(root.glob('budget.json.pending-*')),[])
    def test_expired_stages_do_not_start_worker(self):
        import datetime, tempfile
        from unittest.mock import patch
        class Late(datetime.datetime):
            @classmethod
            def now(cls,tz=None):
                result=datetime.datetime.fromisoformat(self.policy['schedule']['freeze'])+datetime.timedelta(seconds=1)
                return result.astimezone(tz) if tz else result.replace(tzinfo=None)
        with tempfile.TemporaryDirectory(dir=SCRATCH) as t:
            root=Path(t); budget=r.new_budget_state(root); boot=root/'BOOT'
            cmd=[sys.executable,'-c',f'from pathlib import Path; Path({str(boot)!r}).write_text("started")']
            with patch.object(r,'datetime',Late):
                for stage in ('train','selection','test','synthetic'):
                    with self.subTest(stage=stage):
                        with self.assertRaises(r.ResourceError):
                            with r.prepare_worker(cmd,self.policy,root,budget,stage=stage,preflight_receipt=self.receipt): pass
                        self.assertFalse(boot.exists())
                with self.assertRaises(r.ResourceError): r.resource_preflight(self.policy,root,budget)
                with self.assertRaises(r.ResourceError): r.check_time(self.policy,'acquisition',budget)
                self.assertFalse(boot.exists())

if __name__=='__main__': unittest.main()
