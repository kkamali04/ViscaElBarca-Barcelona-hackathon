"""Synthetic export allowlist and immutable artifact checks."""
import hashlib
import copy
import io
import tempfile
from pathlib import Path
import unittest
import zipfile
import json
import subprocess
import sys
from unittest.mock import patch

from experiments.v3 import exporting
from experiments.v3 import cache


def toy_release(root):
    """Only invented weights/config; missing scientific modules stand in PRIVATELY.

    This is an integration fixture, never an actual v3 science/release artifact.
    """
    root.mkdir(parents=True,exist_ok=True)
    roles={name:'scientific' for name in cache.REQUIRED_SCIENTIFIC_PATHS}
    roles.update({name:'runtime' for name in cache.REQUIRED_RUNTIME_PATHS|exporting.REVIEW_PATHS})
    roles.update({name:'notice' for name in exporting.NOTICE_PATHS})
    for name,role in roles.items():
        source=Path(name)
        payload=source.read_bytes() if source.is_file() else b'"""Private synthetic package stand-in; no scientific acceptance."""\n'
        path=root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(payload)
    # The toy core verifies the wrapper prepared features before yielding a
    # known synthetic timeline. It is never created in project source modules.
    (root/'experiments/v3/core.py').write_text('''import numpy as np
def predict_codes(features,models,config,policy):
    assert features.metadata.get('v3_feature_transform') == 'accepted-streaming-v1+noise-v2-local-linear-1.2s'
    assert features.period_id.dtype == np.int16
    assert not features.ball_xy.flags.writeable
    result=np.full(features.n_frames,3,dtype=np.int8)
    result[features.period_id>0]=0
    for a,b in policy.forced_dead: result[a:b]=2
    return result
''',encoding='utf-8')
    def read_source(name):
        path=root/name
        if path.is_file(): return path.read_bytes()
        source=Path(name)
        if not source.is_file(): return None
        payload=source.read_bytes(); path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(payload)
        return payload
    roles.update({name:'scientific' for name in exporting.scientific_names(read_source)})
    candidate={'candidate_id':'A','alpha':0,'support':'none','transition_seconds':.5}
    emitter={'format':'numeric-hgb-v1','feature_names':['invented'],'baseline':[0,0,0],'trees':[]}
    for name,document,role in [('models/v3-emitter.json',emitter,'emitter'),('models/v3-candidate.json',candidate,'config')]:
        (root/name).parent.mkdir(parents=True,exist_ok=True); (root/name).write_bytes(cache.canonical_json(document)); roles[name]=role
    records=[{'relative_path':name,'bytes':(root/name).stat().st_size,'sha256':hashlib.sha256((root/name).read_bytes()).hexdigest(),'role':role}
             for name,role in sorted(roles.items())]
    policy={'kind':'challenge','forced_dead':[[110808,113742]]}
    document={'schema_version':1,'kind':'v3-observation-release','release_id':'synthetic-toy-only','files':records,
        'runtime_digest':cache.digest_json(records),'scientific_digest':cache.digest_json([r for r in records if r['role']=='scientific']),
        'policy':policy,'policy_digest':cache.digest_json(policy),'candidate':candidate,
        'models':{'emitter':'models/v3-emitter.json','head':None,'config':'models/v3-candidate.json'},
        'provenance':dict(study_digest='1'*64,model_seal_digest='2'*64,finalist_digest='3'*64,protocol_digest='4'*64)}
    path=root/'release.json'; path.write_bytes(cache.canonical_json(document)); return path


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='v3-t09-export-',dir=Path('local'))
        self.root=Path(self.temp.name).absolute()
    def tearDown(self): self.temp.cleanup()
    def test_reproducible_zip_and_no_replace(self):
        members={'README.md':b'invented','models/model.json':b'{}'}
        first=exporting.write_zip_once(self.root/'one.zip',members)
        second=exporting.write_zip_once(self.root/'two.zip',members)
        self.assertEqual(first['sha256'],second['sha256'])
        self.assertEqual(set(zipfile.ZipFile(self.root/'one.zip').namelist()),set(members))
        with self.assertRaises((ValueError,FileExistsError)): exporting.write_zip_once(self.root/'one.zip',members)
    def test_unsafe_members_and_size_limit(self):
        for name in ('../secret','/absolute','a\\b','NUL.json','a:stream','a./file','A/../b'):
            with self.subTest(name=name),self.assertRaises(ValueError): exporting.write_zip_once(self.root/'bad.zip',{name:b'x'})
        with self.assertRaises(ValueError): exporting.write_zip_once(self.root/'bad.zip',{'a':b'x','A':b'x'})
    def test_build_missing_gate_fails_before_models(self):
        finalist=self.root/'finalist.json'; finalist.write_text('{}')
        with self.assertRaises(ValueError): exporting.build_release(finalist,self.root/'bad.zip',self.root)
        self.assertFalse((self.root/'bad.zip').exists())
    def test_toy_code_roundtrip_exact_allowlist_and_exclusion(self):
        release=toy_release(self.root/'package')
        (release.parent/'private.csv').write_bytes(b'invented but must never be exported')
        one=exporting.export_release(release,self.root/'one.zip')
        two=exporting.export_release(release,self.root/'two.zip')
        self.assertEqual(one['sha256'],two['sha256'])
        with cache.ReadLease(self.root/'one.zip') as held:
            doc,digest=exporting.verify_code_zip(held,release)
            self.assertEqual(doc['release_id'],'synthetic-toy-only')
        with zipfile.ZipFile(self.root/'one.zip') as archive:
            self.assertNotIn('private.csv',archive.namelist())
            self.assertIn('experiments/v3/TECHNICAL.md',archive.namelist())
            self.assertIn('more-than-a-hack-2027-main/LICENSE',archive.namelist())
            self.assertIn('tools/fetch_validation_data.py',archive.namelist())
            self.assertFalse(any(name.endswith(('.csv','.npy','.xml','.npz','.mp4')) for name in archive.namelist()))
            extracted=self.root/'extracted'; archive.extractall(extracted)
        imported=subprocess.run([sys.executable,'-c','import experiments.v3.runner, experiments.v3.review, experiments.v3.exporting, experiments.v3.promotion, tools.train_and_validate, tools.run_candidate'],
                                cwd=extracted,capture_output=True,timeout=30)
        self.assertEqual(imported.returncode,0,imported.stderr.decode())
        changed=json.loads(release.read_bytes())
        changed['files']=[item for item in changed['files'] if item['relative_path']!='tools/fetch_validation_data.py']
        changed['runtime_digest']=cache.digest_json(changed['files'])
        changed['scientific_digest']=cache.digest_json([item for item in changed['files'] if item['role']=='scientific'])
        release.write_bytes(cache.canonical_json(changed))
        with self.assertRaises(ValueError): exporting.export_release(release,self.root/'missing-helper.zip')
    def test_science_evidence_needs_matching_independent_and_root(self):
        from contextlib import ExitStack
        identities={key:('a'*64) for key in exporting.AUTH_IDENTITIES}
        records={}
        for role in ('independent_report','root_reproduction'):
            evidence={'schema_version':1,'scope':'G07 scientific acceptance','gate_passed':True,
                      **{key:identities[key] for key in ('study_digest','finalist_digest','test_result_digest')}}
            evidence.update({'verdict':'PASS_BOUNDED'} if role=='independent_report' else {'root_verified':True})
            payload=cache.canonical_json(evidence); (self.root/(role+'.json')).write_bytes(payload)
            records[role]={'relative_path':role+'.json','bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
        science={'schema_version':1,'kind':'v3-scientific-acceptance','gate_passed':True,**identities,**records}
        with ExitStack() as stack: exporting.verify_science_receipt(stack,self.root,science,identities)
        for key,value in [('gate_passed',1),('schema_version',True),('extra','unknown')]:
            with ExitStack() as stack,self.assertRaises(ValueError):
                exporting.verify_science_receipt(stack,self.root,{**science,key:value},identities)
    def test_promotion_requires_exact_gates_hashes_and_fallback29(self):
        from experiments.v3 import guard,promotion
        release=toy_release(self.root/'package')
        doc=json.loads(release.read_bytes()); release_digest=hashlib.sha256(release.read_bytes()).hexdigest()
        (self.root/'local/v3-releases').mkdir(parents=True)
        zip_result=exporting.export_release(release,self.root/'code.zip')
        fallback_records={}
        for index in range(29):
            name=f'fallback/file-{index}.bin'; path=self.root/name; path.parent.mkdir(exist_ok=True)
            data=f'invented original {index}'.encode(); path.write_bytes(data)
            fallback_records[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        def write(name,value):
            payload=cache.canonical_json(value); path=self.root/name; path.write_bytes(payload)
            return {'relative_path':name,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
        fallback=write('fallback.json',{'files':fallback_records})
        identities={**doc['provenance'],'scientific_closure_digest':'5'*64,'comparator_digest':fallback['sha256'],'test_result_digest':'6'*64}
        evidence={k:identities[k] for k in ('study_digest','finalist_digest','test_result_digest')}
        independent=write('independent.json',{'schema_version':1,'scope':'G07 scientific acceptance','verdict':'PASS_BOUNDED','gate_passed':True,**evidence})
        reproduced=write('reproduced.json',{'schema_version':1,'scope':'G07 scientific acceptance','root_verified':True,'gate_passed':True,**evidence})
        science=write('science.json',{'schema_version':1,'kind':'v3-scientific-acceptance','gate_passed':True,
                    **identities,'independent_report':independent,'root_reproduction':reproduced})
        acceptance={'schema_version':1,'scope':'G08 exact-package acceptance','verdict':'PASS_BOUNDED','actual_evidence':True,
                    'release_id':doc['release_id'],'release_digest':release_digest,'science_receipt_digest':science['sha256'],
                    'code_zip':{'relative_path':'code.zip','bytes':zip_result['bytes'],'sha256':zip_result['sha256']},
                    'gates':dict.fromkeys(promotion.G08_GATES,True)}
        accepted=write('accepted.json',acceptance)
        root={'schema_version':1,'scope':'G08 root verification','root_verified':True,'release_digest':release_digest,
              'science_receipt_digest':science['sha256'],'acceptance_digest':accepted['sha256'],
              'code_zip_sha256':zip_result['sha256'],'fallback':fallback}
        write('root.json',root)
        args=[release,self.root/'science.json',self.root/'accepted.json',self.root/'root.json']
        with patch.object(guard,'ROOT',self.root):
            receipt=self.root/'local/v3-releases/promoted.json'
            result=promotion.promote(*args,receipt)
            self.assertEqual(result['fallback_files_verified'],29)
            self.assertFalse(result['accepted_default_modified']); self.assertFalse(result['submitted'])
            with self.assertRaises(ValueError): promotion.promote(*args,receipt)
            (self.root/'fallback/file-0.bin').write_bytes(b'changed')
            with self.assertRaises(ValueError): promotion.promote(*args,receipt.with_name('bad.json'))
            self.assertFalse(receipt.with_name('bad.json').exists())
            acceptance['gates']['resource_budget']=1
            accepted=write('accepted.json',acceptance); root['acceptance_digest']=accepted['sha256']; write('root.json',root)
            with self.assertRaises(ValueError): promotion.promote(*args,receipt.with_name('bool-bad.json'))
    def test_authorized_toy_package_selective_models_and_directory_commit(self):
        """Transport integration with guard services mocked, not guard acceptance."""
        from experiments.v3 import guard,evaluate
        from experiments.v3.contracts import AccessCapability
        root=self.root/'transport'; original=toy_release(root)
        original_doc=json.loads(original.read_bytes())
        study=root/'local/v3-studies/invented'; (study/'models').mkdir(parents=True)
        (study/'test').mkdir(); (study/'selection').mkdir(); (study/'release').mkdir(); (root/'local/v3-releases').mkdir()
        def write(path,doc):
            payload=cache.canonical_json(doc); path.write_bytes(payload)
            return hashlib.sha256(payload).hexdigest()
        model=b'{"format":"numeric-hgb-v1","feature_names":["invented"],"baseline":[0,0,0],"trees":[]}'
        model_records=[]
        for name in ('C0','C1','boundary'):
            (study/f'models/{name}.json').write_bytes(model)
            parity=study/f'models/{name}-parity.json'
            digest=write(parity,{'synthetic_only':True,'max_raw_error':0.})
            model_records.append({'name':name,'relative_path':f'models/{name}.json','bytes':len(model),
                'sha256':hashlib.sha256(model).hexdigest(),'parity_receipt':{
                    'relative_path':f'models/{name}-parity.json','bytes':parity.stat().st_size,'sha256':digest}})
        seal={'models':model_records}
        seal_digest=write(study/'models/models.json',seal)
        value={'study_id':'invented','protocol_digest':'a'*64,'scientific_closure_digest':'b'*64,'comparator_digest':'c'*64,
               'catalog_digest':'d'*64,'environment_digest':'e'*64,
               'artifact_bindings':[{k:r[k] for k in ('relative_path','bytes','sha256')} for r in original_doc['files']]}
        study_digest=write(study/'study.json',value)
        selection_digest=write(study/'selection/result.json',{'synthetic_only':True,'status':'complete','eligible':True})
        finalist={'candidate_id':'C0','config':{'id':'C0','emitter':'C0','alpha':0,'support':'none'},
                  'selection_receipt_digest':selection_digest}
        final_digest=write(study/'finalist.json',finalist)
        protocol=json.loads((root/'specs/003-possession-improvements/protocol.json').read_bytes())
        fixtures=tuple(protocol['split']['test'])
        cap=AccessCapability(study_digest,'invented-attempt','test',fixtures,0,'invented','f'*64)
        rows=[]; inputs=[]
        for fixture in fixtures:
            for condition in evaluate.CONDITION_IDS:
                inputs.append({'fixture_id':fixture,'condition':condition,
                    'observation_digest':hashlib.sha256((fixture+condition).encode()).hexdigest(),
                    'target_digest':hashlib.sha256(fixture.encode()).hexdigest(),
                    'corruption':{'invented_metadata_only':True}})
                for candidate,score in (('A',.2),('C0',.7)):
                    rows.append({'fixture_id':fixture,'condition':condition,'candidate_id':candidate,
                        'metrics':dict.fromkeys(evaluate.METRIC_KEYS,score),
                        'prediction_digest':hashlib.sha256((fixture+condition+candidate).encode()).hexdigest()})
        # Run the actual producer and production paired gate, with disclosed
        # metadata/admission and invented aggregate-grid stubs. No raw inputs,
        # fitted models, inference, worker Job or real science is asserted here.
        with patch.object(evaluate,'_admit',return_value=(study/'study.json',value,protocol)),\
                patch.object(guard,'_validate_finalist'),patch.object(evaluate,'load_bundles',return_value={}),\
                patch.object(evaluate,'_evaluate_grid',return_value=(rows,inputs)),\
                patch.object(guard,'load_model_seal',return_value=seal):
            evaluate.run_final_test(study/'study.json',study/'finalist.json',cap,study/'test/result.json')
        result_doc=json.loads((study/'test/result.json').read_bytes())
        self.assertEqual(len(result_doc['rows']),24); self.assertEqual(len(result_doc['inputs']),12)
        self.assertNotIn('model_seal_digest',result_doc)
        def authorize_result(document):
            test_digest=write(study/'test/result.json',document)
            identities={'study_digest':study_digest,'finalist_digest':final_digest,'model_seal_digest':seal_digest,
                        'protocol_digest':'a'*64,'scientific_closure_digest':'b'*64,'comparator_digest':'c'*64,'test_result_digest':test_digest}
            records={}
            for role in ('independent_report','root_reproduction'):
                report={'schema_version':1,'scope':'G07 scientific acceptance','gate_passed':True,
                        **{k:identities[k] for k in ('study_digest','finalist_digest','test_result_digest')}}
                report.update({'verdict':'PASS_BOUNDED'} if role=='independent_report' else {'root_verified':True})
                path=study/'release'/(role+'.json'); digest=write(path,report)
                records[role]={'relative_path':path.relative_to(root).as_posix(),'bytes':path.stat().st_size,'sha256':digest}
            science=study/'release/science.json'
            science_digest=write(science,{'schema_version':1,'kind':'v3-scientific-acceptance','gate_passed':True,**identities,**records})
            authorization={'schema_version':1,'kind':'v3-export-authorization','allow_export':True,**identities,
                'g07_receipt_digest':science_digest,'study_path':(study/'study.json').relative_to(root).as_posix(),
                'finalist_path':(study/'finalist.json').relative_to(root).as_posix(),
                'model_seal_path':(study/'models/models.json').relative_to(root).as_posix(),
                'test_result_path':(study/'test/result.json').relative_to(root).as_posix(),
                'g07_receipt_path':science.relative_to(root).as_posix()}
            write(study/'release/export-authorization.json',authorization)
        authorize_result(result_doc)
        with patch.object(guard,'ROOT',root),patch.object(guard,'load_registered_study',return_value=value) as verify_study,\
                patch.object(guard,'load_model_seal',return_value=seal),patch.object(guard,'_validate_finalist') as verify_finalist:
            destination=root/'local/v3-releases/invented-release'
            result=exporting.build_release(study/'finalist.json',destination,root)
            verify_study.assert_called_once(); verify_finalist.assert_called_once()
            released=json.loads((destination/'release.json').read_bytes())
            self.assertEqual(released['candidate']['candidate_id'],'C0')
            self.assertIsNone(released['models']['head'])
            self.assertFalse(any('export-authorization' in record['relative_path'] for record in released['files']))
            archive=exporting.export_release(destination/'release.json',root/'verified.zip')
            self.assertEqual(archive['sha256'],result['code_zip_sha256'])
            with self.assertRaises(ValueError): exporting.build_release(study/'finalist.json',destination,root)
            invalid=[]
            for key,bad in (('bytes',True),('bytes',result_doc['artifacts'][0]['bytes']+1),
                            ('sha256','0'*64),('sha256',None),('relative_path','../models/models.json'),
                            ('relative_path','models/foreign.json'),('relative_path',['models/models.json']),
                            ('relative_path','MODELS/models.json'),('extra','unknown')):
                changed=copy.deepcopy(result_doc); changed['artifacts'][0][key]=bad
                invalid.append((f'seal-{key}-{len(invalid)}',changed))
            for name,change in (
                ('missing-seal',lambda d:d['artifacts'].pop(0)),
                ('duplicate-seal',lambda d:d['artifacts'].append(copy.deepcopy(d['artifacts'][0]))),
                ('missing-parity',lambda d:d['artifacts'].pop(-2)),
                ('missing-record-key',lambda d:d['artifacts'][0].pop('bytes'))):
                changed=copy.deepcopy(result_doc); change(changed); changed['artifact_count']=len(changed['artifacts'])
                invalid.append((name,changed))
            for key,bad in (('artifact_count',True),('artifact_count',1),('artifacts',{}),
                            ('gate_passed',False),('gate_passed',1),('sealed',False),('sealed',1),
                            ('verdict',{'gate_passed':False}),('verdict',{'gate_passed':1}),('verdict',None),
                            ('status','failed'),('role','selection'),('candidate_id','C1'),
                            ('study_digest','0'*64),('finalist_digest','0'*64),('catalog_digest','0'*64),
                            ('environment_digest','0'*64),('protocol_digest','0'*64),
                            ('scientific_closure_digest','0'*64),('comparator_digest','0'*64)):
                invalid.append((key,dict(result_doc,**{key:bad})))
            legacy=copy.deepcopy(result_doc); legacy['model_seal_digest']=seal_digest
            legacy['artifacts'].pop(0); legacy['artifact_count']=len(legacy['artifacts'])
            invalid.append(('untrusted-top-level-seal-cannot-replace-artifact',legacy))
            for key in ('fixture_ids','fixture_count','attempt_id','N','condition_count','candidate_count','rows','inputs','limitations'):
                changed=copy.deepcopy(result_doc); changed.pop(key)
                invalid.append(('missing-'+key,changed))
            for key in ('fixture_count','N','condition_count','candidate_count'):
                for bad in (True,float(result_doc[key]),str(result_doc[key]),0):
                    invalid.append((f'native-{key}-{bad!r}',dict(result_doc,**{key:bad})))
            for key,bad in (('attempt_id',''),('attempt_id',' '),('attempt_id',True),
                            ('fixture_ids',list(reversed(fixtures))),('fixture_ids',['foreign']),
                            ('fixture_ids',{}),('rows',[]),('rows',{}),('inputs',[]),('inputs',{})):
                invalid.append(('complete-'+key,dict(result_doc,**{key:bad})))
            for name,change in (
                ('row-duplicate',lambda d:d['rows'].__setitem__(-1,copy.deepcopy(d['rows'][0]))),
                ('row-missing',lambda d:d['rows'].pop()),
                ('row-foreign-fixture',lambda d:d['rows'][0].__setitem__('fixture_id','foreign')),
                ('row-foreign-candidate',lambda d:d['rows'][0].__setitem__('candidate_id','C1')),
                ('row-foreign-condition',lambda d:d['rows'][0].__setitem__('condition','foreign')),
                ('row-prediction-type',lambda d:d['rows'][0].__setitem__('prediction_digest',True)),
                ('row-metric-bool',lambda d:d['rows'][0]['metrics'].__setitem__('spell_f1_mean',True)),
                ('row-metric-missing',lambda d:d['rows'][0]['metrics'].pop('spell_f1_mean')),
                ('verdict-failed-check',lambda d:d['verdict']['checks'].__setitem__('each_match_primary',False)),
                ('verdict-nonnative-check',lambda d:d['verdict']['checks'].__setitem__('each_match_primary',1)),
                ('verdict-score',lambda d:d['verdict'].__setitem__('primary_score',.1)),
                ('verdict-count',lambda d:d['verdict'].__setitem__('N',2.0)),
                ('input-duplicate',lambda d:d['inputs'].__setitem__(-1,copy.deepcopy(d['inputs'][0]))),
                ('input-foreign-fixture',lambda d:d['inputs'][0].__setitem__('fixture_id','foreign')),
                ('input-foreign-condition',lambda d:d['inputs'][0].__setitem__('condition','foreign')),
                ('input-digest-type',lambda d:d['inputs'][0].__setitem__('observation_digest',1)),
                ('input-digest-noncanonical',lambda d:d['inputs'][0].__setitem__('observation_digest','F'*64)),
                ('input-target-conflict',lambda d:d['inputs'][0].__setitem__('target_digest','0'*64)),
                ('input-missing-key',lambda d:d['inputs'][0].pop('target_digest')),
                ('input-corruption-type',lambda d:d['inputs'][0].__setitem__('corruption',[]))):
                changed=copy.deepcopy(result_doc); change(changed); invalid.append((name,changed))
            originals={p:p.read_bytes() for p in [study/'study.json',study/'models/models.json',study/'finalist.json']}
            for index,(name,document) in enumerate(invalid):
                with self.subTest(lineage=name):
                    authorize_result(document)
                    rejected=root/f'local/v3-releases/rejected-{index}'
                    with self.assertRaises(ValueError): exporting.build_release(study/'finalist.json',rejected,root)
                    self.assertFalse(rejected.exists())
                    self.assertFalse(any(rejected.parent.glob('.partial-v3-package-*')))
                    self.assertTrue(all(path.read_bytes()==payload for path,payload in originals.items()))
            # Grid/manifest membership has no normative list-order constraint.
            from contextlib import ExitStack
            permuted=copy.deepcopy(result_doc)
            for key in ('rows','inputs','artifacts'): permuted[key].reverse()
            authorize_result(permuted)
            with ExitStack() as stack: exporting._authorize_export(stack,study/'finalist.json',root)


if __name__=='__main__': unittest.main()
