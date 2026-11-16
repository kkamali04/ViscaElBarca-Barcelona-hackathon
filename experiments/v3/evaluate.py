"""Fixed full-timeline scoring, finite selection, and one paired fresh-test cohort."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import numpy as np

from validation.metrics import pm
from possession_model.trees import TreeModel
from . import guard
from .adapter import load_match
from .boundary import NumericHead
from .cache import ReadLease, strict_json
from .contracts import TargetBatch, AccessCapability, ModelBundle, InferencePolicy
from .corruption import build_features, condition_observations, condition_receipt, seed_streams, positive_runs, CONDITIONS
from .core import predict_codes, candidate_config, validate_registry, CANDIDATES
from .training import array_digest, observation_digest, result_envelope

CONDITION_IDS = ('clean','ball4','ball12','combined','stale_players','view_gap')
METRIC_KEYS = ('spell_f1_mean','macro_f1','H_f1','A_f1','D_f1',
              'destination_typed_transition_f1_12_frames','destination_typed_transition_f1_25_frames')
GATES = {'mean_paired_spell_gain_min':.04,'each_match_primary_delta_min':0,
         'mean_clean_spell_delta_min':-.005,'each_match_clean_spell_delta_min':-.01,
         'mean_each_class_frame_f1_delta_min':-.01,'each_condition_mean_spell_delta_min':-.01,
         'comparison_epsilon':1e-12}


def score_match(truth: TargetBatch, codes: np.ndarray, periods: np.ndarray, fps: float) -> dict:
    if type(truth) is not TargetBatch or type(fps) not in (int,float) or not math.isfinite(fps) or abs(fps-25.)>1e-6:
        raise ValueError('typed targets and native25Hz required')
    if (not isinstance(codes,np.ndarray) or codes.dtype != np.int8 or codes.ndim != 1
            or not np.isin(codes,[0,1,2,3]).all() or not isinstance(periods,np.ndarray)
            or periods.dtype != np.int16 or periods.shape != codes.shape or truth.labels.shape != codes.shape):
        raise ValueError('aligned typed prediction/period contract required')
    gt=np.where((truth.labels<0)|(periods<=0),3,truth.labels).astype(np.int8)
    runs=[(a+c,a+d) for a,b in positive_runs(periods) for c,d in pm.valid_runs(gt[a:b])]
    cm=pm.scored_confusion(pm.confusion(gt,codes))
    filled=pm.fill_abstentions(codes,runs)
    spell=pm.spell_scores(gt,filled,runs,ious=(.3,.4,.5,.6,.7))
    result={'spell_f1_mean':float(spell['mean_f1']),'macro_f1':float(pm.macro_f1(cm)),
        'graded_frames':int(cm.sum()),'unknown_active_frames':int(((gt==3)&(periods>0)).sum()),
        'active_frames':int((periods>0).sum()),'valid_run_count':len(runs),'confusion':cm.tolist(),
        'spells':{'n_gt':int(spell['n_gt']),'n_pred':int(spell['n_pred']),
                  'per_iou':{str(k):v for k,v in spell['per_iou'].items()}}}
    for k,label in enumerate('HAD'):
        result[label+'_f1']=float(pm.per_class_prf(cm,k)[2])
    for tolerance in (12,25):
        tp=fp=fn=0
        for run in runs:
            pairs,missed,spurious=pm.match_transitions(pm.transitions(gt,[run]),pm.transitions(filled,[run]),tolerance,typed='to')
            tp+=len(pairs); fn+=len(missed); fp+=len(spurious)
        report={'tp':tp,'fp':fp,'fn':fn,'precision':tp/(tp+fp) if tp+fp else 0.,
                'recall':tp/(tp+fn) if tp+fn else 0.,'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0.}
        result['transitions_'+str(tolerance)]=report
        result['destination_typed_transition_f1_'+str(tolerance)+'_frames']=report['f1']
    return result


def validate_rows(rows, fixtures, candidates):
    expected={(f,c,a) for f in fixtures for c in CONDITION_IDS for a in candidates}
    actual={}
    if type(rows) is not list or len(rows)!=len(expected): raise ValueError('incomplete fixed evaluation grid')
    for row in rows:
        key=(row['fixture_id'],row['condition'],row['candidate_id'])
        if key not in expected or key in actual: raise ValueError('extra/duplicate evaluation row')
        metrics=row['metrics']
        if type(metrics) is not dict or any(type(metrics.get(k)) not in (int,float)
                or not math.isfinite(metrics[k]) or not 0<=metrics[k]<=1 for k in METRIC_KEYS):
            raise ValueError('complete finite bounded aggregate metrics required')
        actual[key]=metrics
    if set(actual)!=expected: raise ValueError('missing evaluation row')
    return actual


def paired_gate(rows, fixtures, candidate_id, gate=None):
    gate=GATES if gate is None else gate
    if gate != GATES or candidate_id=='A': raise ValueError('fixed challenger gate required')
    table=validate_rows(rows,fixtures,('A',candidate_id))
    delta={f:{c:{k:table[f,c,candidate_id][k]-table[f,c,'A'][k] for k in METRIC_KEYS}
                 for c in CONDITION_IDS} for f in fixtures}
    primary={f:float(np.mean([delta[f][c]['spell_f1_mean'] for c in CONDITION_IDS])) for f in fixtures}
    clean={f:delta[f]['clean']['spell_f1_mean'] for f in fixtures}
    condition={c:float(np.mean([delta[f][c]['spell_f1_mean'] for f in fixtures])) for c in CONDITION_IDS}
    classes={label:float(np.mean([delta[f][c][label+'_f1'] for f in fixtures for c in CONDITION_IDS])) for label in 'HAD'}
    mean=float(np.mean(list(primary.values())))
    checks={'mean_paired_spell_gain':mean>=.04-1e-12,
        'each_match_primary':all(v>=-1e-12 for v in primary.values()),
        'mean_clean_spell':float(np.mean(list(clean.values())))>=-.005-1e-12,
        'each_match_clean':all(v>=-.01-1e-12 for v in clean.values()),
        'each_class_frame':all(v>=-.01-1e-12 for v in classes.values()),
        'each_condition_spell':all(v>=-.01-1e-12 for v in condition.values())}
    return {'gate_passed':bool(all(checks.values())),'checks':checks,'N':len(fixtures),
        'primary_delta_mean':mean,'primary_delta_min':min(primary.values()),'primary_delta_max':max(primary.values()),
        'per_match_primary_delta':primary,'per_match_clean_delta':clean,'per_condition_spell_delta':condition,
        'per_class_frame_delta':classes,'paired_deltas':delta,'condition_count':6,
        'primary_score':float(np.mean([table[f,c,candidate_id]['spell_f1_mean'] for f in fixtures for c in CONDITION_IDS])),
        'macro_f1':float(np.mean([table[f,c,candidate_id]['macro_f1'] for f in fixtures for c in CONDITION_IDS]))}


def choose_finalist(rows, fixtures=('J03WPY',)):
    names=tuple(row[0] for row in CANDIDATES)
    validate_rows(rows,fixtures,names)
    evaluations={}
    for name in names[1:]:
        subset=[r for r in rows if r['candidate_id'] in ('A',name)]
        evaluations[name]=paired_gate(subset,fixtures,name)
    eligible=[name for name,result in evaluations.items() if result['gate_passed']]
    eligible.sort(key=lambda name:(-round(evaluations[name]['primary_score'],12),
                                  -round(evaluations[name]['macro_f1'],12),name))
    return eligible[0] if eligible else None,evaluations


def _read_numeric(path, identity):
    with ReadLease(path) as lease:
        lease.verify(identity)
        return strict_json(lease.read())


def load_bundles(study):
    value=guard.load_registered_study(study); protocol=guard._config(study,value)
    validate_registry(protocol); seal=guard.load_model_seal(study)
    digest=guard.sha256(Path(value['model_seal_path']))
    records={r['name']:r for r in seal['models']}
    emitters={name:TreeModel(_read_numeric(study.parent/records[name]['relative_path'],records[name])) for name in ('C0','C1')}
    record=records['boundary']
    head=NumericHead(_read_numeric(study.parent/record['relative_path'],record))
    bindings={r['relative_path']:r for r in value['artifact_bindings']}
    config_path='models/active.json'
    if config_path not in bindings: raise guard.IntegrityError('accepted active config unbound')
    config=_read_numeric(guard.ROOT/config_path,bindings[config_path])
    if (config.get('emitter')!='trees' or config.get('transition_seconds')!=.5 or config.get('tag_weight',0)!=0
            or config.get('feature_transform')!='local-linear-v2'):
        raise guard.IntegrityError('accepted comparator semantic configuration mismatch')
    model_path=config.get('model')
    if model_path not in bindings or bindings[model_path]['sha256']!=config.get('model_sha256'):
        raise guard.IntegrityError('accepted emitter unbound')
    emitters['accepted']=TreeModel(_read_numeric(guard.ROOT/model_path,bindings[model_path]))
    return {name:ModelBundle(emitters[emitter],None if support=='none' else head,digest)
            for name,emitter,alpha,support in CANDIDATES}


def _evaluate_grid(study,cap,candidates,protocol,bundles):
    rows=[]; inputs=[]
    protocol_digest=cap_protocol_digest(study)
    for fixture in cap.fixture_ids:
        obs,truth=load_match(study,cap,fixture)
        if not guard._hex(truth.observation_digest) or not guard._hex(obs.source_digest):
            raise guard.IntegrityError('adapter SHA256 input identities required')
        thash=array_digest(truth.labels)
        for condition in CONDITION_IDS:
            seeds=seed_streams(protocol_digest,cap.role,fixture,condition)
            conditioned=condition_observations(obs,CONDITIONS[condition],seeds)
            ohash=observation_digest(conditioned); features=build_features(conditioned); del conditioned
            inputs.append({'fixture_id':fixture,'condition':condition,'observation_digest':ohash,
                'target_digest':thash,'corruption':condition_receipt(obs,CONDITIONS[condition],seeds)})
            for name in candidates:
                codes=predict_codes(features,bundles[name],candidate_config(name),InferencePolicy('external',()))
                metrics=score_match(truth,codes,features.period_id,features.fps)
                rows.append({'fixture_id':fixture,'condition':condition,'candidate_id':name,
                    'metrics':metrics,'prediction_digest':array_digest(codes)})
                del codes
            del features
        del obs,truth
    validate_rows(rows,cap.fixture_ids,candidates)
    return rows,inputs


def cap_protocol_digest(study):
    return guard.load_registered_study(study)['protocol_digest']


def _admit(study,cap,role,output):
    study=guard._plain(study); value=guard.load_registered_study(study); protocol=guard._config(study,value)
    validate_registry(protocol)
    if (type(cap) is not AccessCapability or cap.role!=role or cap.study_digest!=guard.study_digest(study)
            or cap.fixture_ids!=tuple(protocol['split'][role])
            or guard._plain(output,missing=True)!=study.parent/role/'result.json' or Path(output).exists()):
        raise guard.AccessError('exact role capability/result destination required')
    if tuple(protocol['evaluation']['conditions'])!=CONDITION_IDS or protocol['evaluation']['gate']!=GATES:
        raise guard.IntegrityError('fixed metric/gate policy mismatch')
    return study,value,protocol


def _model_artifacts(study,seal):
    return [study.parent/'models/models.json',
        *(study.parent/row['relative_path'] for row in seal['models']),
        *(study.parent/row['parity_receipt']['relative_path'] for row in seal['models'])]


def select_finalist(study: Path, models: Path, cap: AccessCapability, output: Path):
    study,value,protocol=_admit(study,cap,'selection',output)
    if guard._plain(models)!=Path(value['model_seal_path']): raise guard.IntegrityError('wrong model seal')
    seal=guard.load_model_seal(study); bundles=load_bundles(study)
    rows,inputs=_evaluate_grid(study,cap,tuple(r[0] for r in CANDIDATES),protocol,bundles)
    winner,evaluations=choose_finalist(rows,cap.fixture_ids)
    attribution={pair:float(np.mean([r['metrics']['spell_f1_mean'] for r in rows if r['candidate_id']==left]))
                       -float(np.mean([r['metrics']['spell_f1_mean'] for r in rows if r['candidate_id']==right]))
        for pair,left,right in (('B080-A','B080','A'),('F080-A','F080','A'),('B080-F080','B080','F080'),
            ('C0-A','C0','A'),('C1-C0','C1','C0'),('D0050-C0','D0050','C0'),('D0080-C0','D0080','C0'),
            ('D1050-C1','D1050','C1'),('D1080-C1','D1080','C1'))}
    result={**result_envelope(study,cap,value,_model_artifacts(study,seal)),
        'eligible':winner is not None,'candidate_id':winner,'model_seal_digest':guard.sha256(models),
        'rows':rows,'inputs':inputs,'candidates':evaluations,'selection_only_attribution':attribution,
        'N':1,'condition_count':6,'candidate_count':9,'limitations':'One selection match; no significance or hidden-performance inference.'}
    if winner is None:
        guard._write_once(output,result)
        return None
    finalist={'schema_version':1,'study_digest':cap.study_digest,'model_seal_digest':guard.sha256(models),
        'protocol_digest':value['protocol_digest'],'scientific_closure_digest':value['scientific_closure_digest'],
        'comparator_digest':value['comparator_digest'],
        'selection_receipt_digest':hashlib.sha256(guard.canonical(result)+b'\n').hexdigest(),
        'candidate_id':winner,'config':next(r for r in protocol['candidates'] if r['id']==winner),'models':seal['models']}
    path=study.parent/'finalist.json'; guard._write_once(path,finalist)
    # A recoverable complete result is published only after its strict finalist.
    guard._write_once(output,result)
    return path


def run_final_test(study: Path, finalist: Path, cap: AccessCapability, output: Path) -> Path:
    study,value,protocol=_admit(study,cap,'test',output)
    if guard._plain(finalist)!=study.parent/'finalist.json': raise guard.IntegrityError('canonical finalist required')
    guard._validate_finalist(study,value); chosen=guard.read_json(finalist)['candidate_id']
    bundles=load_bundles(study)
    rows,inputs=_evaluate_grid(study,cap,('A',chosen),protocol,bundles)
    verdict=paired_gate(rows,cap.fixture_ids,chosen)
    seal=guard.load_model_seal(study)
    envelope=result_envelope(study,cap,value,[*_model_artifacts(study,seal),study.parent/'selection/result.json'])
    guard._write_once(output,{**envelope,'gate_passed':verdict['gate_passed'],'candidate_id':chosen,
        'finalist_digest':guard.sha256(finalist),'rows':rows,'inputs':inputs,'verdict':verdict,
        'N':2,'condition_count':6,'candidate_count':2,
        'limitations':'Two provider matches with shared-club dependence; paired engineering outcomes only. '
                      'No confidence interval, significance, population generalization or hidden-performance claim.'})
    return Path(output)
