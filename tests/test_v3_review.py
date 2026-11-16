"""Synthetic-only HTTP checks: no actual input, model, video or timeline."""
import http.client
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
import shutil

from experiments.v3 import review


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='v3-t09-review-',dir=Path('local'))
        self.state=review.ReviewStateV3(Path('.').resolve(),None,Path(self.temp.name)/'never-read-input',True,work=Path(self.temp.name)/'review')
        self.server=review.ServerV3(self.state,port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()
    def request(self,method,path,body=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        connection.request(method,path,body=body,headers=headers or {})
        response=connection.getresponse(); result=(response.status,dict(response.getheaders()),response.read()); connection.close(); return result
    def test_state_origin_and_no_video(self):
        status,headers,body=self.request('GET','/api/state')
        state=json.loads(body)
        self.assertEqual(status,200); self.assertEqual(state['mode'],'demo'); self.assertEqual(state['version'],'3')
        self.assertFalse(state['inputs']['video_ready']); self.assertIn('synthetic',state['release_id'])
        self.assertEqual(self.request('GET','/api/state',headers={'Host':'evil.example'})[0],403)
        self.assertEqual(self.request('GET','/media/tactical.mp4')[0],404)
        self.assertEqual(self.request('GET','/../../models/active.json')[0],404)
        self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
    def test_post_protection_and_exact_generation_download(self):
        self.assertEqual(self.request('POST','/api/run',body='{}',headers={'Content-Type':'application/json'})[0],403)
        headers={'Content-Type':'application/json','X-Review-Token':self.state.token}
        self.assertEqual(self.request('POST','/api/run',body='{}',headers=headers)[0],202)
        self.state.worker.join(20)
        self.assertEqual(self.state.run['status'],'complete')
        status,download_headers,csv=self.request('GET','/download/candidate')
        self.assertEqual(status,200); self.assertEqual(csv.count(b'\n'),199320)
        self.assertIn('DEMO-candidate.csv',download_headers['Content-Disposition'])
        self.assertEqual(self.request('GET','/download/code')[0],404)
        self.assertEqual(self.request('POST','/api/run',body='{}',headers={**headers,'Origin':'https://evil.example'})[0],403)
    def test_content_limits_and_unknown_routes(self):
        headers={'X-Review-Token':self.state.token,'Content-Type':'text/plain'}
        self.assertEqual(self.request('POST','/api/run',body='{}',headers=headers)[0],415)
        headers['Content-Type']='application/json'
        self.assertEqual(self.request('POST','/api/run',body='[]',headers=headers)[0],400)
        self.assertEqual(self.request('POST','/api/run',body='x'*8193,headers=headers)[0],413)
        self.assertEqual(self.request('POST','/api/unknown',body='{}',headers=headers)[0],404)
        self.assertEqual(self.request('HEAD','/')[0],200)
        self.assertEqual(self.request('GET','/download/review-pack')[0],404)
    def test_restart_uses_utf8_basename_order_and_preserves_prior(self):
        from experiments.v3 import runner
        import numpy as np
        state=self.state
        codes=np.full(runner.FRAMES,3,dtype=np.int8)
        for _,start,stop in runner.PERIODS: codes[start:stop]=0
        codes[110808:113742]=2
        provenance={'release_id':state.release_id,'release_digest':state.release_digest,
                    'source_manifest_digest':'b'*64,'policy_digest':state.doc['policy_digest'],
                    'synthetic_demo':True}
        def publish(name):
            path=state.runs/name
            runner.publish_generation(path/'candidate.csv',path/'run.json',codes,provenance,state.root)
            return path
        def snapshot():
            return {p.relative_to(state.runs).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in state.runs.rglob('*') if p.is_file()}
        def restart(expected):
            before=snapshot()
            restored=review.ReviewStateV3(state.root,None,state.data_dir,True,work=state.work)
            self.assertEqual(restored.generation.name,expected)
            self.assertTrue(restored.current()['valid'])
            self.assertEqual(snapshot(),before)
            return restored
        publish('Z-final'); prior=publish('a-final')
        prior_hashes=snapshot()
        restart('a-final')  # ASCII bytes a > Z, unlike WindowsPath comparisons.
        publish('\u00c9-upper'); publish('\u00e0-lower')
        restart('\u00e0-lower')  # UTF-8 C3 A0 > C3 89; case folding reverses this pair.
        malformed=publish('\u9ffe-malformed')
        (malformed/'commit.json').write_text('{}')
        incomplete=state.runs/'\u9fff-incomplete'; incomplete.mkdir()
        (incomplete/'candidate.csv').write_bytes(b'frame,label\n0,H\n')
        shutil.copytree(prior,state.runs/('.partial-v3-'+'f'*32))
        (state.runs/'\ufffd-file').write_bytes(b'invented non-directory')
        restored=restart('\u00e0-lower')
        for name,digest in prior_hashes.items(): self.assertEqual(snapshot()[name],digest)
        self.assertEqual(restored.csv.read_bytes(),(prior/'candidate.csv').read_bytes())
    def test_private_toy_bundle_release_identity_and_range_contract(self):
        from test_v3_export import toy_release
        from experiments.v3 import cache
        import zipfile
        root=Path(self.temp.name).absolute()/'toy'
        release=toy_release(root)
        # Swap only this test server's explicitly constructed state; never a
        # module default or monkeypatch of the old MVP state/server.
        state=review.ReviewStateV3(root,release,root/'never-read-input',True)
        self.server.app=state; state.start_run(); state.worker.join(20)
        self.assertEqual(state.run['status'],'complete')
        headers={'Content-Type':'application/json','X-Review-Token':state.token}
        status,_,body=self.request('POST','/api/export',body=json.dumps({'team_name':'Invented Team','repository_url':''}),headers=headers)
        self.assertEqual(status,200,body.decode())
        result=json.loads(body); self.assertEqual(result['release_id'],state.release_id)
        self.assertFalse(result['submission_ready'])
        with zipfile.ZipFile(state.bundle) as bundle:
            manifest=json.loads(bundle.read('PRIVATE-REVIEW.json'))
            self.assertTrue(manifest['synthetic_demo']); self.assertFalse(manifest['submitted'])
            self.assertEqual(manifest['release_digest'],state.release_digest)
            self.assertEqual(manifest['generation_id'],state.generation.name)
            generation_dir=manifest['generation_directory']
            self.assertEqual(generation_dir,'generations/'+state.generation.name)
            commit=json.loads(bundle.read(generation_dir+'/commit.json'))
            report=json.loads(bundle.read(generation_dir+'/'+commit['report']['filename']))
            self.assertEqual(report['generation_id'],commit['generation_id'])
            self.assertEqual(report['csv_filename'],commit['csv']['filename'])
            restored=root/'restored'/state.generation.name; restored.mkdir(parents=True)
            for name in ('commit.json',commit['csv']['filename'],commit['report']['filename']):
                (restored/name).write_bytes(bundle.read(generation_dir+'/'+name))
            from experiments.v3.runner import open_generation
            with open_generation(restored,state.release_digest) as pair:
                self.assertEqual(pair.report['frame_count'],199319)
            restored.rename(restored.with_name('renamed'))
            with self.assertRaises(ValueError):
                with open_generation(restored.with_name('renamed'),state.release_digest): pass
        self.assertEqual(self.request('HEAD','/download/code')[0],200)
        self.assertEqual(self.request('HEAD','/download/review-pack')[0],200)
        # Purely invented byte stream exercises the unchanged single-range
        # semantics. No browser or real video/tracking is involved.
        data=root/'invented-input'; (data/'tactical').mkdir(parents=True)
        (data/'tactical/BAR-ATH_tactical.mp4').write_bytes(b'0123456789')
        local=review.ReviewStateV3(root,release,data,False); self.server.app=local
        status,headers,payload=self.request('GET','/media/tactical.mp4',headers={'Range':'bytes=2-5'})
        self.assertEqual(status,206); self.assertEqual(payload,b'2345'); self.assertEqual(headers['Content-Range'],'bytes 2-5/10')
        self.assertEqual(self.request('GET','/media/tactical.mp4',headers={'Range':'bytes=-3'})[2],b'789')
        for value in ('bytes=10-','bytes=5-2','bytes=0-1,4-5','bytes=-0'):
            self.assertEqual(self.request('GET','/media/tactical.mp4',headers={'Range':value})[0],416)


if __name__=='__main__': unittest.main()
