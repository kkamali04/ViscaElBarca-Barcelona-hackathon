"""Frozen v3 prediction core. Runtime dependencies are stdlib and NumPy only.

Features are already finalized once by corruption.finalize_features. This module
never opens inputs, reads targets, smooths motion again, or imports training code.
"""
from __future__ import annotations

import math
import re
import numpy as np

from possession_model.evidence import feature_matrix
from possession_model.trees import TreeModel
from .contracts import CandidateConfig, ModelBundle, InferencePolicy
from .boundary import NumericHead, _validate_features, build_boundary_features, boundary_support, flatten_support
from .decoder import decode_change_aware

TRANSFORM = 'accepted-streaming-v1+noise-v2-local-linear-1.2s'
CANDIDATES = (
    ('A','accepted',0.,'none'),
    ('F080','accepted',.8,'flattened_valid_run_mean'),
    ('B080','accepted',.8,'learned'),
    ('C0','C0',0.,'none'), ('C1','C1',0.,'none'),
    ('D0050','C0',.5,'learned'), ('D0080','C0',.8,'learned'),
    ('D1050','C1',.5,'learned'), ('D1080','C1',.8,'learned'))


def candidate_config(candidate_id: str) -> CandidateConfig:
    matches = [row for row in CANDIDATES if row[0] == candidate_id]
    if type(candidate_id) is not str or len(matches) != 1:
        raise ValueError('undeclared candidate')
    row = matches[0]
    return CandidateConfig(row[0], row[2], row[3], .5)


def validate_registry(protocol: dict) -> None:
    expected = [dict(id=i, emitter=e, alpha=a, support=s) for i,e,a,s in CANDIDATES]
    if protocol.get('candidates') != expected:
        raise ValueError('exact nine candidate registry required')
    for row in protocol['candidates']:
        if type(row['alpha']) not in (int,float) or not math.isfinite(row['alpha']):
            raise ValueError('real finite alpha required')


def validate_prepared_features(features) -> int:
    n = _validate_features(features)
    if (type(features.metadata) is not dict or features.metadata.get('v3_feature_transform') != TRANSFORM
            or features.metadata.get('ball_motion_transform') != 'noise-v2-local-linear-1.2s'):
        raise ValueError('exact once-finalized v3 features required')
    if not np.isin(features.period_id, [0,1,2,3,4]).all():
        raise ValueError('invalid period IDs')
    return n


def predict_codes(features, models: ModelBundle, config: CandidateConfig,
                  policy: InferencePolicy) -> np.ndarray:
    n = validate_prepared_features(features)
    if (type(config) is not CandidateConfig or config != candidate_config(config.candidate_id)
            or type(config.alpha) not in (int,float) or type(config.transition_seconds) not in (int,float)):
        raise ValueError('canonical candidate configuration required')
    if (type(models) is not ModelBundle or type(models.emitter) is not TreeModel
            or type(models.manifest_digest) is not str or not re.fullmatch('[0-9a-f]{64}', models.manifest_digest)):
        raise ValueError('verified numeric model bundle required')
    if config.support == 'none':
        if models.head is not None:
            raise ValueError('constant candidate must not carry a head')
    elif type(models.head) is not NumericHead:
        raise ValueError('boundary candidate requires exact shared numeric head')
    if type(policy) is not InferencePolicy or type(policy.forced_dead) is not tuple:
        raise ValueError('typed inference policy required')
    if policy.kind == 'external':
        if policy.forced_dead:
            raise ValueError('external study has no forced intervals')
    elif policy.kind == 'challenge':
        if policy.forced_dead != ((110808,113742),) or n != 199319:
            raise ValueError('exact public challenge interval/length required')
        expected = np.zeros(n,np.int16)
        expected[11185:90652] = 1; expected[110808:190198] = 2
        if not np.array_equal(features.period_id,expected):
            raise ValueError('public challenge periods mismatch')
        del expected
    else:
        raise ValueError('unknown inference policy')
    matrix, names, _ = feature_matrix(features)
    scores = models.emitter.scores(matrix,names)
    del matrix
    for start,stop in policy.forced_dead:
        if type(start) is not int or type(stop) is not int:
            raise ValueError('integer forced intervals required')
        scores[start:stop,:2] = -np.inf
        scores[start:stop,2] = 0.
    if config.support == 'none':
        q = np.zeros((n,2),np.float32)
    else:
        batch = build_boundary_features(features)
        q = boundary_support(models.head,batch)
        if config.support == 'flattened_valid_run_mean':
            q = flatten_support(q,features.period_id,batch.valid)
        del batch
    costs = np.full((3,3),config.transition_seconds*features.fps,np.float64)
    np.fill_diagonal(costs,0.)
    result = decode_change_aware(scores,features.period_id,costs,q,config.alpha)
    result[result < 0] = 3
    return result
