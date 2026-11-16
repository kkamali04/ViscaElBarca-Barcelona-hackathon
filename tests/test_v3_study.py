import unittest
from unittest import mock
from dataclasses import replace
from pathlib import Path
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import numpy as np
from experiments.v3 import guard
from experiments.v3.core import candidate_config, predict_codes, CANDIDATES, TRANSFORM
from experiments.v3.contracts import ModelBundle, InferencePolicy, CandidateConfig, AccessCapability
from experiments.v3.corruption import finalize_features
from possession_model.schema import FeatureSet
from possession_model.evidence import feature_matrix
from possession_model.trees import TreeModel
from possession_model.decoder import decode_scores
from experiments.v3.boundary import NumericHead, BOUNDARY_NAMES
from experiments.v3.evaluate import choose_finalist, paired_gate, METRIC_KEYS, CONDITION_IDS
from test_v3_training import synthetic_provenance

ROOT=Path(__file__).resolve().parents[1]


def scratch(prefix):
    parent=ROOT/'local/v3-t05-integrator'; parent.mkdir(parents=True,exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix,dir=parent))


def prepared_features(n=120):
    p=np.ones(n,np.int16); p[n//2:]=2
    ball=np.column_stack((40+np.arange(n)*.001,np.full(n,30.))).astype(np.float32)
    base=FeatureSet(25.,(105.,68.),p,ball,np.ones(n,bool),
        np.tile(np.array([1.,5.],np.float32),(n,1)),np.full((n,2),4,np.int16),
        np.ones((n,2),np.float32),np.full(n,.1,np.float32),{})
    return finalize_features(base)


def constant_model(features,baseline=(0.,-2.,-3.)):
    _,names,_=feature_matrix(features)
    return TreeModel(dict(format='numeric-hgb-v1',feature_names=names,baseline=list(baseline),trees=[],provenance={}))


def constant_head():
    nodes=dict(value=[0.],feature_idx=[0],num_threshold=[0.],missing_go_to_left=[0],left=[0],right=[0],is_leaf=[1])
    return NumericHead(dict(format='numeric-boundary-hgb-v1',class_names=['NONE','TEAM_CHANGE','LIVE_DEAD'],
        feature_names=list(BOUNDARY_NAMES),baseline=[0.,0.,0.],trees=[dict(**{'class':k},nodes=copy.deepcopy(nodes)) for k in range(3)],
        provenance=synthetic_provenance('boundary')))


def aggregate_rows(fixtures=('J03WPY',),names=tuple(r[0] for r in CANDIDATES),gain=.1):
    return [dict(fixture_id=f,condition=c,candidate_id=name,
        metrics={k:.4+(0 if name=='A' else gain) for k in METRIC_KEYS})
        for f in fixtures for c in CONDITION_IDS for name in names]


class StudyTests(unittest.TestCase):
    def test_exact_candidates(self):
        names = ('A','F080','B080','C0','C1','D0050','D0080','D1050','D1080')
        for name in names:
            self.assertEqual(candidate_config(name).candidate_id, name)
        with self.assertRaises(ValueError): candidate_config('B050')

    def test_core_alpha_zero_matches_accepted_decoder(self):
        f=prepared_features(); m=constant_model(f); matrix,names,_=feature_matrix(f)
        costs=np.full((3,3),12.5); np.fill_diagonal(costs,0.)
        expected=decode_scores(m.scores(matrix,names),f.period_id,costs); expected[expected<0]=3
        before=hashlib.sha256(f.ball_speed.tobytes()).hexdigest()
        actual=predict_codes(f,ModelBundle(m,None,'a'*64),candidate_config('A'),InferencePolicy('external',()))
        np.testing.assert_array_equal(actual,expected)
        self.assertEqual(before,hashlib.sha256(f.ball_speed.tobytes()).hexdigest())

    def test_core_requires_single_transform_and_exact_config(self):
        f=prepared_features(); m=ModelBundle(constant_model(f),None,'a'*64)
        with self.assertRaises(ValueError): finalize_features(f)
        unmarked=replace(f,metadata={})
        with self.assertRaises(ValueError): predict_codes(unmarked,m,candidate_config('A'),InferencePolicy('external',()))
        with self.assertRaises(ValueError): predict_codes(f,m,CandidateConfig('A',False,'none',.5),InferencePolicy('external',()))
        with self.assertRaises(ValueError): predict_codes(f,m,candidate_config('A'),InferencePolicy('external',((1,2),)))

    def test_boundary_and_flattened_use_exact_bundle(self):
        f=prepared_features(); model=constant_model(f); head=constant_head()
        bundle=ModelBundle(model,head,'a'*64)
        for name in ('B080','F080','D0050','D0080','D1050','D1080'):
            a=predict_codes(f,bundle,candidate_config(name),InferencePolicy('external',()))
            b=predict_codes(f,bundle,candidate_config(name),InferencePolicy('external',()))
            np.testing.assert_array_equal(a,b)
        with self.assertRaises(ValueError): predict_codes(f,ModelBundle(model,None,'a'*64),candidate_config('F080'),InferencePolicy('external',()))

    def test_selection_grid_tie_and_complete_denominators(self):
        winner,evidence=choose_finalist(aggregate_rows())
        self.assertEqual(winner,'B080')
        self.assertEqual(len(evidence),8)
        self.assertTrue(all(e['gate_passed'] for e in evidence.values()))
        rows=aggregate_rows(); rows.pop()
        with self.assertRaises(ValueError): choose_finalist(rows)
        rows=aggregate_rows(); rows[-1]=rows[0]
        with self.assertRaises(ValueError): choose_finalist(rows)

    def test_gate_epsilon_and_clean_veto(self):
        rows=aggregate_rows(names=('A','C0'),gain=.04-5e-13)
        self.assertTrue(paired_gate(rows,('J03WPY',),'C0')['gate_passed'])
        rows=aggregate_rows(names=('A','C0'),gain=.04-2e-12)
        self.assertFalse(paired_gate(rows,('J03WPY',),'C0')['gate_passed'])
        rows=aggregate_rows(fixtures=('J03WN1','J03WQQ'),names=('A','C0'))
        for row in rows:
            if row['candidate_id']=='C0' and row['condition']=='clean': row['metrics']['spell_f1_mean']=.38
        verdict=paired_gate(rows,('J03WN1','J03WQQ'),'C0')
        self.assertFalse(verdict['gate_passed']); self.assertFalse(verdict['checks']['mean_clean_spell'])

    def test_absent_nonfinite_metric_or_undeclared_condition_refused(self):
        for bad in (float('nan'),float('inf'),True,-.01,1.1,None):
            rows=aggregate_rows(); rows[0]['metrics']['spell_f1_mean']=bad
            with self.assertRaises(ValueError): choose_finalist(rows)

    def test_stdlib_cli_import_has_no_numpy_or_guard(self):
        code="import sys; import experiments.v3.cli; assert 'numpy' not in sys.modules; assert 'experiments.v3.guard' not in sys.modules"
        result=subprocess.run([str(ROOT/'.venv/Scripts/python.exe'),'-c',code],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_test_result_requires_exact_gate_boolean(self):
        from experiments.v3.cli import validate_stage_result
        root=scratch('result-bool-'); study=root/'study.json'; study.write_text('{}')
        cap=AccessCapability('a'*64,'invented','test',('J03WN1','J03WQQ'),os.getpid(),guard.process_creation_time(),'b'*64)
        for flag in (None,0,1,'true'):
            path=root/('result-'+str(flag)+'.json')
            path.write_text(json.dumps(dict(schema_version=1,study_digest=cap.study_digest,attempt_id=cap.attempt_id,
                                           status='complete',gate_passed=flag)))
            with self.assertRaises(guard.IntegrityError): validate_stage_result(study,cap,path)

    def test_first_fit_missing_budget_cannot_reserve(self):
        from experiments.v3 import cli,resources
        root=scratch('missing-budget-'); protocol=ROOT/'specs/003-possession-improvements/protocol.json'
        args=type('Args',(),dict(command='fit',study=root/'study.json'))()
        args.study.write_text('{}')
        value={'artifact_bindings':[{'relative_path':protocol.as_posix()}]}
        with mock.patch.object(guard,'ROOT',root),mock.patch.object(Path,'cwd',return_value=root),mock.patch.object(guard,'load_registered_study',return_value=value),\
             mock.patch.object(guard,'_config',return_value={}),mock.patch.object(guard,'reserve_attempt') as reserve:
            with self.assertRaises((FileNotFoundError,resources.ResourceError)): cli._study_command(args)
            reserve.assert_not_called()

    def test_preflight_and_ready_precede_reservation_owner_finishes(self):
        from experiments.v3 import cli,resources
        root=scratch('lifecycle-'); study=root/'study.json'; study.write_text('{}'); events=[]
        cap=AccessCapability('a'*64,'invented','test',('J03WN1','J03WQQ'),os.getpid(),guard.process_creation_time(),'b'*64)
        value={'artifact_bindings':[{'relative_path':'specs/protocol.json'}]}
        class Worker:
            def __enter__(self): events.append('ready'); return self
            def __exit__(self,*exc): events.append('closed')
            def authorize(self,owner_cap,result_path): self.assert_cap=owner_cap; events.append('authorized')
            def wait(self):
                events.append('waited')
                return dict(exit_code=0,termination_reason=None,sampling_errors=[],gaps_over_50ms=0,
                    sample_count=2,worker_peak_working_set_bytes=100,sampled_job_peak_working_set_bytes=200,wall_seconds=.1)
        def preflight(*a): events.append('preflight'); return {}
        def reserve(*a): events.append('reserved'); return cap
        def finish(*a): events.append('finished'); self.assertIs(a[0],cap)
        args=type('Args',(),dict(command='test',study=study))()
        with mock.patch.object(guard,'ROOT',root),mock.patch.object(Path,'cwd',return_value=root),mock.patch.object(guard,'load_registered_study',return_value=value),\
             mock.patch.object(guard,'_config',return_value={'split':{'test':['J03WN1','J03WQQ']}}),\
             mock.patch.object(cli,'_module'),mock.patch.object(resources,'policy_from_protocol',return_value={}),\
             mock.patch.object(resources,'load_budget',return_value={}),mock.patch.object(resources,'resource_preflight',side_effect=preflight),\
             mock.patch.object(resources,'prepare_worker',return_value=Worker()),mock.patch.object(guard,'reserve_attempt',side_effect=reserve),\
             mock.patch.object(cli,'validate_stage_result',return_value=4),mock.patch.object(guard,'finish_attempt',side_effect=finish):
            self.assertEqual(cli._study_command(args)['exit_code'],4)
        self.assertEqual(events,['preflight','ready','reserved','authorized','waited','finished','closed'])

    def test_preflight_failure_consumes_no_cohort(self):
        from experiments.v3 import cli,resources
        root=scratch('preflight-fail-'); study=root/'study.json'; study.write_text('{}')
        value={'artifact_bindings':[{'relative_path':'specs/protocol.json'}]}
        args=type('Args',(),dict(command='select',study=study))()
        with mock.patch.object(guard,'ROOT',root),mock.patch.object(Path,'cwd',return_value=root),mock.patch.object(guard,'load_registered_study',return_value=value),\
             mock.patch.object(guard,'_config',return_value={}),mock.patch.object(cli,'_module'),\
             mock.patch.object(resources,'policy_from_protocol',return_value={}),mock.patch.object(resources,'load_budget',return_value={}),\
             mock.patch.object(resources,'resource_preflight',side_effect=resources.ResourceError('invented failure')),\
             mock.patch.object(guard,'reserve_attempt') as reserve:
            with self.assertRaises(resources.ResourceError): cli._study_command(args)
            reserve.assert_not_called()

    def test_resource_baseline_never_initialized_after_raw_acquisition(self):
        from experiments.v3 import cli,resources
        root=scratch('raw-before-budget-'); raw=root/'local/v3-data/originals'; raw.mkdir(parents=True)
        (raw/'invented.xml').write_text('<synthetic/>')
        with mock.patch.object(guard,'ROOT',root),mock.patch.object(resources,'initialize_budget') as initialize:
            with self.assertRaises(guard.IntegrityError): cli._initialize_budget_before_registration()
            initialize.assert_not_called()

    def test_fetch_exact_forecast_admitted_before_acquisition(self):
        from experiments.v3 import cli,resources
        root=scratch('fetch-admission-'); study=root/'study.json'; study.write_text('{}'); events=[]
        value={'artifact_bindings':[{'relative_path':'specs/protocol.json'}],
            'catalog_path':str(root/'catalog.json'),'raw_root':str(root/'raw')}
        catalog={'fixtures':{'J03WOH':{'metadata':{'bytes':11,'relative_path':'m.xml'},
            'tracking':{'bytes':29,'relative_path':'t.xml'}}}}
        args=type('Args',(),dict(command='fetch',study=study,fixtures=['J03WOH']))()
        module=mock.Mock(); module.fetch_registered_sources.side_effect=lambda *a: events.append(('fetch',)) or 'receipt'
        with mock.patch.object(guard,'ROOT',root),mock.patch.object(Path,'cwd',return_value=root),mock.patch.object(guard,'load_registered_study',return_value=value),\
             mock.patch.object(guard,'_config',return_value={'split':{'train':['J03WOH'],'selection':[],'test':[]}}),\
             mock.patch.object(guard,'read_json',return_value=catalog),mock.patch.object(cli,'_module',return_value=module),\
             mock.patch.object(resources,'policy_from_protocol',return_value={}),mock.patch.object(resources,'load_budget',return_value={}),\
             mock.patch.object(resources,'check_time',side_effect=lambda *a:events.append(('time',))),\
             mock.patch.object(resources,'check_disk',side_effect=lambda *a,**kw:events.append(('disk',kw.get('forecast_bytes',0)))):
            self.assertEqual(cli._study_command(args),'receipt')
        self.assertEqual(events,[('time',),('disk',40),('fetch',),('time',),('disk',0)])

    def test_package_uses_canonical_study_finalist_and_absent_release(self):
        from experiments.v3 import cli
        root=scratch('package-alias-'); study=root/'study.json'; study.write_text('{}')
        args=type('Args',(),dict(command='package',study=study))()
        module=mock.Mock()
        with mock.patch.object(guard,'ROOT',root),mock.patch.object(guard,'load_registered_study',return_value={'study_id':'invented'}),\
             mock.patch.object(cli,'_module',return_value=module):
            cli.dispatch(args)
        module.build_release.assert_called_once_with(root/'finalist.json',root/'local/v3-releases/invented',root)

    def test_complete_test_true_and_false_exit_codes(self):
        from experiments.v3.cli import validate_stage_result
        from experiments.v3.training import result_envelope, RESULT_BINDINGS
        root=scratch('test-verdict-'); study=root/'study.json'; study.write_text('{}')
        final=root/'finalist.json'; final.write_text(json.dumps({'candidate_id':'C0'}))
        cap=AccessCapability('a'*64,'invented','test',('J03WN1','J03WQQ'),os.getpid(),guard.process_creation_time(),'b'*64)
        value={key:'c'*64 for key in RESULT_BINDINGS}
        artifacts=[root/'models/models.json',root/'selection/result.json']
        for artifact in artifacts:
            artifact.parent.mkdir(parents=True,exist_ok=True); artifact.write_text('{}')
        for gain,expected in ((.1,0),(.0,4)):
            rows=aggregate_rows(cap.fixture_ids,('A','C0'),gain)
            verdict=paired_gate(rows,cap.fixture_ids,'C0'); path=root/('result-'+str(gain)+'.json')
            path.write_text(json.dumps(dict(**result_envelope(study,cap,value,artifacts),
                candidate_id='C0',finalist_digest=guard.sha256(final),rows=rows,verdict=verdict,
                gate_passed=verdict['gate_passed'])))
            with mock.patch.object(guard,'load_registered_study',return_value=value),\
                 mock.patch.object(guard,'load_model_seal',return_value={'models':[]}):
                self.assertEqual(validate_stage_result(study,cap,path),expected)


def make_synthetic_study():
    """A private root with genuine public source closure and invented raw XML.

    No accepted model, result, cache, control file or actual fixture is read.
    """
    root=scratch('registered-'); protocol_path=ROOT/'specs/003-possession-improvements/protocol.json'
    protocol=json.loads(protocol_path.read_text())
    sources=guard._scientific_paths(ROOT,protocol,(ROOT/'tools/v3_prepare_catalog.py',))
    extra=[protocol_path,protocol_path.parent/'PRD-TURNOVER.md',protocol_path.parent/'PRD-MULTIMATCH.md',
           protocol_path.parent/'contracts.md',ROOT/'requirements-lock.txt',ROOT/'requirements-training-lock.txt']
    for source in set(sources)|set(extra):
        target=root/source.relative_to(ROOT); target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source,target)
    def write(path,value):
        path=root/path; path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value,sort_keys=True,separators=(',',':')),encoding='utf-8'); return path
    overlap=write(Path('reports/v3-metadata-overlap.json'),{'synthetic':True})
    attribution=write(Path('reports/v3-source-attribution.json'),{'synthetic':True})
    feature=prepared_features(); numeric=constant_model(feature,(0.,0.,6.)).document
    model=write(Path('models/synthetic-trees.json'),numeric)
    active=write(Path('models/active.json'),dict(emitter='trees',transition_seconds=.5,tag_weight=0.,
        feature_transform='local-linear-v2',model='models/synthetic-trees.json',model_sha256=guard.sha256(model)))
    fallback_names=['models/active.json','models/synthetic-trees.json']+sorted(
        str(p.relative_to(ROOT)).replace('\\','/') for p in sources if p.suffix=='.py')[:27]
    fallback=write(Path('reports/synthetic-fallback.json'),{'files':{n:{'bytes':(root/n).stat().st_size,
        'sha256':guard.sha256(root/n)} for n in fallback_names}})
    raw=root/'local/v3-data/originals'; raw.mkdir(parents=True)
    records={}; n_half=900
    for role in ('train','selection','test'):
        for fixture in protocol['split'][role]:
            meta=('<Match><General MatchId="'+fixture+'" HomeTeamId="H" GuestTeamId="A" />'
                  '<Environment PitchX="105" PitchY="68" />'+''.join('<Team TeamId="'+side+'">'+
                  ''.join('<Player PersonId="'+side+str(i)+'" />' for i in range(4))+'</Team>' for side in ('H','A'))+'</Match>')
            chunks=['<Tracking>']
            for period,section in enumerate(('firstHalf','secondHalf')):
                for object_index in range(9):
                    ball=object_index==8; side='H' if object_index<4 else 'A'; person=side+str(object_index%4)
                    attrs='TeamId="BALL"' if ball else 'TeamId="'+side+'" PersonId="'+person+'"'
                    chunks.append('<FrameSet MatchId="'+fixture+'" GameSection="'+section+'" '+attrs+'>')
                    for i in range(n_half):
                        state=(i//100)%3
                        previous=((i//100)-1)%3 if i>=100 else state
                        blend=min((i%100)/20.,1.)
                        bx=(1-blend)*(-4.,4.,0.)[previous]+blend*(-4.,4.,0.)[state]
                        by=(1-blend)*(20. if previous==2 else 0.)+blend*(20. if state==2 else 0.)
                        x=bx if ball else (-5. if side=='H' else 5.)+object_index%4
                        y=by if ball else float(object_index%4)
                        total_ms=i*40; seconds=total_ms//1000; ms=total_ms%1000
                        timestamp=f'2026-01-01T0{period}:{seconds//60:02d}:{seconds%60:02d}.{ms:03d}Z'
                        label=f' BallStatus="{0 if state==2 else 1}" BallPossession="{state+1 if state<2 else 0}"' if ball else ''
                        chunks.append(f'<Frame N="{i}" T="{timestamp}" X="{x}" Y="{y}"{label} />')
                    chunks.append('</FrameSet>')
            chunks.append('</Tracking>')
            record=dict(fixture_id=fixture,canonical_fixture_id='invented-'+fixture,duplicate_group='invented-'+fixture,
                role=role,fps=25.,license={'spdx':'CC-BY-4.0','attribution_receipt_digest':guard.sha256(attribution)})
            for kind,content in (('metadata',meta),('tracking',''.join(chunks))):
                path=raw/(fixture+'-'+kind+'.xml'); data=content.encode(); path.write_bytes(data)
                record[kind]=dict(kind=kind,relative_path=path.name,source_url='https://example.invalid/'+path.name,
                    bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),md5=hashlib.md5(data).hexdigest())
            records[fixture]=record
    catalog=write(Path('local/synthetic-catalog.json'),dict(schema_version=1,provider='IDSSE',raw_root=str(raw),
        metadata_overlap_receipt_digest=guard.sha256(overlap),fixtures=records))
    with mock.patch.object(guard,'ROOT',root):
        study=guard.register_study(root/protocol_path.relative_to(ROOT),catalog,fallback,root/'local/v3-control')
    return root,study


class RegisteredSyntheticStudyTests(unittest.TestCase):
    def test_real_supervised_cli_bootstrap_child_and_owner_authority(self):
        from experiments.v3 import resources
        root,study=make_synthetic_study()
        policy=resources.policy_from_protocol(ROOT/'specs/003-possession-improvements/protocol.json')
        budget=resources.initialize_budget(root/'bootstrap-budget.json',root)
        preflight=resources.resource_preflight(policy,root,budget)
        code="""
from experiments.v3.resources import worker_handshake
grant=worker_handshake()
import os
from pathlib import Path
from types import SimpleNamespace
from experiments.v3 import resources,guard,cli,training
guard.ROOT=Path(ROOT_VALUE)
resources.worker_handshake=lambda:grant
def invented_callback(study,cap,output):
    assert cap.process_id==os.getpid()
    guard.assert_access(cap,cap.fixture_ids[0],'targets')
    result=study.parent/'train/result.json'
    guard._write_once(result,dict(schema_version=1,status='complete',study_digest=cap.study_digest,attempt_id=cap.attempt_id,synthetic_bootstrap_only=True,worker_pid=os.getpid()))
    try:
        guard.finish_attempt(cap,result,'complete')
    except guard.AccessError:
        pass
    else:
        raise AssertionError('child cannot finish owner attempt')
training.fit_models=invented_callback
raise SystemExit(cli._resource_worker(SimpleNamespace(study=Path(STUDY_VALUE),stage='train')))
""".replace('ROOT_VALUE',repr(str(root))).replace('STUDY_VALUE',repr(str(study)))
        with mock.patch.object(guard,'ROOT',root):
            with resources.prepare_worker([str(ROOT/'.venv/Scripts/python.exe'),'-c',code],policy,root,budget,
                    stage='synthetic',preflight_receipt=preflight) as worker:
                cap=guard.reserve_attempt(study,'train',('J03WOH','J03WOY'),root/'local/v3-control')
                result=study.parent/'train/result.json'; worker.authorize(cap,result_path=result)
                measured=worker.wait()
                (root/'bootstrap-resources.json').write_text(json.dumps(measured,indent=2))
                self.assertEqual(measured['exit_code'],0)
                self.assertFalse(measured['termination_reason']); self.assertFalse(measured['sampling_errors'])
                self.assertEqual(measured['gaps_over_50ms'],0)
                doc=guard.read_json(result)
                self.assertEqual(doc['worker_pid'],measured['worker_pid'])
                self.assertNotEqual(doc['worker_pid'],os.getpid())
                guard.finish_attempt(cap,result,'complete')
                with self.assertRaises(guard.AccessError):
                    guard.reserve_attempt(study,'train',('J03WOH','J03WOY'),root/'local/v3-control')

    def test_three_production_parameter_fits_and_full_selection(self):
        from experiments.v3 import training
        from experiments.v3.training import fit_models
        from experiments.v3.evaluate import select_finalist,run_final_test
        from experiments.v3.cli import validate_stage_result
        root,study=make_synthetic_study()
        child_code="""
import json,os
from dataclasses import asdict
from pathlib import Path
from unittest import mock
from experiments.v3 import guard,training
guard.ROOT=Path(ROOT_VALUE)
study=Path(STUDY_VALUE)
cap=guard.reserve_attempt(study,'train',('J03WOH','J03WOY'),guard.ROOT/'local/v3-control')
with mock.patch.object(training,'load_match',wraps=training.load_match) as loads:
    training.fit_models(study,cap,study.parent/'models')
    count=loads.call_count
(guard.ROOT/'author-owner.json').write_text(json.dumps({'capability':asdict(cap),'adapter_load_count':count}))
os._exit(17)
""".replace('ROOT_VALUE',repr(str(root))).replace('STUDY_VALUE',repr(str(study)))
        child=subprocess.run([str(ROOT/'.venv/Scripts/python.exe'),'-c',child_code],capture_output=True,text=True)
        (root/'author-child-log.txt').write_text(child.stdout+child.stderr)
        self.assertEqual(child.returncode,17,child.stderr)
        owner=guard.read_json(root/'author-owner.json')
        self.assertEqual(owner['adapter_load_count'],2)
        fields=owner['capability']; fields['fixture_ids']=tuple(fields['fixture_ids'])
        cap=AccessCapability(**fields)
        with mock.patch.object(guard,'ROOT',root):
            models=study.parent/'models/models.json'
            inputs=[guard.read_json(study.parent/'models'/(name+'-parity.json'))['training_input_digests'] for name in ('C0','C1','boundary')]
            for fixture in ('J03WOH','J03WOY'):
                for condition in ('clean','ball4','combined'):
                    shared=[next(r for r in rows if r['fixture_id']==fixture and r['condition']==condition) for rows in inputs]
                    self.assertEqual(len({r['observation_digest'] for r in shared}),1)
                    self.assertEqual(len({r['target_digest'] for r in shared}),1)
            self.assertEqual(validate_stage_result(study,cap,study.parent/'train/result.json'),0)
            complete=guard.read_json(study.parent/'train/result.json')
            incomplete=copy.deepcopy(complete); incomplete['sealed']=False
            incomplete_path=study.parent/'train/incomplete-author-copy.json'
            guard._write_once(incomplete_path,incomplete)
            with self.assertRaises(guard.IntegrityError): guard.finalize_recorded_result(study,incomplete_path)
            changed=copy.deepcopy(complete)
            identity=changed['artifacts'][0]
            corrupted=study.parent/'train/changed-author-artifact.json'
            corrupted.write_bytes((study.parent/identity['relative_path']).read_bytes()+b' ')
            identity['relative_path']=corrupted.relative_to(study.parent).as_posix()
            changed_path=study.parent/'train/changed-author-result.json'; guard._write_once(changed_path,changed)
            with self.assertRaises(guard.IntegrityError): guard.finalize_recorded_result(study,changed_path)
            with mock.patch.object(training,'load_match',side_effect=AssertionError('recovery cannot parse')),\
                 mock.patch.object(training,'fit_numeric',side_effect=AssertionError('recovery cannot fit')):
                guard.finalize_recorded_result(study,study.parent/'train/result.json')
                guard.finalize_recorded_result(study,study.parent/'train/result.json')
            with self.assertRaises(guard.AccessError):
                guard.reserve_attempt(study,'train',('J03WOH','J03WOY'),root/'local/v3-control')
            seal=guard.load_model_seal(study)
            self.assertEqual([r['name'] for r in seal['models']],['C0','C1','boundary'])
            self.assertEqual(len(list((study.parent/'models').glob('fit-start-*.json'))),3)
            cap=guard.reserve_attempt(study,'selection',('J03WPY',),root/'local/v3-control')
            path=study.parent/'selection/result.json'; finalist=select_finalist(study,models,cap,path)
            result=guard.read_json(path); self.assertEqual(len(result['rows']),54)
            self.assertEqual(validate_stage_result(study,cap,path),0 if finalist else 4)
            guard.finish_attempt(cap,path,'complete')
            with self.assertRaises(guard.AccessError):
                guard.reserve_attempt(study,'selection',('J03WPY',),root/'local/v3-control')
            if finalist:
                cap=guard.reserve_attempt(study,'test',('J03WN1','J03WQQ'),root/'local/v3-control')
                path=run_final_test(study,finalist,cap,study.parent/'test/result.json')
                result=guard.read_json(path); self.assertEqual(len(result['rows']),24)
                self.assertIs(type(result['gate_passed']),bool)
                self.assertEqual(validate_stage_result(study,cap,path),0 if result['gate_passed'] else 4)
                guard.finish_attempt(cap,path,'complete')
                with self.assertRaises(guard.AccessError):
                    guard.reserve_attempt(study,'test',('J03WN1','J03WQQ'),root/'local/v3-control')
            (root/'author-summary.json').write_text(json.dumps({'synthetic':True,'three_fits':True,
                'selection_rows':54,'finalist':bool(finalist),'test_rows':24 if finalist else 0,
                'dead_owner_metadata_recovery':True,'incomplete_and_mutated_refused':True}))


if __name__ == '__main__': unittest.main()
