"""Independent invented-only acceptance utilities, prepared before candidate freeze.

No study/cache/model/raw-data path is opened. Auth and adapter are scoped test
stubs. All numerical preparation functions remain the original public source.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from experiments.v3 import training as original
from experiments.v3.contracts import AccessCapability, ObservationBatch, PeriodOrigin, TargetBatch
from experiments.v3.corruption import validate_observations

PUBLIC_FILES = (
    'experiments/v3/training.py', 'experiments/v3/corruption.py',
    'experiments/v3/boundary.py', 'experiments/v3/contracts.py',
    'possession_model/features.py', 'possession_model/evidence.py',
    'possession_model/schema.py', 'experiments/noise_v2/features.py',
)
ORDER = ('C0', 'C1', 'boundary')


def digest_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def public_identity():
    return {name: digest_file(ROOT / name) for name in PUBLIC_FILES}


def capability(**changes):
    return replace(AccessCapability(
        study_digest=hashlib.sha256(b'blind-invented-study').hexdigest(),
        attempt_id='blind-invented-attempt', role='train',
        fixture_ids=original.TRAIN_FIXTURES, process_id=os.getpid(),
        process_creation_time='blind-invented-process',
        reservation_event_digest=hashlib.sha256(b'blind-invented-reservation').hexdigest(),
    ), **changes)


def fixtures(scale=1, label_shift=0):
    """Create observations independently of all targets, with five positive runs.

    Repeated period code 1 is separated by inactive frames; 2/3/4 also occur.
    Sparse UTC samples include distinct slots, and source frame axes reset only
    between runs. Noncanonical NaN payloads test the original canonicalization.
    """
    blocks = [(1,353),(0,7),(2,397),(0,11),(1,337),(3,389),(0,5),(4,431)]
    periods = np.concatenate([np.full(length*scale, p, np.int16) for p,length in blocks])
    n = len(periods)
    slot_ids = ('home-a','home-b','home-c','away-a','away-b','away-c')
    sides = np.array([0,0,0,1,1,1], np.int8)
    slot_digest = hashlib.sha256(json.dumps(list(slot_ids), separators=(',',':')).encode()).hexdigest()
    made = {}
    for fixture_no, fixture in enumerate(original.TRAIN_FIXTURES):
        t = np.arange(n, dtype=np.float64)
        ball = np.column_stack((30 + 6*np.sin(t/601 + fixture_no),
                                26 + 4*np.cos(t/431 + fixture_no))).astype(np.float32)
        positions = np.empty((n,6,2), np.float32)
        for j in range(6):
            positions[:,j,0] = ball[:,0] + (j-2.5)*1.7 + .15*np.sin(t/43+j)
            positions[:,j,1] = ball[:,1] + ((j%3)-1)*2 + .2*np.cos(t/37+j)
        qnan = np.array(0x7fc12345, np.uint32).view(np.float32)
        ball[67+fixture_no:74+fixture_no] = qnan
        ball[1121:1138] = qnan
        positions[109:127,0] = qnan
        positions[788:799,3:] = qnan
        positions[periods == 0] = qnan
        ball[periods == 0] = qnan
        source = np.zeros(n, np.int64)
        time_rows = []
        origins = []
        for run_no,(a,b) in enumerate(original.positive_runs(periods)):
            source[a:b] = 10000*(run_no+1) + np.arange(b-a, dtype=np.int64)
            utc = 1_700_000_000_000_000_000 + fixture_no*10**13 + run_no*10**11
            origins.append(PeriodOrigin(int(periods[a]), int(source[a]), utc))
            for row,slot in ((a,0),(a,6),(min(a+1,b-1),2),((a+b)//2,6)):
                time_rows.append((row,slot,utc+(row-a)*40_000_000))
        time_rows = sorted(set(time_rows))
        obs = ObservationBatch(
            frame_id=np.arange(n,dtype=np.int64), source_frame_id=source,
            period_id=periods.copy(), positions=positions, ball_xy=ball,
            team_of_slot=sides, slot_ids=slot_ids, slot_ids_digest=slot_digest,
            source_time_frame_index=np.array([r[0] for r in time_rows],np.int64),
            source_time_slot=np.array([r[1] for r in time_rows],np.int32),
            source_time_utc_ns=np.array([r[2] for r in time_rows],np.int64),
            period_origins=tuple(origins), fps=25., pitch=(105.3,68.),
            fixture_id=fixture,
            source_digest=hashlib.sha256(('blind-'+fixture).encode()).hexdigest(),
        )
        validate_observations(obs)
        labels = ((np.arange(n)//25 + fixture_no + label_shift)%3).astype(np.int8)
        labels[periods == 0] = -1
        labels[np.arange(n)%109 == 17] = -1
        truth = TargetBatch(labels, hashlib.sha256(('blind-target-link-'+fixture).encode()).hexdigest())
        made[fixture] = (obs,truth)
    return made


class SyntheticAccess:
    def __init__(self, matches, cap):
        self.matches = matches
        self.cap = cap
        self.calls = []
        self.loads = []
        self.denied = set()

    def authorize(self, cap, fixture, kind):
        self.calls.append((fixture,kind))
        if cap is not self.cap or cap.role != 'train' or fixture not in cap.fixture_ids:
            raise original.guard.AccessError('invented test capability rejected')
        if (fixture,kind) in self.denied:
            raise original.guard.AccessError('invented test access revoked')

    def load(self, study, cap, fixture):
        self.authorize(cap,fixture,'observations')
        self.authorize(cap,fixture,'targets')
        self.loads.append(fixture)
        return self.matches[fixture]

    @contextmanager
    def bind_original(self):
        with patch.object(original.guard,'assert_access',self.authorize), patch.object(original,'load_match',self.load):
            yield


def exact(actual, expected, path='value'):
    if isinstance(expected,np.ndarray):
        assert isinstance(actual,np.ndarray), f'{path}: array type'
        assert actual.dtype.str == expected.dtype.str, f'{path}: dtype'
        assert actual.shape == expected.shape, f'{path}: shape'
        assert actual.flags.c_contiguous == expected.flags.c_contiguous, f'{path}: contiguous order'
        assert actual.tobytes(order='C') == expected.tobytes(order='C'), f'{path}: bytes'
    elif type(expected) is dict:
        assert type(actual) is dict and set(actual) == set(expected), f'{path}: dict keys'
        for key in expected:
            exact(actual[key],expected[key],path+'.'+str(key))
    elif type(expected) in (tuple,list):
        assert type(actual) is type(expected), f'{path}: sequence type'
        assert len(actual) == len(expected), f'{path}: sequence length'
        for i,(a,b) in enumerate(zip(actual,expected)):
            exact(a,b,path+f'[{i}]')
    else:
        assert type(actual) is type(expected) and actual == expected, f'{path}: scalar'


def aggregate_digest(value):
    h = hashlib.sha256()
    def take(v):
        if isinstance(v,np.ndarray):
            h.update(b'array'+v.dtype.str.encode()+str(v.shape).encode()+v.tobytes(order='C'))
        elif type(v) is dict:
            h.update(b'dict')
            for k in sorted(v):
                h.update(k.encode()); take(v[k])
        elif type(v) in (list,tuple):
            h.update(type(v).__name__.encode())
            for child in v: take(child)
        else:
            h.update(type(v).__name__.encode()+repr(v).encode())
    take(value)
    return h.hexdigest()


def original_run(matches, cap, protocol, order=ORDER):
    access = SyntheticAccess(matches,cap)
    owned = {}
    outputs = []
    with access.bind_original():
        for name in order:
            strata,names = original._source_strata(PRIVATE/'invented-study.json', cap, name, protocol, owned)
            corpus = original.assemble_corpus(name,strata)
            outputs.append((strata,names,corpus))
    return outputs,access


def write_prepared():
    PRIVATE.mkdir(parents=True, exist_ok=True)
    protocol = PRIVATE/'invented-protocol.json'
    protocol.write_text('{"purpose":"independent invented preparation acceptance","revision":1}\n',encoding='utf-8')
    prepared = {
        'status':'oracles prepared before candidate inspection',
        'public_source_sha256':public_identity(),
        'curriculum_order':list(ORDER),
        'baseline_expensive_calls':{'condition_observations':24,'build_features':24,
                                    'condition_receipt':24,'feature_matrix':16,'build_boundary_features':8},
        'unique_fixture_condition_pairs':10,
        'required_cases':[
            'whole-corpus exact bytes/dtypes/order/NaN/metadata/provenance',
            'all curricula with repeats and alternate order',
            'authorization on warm hits and protocol identity drift',
            'observation-content/schema drift and target-only mutation',
            'bounded LRU, oversize entries, zero cap and clear',
            'immutable owned entries and returned diagnostics/arrays cannot poison hits',
            'fresh sessions, train-only capabilities, invalid inputs, close forbids reuse',
        ],
        'timing_predeclared':{
            'grant_required':True,'workload':'two independently invented fixtures; C0/C1/boundary source plus assembly; no fitting',
            'warmups':1,'paired_repeats':3,
            'scenarios':['original repeated preparation','candidate fresh session cold curriculum sequence',
                         'candidate same session warmed curriculum sequence'],
            'measurement':'same process perf_counter around complete source+assembly workload; retained bytes from stats; isolated compute',
            'limits':'synthetic CPU preparation only; no actual study speedup, fitting, inference, export, official validator or package E2E claim',
        },
    }
    (PRIVATE/'prepared-oracles.json').write_text(json.dumps(prepared,indent=2)+'\n',encoding='utf-8')
    return prepared


if __name__ == '__main__':
    prepared = write_prepared()
    outputs,access = original_run(fixtures(),capability(),PRIVATE/'invented-protocol.json')
    print(json.dumps({'prepared':True,'synthetic_oracle_digest':aggregate_digest(outputs),
                      'curricula':len(outputs),'strata':sum(len(v[0]) for v in outputs),
                      'corpus_rows':[len(v[2][1]) for v in outputs],
                      'access_calls':len(access.calls),'adapter_calls':len(access.loads)}))
