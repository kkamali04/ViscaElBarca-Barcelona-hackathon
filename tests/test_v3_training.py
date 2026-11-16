import unittest
import hashlib
import json
from pathlib import Path
import tempfile
import numpy as np

from experiments.v3.training import (emitter_rows, normalize_weights, boundary_population, sample_boundary,
    emitter_stratum, assemble_corpus, array_digest, CURRICULA, TRAIN_FIXTURES, fit_numeric)
from experiments.v3.boundary import BOUNDARY_NAMES, TREE_PARAMETERS, FEATURE_VERSION, WEIGHT_RECIPE


def synthetic_provenance(name):
    p={key:hashlib.sha256(key.encode()).hexdigest() for key in ('study_digest','scientific_source_digest',
        'protocol_digest','split_digest','metric_digest','dependency_digest')}
    p['training_input_digests']=[dict(fixture_id=f,condition=c,observation_digest='1'*64,
        target_digest='2'*64,sampling_digest='3'*64) for f in TRAIN_FIXTURES for c in CURRICULA[name]]
    if name=='boundary':
        p.update(weight_recipe=WEIGHT_RECIPE,feature_version=FEATURE_VERSION,fps=25.,windows_frames=[5,15],
            coverage=.8,temperature=1.,tree_parameters=TREE_PARAMETERS,random_state=20261116)
    return p


def invented_strata(name, width=4):
    out=[]
    for f in TRAIN_FIXTURES:
        for c in CURRICULA[name]:
            y=np.array([0,0,0,1,1,2],np.int8)
            x=np.arange(6*width,dtype=np.float32).reshape(6,width)
            s=dict(fixture_id=f,condition=c,x=x,y=y,population_counts=np.array([30,2,1]))
            if name=='boundary': s['inclusion']=np.array([.1,.1,.1,1,1,1])
            else: s['weights']=np.array([1/72]*3+[1/48]*2+[1/24])
            out.append(s)
    return out


class TrainingTests(unittest.TestCase):
    def test_stride_restarts_and_known_filter(self):
        p = np.array([1]*8+[2]*8, np.int16)
        y = np.zeros(16, np.int8); y[5] = -1
        np.testing.assert_array_equal(emitter_rows(y, p), [0, 8, 13])

    def test_global_mean_one(self):
        w = normalize_weights(np.array([.1, .2, .7], np.float64))
        self.assertAlmostEqual(float(w.mean()), 1.)
        np.testing.assert_allclose(w / w.sum(), [.1, .2, .7])

    def test_global_scale_preserves_declared_l2_leaf_objective(self):
        # Independently minimize sum_i w_i*(g_i*v + h_i*v*v/2) + 2*v*v/2.
        # A stratum-total-normalized vector alone changes the relative L2 term.
        raw=np.full(12,1/96,dtype=np.float64)
        weights=normalize_weights(raw)
        gradients=np.array([-2/3]*8+[1/3]*4)
        hessians=np.full(12,2/9)
        fitted_leaf=-np.dot(weights,gradients)/(np.dot(weights,hessians)+2.)
        expected=(8*(2/3)-4*(1/3))/(12*(2/9)+2.)
        self.assertAlmostEqual(fitted_leaf,expected)
        wrong_leaf=-np.dot(raw,gradients)/(np.dot(raw,hessians)+2.)
        self.assertGreater(abs(fitted_leaf-wrong_leaf),.5)

    def test_boundary_edges(self):
        p = np.array([1,1,1,1,1,2,2], np.int16)
        y = np.array([0,1,2,-1,0,1,1], np.int8)
        ids, labels = boundary_population(y, p, np.ones((7,2), bool))
        np.testing.assert_array_equal(ids, [1,2,6])
        np.testing.assert_array_equal(labels, [1,2,0])

    def test_exact_integer_cap_interior(self):
        n=150010
        result=emitter_rows(np.zeros(n,np.int8),np.ones(n,np.int16))
        eligible=np.arange(0,n,5,dtype=np.int64)
        expected=np.array([eligible[j*(len(eligible)-1)//29999] for j in range(30000)])
        np.testing.assert_array_equal(result,expected)

    def test_side_copy_weights_and_pairs(self):
        x=np.arange(24,dtype=np.float32).reshape(6,4); y=np.array([0,0,0,1,1,2],np.int8)
        a,b,w,count=emitter_stratum(x,y,np.arange(6,dtype=np.int64),[(0,1),(2,3)])
        np.testing.assert_array_equal(a[6:],x[:,[1,0,3,2]])
        np.testing.assert_array_equal(b[6:],[1,1,1,0,0,2])
        for label in range(3): self.assertAlmostEqual(float(w[:6][y==label].sum()),1/48)
        self.assertAlmostEqual(float(w.sum()),1/8)

    def test_emitter_missing_class_refused(self):
        with self.assertRaises(ValueError):
            emitter_stratum(np.zeros((5,2),np.float32),np.zeros(5,np.int8),np.arange(5,dtype=np.int64),[(0,1)])

    def test_sampling_inclusion_matches_independent_rng(self):
        ids=np.arange(1003,dtype=np.int64); target=np.zeros(1003,np.int8); target[-3:]=[1,2,1]
        chosen,y,pi,counts=sample_boundary(ids,target,123)
        rng=np.random.Generator(np.random.PCG64(123))
        expected=np.sort(np.r_[rng.choice(1000,size=60,replace=False,shuffle=True),[1000,1001,1002]])
        np.testing.assert_array_equal(chosen,expected)
        np.testing.assert_array_equal(counts,[1000,2,1])
        np.testing.assert_allclose(pi[y==0],.06)
        np.testing.assert_array_equal(pi[y!=0],1.)

    def test_boundary_global_prevalence_and_equal_strata(self):
        strata=invented_strata('boundary'); x,y,w,report=assemble_corpus('boundary',strata)
        self.assertAlmostEqual(float(w.mean()),1.)
        np.testing.assert_allclose(report['stratum_weight_fractions'],np.full(8,1/8))
        raw=np.sqrt(33/(3*np.array([30,30,30,2,2,1])))/np.array([.1,.1,.1,1,1,1])
        np.testing.assert_allclose(w[:6]/w[:6].sum(),raw/raw.sum())

    def test_empty_stratum_and_missing_head_class_refused(self):
        strata=invented_strata('boundary'); strata[0]['y']=np.empty(0,np.int8)
        with self.assertRaises(ValueError): assemble_corpus('boundary',strata)
        strata=invented_strata('boundary')
        for s in strata: s['population_counts'][2]=0
        with self.assertRaises(ValueError): assemble_corpus('boundary',strata)

    def test_typed_digest_changes_for_shape_dtype_or_actual_values(self):
        a=np.arange(4,dtype=np.int8)
        self.assertEqual(len({array_digest(a),array_digest(a.reshape(2,2)),array_digest(a.astype(np.int16)),array_digest(a+1)}),4)

    def test_bad_weights(self):
        for values in ([],[0,1],[-1,2],[np.nan,1],[np.inf,1]):
            with self.assertRaises(ValueError): normalize_weights(np.array(values))

    def test_boundary_unknown_and_period_start_excluded(self):
        y=np.array([0,1,2,0,-1,2,0,1],np.int8); p=np.array([1,1,1,1,1,1,2,2],np.int16)
        mask=np.ones((8,2),bool); mask[2,0]=False
        ids,target=boundary_population(y,p,mask)
        np.testing.assert_array_equal(ids,[1,3,7]); np.testing.assert_array_equal(target,[1,2,1])


if __name__ == '__main__': unittest.main()
