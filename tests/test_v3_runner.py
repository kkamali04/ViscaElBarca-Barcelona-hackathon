"""Implementer checks with invented outputs; independent G08 remains required."""
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
import time
import hashlib
import shutil
from unittest.mock import patch

import numpy as np

from experiments.v3 import runner


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='v3-t09-', dir=Path('local'))
        self.root = Path(self.tmp.name).absolute()
    def tearDown(self):
        self.tmp.cleanup()
    def codes(self):
        result = np.full(runner.FRAMES, 3, dtype=np.int8)
        for _, start, end in runner.PERIODS:
            result[start:end] = 0
        result[110808:113742] = 2
        return result
    def publish(self, name='generation'):
        return runner.publish_generation(self.root/name/'candidate.csv', self.root/name/'run.json', self.codes(),
            {'release_digest':'a'*64, 'release_id':'synthetic', 'source_manifest_digest':'b'*64,
             'policy_digest':'c'*64, 'synthetic_demo':True},
            Path('.').resolve())
    def test_complete_held_pair_and_immutable_prior(self):
        self.publish()
        with runner.open_generation(self.root/'generation', expected_release='a'*64) as pair:
            self.assertEqual(set(pair.commit),{'schema_version','kind','generation_id','release_digest',
                'source_manifest_digest','policy_digest','csv','report'})
            self.assertEqual(pair.commit['kind'],'v3-run-generation')
            self.assertEqual(pair.commit['generation_id'],'generation')
            self.assertEqual(pair.report['generation_id'],'generation')
            self.assertEqual(pair.report['frame_count'],199319)
            self.assertEqual(pair.report['csv_filename'],'candidate.csv')
            self.assertEqual(pair.report['csv_sha256'], pair.commit['csv']['sha256'])
            self.assertEqual(pair.inspect()['frames'], 199319)
            with self.assertRaises(OSError):
                (self.root/'generation'/'candidate.csv').write_bytes(b'changed')
        before=(self.root/'generation'/'commit.json').read_bytes()
        with self.assertRaises((ValueError, PermissionError)):
            self.publish()
        self.assertEqual(before,(self.root/'generation'/'commit.json').read_bytes())
        for name in ('copied','.partial-v3-'+'1'*32):
            shutil.copytree(self.root/'generation',self.root/name)
            with self.assertRaises(ValueError):
                with runner.open_generation(self.root/name): pass
        with self.assertRaises(TypeError):
            runner.open_generation(self.root/'copied',_allow_staging=True)
        with self.assertRaises(ValueError):
            runner._verify_staged_generation(self.root/('.partial-v3-'+'1'*32),self.root/'wrong-final','a'*64)
    def test_corrupt_pair_extra_members_and_scratch_rejected(self):
        self.publish()
        (self.root/'generation'/'candidate.csv').write_bytes(b'frame,label\n0,H\n')
        with self.assertRaises(ValueError):
            with runner.open_generation(self.root/'generation'): pass
        self.publish('second')
        (self.root/'second'/'extra').write_bytes(b'')
        with self.assertRaises(ValueError):
            with runner.open_generation(self.root/'second'): pass
        with self.assertRaises(ValueError):
            with runner.open_generation(self.root/'.partial-example'): pass
    def test_paths_and_public_constraints(self):
        for out,report in [(self.root/'x'/'a',self.root/'y'/'b'),
                           (self.root/'x'/'A.csv',self.root/'x'/'a.csv'),
                           (self.root/'x'/'commit.json',self.root/'x'/'b')]:
            with self.assertRaises((ValueError,PermissionError)):
                runner.preflight_paths(out,report)
        for index,value in [(0,0),(110808,0),(199318,2)]:
            codes=self.codes(); codes[index]=value
            with self.assertRaises(ValueError): runner.validate_codes(codes)
    def test_no_publication_after_validator_failure(self):
        with self.assertRaises((FileNotFoundError,OSError,ValueError)):
            runner.publish_generation(self.root/'failed'/'candidate.csv',self.root/'failed'/'run.json',self.codes(),
                {'release_digest':'a'*64,'release_id':'synthetic','source_manifest_digest':'b'*64,
                 'policy_digest':'c'*64,'synthetic_demo':True},self.root/'absent-validator-root')
        self.assertFalse((self.root/'failed').exists())
    def test_exact_schema_types(self):
        self.publish()
        path=self.root/'generation'/'commit.json'; original=path.read_bytes()
        for edit in ({'schema_version':True},{'generation_id':False},{'generation_id':'other'},
                     {'kind':'v3-committed-generation'},{'release_id':'extra'}):
            document=json.loads(original); document.update(edit); path.write_text(json.dumps(document))
            with self.assertRaises(ValueError):
                with runner.open_generation(path.parent): pass
        path.write_bytes(original)
        report=path.parent/'run.json'; report_original=report.read_bytes()
        for edit in ({'schema_version':True},{'unknown':1},{'frame_count':True},{'rows':199319},
                     {'generation_id':'other'},{'csv_filename':'other.csv'},{'synthetic_demo':1},
                     {'cache_hit':1},{'total_seconds':True},{'total_seconds':float('inf')},
                     {'peak_process_working_set_bytes':True},{'process_id':False},
                     {'process_creation_time':False},{'runtime_digest':False},{'candidate_id':False},
                     {'resource_scope':{}},{'inference_seconds':-1},{'release_id':False},
                     {'synthetic_demo':False}):
            document=json.loads(report_original); document.update(edit)
            payload=json.dumps(document).encode(); report.write_bytes(payload)
            commit=json.loads(original); commit['report'].update(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest())
            path.write_text(json.dumps(commit))
            with self.subTest(edit=edit),self.assertRaises(ValueError):
                with runner.open_generation(path.parent): pass
    def test_held_atd_parser_and_single_finalizer(self):
        from test_v3_export import toy_release
        from test_features import metadata
        from experiments.v3 import cache
        release=toy_release(self.root/'toy')
        sources=self.root/'inputs'; tactical=sources/'tactical'; tactical.mkdir(parents=True)
        (tactical/'BAR-ATH_tactical_atd.xml').write_text(metadata(n=60))
        raw=tactical/'BAR-ATH_tactical_atd.txt'
        raw.write_text(''.join(f'{i+1}:0.1,0.2,0;0.8,0.7,0:0.3,0.4,0\n' for i in range(60)))
        with cache.open_inference_context(release,sources,self.root/'cache','synthetic_observations') as context:
            with patch('possession_model.features.load_atd',side_effect=AssertionError('path-reopen parser used')):
                features=runner.extract_features(context,n_frames=60,blocks=((1,0,60),))
            self.assertEqual(features.period_id.dtype,np.int16)
            self.assertFalse(features.ball_xy.flags.writeable)
            np.testing.assert_allclose(features.ball_xy[0],[31.59,27.2],rtol=1e-6)
            with self.assertRaises(OSError): raw.write_bytes(b'invented replacement')
        from experiments.v3.corruption import finalize_features
        with self.assertRaises(ValueError): finalize_features(features)
    def test_hard_kill_at_publication_boundaries(self):
        self.publish('prior')
        prior=(self.root/'prior'/'commit.json').read_bytes()
        script=self.root/'kill_probe.py'
        script.write_text('''import os,sys,time
from pathlib import Path
import numpy as np
from experiments.v3 import runner
base=Path(sys.argv[1]); point=sys.argv[2]; project=Path(sys.argv[3]); sentinel=base/'ready'
def stop():
    sentinel.write_text('ready')
    while True: time.sleep(.1)
original_write=runner._write
def write(path,payload):
    original_write(path,payload)
    if (point=='report' and path.name=='run.json') or (point=='commit' and path.name=='commit.json'): stop()
runner._write=write
original_validate=runner._official_validate
def validate(path,root):
    if point=='csv': stop()
    return original_validate(path,root)
runner._official_validate=validate
original_rename=Path.rename
def rename(path,target):
    if path.name.startswith('.partial-v3-'):
        if point=='before_rename': stop()
        result=original_rename(path,target)
        if point=='after_rename': stop()
        return result
    return original_rename(path,target)
Path.rename=rename
codes=np.full(runner.FRAMES,3,dtype=np.int8)
for _,a,b in runner.PERIODS: codes[a:b]=0
codes[110808:113742]=2
runner.publish_generation(base/'generation'/'candidate.csv',base/'generation'/'run.json',codes,
    dict(release_digest='a'*64,release_id='synthetic',source_manifest_digest='b'*64,policy_digest='c'*64,synthetic_demo=True),project)
''')
        for point in ('csv','report','commit','before_rename','after_rename'):
            base=self.root/point; base.mkdir()
            process=subprocess.Popen([sys.executable,'-c',"import runpy,sys; p=sys.argv.pop(1); runpy.run_path(p,run_name='__main__')",str(script),str(base),point,str(Path('.').resolve())],
                                     stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            try:
                until=time.monotonic()+15
                while not (base/'ready').exists() and process.poll() is None and time.monotonic()<until: time.sleep(.02)
                self.assertTrue((base/'ready').exists(),'kill boundary was not reached: '+point)
                process.kill(); process.wait(timeout=5)
                self.assertEqual((base/'generation').exists(),point=='after_rename')
                if point=='after_rename':
                    with runner.open_generation(base/'generation') as pair: self.assertTrue(pair.inspect()['valid'])
                self.assertEqual(prior,(self.root/'prior'/'commit.json').read_bytes())
            finally:
                if process.poll() is None: process.kill(); process.wait()
                process.stderr.close()
    def test_fresh_toy_process_cold_warm_and_config_preflight(self):
        from test_v3_export import toy_release
        from test_features import metadata
        from experiments.v3 import cache
        release=toy_release(self.root/'package')
        inputs=self.root/'inputs'; tactical=inputs/'tactical'; tactical.mkdir(parents=True)
        (tactical/'BAR-ATH_tactical_atd.xml').write_text(metadata(n=runner.FRAMES))
        with (tactical/'BAR-ATH_tactical_atd.txt').open('w') as stream:
            for frame in range(runner.FRAMES): stream.write(f'{frame+1}:nan,nan,0;nan,nan,0:nan,nan,0\n')
        output=self.root/'outputs'; output.mkdir()
        def invoke(name):
            command=[sys.executable,'-m','experiments.v3.cli','run','--release',str(release),'--data-dir',str(inputs),
                     '--out',str(output/name/'candidate.csv'),'--report',str(output/name/'run.json')]
            return subprocess.run(command,cwd=release.parent,capture_output=True,timeout=120)
        first=invoke('one')
        self.assertEqual(first.returncode,0,first.stderr.decode())
        second=invoke('two')
        self.assertEqual(second.returncode,0,second.stderr.decode())
        with runner.open_generation(output/'one') as one,runner.open_generation(output/'two') as two:
            self.assertEqual(one.report['csv_sha256'],two.report['csv_sha256'])
            self.assertFalse(one.report['cache_hit']); self.assertTrue(two.report['cache_hit'])
            self.assertGreater(one.report['peak_process_working_set_bytes'],0)
        # A manifest-valid but candidate-inconsistent config must fail before
        # missing raw input can be considered; fixture mutation is synthetic.
        config=release.parent/'models/v3-candidate.json'; config.write_text('{}')
        document=json.loads(release.read_bytes())
        for record in document['files']:
            if record['relative_path']=='models/v3-candidate.json':
                record.update(bytes=2,sha256=hashlib.sha256(b'{}').hexdigest())
        document['runtime_digest']=cache.digest_json(document['files']); release.write_bytes(cache.canonical_json(document))
        third=invoke('three')
        self.assertEqual(third.returncode,2)
        self.assertFalse((output/'three').exists())


if __name__ == '__main__': unittest.main()
