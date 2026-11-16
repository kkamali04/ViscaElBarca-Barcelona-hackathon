"""The fixed three-fit v3 study; no raw access without its live train capability."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import time
import numpy as np

from possession_model.evidence import feature_matrix
from possession_model.trees import TreeModel, export_sklearn
from . import guard
from .adapter import load_match
from .boundary import (build_boundary_features, NumericHead, export_boundary_sklearn,
                       BOUNDARY_NAMES, TREE_PARAMETERS, WEIGHT_RECIPE, FEATURE_VERSION)
from .contracts import AccessCapability, TargetBatch
from .corruption import (build_features, condition_observations, seed_streams,
                         positive_runs, capped_row_ids, CONDITIONS, condition_receipt)
from .core import validate_registry

EMITTER_PARAMETERS = dict(max_iter=64,max_leaf_nodes=15,learning_rate=.08,
    l2_regularization=2.,min_samples_leaf=80,max_bins=63,early_stopping=False,categorical_features=None)
FIT_SEED = 20261116
TRAIN_FIXTURES = ('J03WOH','J03WOY')
CURRICULA = {'C0':('clean','ball4','ball12','combined'),
             'C1':('clean','ball4','combined','stale_players'),
             'boundary':('clean','ball4','combined','stale_players')}

RESULT_BINDINGS = ('protocol_digest','catalog_digest','scientific_closure_digest',
                   'environment_digest','comparator_digest')


def result_envelope(study, cap, value, artifacts):
    """Complete aggregate envelope for guard's metadata-only dead-owner recovery."""
    identities=[]; seen=set()
    for supplied in artifacts:
        path=guard._plain(Path(supplied))
        if (not path.is_relative_to(study.parent) or path.suffix!='.json'
                or path.relative_to(study.parent).parts[0] not in ('models','train','selection','test')
                or path in seen):
            raise guard.IntegrityError('invalid complete result artifact')
        seen.add(path)
        identities.append({'relative_path':path.relative_to(study.parent).as_posix(),
                           'bytes':path.stat().st_size,'sha256':guard.sha256(path)})
    if not identities: raise guard.IntegrityError('nonempty result artifact manifest required')
    return {'schema_version':1,'study_digest':cap.study_digest,'attempt_id':cap.attempt_id,
        'status':'complete','sealed':True,'role':cap.role,'fixture_ids':list(cap.fixture_ids),
        'fixture_count':len(cap.fixture_ids),'artifact_count':len(identities),'artifacts':identities,
        **{key:value[key] for key in RESULT_BINDINGS}}


def array_digest(*arrays) -> str:
    """Hash typed, shaped actual array content in bounded contiguous byte chunks."""
    h = hashlib.sha256()
    for a in arrays:
        if not isinstance(a,np.ndarray) or a.dtype.hasobject:
            raise ValueError('plain numeric arrays required')
        a = np.ascontiguousarray(a)
        h.update(guard.canonical({'dtype':a.dtype.str,'shape':list(a.shape)})); h.update(b'\0')
        data = memoryview(a).cast('B')
        for start in range(0,len(data),1024*1024): h.update(data[start:start+1024*1024])
    return h.hexdigest()


def observation_digest(obs) -> str:
    from .cache import OBSERVATION_ARRAYS
    digest = array_digest(*(getattr(obs,name) for name in sorted(OBSERVATION_ARRAYS)))
    return hashlib.sha256(guard.canonical({'arrays':digest,'fixture_id':obs.fixture_id,
        'source_digest':obs.source_digest,'slot_ids':list(obs.slot_ids),'fps':obs.fps,'pitch':list(obs.pitch),
        'period_origins':[[p.period_id,p.source_frame_id,p.utc_ns] for p in obs.period_origins]})).hexdigest()


def _aligned(labels, periods):
    if (not isinstance(labels,np.ndarray) or labels.dtype != np.int8 or labels.ndim != 1
            or not np.isin(labels,[-1,0,1,2]).all() or not isinstance(periods,np.ndarray)
            or periods.dtype != np.int16 or periods.shape != labels.shape):
        raise ValueError('aligned exact target/period arrays required')


def emitter_rows(labels: np.ndarray, periods: np.ndarray) -> np.ndarray:
    _aligned(labels,periods)
    chunks = [np.arange(a,b,5,dtype=np.int64) for a,b in positive_runs(periods)]
    ids = np.concatenate(chunks) if chunks else np.empty(0,np.int64)
    return capped_row_ids(ids[labels[ids] >= 0])


def normalize_weights(weights: np.ndarray) -> np.ndarray:
    w = np.asarray(weights,dtype=np.float64)
    if w.ndim != 1 or not len(w) or not np.isfinite(w).all() or (w <= 0).any():
        raise ValueError('nonempty finite positive weights required')
    result = w / np.mean(w,dtype=np.float64)
    if not np.isfinite(result).all() or (result <= 0).any() or not math.isclose(float(result.mean()),1.,rel_tol=1e-12):
        raise ValueError('global mean-one normalization failed')
    return result


def emitter_stratum(matrix, labels, ids, pairs):
    y = labels[ids].copy()
    counts = np.bincount(y,minlength=3)
    if len(counts) != 3 or (counts == 0).any():
        raise ValueError('every emitter stratum must include H/A/D')
    x = np.array(matrix[ids],dtype=np.float32,copy=True)
    swapped = x.copy(); sy = y.copy()
    seen = set()
    for a,b in pairs:
        if a == b or a in seen or b in seen or not 0 <= a < x.shape[1] or not 0 <= b < x.shape[1]:
            raise ValueError('invalid side feature pairs')
        seen.update((a,b)); swapped[:,a] = x[:,b]; swapped[:,b] = x[:,a]
    sy[y == 0] = 1; sy[y == 1] = 0
    w = 1. / (2*4*3*counts[y]) / 2.
    return np.concatenate((x,swapped)),np.concatenate((y,sy)),np.concatenate((w,w)),counts


def boundary_population(labels, periods, valid):
    _aligned(labels,periods)
    if not isinstance(valid,np.ndarray) or valid.dtype != np.bool_ or valid.shape != (len(labels),2):
        raise ValueError('aligned typed validity required')
    eligible = np.zeros(len(labels),bool)
    eligible[1:] = ((labels[1:] >= 0)&(labels[:-1] >= 0)&(periods[1:] > 0)
        &(periods[1:] == periods[:-1])&valid[1:].all(axis=1))
    ids = np.flatnonzero(eligible).astype(np.int64)
    target = np.where(labels[ids] == labels[ids-1],0,
                      np.where((labels[ids] == 2)|(labels[ids-1] == 2),2,1)).astype(np.int8)
    return ids,target


def sample_boundary(ids, target, seed):
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError('exact sampling seed required')
    if not len(ids): raise ValueError('empty eligible boundary stratum')
    none = np.flatnonzero(target == 0); positive = np.flatnonzero(target != 0)
    count = min(len(none),20*max(1,len(positive)))
    rng = np.random.Generator(np.random.PCG64(seed))
    sampled = rng.choice(len(none),size=count,replace=False,shuffle=True)
    chosen = np.sort(np.concatenate((none[sampled],positive)))
    inclusion = np.ones(len(chosen),np.float64)
    if len(none): inclusion[target[chosen] == 0] = count/len(none)
    return ids[chosen],target[chosen],inclusion,np.bincount(target,minlength=3)


def assemble_corpus(name: str, strata: list[dict]) -> tuple:
    """Assemble only already-selected invented/authorized rows; no data opens."""
    if name not in CURRICULA or [(s['fixture_id'],s['condition']) for s in strata] != [
            (f,c) for f in TRAIN_FIXTURES for c in CURRICULA[name]]:
        raise ValueError('exact eight ordered training strata required')
    if any(not len(s['y']) for s in strata): raise ValueError('empty training stratum')
    n = sum(len(s['y']) for s in strata)
    if n > (750000 if name == 'boundary' else 480000): raise ValueError('fit row cap exceeded')
    if name == 'boundary':
        population = np.sum([s['population_counts'] for s in strata],axis=0,dtype=np.int64)
        if (population <= 0).any(): raise ValueError('globally missing boundary class')
        weights = []
        for s in strata:
            w = np.sqrt(float(population.sum())/(3*population[s['y']]))/s['inclusion']
            weights.append(w/(8*np.sum(w,dtype=np.float64)))
    else:
        population = None; weights = [s['weights'] for s in strata]
    x = np.concatenate([s['x'] for s in strata]).astype(np.float32,copy=False)
    y = np.concatenate([s['y'] for s in strata]).astype(np.int8,copy=False)
    w = normalize_weights(np.concatenate(weights))
    if not np.array_equal(np.unique(y),[0,1,2]): raise ValueError('all fit classes required')
    return x,y,w,{'rows':n,'weight_mean':float(w.mean()),'weight_sum':float(w.sum()),
        'stratum_rows':[len(s['y']) for s in strata],
        'stratum_weight_fractions':[float(v.sum()/sum(a.sum() for a in weights)) for v in weights],
        'population_counts':None if population is None else population.tolist()}


def _source_strata(study, cap, name, protocol, owned_matches=None):
    # Reuse only immutable adapter-owned values inside this one live attempt.
    # This is not a persistent cache and never crosses a capability boundary.
    owned_matches = {} if owned_matches is None else owned_matches
    strata=[]; names=None
    for fixture in TRAIN_FIXTURES:
        if fixture not in owned_matches:
            owned_matches[fixture] = load_match(study,cap,fixture)
        else:
            guard.assert_access(cap,fixture,'observations')
            guard.assert_access(cap,fixture,'targets')
        obs, truth = owned_matches[fixture]
        if type(truth) is not TargetBatch or len(truth.labels) != len(obs.frame_id):
            raise ValueError('aligned actual targets required')
        # The adapter's metadata digest is checked, but actual values are hashed
        # independently below; arbitrary TargetBatch metadata is never a receipt.
        if not guard._hex(truth.observation_digest) or not guard._hex(obs.source_digest):
            raise ValueError('adapter input identity is not a SHA256')
        ids = emitter_rows(truth.labels,obs.period_id) if name != 'boundary' else None
        target_hash = array_digest(truth.labels)
        for condition in CURRICULA[name]:
            seeds = seed_streams(guard.sha256(Path(protocol)), 'train',fixture,condition)
            conditioned = condition_observations(obs,CONDITIONS[condition],seeds)
            input_hash = observation_digest(conditioned)
            features = build_features(conditioned)
            masks = condition_receipt(obs,CONDITIONS[condition],seeds)
            del conditioned
            if name == 'boundary':
                boundary = build_boundary_features(features)
                eligible,target = boundary_population(truth.labels,features.period_id,boundary.valid)
                chosen,y,inclusion,counts = sample_boundary(eligible,target,seeds['boundary_none_sampling'])
                x = boundary.values[chosen].copy(); names = BOUNDARY_NAMES
                s = dict(x=x,y=y,inclusion=inclusion,population_counts=counts)
                sampling = array_digest(eligible,target,chosen,y,inclusion,counts)
                del boundary
            else:
                matrix,names,pairs = feature_matrix(features)
                x,y,w,counts = emitter_stratum(matrix,truth.labels,ids,pairs)
                s = dict(x=x,y=y,weights=w,population_counts=counts)
                sampling = array_digest(ids,y,w,counts)
                del matrix
            s.update(fixture_id=fixture,condition=condition,observation_digest=input_hash,
                     target_digest=target_hash,sampling_digest=sampling,corruption=masks)
            strata.append(s)
            del features
        del obs,truth
    return strata,names


def parity_probes(document, n_features):
    """Deterministic synthetic missing/extreme/threshold probes, no data rows."""
    yield np.vstack((np.zeros((1,n_features),np.float32),np.full((1,n_features),np.nan,np.float32),
                     np.full((1,n_features),np.finfo(np.float32).max,np.float32),
                     np.full((1,n_features),-np.finfo(np.float32).max,np.float32)))
    chunk=[]
    for tree in document['trees']:
        nodes=tree['nodes']
        for i,leaf in enumerate(nodes['is_leaf']):
            if leaf: continue
            threshold=nodes['num_threshold'][i]; feature=nodes['feature_idx'][i]
            if abs(threshold) > float(np.finfo(np.float32).max): values=[np.float32(0),np.float32(np.nan)]
            else:
                value=np.float32(threshold)
                with np.errstate(over='ignore'):
                    values=[value,np.nextafter(value,np.float32(-np.inf)),np.nextafter(value,np.float32(np.inf)),np.float32(np.nan)]
                values=[v for v in values if not np.isinf(v)]
            for value in values:
                row=np.zeros(n_features,np.float32); row[feature]=value; chunk.append(row)
                if len(chunk)==4096: yield np.array(chunk,np.float32); chunk=[]
    if chunk: yield np.array(chunk,np.float32)


def fit_numeric(name, x, y, weights, names, provenance):
    """One fit with the production parameters; called exactly once per artifact."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from threadpoolctl import threadpool_limits
    parameters = TREE_PARAMETERS if name == 'boundary' else EMITTER_PARAMETERS
    estimator=HistGradientBoostingClassifier(**parameters,random_state=FIT_SEED)
    started=time.monotonic()
    with threadpool_limits(limits=4):
        estimator.fit(x,y,sample_weight=weights)
        document=(export_boundary_sklearn(estimator,provenance) if name == 'boundary'
                  else export_sklearn(estimator,names,provenance))
        numeric=NumericHead(document) if name == 'boundary' else TreeModel(document)
        error=0.; checked=0; probes=0
        for start in range(0,len(x),4096):
            batch=x[start:start+4096]
            delta=np.max(np.abs(estimator._raw_predict(batch)-numeric.raw_scores(batch,names)),initial=0.)
            error=max(error,float(delta)); checked+=len(batch)
        for batch in parity_probes(document,len(names)):
            delta=np.max(np.abs(estimator._raw_predict(batch)-numeric.raw_scores(batch,names)),initial=0.)
            error=max(error,float(delta)); probes+=len(batch)
    if not math.isfinite(error) or error > 1e-10: raise ValueError('numeric raw export parity failed')
    return document,dict(max_absolute_raw_error=error,checked_training_rows=checked,
        checked_synthetic_rows=probes,fit_seconds=time.monotonic()-started,
        passed=True,numeric_export_passed=True,parity_passed=True)


def fit_models(study: Path, cap: AccessCapability, output: Path) -> Path:
    study=guard._plain(study); output=guard._plain(output,missing=True)
    value=guard.load_registered_study(study); protocol=guard._config(study,value)
    validate_registry(protocol)
    if (type(cap) is not AccessCapability or cap.role != 'train' or cap.fixture_ids != TRAIN_FIXTURES
            or cap.study_digest != guard.study_digest(study) or output != study.parent/'models'):
        raise guard.AccessError('exact train capability/model destination required')
    if output.exists(): raise guard.AccessError('model generation already exists; no refit')
    if protocol['fit']['emitter'] != EMITTER_PARAMETERS or protocol['fit']['boundary'] != TREE_PARAMETERS:
        raise guard.IntegrityError('fixed estimator recipe mismatch')
    for name in CURRICULA:
        if tuple(protocol['fit'][name+'_conditions']) != CURRICULA[name]:
            raise guard.IntegrityError('fixed curriculum mismatch')
    guard.assert_access(cap,TRAIN_FIXTURES[0],'observations')
    output.mkdir(parents=True,exist_ok=False)
    models={}; receipts={}; summaries=[]; owned_matches={}
    protocol_path=next(guard.ROOT/row['relative_path'] for row in value['artifact_bindings']
        if row['relative_path'].endswith('/protocol.json'))
    for name in ('C0','C1','boundary'):
        guard.load_registered_study(study)
        source_started=time.monotonic()
        strata,names=_source_strata(study,cap,name,protocol_path,owned_matches)
        x,y,w,summary=assemble_corpus(name,strata)
        summary['source_and_assembly_seconds']=time.monotonic()-source_started
        inputs=[{k:s[k] for k in ('fixture_id','condition','observation_digest','target_digest','sampling_digest')} for s in strata]
        expected=guard.expected_model_provenance(study,name)
        if [{k:r[k] for k in ('fixture_id','condition')} for r in inputs] != expected.pop('training_input_order'):
            raise guard.IntegrityError('training identity order mismatch')
        provenance={**expected,'training_input_digests':inputs}
        if name == 'boundary':
            provenance.update(weight_recipe=WEIGHT_RECIPE,feature_version=FEATURE_VERSION,fps=25.,
                windows_frames=[5,15],coverage=.8,temperature=1.,tree_parameters=TREE_PARAMETERS,random_state=FIT_SEED)
        else:
            provenance.update(weight_recipe=protocol['fit']['emitter_weights'],tree_parameters=EMITTER_PARAMETERS,
                random_state=FIT_SEED,feature_version='accepted-streaming-v1+noise-v2-local-linear-1.2s')
        mask_receipts=[s['corruption'] for s in strata]
        del strata
        guard._write_once(output/('fit-start-'+name+'.json'),{'schema_version':1,'study_digest':cap.study_digest,
            'attempt_id':cap.attempt_id,'model':name,'rows':len(y),'fit_ordinal':len(models)+1})
        document,parity=fit_numeric(name,x,y,w,names,provenance)
        model=output/(name+'.json'); guard._write_once(model,document)
        parity.update(schema_version=1,study_digest=cap.study_digest,attempt_id=cap.attempt_id,
            scientific_closure_digest=value['scientific_closure_digest'],model_sha256=guard.sha256(model),
            training_input_digests=inputs,summary=summary,corruptions=mask_receipts)
        receipt=output/(name+'-parity.json'); guard._write_once(receipt,parity)
        models[name]=model; receipts[name]=receipt; summaries.append({'model':name,**summary})
        del x,y,w,document
    owned_matches.clear()
    seal=guard.seal_fitted_models(study,cap,models,receipts)
    envelope=result_envelope(study,cap,value,[seal,*models.values(),*receipts.values()])
    guard._write_once(study.parent/'train/result.json',{**envelope,'model_seal_digest':guard.sha256(seal),
        'fits':summaries,'adapter_load_count':2,'same_attempt_immutable_match_reuse':True})
    return seal
