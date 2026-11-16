"""Rerunnable independent synthetic acceptance. No fitting or actual data.

Run with the pinned project interpreter and a NEW --output path. Candidate and
public source identities are checked against the root freeze before and after.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager, ExitStack
from dataclasses import replace
import gc
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
import time
import traceback
from unittest.mock import patch

import numpy as np

from oracle import (ROOT, PRIVATE, ORDER, original, capability, fixtures,
                    SyntheticAccess, exact, aggregate_digest, public_identity,
                    digest_file, write_prepared, TargetBatch)
from experiments.speed_v1 import TrainingPreparationSession

PURE = ('condition_observations','build_features','condition_receipt',
        'feature_matrix','build_boundary_features')


@contextmanager
def counted():
    counts = Counter()
    with ExitStack() as stack:
        for name in PURE:
            fn = getattr(original,name)
            def wrapper(*a,_fn=fn,_name=name,**kw):
                counts[_name] += 1
                return _fn(*a,**kw)
            stack.enter_context(patch.object(original,name,wrapper))
        yield counts


def expect_error(fn, types=(ValueError,RuntimeError,TypeError,KeyError)):
    try:
        fn()
    except types:
        return
    raise AssertionError('invalid/unauthorized use succeeded')


def full_run(matches, cap, protocol, mode, order=ORDER, session=None):
    access = SyntheticAccess(matches,cap)
    output = []
    owned = {} if mode == 'baseline' else dict(matches)
    with access.bind_original():
        if mode == 'baseline':
            for name in order:
                strata,names = original._source_strata(PRIVATE/'invented-study.json',cap,name,protocol,owned)
                output.append((strata,names,original.assemble_corpus(name,strata)))
        else:
            own_session = session is None
            if own_session:
                session = TrainingPreparationSession(PRIVATE/'invented-study.json',cap,protocol,owned)
            for name in order:
                strata,names = session.source_strata(name)
                output.append((strata,names,original.assemble_corpus(name,strata)))
            if own_session:
                session.close()
    return output,access


def freeze_identity():
    freeze = json.loads((ROOT/'reports/speed-implementation-freeze.json').read_text(encoding='utf-8'))
    checked = {}
    for name,record in freeze['files'].items():
        path = ROOT/name
        assert path.stat().st_size == record['bytes'], 'freeze byte-size drift'
        assert digest_file(path) == record['sha256'], 'freeze candidate/spec digest drift'
        checked[name] = record['sha256']
    # Only the already-authorized public numerical files are read here. The root
    # separately owns broad protected-artifact inventory verification.
    for name,digest in public_identity().items():
        assert freeze['original_source_bindings'][name] == digest, 'public oracle source drift'
    return checked


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output',required=True)
    p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--skip-benchmark',action='store_true')
    args = p.parse_args()
    assert 1 <= args.repeats <= 5, 'bounded repeats required'
    output = Path(args.output).resolve()
    assert not output.exists(), 'report output must be new'
    allowed = [PRIVATE.resolve(),(ROOT/'reports').resolve()]
    assert any(output.is_relative_to(a) for a in allowed), 'private/report output path required'
    write_prepared()
    protocol = PRIVATE/'invented-protocol.json'
    report = {
        'scope':'independent invented-only preparation acceptance',
        'candidate_freeze':freeze_identity(), 'oracle_public_sources':public_identity(),
        'interpreter':sys.executable, 'python':platform.python_version(), 'numpy':np.__version__,
        'fixture_recipe_sha256':digest_file(PRIVATE/'oracle.py'),
        'harness_sha256':digest_file(Path(__file__)), 'checks':[], 'failures':[],
        'limits':[
            'Only invented observations and labels; synthetic loader and authorization stubs do not prove live study authority.',
            'No actual study, raw input, model, cache, CSV, fitting, network or Jobs were read or executed.',
            'Retained cache bytes exclude caller-owned input matches, returned arrays, transients and Python allocator overhead.',
            'No input-to-CSV, exported-package, official-validator, actual training-stage speedup or hidden-quality claim.',
        ],
    }
    matches = fixtures()
    cap = capability()
    baselines = None

    def check(name,fn):
        started = time.perf_counter()
        try:
            detail = fn()
            report['checks'].append({'name':name,'passed':True,'seconds':time.perf_counter()-started,
                                     'detail':detail})
            print(json.dumps({'check':name,'passed':True}),flush=True)
        except Exception as exc:
            failure = {'name':name,'type':type(exc).__name__,'message':str(exc),
                       'traceback':traceback.format_exc()}
            report['failures'].append(failure)
            print(json.dumps({'check':name,'passed':False,'type':type(exc).__name__,'message':str(exc)}),flush=True)

    def basic():
        nonlocal baselines
        with counted() as baseline_calls:
            baselines,base_access = full_run(matches,cap,protocol,'baseline')
        assert dict(baseline_calls) == dict(condition_observations=24,build_features=24,
            condition_receipt=24,feature_matrix=16,build_boundary_features=8), 'baseline call oracle'
        owned = dict(matches)
        access = SyntheticAccess(matches,cap)
        with access.bind_original(), counted() as candidate_calls:
            session = TrainingPreparationSession(PRIVATE/'invented-study.json',cap,protocol,owned)
            actual,_ = full_run(matches,cap,protocol,'candidate',session=session)
            exact(actual,baselines)
            assert dict(candidate_calls) == dict(condition_observations=10,build_features=10,
                condition_receipt=10,feature_matrix=16,build_boundary_features=8), 'candidate unique prep count'
            cold_stats = dict(session.stats)
            assert cold_stats['preparations']==10 and cold_stats['hits']==14 and cold_stats['cache_entries']==10
            assert 0 < cold_stats['retained_bytes'] <= cold_stats['max_cache_bytes']
            snapshots = session.stats
            warm,_ = full_run(matches,cap,protocol,'candidate',session=session)
            exact(warm,baselines)
            assert candidate_calls['build_features']==10
            assert dict(snapshots)==cold_stats, 'stats must be snapshots'
            expect_error(lambda: snapshots.__setitem__('hits',999), (AttributeError,TypeError))
            # Retained arrays must own immutable buffers, even against write-enable.
            for prepared in session._cache.values():
                for arr in prepared.arrays:
                    assert not arr.flags.writeable
                    expect_error(lambda a=arr:a.setflags(write=True), (ValueError,))
                assert type(prepared.metadata) is bytes and type(prepared.receipt) is bytes
            for result in actual:
                for stratum in result[0]:
                    for value in stratum.values():
                        if isinstance(value,np.ndarray) and value.size:
                            value.flat[0]=0
                    stratum['corruption']['counts']['selected_ball_frames']=-999
                    stratum['corruption']['seeds']['ball_gap']=0
                if type(result[1]) is list: result[1][0]='poisoned'
            unpoisoned,_ = full_run(matches,cap,protocol,'candidate',session=session)
            exact(unpoisoned,baselines)
            retained = cold_stats['retained_bytes']
            sizes = [p.retained_bytes for p in session._cache.values()]
            numeric = sum(arr.nbytes for item in session._cache.values() for arr in item.arrays)
            assert retained == sum(sizes) and retained > numeric, 'retention covers numeric plus metadata'
            session.close()
            assert session.stats['retained_bytes']==0 and session.stats['cache_entries']==0 and session.stats['closed']
        # A fresh order starts boundary-first and adds C0's ball12 later.
        reordered,_ = full_run(matches,cap,protocol,'candidate',order=('boundary','C1','C0'))
        exact(reordered,[baselines[2],baselines[1],baselines[0]])
        return {'baseline_calls':dict(baseline_calls),'candidate_calls_cold':{
                'condition_observations':10,'build_features':10,'condition_receipt':10,
                'feature_matrix':16,'build_boundary_features':8},
                'corpus_digest':aggregate_digest(baselines),'corpus_rows':[len(r[2][1]) for r in baselines],
                'strata_compared':24,'cache_bytes':retained,'numeric_payload_bytes':numeric,
                'entry_bytes_min':min(sizes),'entry_bytes_max':max(sizes)}
    check('exact_curricula_repeats_reordering_ownership_stats',basic)

    def access_and_identity():
        owned = dict(matches)
        access = SyntheticAccess(matches,cap)
        with access.bind_original():
            s = TrainingPreparationSession(PRIVATE/'invented-study.json',cap,protocol,owned)
            s.source_strata('C0')
            for fixture in original.TRAIN_FIXTURES:
                for kind in ('observations','targets'):
                    access.calls.clear(); access.denied={(fixture,kind)}
                    before=s.stats['preparations']
                    expect_error(lambda:s.source_strata('C0'))
                    assert (fixture,kind) in access.calls
                    assert s.stats['preparations']==before
            access.denied=set()
            protocol.write_text('{"purpose":"independent invented preparation acceptance","revision":2}\n',encoding='utf-8')
            expect_error(lambda:s.source_strata('C0'))
            protocol.write_text('{"purpose":"independent invented preparation acceptance","revision":1}\n',encoding='utf-8')
            old=cap.attempt_id
            object.__setattr__(cap,'attempt_id','mutated-attempt')
            expect_error(lambda:s.source_strata('C0'))
            object.__setattr__(cap,'attempt_id',old)
            s.source_strata('C0')
            s.close(); s.close()
            expect_error(lambda:s.source_strata('C0'))
            expect_error(s.clear)
            expect_error(s.__enter__)
        # Loader test uses no supplied owned matches: the existing loader stub
        # must be called once for each fixture and both gates checked thereafter.
        access = SyntheticAccess(matches,cap)
        with access.bind_original():
            s=TrainingPreparationSession(PRIVATE/'invented-study.json',cap,protocol)
            s.source_strata('C0'); access.calls.clear(); s.source_strata('C0')
            assert access.loads==list(original.TRAIN_FIXTURES)
            assert access.calls==[(f,k) for f in original.TRAIN_FIXTURES for k in ('observations','targets')]
            s.close()
        return {'revoked_hit_cases':4,'loader_calls':2,'warm_authorization_calls':4,
                'protocol_drift_refused':True,'capability_drift_refused':True,'closed_refused':True}
    check('authorization_loader_protocol_capability_close',access_and_identity)

    def changed_inputs():
        assert baselines is not None
        owned=dict(matches); access=SyntheticAccess(owned,cap)
        with access.bind_original():
            s=TrainingPreparationSession(PRIVATE/'invented-study.json',cap,protocol,owned)
            for name in ORDER: s.source_strata(name)
            # Labels change alone: every feature hits, while labels, counts,
            # inclusion/weights and target/sampling digests follow the oracle.
            changed=fixtures(label_shift=1)
            for f in owned: owned[f]=(owned[f][0],changed[f][1])
            before=s.stats['preparations']
            expected,_=full_run(owned,cap,protocol,'baseline')
            actual,_=full_run(owned,cap,protocol,'candidate',session=s)
            exact(actual,expected)
            assert s.stats['preparations']==before
            assert aggregate_digest(actual)!=aggregate_digest(baselines)
            assert [q['observation_digest'] for r in actual for q in r[0]] == [q['observation_digest'] for r in baselines for q in r[0]]
            # Original observations are read-only by convention but adapter-owned
            # buffers can be made writable. Content hashing must catch this.
            f=original.TRAIN_FIXTURES[0]
            obs,truth=owned[f]
            obs.positions.setflags(write=True); obs.positions[400,1,0] += np.float32(.125); obs.positions.setflags(write=False)
            before=s.stats['preparations']
            expected,_=full_run(owned,cap,protocol,'baseline',order=('C0',))
            actual,_=full_run(owned,cap,protocol,'candidate',order=('C0',),session=s)
            exact(actual,expected)
            assert s.stats['preparations']-before==4, 'observation mutation must miss four conditions'
            assert actual[0][0][0]['observation_digest']!=baselines[0][0][0]['observation_digest']
            # Valid metadata and sparse-time mutations must each miss/refuse.
            for changed_obs in (replace(obs,pitch=(106.3,68.)),
                                replace(obs,fps=25.0000005)):
                owned[f]=(changed_obs,truth); before=s.stats['preparations']
                expected,_=full_run(owned,cap,protocol,'baseline',order=('C0',))
                actual,_=full_run(owned,cap,protocol,'candidate',order=('C0',),session=s)
                exact(actual,expected); assert s.stats['preparations']-before==4
            time_values=obs.source_time_utc_ns.copy(); time_values[3]+=40
            owned[f]=(replace(obs,source_time_utc_ns=time_values),truth)
            before=s.stats['preparations']; s.source_strata('C0')
            assert s.stats['preparations']-before==4
            s.close()
        return {'target_only_recomputes':True,'observation_content_schema_metadata_bound':True}
    check('target_and_observation_mutations',changed_inputs)

    def retention():
        stable=fixtures(); access=SyntheticAccess(stable,cap)
        with access.bind_original():
            probe=TrainingPreparationSession(PRIVATE/'invented-study.json',cap,protocol,dict(stable))
            for name in ORDER: probe.source_strata(name)
            sizes=[p.retained_bytes for p in probe._cache.values()]
            cap8=max(sizes)*8
            assert cap8 < min(sizes)*9, 'chosen cap must fit eight, never nine entries'
            probe.close()
            lru=TrainingPreparationSession(PRIVATE/'invented-study.json',cap,protocol,dict(stable),cap8)
            lru.source_strata('C0'); assert lru.stats['cache_entries']==8
            before=dict(lru.stats); lru.source_strata('C1')
            assert lru.stats['hits']-before['hits']==6
            assert lru.stats['preparations']-before['preparations']==2
            assert lru.stats['evictions']==2 and lru.stats['cache_entries']==8
            before=dict(lru.stats); lru.source_strata('C1'); lru.source_strata('boundary')
            assert lru.stats['preparations']==before['preparations'], 'LRU must retain recently touched C1 entries'
            assert lru.stats['retained_bytes']<=cap8 and lru.stats['peak_retained_bytes']<=cap8
            lru.clear(); assert lru.stats['cache_entries']==0 and lru.stats['retained_bytes']==0
            before=lru.stats['preparations']; lru.source_strata('C0')
            assert lru.stats['preparations']-before==8
            lru.close()
            for cap_bytes,repeats in ((0,2),(1,1)):
                s=TrainingPreparationSession(PRIVATE/'invented-study.json',cap,protocol,dict(stable),cap_bytes)
                for _ in range(repeats):
                    strata,names=s.source_strata('C0')
                    expected,_=full_run(stable,cap,protocol,'baseline',order=('C0',))
                    exact([(strata,names,original.assemble_corpus('C0',strata))],expected)
                assert s.stats['retained_bytes']==0 and s.stats['cache_entries']==0
                assert s.stats['preparations']==8*repeats and s.stats['skipped_retention']==8*repeats
                s.close()
            for newcap in (cap,capability(attempt_id='fresh-independent-attempt')):
                own_access=SyntheticAccess(stable,newcap)
                with own_access.bind_original():
                    s=TrainingPreparationSession(PRIVATE/'invented-study.json',newcap,protocol,dict(stable))
                    s.source_strata('C0'); assert s.stats['preparations']==8; s.close()
        return {'lru_capacity_bytes':cap8,'capacity_entries':8,'evictions':2,
                'zero_and_oversize_bypass':True,'clear_and_fresh_sessions':True}
    check('lru_zero_oversize_clear_fresh_sessions',retention)

    def invalid_inputs():
        stable=fixtures(); access=SyntheticAccess(stable,cap)
        constructor_cases=0
        with access.bind_original():
            for badcap in (None,capability(role='selection'),capability(role='test'),
                           capability(fixture_ids=tuple(reversed(original.TRAIN_FIXTURES)))):
                expect_error(lambda c=badcap:TrainingPreparationSession(PRIVATE/'invented-study.json',c,protocol,dict(stable)))
                constructor_cases+=1
            for badcapbytes in (-1,True,1.5,'10'):
                expect_error(lambda n=badcapbytes:TrainingPreparationSession(PRIVATE/'invented-study.json',cap,protocol,dict(stable),n))
                constructor_cases+=1
            expect_error(lambda:TrainingPreparationSession(PRIVATE/'invented-study.json',cap,protocol,[])); constructor_cases+=1
            s=TrainingPreparationSession(PRIVATE/'invented-study.json',cap,protocol,dict(stable))
            for badname in ('',None,1,[],{},'c0'):
                expect_error(lambda n=badname:s.source_strata(n))
            s.close()
            f=original.TRAIN_FIXTURES[0]
            invalid_cases=0
            for kind in ('misaligned-target','target-identity','source-identity','observation-dtype','partial-coordinate','period-source-axis','timestamp-drift'):
                owned=dict(fixtures()); obs,truth=owned[f]
                if kind=='misaligned-target': truth=TargetBatch(truth.labels[:-1],truth.observation_digest)
                elif kind=='target-identity': truth=TargetBatch(truth.labels,'bad')
                elif kind=='source-identity': object.__setattr__(obs,'source_digest','bad')
                elif kind=='observation-dtype': object.__setattr__(obs,'period_id',obs.period_id.astype(np.int32))
                elif kind=='partial-coordinate':
                    a=obs.ball_xy.copy(); a[5,0]=np.nan; object.__setattr__(obs,'ball_xy',a)
                elif kind=='period-source-axis':
                    a=obs.source_frame_id.copy(); a[6]+=7; object.__setattr__(obs,'source_frame_id',a)
                else:
                    a=obs.source_time_utc_ns.copy(); a[3]+=4_000_000; object.__setattr__(obs,'source_time_utc_ns',a)
                owned[f]=(obs,truth)
                s=TrainingPreparationSession(PRIVATE/'invented-study.json',cap,protocol,owned)
                expect_error(lambda:s.source_strata('C0')); s.close(); invalid_cases+=1
        return {'constructor_cases':constructor_cases,'invalid_curricula':6,'invalid_observation_target_cases':invalid_cases}
    check('input_validation',invalid_inputs)

    if not args.skip_benchmark:
        def benchmark():
            # New stable fixtures, no acceptance mutations; warmed imports and
            # complete original/candidate workloads receive equal one-run warmups.
            stable=fixtures(); bc=capability(attempt_id='timing-only-invented-attempt')
            for mode in ('baseline','candidate'):
                full_run(stable,bc,protocol,mode)
            times={'baseline':[],'candidate_cold':[],'candidate_warm':[]}
            digests=[]; retained=[]
            for rep in range(args.repeats):
                # Alternate order across paired repetitions to reduce drift bias.
                modes=('baseline','candidate') if rep%2==0 else ('candidate','baseline')
                for mode in modes:
                    gc.collect()
                    started=time.perf_counter()
                    if mode=='baseline':
                        result,_=full_run(stable,bc,protocol,'baseline')
                        elapsed=time.perf_counter()-started
                        times['baseline'].append(elapsed)
                    else:
                        # Constructor included in cold interval; fixture
                        # construction, output hashing and GC are excluded.
                        a=SyntheticAccess(stable,bc)
                        with a.bind_original():
                            session=TrainingPreparationSession(PRIVATE/'invented-study.json',bc,protocol)
                            result,_=full_run(stable,bc,protocol,'candidate',session=session)
                            retained.append(dict(session.stats))
                            cold_elapsed=time.perf_counter()-started
                            warm_started=time.perf_counter()
                            warm_result,_=full_run(stable,bc,protocol,'candidate',session=session)
                            warm_elapsed=time.perf_counter()-warm_started
                            session.close()
                        times['candidate_cold'].append(cold_elapsed)
                        times['candidate_warm'].append(warm_elapsed)
                        assert aggregate_digest(warm_result)==aggregate_digest(result)
                    digests.append(aggregate_digest(result))
            assert len(set(digests))==1, 'timed complete corpus parity'
            medians={k:statistics.median(v) for k,v in times.items()}
            return {'workload':{'fixtures':2,'frames_per_fixture':len(stable[original.TRAIN_FIXTURES[0]][0].frame_id),
                    'slots_per_fixture':6,'curricula':list(ORDER),'strata':24,'includes':'source preparation plus complete corpus assembly; constructor and loader included for cold',
                    'excludes':'fixture generation, output comparison, GC, session close, fitting, model export, inference'},
                    'warmups_per_mode':1,'paired_repeats':args.repeats,'wall_seconds':times,'median_seconds':medians,
                    'baseline_to_cold_median_ratio':medians['baseline']/medians['candidate_cold'],
                    'baseline_to_warm_median_ratio':medians['baseline']/medians['candidate_warm'],
                    'cache_statistics_per_repeat':retained,'corpus_digest':digests[0],
                    'measurement_limits':'Same-process exclusive task compute; wall time includes OS noise; cache retention is not peak process memory; no actual-study/fitting-stage extrapolation.'}
        check('bounded_complete_preparation_benchmark',benchmark)
    check('freeze_unchanged_after_acceptance',lambda:freeze_identity())
    report['passed']=not report['failures']
    report['check_count']=len(report['checks'])+len(report['failures'])
    with output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,indent=2,allow_nan=False); stream.write('\n')
    print(json.dumps({'report':str(output),'passed':report['passed'],'checks':report['check_count'],
                      'failures':len(report['failures'])}),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
