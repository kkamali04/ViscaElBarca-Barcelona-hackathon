"""Public XML schema with invented values only."""
import io
import dataclasses
import hashlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch,Mock
import numpy as np
from experiments.v3.adapter import parse_timestamp_ns, parse_sportec,load_match
from experiments.v3.contracts import AccessCapability
from experiments.v3.cache import canonical_json

META=b'<Root><General MatchId="invented" HomeTeamId="home" GuestTeamId="away"/><Environment PitchX="100" PitchY="60"/><Teams><Team TeamId="away"><Player PersonId="a"/></Team><Team TeamId="home"><Player PersonId="z"/><Player PersonId="h"/></Team></Teams></Root>'

def raw(label='1', reverse=False):
    sets=[]
    for section,start in [('firstHalf',0),('secondHalf',100)]:
        for person,team in [('z','home'),('h','home'),('a','away'),('', 'BALL')]:
            frames=[]
            for n in [start,start+2]:
                millis=(n-start)*40
                frames.append(f'<Frame N="{n}" T="2020-01-01T00:00:00.{millis:03d}Z" X="1" Y="2" BallStatus="1" BallPossession="{label}"/>')
            if reverse: frames.reverse()
            sets.append(f'<FrameSet MatchId="invented" GameSection="{section}" PersonId="{person}" TeamId="{team}">'+''.join(frames)+'</FrameSet>')
    if reverse: sets.reverse()
    return ('<Root>'+''.join(sets)+'</Root>').encode()


class AdapterTests(unittest.TestCase):
    def test_exact_timestamp(self):
        self.assertEqual(parse_timestamp_ns('1970-01-01T01:00:00.123456789+01:00'),123456789)
        for v in ('2020-01-01T00:00:00','2020-01-01T00:00:00.1234567890Z','bad'):
            with self.assertRaises(ValueError): parse_timestamp_ns(v)
    def test_dense_order_targets_and_metamorphism(self):
        a,t=parse_sportec(io.BytesIO(META),io.BytesIO(raw()),'invented','a'*64)
        b,u=parse_sportec(io.BytesIO(META),io.BytesIO(raw('2',True)),'invented','b'*64)
        self.assertEqual(a.slot_ids,('h','z','a')); self.assertEqual(a.frame_id.tolist(),list(range(6)))
        self.assertEqual(t.labels.tolist(),[0,-1,0,0,-1,0]); self.assertEqual(u.labels.tolist(),[1,-1,1,1,-1,1])
        for name in ('positions','ball_xy','source_frame_id','source_time_utc_ns','source_time_slot'):
            np.testing.assert_array_equal(getattr(a,name),getattr(b,name))
        self.assertFalse(a.positions.flags.writeable)
    def test_duplicate_and_sparse_bad_time(self):
        bad=raw().replace(b'<Frame N="0"',b'<Frame N="0"',1)
        frame=b'<Frame N="0" T="2020-01-01T00:00:00.000Z" X="1" Y="2"/>'
        bad=bad.replace(b'</FrameSet>',frame+b'</FrameSet>',1)
        with self.assertRaises(ValueError): parse_sportec(io.BytesIO(META),io.BytesIO(bad),'invented','a'*64)
        with self.assertRaises(ValueError): parse_sportec(io.BytesIO(META),io.BytesIO(raw().replace(b'00.080Z',b'00.082Z',1)),'invented','a'*64)

    def test_target_lexical_and_coordinate_normalization(self):
        for status,owner,code in [('0','anything',2),('1','1',0),('1','2',1),('1',' 1',-1),('1','01',-1),('2','1',-1)]:
            data=raw(owner).replace(b'BallStatus="1"',f'BallStatus="{status}"'.encode()).replace(b'X="1" Y="2"',b'X="nan" Y="2"')
            stats={}; obs,truth=parse_sportec(io.BytesIO(META),io.BytesIO(data),'invented','a'*64,stats)
            self.assertEqual(truth.labels[0],code); self.assertGreater(stats['normalized_coordinate_pairs'],0)
            self.assertTrue(np.isnan(obs.positions).all()); self.assertTrue(np.isnan(obs.ball_xy).all())
            self.assertTrue(np.all(obs.positions.view(np.uint32)==0x7fc00000))

    def test_origin_ball_preference_tolerance_and_roster_order(self):
        data=raw().replace(b'T="2020-01-01T00:00:00.000Z"',b'T="2020-01-01T00:00:00.001Z"',1)
        obs,_=parse_sportec(io.BytesIO(META),io.BytesIO(data),'invented','a'*64)
        self.assertEqual(obs.period_origins[0].utc_ns,parse_timestamp_ns('2020-01-01T00:00:00Z'))
        self.assertIn(1_577_836_800_001_000_000,obs.source_time_utc_ns)
        with self.assertRaises(ValueError): parse_sportec(io.BytesIO(META.replace(b'PersonId="h"',b'PersonId="z"')),io.BytesIO(raw()),'invented','a'*64)
        with self.assertRaises(ValueError): parse_sportec(io.BytesIO(META),io.BytesIO(raw().replace(b'firstHalf',b'unknown',1)),'invented','a'*64)

    def test_guard_precedes_any_lookup_and_closed_denial(self):
        cap=AccessCapability('a'*64,'s','test',('J03WN1',),1,'t','b'*64)
        fake=types.ModuleType('experiments.v3.guard'); fake.assert_access=Mock(side_effect=PermissionError('synthetic denied'))
        with patch.dict('sys.modules',{'experiments.v3.guard':fake}),patch('experiments.v3.fetch.registered_sources') as catalog:
            with self.assertRaises(PermissionError): load_match(Path('must-not-open.json'),cap,'J03WN1')
            catalog.assert_not_called(); fake.assert_access.assert_called_once_with(cap,'J03WN1','raw')
        with self.assertRaises(PermissionError): load_match(Path('must-not-open.json'),cap,'J03WR9')

    def test_guarded_synthetic_cache_miss_hit_and_tamper(self):
        from experiments.v3.fetch import FIXTURES
        scratch=Path('local/v3-t03-tests'); scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='adapter-',dir=scratch) as temporary:
            root=Path(temporary).resolve(); originals=root/'originals'; originals.mkdir(); catalog={'schema_version':1,'provider':'IDSSE','raw_root':str(originals),'metadata_overlap_receipt_digest':'a'*64,'fixtures':{}}
            for fixture,role in FIXTURES.items():
                item={'fixture_id':fixture,'canonical_fixture_id':'invented-'+fixture,'duplicate_group':'invented-'+fixture,'role':role,'fps':25.,'license':{'spdx':'CC-BY-4.0','attribution_receipt_digest':'b'*64}}
                for kind,data in [('metadata',META),('tracking',raw())]:
                    name=fixture+'-'+kind+'.xml'; (originals/name).write_bytes(data)
                    item[kind]={'kind':kind,'relative_path':name,'source_url':'https://example.invalid/'+name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'md5':hashlib.md5(data).hexdigest()}
                catalog['fixtures'][fixture]=item
            catalog_path=root/'catalog.json'; catalog_path.write_bytes(canonical_json(catalog))
            manifest={'raw_root':str(originals),'catalog_path':str(catalog_path),'catalog_digest':hashlib.sha256(catalog_path.read_bytes()).hexdigest(),'protocol_digest':'c'*64,'scientific_closure_digest':'d'*64,'environment_digest':'e'*64}
            study=root/'study.json'; study.write_bytes(canonical_json(manifest)); cap=AccessCapability(hashlib.sha256(study.read_bytes()).hexdigest(),'invented-attempt','train',('J03WOH',),1,'t','f'*64)
            events=[]; fake=types.ModuleType('experiments.v3.guard'); fake.assert_access=lambda *args:events.append(args[2]); fake.load_registered_study=lambda path:manifest
            with patch.dict('sys.modules',{'experiments.v3.guard':fake}):
                from experiments.v3.adapter import parse_sportec as parser
                def checked(*args,**kwargs):
                    self.assertIn('raw',events); return parser(*args,**kwargs)
                with patch('experiments.v3.adapter.parse_sportec',side_effect=checked) as parse_spy:
                    a,t=load_match(study,cap,'J03WOH'); b,u=load_match(study,cap,'J03WOH'); self.assertEqual(parse_spy.call_count,1)
                self.assertEqual(a.positions.tobytes(),b.positions.tobytes()); self.assertEqual(t.labels.tobytes(),u.labels.tobytes()); self.assertFalse(b.positions.flags.writeable)
                cache=next((root/'caches').iterdir())/'targets'/'labels.npy'
                with cache.open('r+b') as handle: handle.seek(-1,2); handle.write(b'\x02')
                with patch('experiments.v3.adapter.parse_sportec') as no_reparse:
                    with self.assertRaises(ValueError): load_match(study,cap,'J03WOH')
                    no_reparse.assert_not_called()


class FetchTests(unittest.TestCase):
    def test_forbidden_fixture_before_catalog_lookup(self):
        from experiments.v3.fetch import fetch_registered_sources
        with patch('experiments.v3.fetch.registered_sources') as catalog:
            with self.assertRaises(PermissionError): fetch_registered_sources(Path('absent'),('J03WR9',),Path('absent'))
            catalog.assert_not_called()
    def test_opaque_registered_download_reuse_mismatch_and_destination(self):
        from experiments.v3.fetch import fetch_registered_sources
        scratch=Path('local/v3-t03-tests'); scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='fetch-',dir=scratch) as temporary:
            root=Path(temporary).resolve(); originals=root/'originals'; originals.mkdir(); study=root/'study.json'
            item={}; payloads={}
            for kind in ('metadata','tracking'):
                data=b'invented-opaque-'+kind.encode(); name=kind+'.xml'; url='https://example.invalid/'+name; payloads[url]=data
                item[kind]={'kind':kind,'relative_path':name,'source_url':url,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'md5':hashlib.md5(data).hexdigest()}
            manifest={'raw_root':str(originals),'catalog_digest':'a'*64}; catalog={'fixtures':{'J03WOH':item}}
            class Response(io.BytesIO):
                def __init__(self,url): super().__init__(payloads[url]); self.url=url
                def geturl(self): return self.url
            with patch('experiments.v3.fetch.registered_sources',return_value=(manifest,catalog)),patch('experiments.v3.fetch.urllib.request.urlopen',side_effect=lambda request,timeout:Response(request.full_url)) as network:
                receipt=fetch_registered_sources(study,('J03WOH',),originals)
                report=json.loads(receipt.read_text()); self.assertFalse(report['records_parsed']); self.assertEqual(network.call_count,2)
                fetch_registered_sources(study,('J03WOH',),originals); self.assertEqual(network.call_count,2)
                before=(originals/'tracking.xml').read_bytes(); (originals/'metadata.xml').write_bytes(b'wrong')
                with self.assertRaises(ValueError): fetch_registered_sources(study,('J03WOH',),originals)
                self.assertEqual(before,(originals/'tracking.xml').read_bytes()); self.assertEqual(network.call_count,2)
                with self.assertRaises(ValueError): fetch_registered_sources(study,('J03WOH',),root/'elsewhere')


class RealGuardIntegrationTests(unittest.TestCase):
    """Actual guard/lease/parser control flow, confined invented whole study."""
    def test_reserved_before_parse_cache_hit_and_finished_denial(self):
        from experiments.v3 import guard
        protocol=json.loads(Path('specs/003-possession-improvements/protocol.json').read_text())
        scratch=Path('local/v3-t03-tests'); scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='guard-integration-',dir=scratch) as temporary:
            root=Path(temporary).resolve()
            def put(name,data):
                path=root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data); return path
            def dump(name,value): return put(name,canonical_json(value))
            for name in protocol['fit']['source_closure']['scientific_new_modules']:
                put('experiments/v3/'+name,b'# invented registered scientific fixture\n')
            for name in ('PRD-TURNOVER.md','PRD-MULTIMATCH.md','contracts.md'):
                put('specs/003-possession-improvements/'+name,b'invented requirement\n')
            for name in ('requirements-lock.txt','requirements-training-lock.txt','tools/v3_prepare_catalog.py','more-than-a-hack-2027-main/evaluation/possession_metrics.py'):
                put(name,b'# invented dependency\n')
            # G02's full closure now requires these public sources. Preserve the
            # explicit fixtures above; fill only absent required paths locally.
            public_project=Path(__file__).resolve().parents[1]
            planned={f'experiments/v3/{name}.py' for name in ('training','evaluate','resources','core')}
            # The accepted training helper imports this additional public fetch
            # module; its actual source is part of the transitive closure too.
            required=set(guard._REQUIRED_SCIENTIFIC_PATHS)|{'tools/fetch_validation_data.py'}
            for name in sorted(required):
                if (root/name).exists(): continue
                source=public_project/name
                if source.is_file(): put(name,source.read_bytes())
                elif name in planned: put(name,b'# invented future scientific fixture\n')
                else: raise FileNotFoundError('required public scientific fixture source missing')
            overlap=put('reports/v3-metadata-overlap.json',b'{}'); attribution=put('reports/v3-source-attribution.json',b'{}')
            fallback={}
            for i in range(29):
                name=f'fallback/{i}.txt'; file=put(name,f'invented-{i}'.encode()); fallback[name]={'bytes':file.stat().st_size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()}
            fallback_path=dump('reports/fallback.json',{'files':fallback})
            protocol['study_id']='invented-guard-adapter'; protocol_path=dump('specs/003-possession-improvements/protocol.json',protocol)
            originals=root/'local/v3-data/originals'; fixtures={}
            for role in ('train','selection','test'):
                for fixture in protocol['split'][role]:
                    item={'fixture_id':fixture,'canonical_fixture_id':'invented:'+fixture,'duplicate_group':'invented:'+fixture,'role':role,'fps':25.,
                          'license':{'spdx':'CC-BY-4.0','attribution_receipt_digest':hashlib.sha256(attribution.read_bytes()).hexdigest()}}
                    for kind,data in [('metadata',META),('tracking',raw())]:
                        name=fixture+'/'+kind+'.xml'; put('local/v3-data/originals/'+name,data)
                        item[kind]={'kind':kind,'relative_path':name,'source_url':'https://example.invalid/'+name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'md5':hashlib.md5(data).hexdigest()}
                    fixtures[fixture]=item
            catalog=dump('local/v3-control/catalog-complete.json',{'schema_version':1,'provider':'IDSSE','raw_root':str(originals),
                'metadata_overlap_receipt_digest':hashlib.sha256(overlap.read_bytes()).hexdigest(),'fixtures':fixtures})
            old_locations=dict(guard._LOCATIONS); old_controls=dict(guard._CONTROL_BY_PATH)
            try:
                with patch.object(guard,'ROOT',root):
                    control=root/'local/v3-control'; study=guard.register_study(protocol_path,catalog,fallback_path,control)
                    cap=guard.reserve_attempt(study,'train',tuple(protocol['split']['train']),control)
                    parser=__import__('experiments.v3.adapter',fromlist=['parse_sportec']).parse_sportec
                    def verify_reservation(*args,**kwargs):
                        events=guard._replay(control)
                        self.assertTrue(any(x['kind']=='reserve' and x['attempt_id']==cap.attempt_id for x in events))
                        self.assertTrue(any(x['kind']=='first_access' and x['attempt_id']==cap.attempt_id for x in events))
                        return parser(*args,**kwargs)
                    with patch('experiments.v3.adapter.parse_sportec',side_effect=verify_reservation) as spy:
                        a,t=load_match(study,cap,'J03WOH'); b,u=load_match(study,cap,'J03WOH'); self.assertEqual(spy.call_count,1)
                    self.assertEqual(a.positions.tobytes(),b.positions.tobytes()); self.assertEqual(t.labels.tobytes(),u.labels.tobytes())
                    result=study.parent/'result.json'; result.write_bytes(canonical_json({'study_digest':cap.study_digest,'attempt_id':cap.attempt_id,'status':'complete'}))
                    guard.finish_attempt(cap,result,'complete')
                    with patch('experiments.v3.adapter.parse_sportec') as spy:
                        with self.assertRaises(guard.AccessError): load_match(study,cap,'J03WOH')
                        spy.assert_not_called()
            finally:
                guard._LOCATIONS.clear(); guard._LOCATIONS.update(old_locations)
                guard._CONTROL_BY_PATH.clear(); guard._CONTROL_BY_PATH.update(old_controls)

if __name__=='__main__': unittest.main()
