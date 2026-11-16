"""Synthetic cache integrity and handle lifetime tests."""
import dataclasses
import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from experiments.v3.contracts import AccessCapability, ReleaseAccess
from experiments.v3.cache import ReadLease, verify_cache, write_cache_atomic, assert_cache_authority,open_inference_context,canonical_json,digest_json,assert_release_access


def invented_atd(n=3):
    channels=''.join(f'<Channel id="{i}"><Name>{name}</Name><Unit>{unit}</Unit></Channel>' for i,name,unit in [('x','position_x','normalized'),('y','position_y','normalized'),('s','speed_mps','m/s')])
    links=''.join(f'<PlayerChannel id="{p}{i}" playerId="{p}" channelId="{i}"/>' for p in ('h','a') for i in ('x','y','s'))
    groups=''.join('<SplitRegister separator=",">'+''.join(f'<PlayerChannelRef playerChannelId="{p}{i}"/>' for i in ('x','y','s'))+'</SplitRegister>' for p in ('h','a'))
    xml=f'<Root><Team id="home"/><Team id="away"/><Score idLocalTeam="home" idVisitingTeam="away"/><Player id="h" teamId="home"/><Player id="a" teamId="away"/><FrameRate>25</FrameRate>{channels}{links}<DataFormatSpecification separator=":" startFrame="1" endFrame="{n}"><StringRegister name="frameCount"/><SplitRegister separator=";">{groups}</SplitRegister><SplitRegister separator=","><BallChannelRef channelId="x"/><BallChannelRef channelId="y"/><BallChannelRef channelId="s"/></SplitRegister></DataFormatSpecification></Root>'
    raw=''.join(f'{i}:0.1,0.2,0;0.3,0.4,0:0.5,0.6,0\n' for i in range(1,n+1))
    return xml.encode(),raw.encode()


def invented_release(root):
    from experiments.v3.cache import REQUIRED_RUNTIME_PATHS,REQUIRED_SCIENTIFIC_PATHS
    files=[]
    items=[(name,'scientific') for name in REQUIRED_SCIENTIFIC_PATHS]+[(name,'runtime') for name in REQUIRED_RUNTIME_PATHS]+[('emitter.json','emitter'),('config.json','config')]
    for name,role in items:
        # Current local public source code may be copied; future modules stand
        # in with invented bytes. No real model/data/report artifact is copied.
        source=Path(name); data=source.read_bytes() if source.is_file() and role in ('runtime','scientific') else b'{}'
        (root/name).parent.mkdir(parents=True,exist_ok=True); (root/name).write_bytes(data)
        files.append({'relative_path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'role':role})
    files.sort(key=lambda x:x['relative_path']); policy={'kind':'challenge','forced_dead':[[110808,113742]]}
    doc={'schema_version':1,'kind':'v3-observation-release','release_id':'invented','files':files,'runtime_digest':digest_json(files),'scientific_digest':digest_json([x for x in files if x['role']=='scientific']),
         'policy':policy,'policy_digest':digest_json(policy),'candidate':{'candidate_id':'A','alpha':0,'support':'none','transition_seconds':.5},'models':{'emitter':'emitter.json','head':None,'config':'config.json'},
         'provenance':dict(study_digest='a'*64,model_seal_digest='b'*64,finalist_digest='c'*64,protocol_digest='d'*64)}
    release=root/'release.json'; release.write_bytes(canonical_json(doc)); return release,doc


class CacheTests(unittest.TestCase):
    def setUp(self):
        scratch=Path('local/v3-t03-tests'); scratch.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(prefix='cache-',dir=scratch); self.root=Path(self.tmp.name)
        self.cap=AccessCapability('a'*64,'synthetic','train',('invented',),123,'time','b'*64)
        self.meta=dict(domain='study',kind='targets',fixture_id='invented',role='train',attempt_id='synthetic',study_digest='a'*64,source_digest='c'*64,protocol_digest='d'*64,dependency_digest='e'*64,environment_digest='f'*64,config_digest='0'*64,condition='clean',seeds={},n_frames=4)
        self.spy=patch('experiments.v3.cache._assert_study_access'); self.access=self.spy.start()
    def tearDown(self): self.spy.stop(); self.tmp.cleanup()
    def test_roundtrip_tamper_and_closed_lease(self):
        p=self.root/'cache'; labels=np.array([0,1,2,-1],dtype=np.int8)
        write_cache_atomic(p,{'labels':labels},self.meta,self.cap)
        with verify_cache(p,self.meta,self.cap) as lease:
            np.testing.assert_array_equal(lease.arrays['labels'],labels)
            escaped=lease.arrays['labels']
            with self.assertRaises(OSError): (p/'labels.npy').rename(p/'changed.npy')
        with self.assertRaises(RuntimeError): _=lease.arrays
        with self.assertRaises(RuntimeError): _=escaped[0]
        with self.assertRaises(RuntimeError): escaped.tobytes()
        with (p/'labels.npy').open('r+b') as h: h.seek(-1,2); h.write(b'\x01')
        with self.assertRaises(ValueError): verify_cache(p,self.meta,self.cap)
    def test_missing_extra_and_dtype(self):
        p=self.root/'cache'; write_cache_atomic(p,{'labels':np.zeros(4,dtype=np.int8)},self.meta,self.cap)
        (p/'extra').write_bytes(b'x')
        with self.assertRaises(ValueError): verify_cache(p,self.meta,self.cap)
        with self.assertRaises(ValueError): write_cache_atomic(self.root/'bad',{'labels':np.zeros(4,dtype=np.int64)},self.meta,self.cap)
    def test_wrong_domain_before_lookup(self):
        with self.assertRaises(PermissionError): assert_cache_authority(self.cap,'release','observations')
        self.access.assert_not_called()
    def test_read_lease_blocks_mutation(self):
        p=self.root/'opaque'; p.write_bytes(b'invented')
        with ReadLease(p) as lease:
            self.assertEqual(lease.read(),b'invented')
            with self.assertRaises(OSError): p.open('wb')
            self.assertEqual(lease.sha256(),__import__('hashlib').sha256(b'invented').hexdigest())

    def test_truncated_header_manifest_extra_and_failed_reservation(self):
        p=self.root/'cache'; write_cache_atomic(p,{'labels':np.zeros(4,dtype=np.int8)},self.meta,self.cap)
        arr=p/'labels.npy'; data=arr.read_bytes(); arr.write_bytes(data[:-1])
        with self.assertRaises(ValueError): verify_cache(p,self.meta,self.cap)
        self.access.side_effect=PermissionError('synthetic consumed')
        with self.assertRaises(PermissionError): verify_cache(self.root/'does-not-exist',self.meta,self.cap)
    def test_immutable_existing_and_writer_reservation(self):
        p=self.root/'cache'; write_cache_atomic(p,{'labels':np.zeros(4,dtype=np.int8)},self.meta,self.cap)
        with self.assertRaises(ValueError): write_cache_atomic(p,{'labels':np.ones(4,dtype=np.int8)},self.meta,self.cap)
        (self.root/'.next.writer-reservation').write_bytes(b'invented other writer')
        with self.assertRaises(FileExistsError): write_cache_atomic(self.root/'next',{'labels':np.zeros(4,dtype=np.int8)},self.meta,self.cap)
    def test_fabricated_release_authority_rejected_without_lookups(self):
        from experiments.v3.cache import process_creation_time
        access=ReleaseAccess('a'*64,'b'*64,'synthetic_observations',(), 'c'*64,'d'*64,self.root.resolve(),__import__('os').getpid(),process_creation_time())
        with patch('experiments.v3.cache.ReadLease') as reads:
            with self.assertRaises(PermissionError): assert_cache_authority(access,'release','features')
            with self.assertRaises(PermissionError): assert_cache_authority(access,'release','targets')
            with self.assertRaises(PermissionError): assert_cache_authority(access,'study','observations')
            reads.assert_not_called()
    def test_standalone_release_cache_and_expired_context(self):
        release,doc=invented_release(self.root); sources=self.root/'sources'; (sources/'tactical').mkdir(parents=True)
        xml,raw=invented_atd()
        (sources/'tactical/BAR-ATH_tactical_atd.xml').write_bytes(xml); (sources/'tactical/BAR-ATH_tactical_atd.txt').write_bytes(raw)
        cache=self.root/'release-cache'
        from experiments.v3.cache import FEATURE_ARRAYS
        arrays={'period_id':np.ones(3,dtype=np.int16),'ball_xy':np.ones((3,2),dtype=np.float32),'ball_observed':np.ones(3,dtype=bool),'nearest':np.ones((3,2),dtype=np.float32),
                'tracked_counts':np.ones((3,2),dtype=np.int16),'collective_speed':np.ones((3,2),dtype=np.float32),'ball_speed':np.ones(3,dtype=np.float32)}
        self.access.side_effect=AssertionError('standalone release consulted study guard')
        with open_inference_context(release,sources,cache,'synthetic_observations') as context:
            access=context.access
            metadata={key:getattr(access,key) for key in ('release_digest','source_manifest_digest','runtime_digest','policy_digest','input_kind')}
            metadata.update(domain='release',kind='features',feature_transform_digest='e'*64,n_frames=3,fps=25.,pitch=[105.,68.],feature_names=list(FEATURE_ARRAYS),feature_metadata={})
            write_cache_atomic(cache/'features',arrays,metadata,access)
            with verify_cache(cache/'features',metadata,access) as held:
                np.testing.assert_array_equal(held.arrays['ball_speed'],arrays['ball_speed'])
            assert_release_access(access,sources/'tactical/BAR-ATH_tactical_atd.txt','raw_observations')
            with self.assertRaises(PermissionError): assert_release_access(access,self.root/'elsewhere','features')
            with self.assertRaises(PermissionError): assert_cache_authority(dataclasses.replace(access),'release','features')
        with self.assertRaises(PermissionError): assert_cache_authority(access,'release','features')
    def test_release_closure_and_schema_fail_before_source_open(self):
        release,doc=invented_release(self.root)
        (self.root/'experiments/v3/core.py').write_bytes(b'changed')
        with self.assertRaises(ValueError): open_inference_context(release,self.root/'absent',self.root/'cache','synthetic_observations')
        release,doc=invented_release(self.root); sources=self.root/'sources'; (sources/'tactical').mkdir(parents=True)
        xml,raw=invented_atd(); xml=xml.replace(b'<Root>',b'<Root><BallStatus>1</BallStatus>')
        (sources/'tactical/BAR-ATH_tactical_atd.xml').write_bytes(xml); (sources/'tactical/BAR-ATH_tactical_atd.txt').write_bytes(raw)
        with self.assertRaises(ValueError): open_inference_context(release,sources,self.root/'cache','synthetic_observations')
    def test_exact_runtime_and_training_lock_names_allowed_other_text_refused(self):
        from experiments.v3.cache import _release_document
        release,document=invented_release(self.root)
        # Runtime lock is already in the required closure. Add the pinned
        # training lock as reproduction material, never a raw input document.
        _release_document(release)
        for name,accepted in [('requirements-training-lock.txt',True),('arbitrary-private.txt',False),('PRIVATE.TXT',False)]:
            data=b'# invented pinned lock or forbidden text fixture\n'
            (self.root/name).write_bytes(data)
            document['files'].append({'relative_path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'role':'runtime'})
            document['files'].sort(key=lambda item:item['relative_path'])
            document['runtime_digest']=digest_json(document['files'])
            release.write_bytes(canonical_json(document))
            if accepted:
                checked,_=_release_document(release)
                self.assertIn('requirements-lock.txt',[item['relative_path'] for item in checked['files']])
                self.assertIn(name,[item['relative_path'] for item in checked['files']])
            else:
                with self.assertRaises(ValueError): _release_document(release)
                document['files']=[item for item in document['files'] if item['relative_path']!=name]
    def test_boolean_schema_versions_and_release_numeric_aliases_refused(self):
        from experiments.v3.cache import _release_document
        p=self.root/'cache'; write_cache_atomic(p,{'labels':np.zeros(4,dtype=np.int8)},self.meta,self.cap)
        manifest=json.loads((p/'cache.json').read_text()); manifest['schema_version']=True
        (p/'cache.json').write_bytes(canonical_json(manifest))
        with self.assertRaises(ValueError): verify_cache(p,self.meta,self.cap)
        release,original=invented_release(self.root)
        variants=[]
        bad=json.loads(json.dumps(original)); bad['schema_version']=True; variants.append(bad)
        bad=json.loads(json.dumps(original)); bad['candidate']['alpha']=False; variants.append(bad)
        bad=json.loads(json.dumps(original)); bad['candidate']['transition_seconds']=True; variants.append(bad)
        bad=json.loads(json.dumps(original)); bad['policy']['forced_dead']=[[110808.0,113742.0]]; bad['policy_digest']=digest_json(bad['policy']); variants.append(bad)
        bad=json.loads(json.dumps(original)); bad['policy']['forced_dead']=[[True,113742]]; bad['policy_digest']=digest_json(bad['policy']); variants.append(bad)
        for document in variants:
            release.write_bytes(canonical_json(document))
            with self.assertRaises(ValueError): _release_document(release)

    def test_actual_manifest_metadata_and_shape_types_before_mapping(self):
        p=self.root/'one'; metadata={**self.meta,'n_frames':1}
        write_cache_atomic(p,{'labels':np.zeros(1,dtype=np.int8)},metadata,self.cap)
        original=json.loads((p/'cache.json').read_text())
        variants=[]
        for value in (True,1.0):
            bad=json.loads(json.dumps(original)); bad['metadata']['n_frames']=value; variants.append(bad)
            bad=json.loads(json.dumps(original)); bad['members']['labels']['shape']=[value]; variants.append(bad)
        for bad in variants:
            (p/'cache.json').write_bytes(canonical_json(bad))
            with patch('experiments.v3.cache.mmap.mmap') as mapping:
                with self.assertRaises(ValueError): verify_cache(p,metadata,self.cap)
                mapping.assert_not_called()

    def observation_fixture(self):
        from test_v3_corruption import invented
        from dataclasses import asdict
        from experiments.v3.cache import OBSERVATION_ARRAYS
        obs=invented(); metadata={**self.meta,'kind':'observations','n_frames':len(obs.frame_id),'n_slots':len(obs.slot_ids),
            'slot_ids':list(obs.slot_ids),'slot_ids_digest':obs.slot_ids_digest,'period_origins':[asdict(x) for x in obs.period_origins],
            'fps':obs.fps,'pitch':list(obs.pitch),'normalization_counts':{'coordinate_pairs':0}}
        return {name:getattr(obs,name) for name in OBSERVATION_ARRAYS},metadata

    def test_closed_observation_nested_wire(self):
        arrays,metadata=self.observation_fixture(); cases=[]
        for value in ('hha',{'h1':0,'h2':0,'a1':1},tuple(metadata['slot_ids'])):
            cases.append(('slot_ids',value))
        for value in (None,{}, {'coordinate_pairs':True},{'coordinate_pairs':-1},{'targets':[]},{'coordinate_pairs':0,'other':0},{'coordinate_pairs':1000000}):
            cases.append(('normalization_counts',value))
        cases += [('n_slots',3.0),('period_origins',tuple(metadata['period_origins'])),('pitch',[True,68.])]
        for key,value in cases:
            with self.subTest(key=key,value=value):
                bad={**metadata,key:value}
                with patch('experiments.v3.cache.ReadLease') as reads:
                    with self.assertRaises(ValueError): write_cache_atomic(self.root/'bad',arrays,bad,self.cap)
                    reads.assert_not_called()

    def test_actual_nested_origin_and_count_aliases_refused(self):
        arrays,metadata=self.observation_fixture(); p=self.root/'obs'; write_cache_atomic(p,arrays,metadata,self.cap)
        original=json.loads((p/'cache.json').read_text()); variants=[]
        for key,value in [('period_id',True),('source_frame_id',0.0),('utc_ns',0.0)]:
            bad=json.loads(json.dumps(original)); bad['metadata']['period_origins'][0][key]=value; variants.append(bad)
        bad=json.loads(json.dumps(original)); bad['metadata']['normalization_counts']['coordinate_pairs']=False; variants.append(bad)
        for bad in variants:
            (p/'cache.json').write_bytes(canonical_json(bad))
            with patch('experiments.v3.cache.mmap.mmap') as mapping:
                with self.assertRaises(ValueError): verify_cache(p,metadata,self.cap)
                mapping.assert_not_called()

    def test_closed_optional_feature_metadata_wire(self):
        from experiments.v3.cache import FEATURE_ARRAYS
        metadata={**self.meta,'kind':'features','fps':25.,'pitch':[105.,68.],'feature_names':list(FEATURE_ARRAYS),'feature_metadata':{}}
        arrays={name:np.zeros((4,2) if name in ('ball_xy','nearest','tracked_counts','collective_speed') else (4,),dtype=dtype) for name,dtype in FEATURE_ARRAYS.items()}
        arrays['ball_observed'][:]=True
        for i,value in enumerate((None,[],{'targets':[0,1]},{'unknown':0},{'v3_feature_transform':True},{'slots':True},{'ball_motion_offline':1},{'exported_speeds_used':True})):
            with self.subTest(metadata=value):
                with self.assertRaises(ValueError): write_cache_atomic(self.root/('bad-features-'+str(i)),arrays,{**metadata,'feature_metadata':value},self.cap)
        for value in ({},{'feature_version':'streaming-v1'},{'v3_feature_transform':'accepted-streaming-v1+noise-v2-local-linear-1.2s','ball_motion_offline':True}):
            p=self.root/('feature-'+str(len(list(self.root.iterdir()))))
            write_cache_atomic(p,arrays,{**metadata,'feature_metadata':value},self.cap)

    def test_private_extensions_case_insensitive(self):
        from experiments.v3.cache import _release_document
        release,original=invented_release(self.root)
        for suffix in ('.xml','.npy','.npz','.csv','.mp4','.pkl','.pickle'):
            for extension in (suffix,suffix.upper()):
                doc=json.loads(json.dumps(original)); name='invented-notice'+extension; data=b'invented forbidden extension'
                (self.root/name).write_bytes(data); doc['files'].append({'relative_path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'role':'notice'})
                doc['files'].sort(key=lambda x:x['relative_path']); doc['runtime_digest']=digest_json(doc['files']); release.write_bytes(canonical_json(doc))
                with self.assertRaises(ValueError): _release_document(release)

    def test_accepted_atd_loader_finalizer_cache_roundtrip_and_diagnostic_types(self):
        from possession_model.features import load_atd
        from experiments.v3.corruption import finalize_features
        from experiments.v3.cache import FEATURE_ARRAYS
        xml,raw=invented_atd(3); meta_path=self.root/'invented.xml'; raw_path=self.root/'invented.txt'
        meta_path.write_bytes(xml); raw_path.write_bytes(raw)
        prepared=finalize_features(load_atd(meta_path,raw_path,3))
        self.assertEqual(prepared.metadata['input_format'],'metrica-epts-normalized')
        self.assertIs(type(prepared.metadata['raw_records']),int); self.assertEqual(prepared.metadata['raw_records'],3)
        arrays={name:getattr(prepared,name) for name in FEATURE_ARRAYS}
        metadata={**self.meta,'kind':'features','n_frames':3,'fps':prepared.fps,'pitch':list(prepared.pitch),
                  'feature_names':list(FEATURE_ARRAYS),'feature_metadata':prepared.metadata}
        path=self.root/'atd-cache'; write_cache_atomic(path,arrays,metadata,self.cap)
        with verify_cache(path,metadata,self.cap) as lease:
            self.assertEqual(lease.manifest['metadata']['feature_metadata'],prepared.metadata)
            for name,value in arrays.items(): self.assertEqual(lease.arrays[name].tobytes(),value.tobytes())
        malformed=[{'input_format':True},{'input_format':'other'},{'raw_records':True},{'raw_records':3.0},
                   {'raw_records':0},{'raw_records':-1},{'raw_records':2},{'targets':[0]},
                   {'source':'sportec'},{'match_id':'invented'},{'blocks':[]},{'corruption':{}},{'unknown':1}]
        for i,diagnostics in enumerate(malformed):
            with self.subTest(diagnostics=diagnostics):
                with self.assertRaises(ValueError): write_cache_atomic(self.root/f'bad-atd-{i}',arrays,{**metadata,'feature_metadata':diagnostics},self.cap)
        # Diagnostics remain optional individually and collectively.
        for i,diagnostics in enumerate(({}, {'input_format':'metrica-epts-normalized'}, {'raw_records':3})):
            write_cache_atomic(self.root/f'optional-atd-{i}',arrays,{**metadata,'feature_metadata':diagnostics},self.cap)

class CachePublicationTests(unittest.TestCase):
    """Bounded retries of an invented cache's single atomic publication."""
    def setUp(self):
        scratch=Path('local/v3-cache-publication-repair/tests'); scratch.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(prefix='publication-',dir=scratch); self.root=Path(self.tmp.name)
        self.cap=AccessCapability('a'*64,'synthetic','train',('invented',),123,'time','b'*64)
        self.meta=dict(domain='study',kind='targets',fixture_id='invented',role='train',attempt_id='synthetic',study_digest='a'*64,source_digest='c'*64,protocol_digest='d'*64,dependency_digest='e'*64,environment_digest='f'*64,config_digest='0'*64,condition='clean',seeds={},n_frames=4)
        self.arrays={'labels':np.array([0,1,2,-1],dtype=np.int8)}
        self.spy=patch('experiments.v3.cache._assert_study_access'); self.spy.start()
        self.rename=Path.rename
    def tearDown(self): self.spy.stop(); self.tmp.cleanup()
    def error(self,code): return OSError(13,'invented publication failure',None,code)
    def write(self,name='cache'): return write_cache_atomic(self.root/name,self.arrays,self.meta,self.cap)
    def test_transient_windows_errors_publish_identical_numeric_cache(self):
        for code in (5,32,33):
            with self.subTest(winerror=code):
                name='cache-'+str(code); attempts=[]
                def rename(source,destination):
                    self.assertTrue(destination.with_name('.'+destination.name+'.writer-reservation').is_file())
                    attempts.append(source)
                    if len(attempts)<3: raise self.error(code)
                    return self.rename(source,destination)
                with patch.object(Path,'rename',rename),patch('experiments.v3.cache.time.sleep') as sleep:
                    document=self.write(name)
                self.assertEqual(len(attempts),3); self.assertEqual(len(set(attempts)),1)
                self.assertEqual(sleep.call_count,2)
                self.assertFalse((self.root/('.'+name+'.writer-reservation')).exists())
                with verify_cache(self.root/name,self.meta,self.cap) as lease:
                    self.assertEqual(lease.manifest,document)
                    self.assertEqual(lease.arrays['labels'].tobytes(),self.arrays['labels'].tobytes())
    def test_exhaustion_is_finite_and_preserves_verified_partial(self):
        clock=[0.0]; attempts=[]
        def rename(source,destination): attempts.append(source); raise self.error(32)
        def sleep(seconds): self.assertGreater(seconds,0); self.assertLessEqual(seconds,.02); clock[0]+=seconds
        with patch.object(Path,'rename',rename),patch('experiments.v3.cache.time.monotonic',side_effect=lambda:clock[0]),patch('experiments.v3.cache.time.sleep',side_effect=sleep):
            with self.assertRaises(OSError): self.write()
        self.assertEqual(len(attempts),50); self.assertLessEqual(clock[0],1.0)
        self.assertFalse((self.root/'cache').exists()); self.assertEqual(len(set(attempts)),1)
        with verify_cache(attempts[0],self.meta,self.cap) as lease:
            self.assertEqual(lease.arrays['labels'].tobytes(),self.arrays['labels'].tobytes())
    def test_deadline_refuses_without_another_rename(self):
        with patch.object(Path,'rename',side_effect=self.error(5)) as rename,patch('experiments.v3.cache.time.monotonic',side_effect=[0.0,1.001]),patch('experiments.v3.cache.time.sleep') as sleep:
            with self.assertRaises(OSError): self.write()
        self.assertEqual(rename.call_count,1); sleep.assert_not_called()
    def test_new_destination_is_never_accepted_or_overwritten(self):
        calls=[]
        def rename(source,destination):
            calls.append(source); destination.mkdir(); (destination/'foreign').write_bytes(b'invented owner')
            raise self.error(5)
        with patch.object(Path,'rename',rename),patch('experiments.v3.cache.time.sleep'):
            with self.assertRaises(FileExistsError): self.write()
        self.assertEqual(len(calls),1); self.assertEqual((self.root/'cache'/'foreign').read_bytes(),b'invented owner')
        self.assertTrue(calls[0].is_dir())
    def test_file_exists_and_unrelated_errors_are_not_retried(self):
        for error in (FileExistsError('invented destination'),self.error(2),self.error(87),PermissionError(13,'invented non-Windows denial')):
            with self.subTest(error=repr(error)):
                with patch.object(Path,'rename',side_effect=error) as rename,patch('experiments.v3.cache.time.sleep') as sleep:
                    with self.assertRaises(OSError): self.write('cache-'+str(id(error)))
                self.assertEqual(rename.call_count,1); sleep.assert_not_called()
    def test_replaced_staging_directory_is_refused_and_original_preserved(self):
        calls=[]; moved=self.root/'original-partial'
        def rename(source,destination):
            calls.append(source); self.rename(source,moved); source.mkdir()
            raise self.error(32)
        with patch.object(Path,'rename',rename),patch('experiments.v3.cache.time.sleep'):
            with self.assertRaises(ValueError): self.write()
        self.assertEqual(len(calls),1); self.assertFalse((self.root/'cache').exists())
        with verify_cache(moved,self.meta,self.cap) as lease:
            self.assertEqual(lease.arrays['labels'].tobytes(),self.arrays['labels'].tobytes())
    def test_replaced_staging_member_is_refused(self):
        calls=[]
        def rename(source,destination):
            calls.append(source); member=source/'labels.npy'; data=member.read_bytes()
            self.rename(member,self.root/'original-labels.npy'); member.write_bytes(data)
            raise self.error(33)
        with patch.object(Path,'rename',rename),patch('experiments.v3.cache.time.sleep'):
            with self.assertRaises(ValueError): self.write()
        self.assertEqual(len(calls),1); self.assertFalse((self.root/'cache').exists())
    def test_reparse_staging_or_destination_is_refused(self):
        for which in ('staging','destination'):
            with self.subTest(which=which):
                calls=[]; name='cache-'+which; moved=self.root/('original-'+which)
                def rename(source,destination):
                    calls.append(source)
                    if which=='staging':
                        self.rename(source,moved); source.symlink_to(moved.resolve(),target_is_directory=True)
                    else: destination.symlink_to(source.resolve(),target_is_directory=True)
                    raise self.error(5)
                try:
                    with patch.object(Path,'rename',rename),patch('experiments.v3.cache.time.sleep'):
                        with self.assertRaises(ValueError): self.write(name)
                except OSError as error:
                    if getattr(error,'winerror',None)==1314: self.skipTest('Windows symlink privilege unavailable')
                    raise
                self.assertEqual(len(calls),1)


if __name__=='__main__': unittest.main()
