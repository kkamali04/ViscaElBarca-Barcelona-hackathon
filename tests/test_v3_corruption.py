"""Invented observations and independent numerical oracles; no match inputs."""
import dataclasses
import hashlib
import json
import unittest
import numpy as np

from experiments.v3.contracts import ObservationBatch, PeriodOrigin
from experiments.v3.corruption import condition_observations, build_features, validate_observations,CONDITIONS,seed_streams,condition_receipt,capped_row_ids
from experiments.v3.corruption import finalize_features
from possession_model.features import FeatureAccumulator
from possession_model.schema import FeatureSet
from experiments.noise_v2.features import robustify_ball_motion


def invented(n=137):
    ids = ('h1', 'h2', 'a1')
    times = np.arange(n, dtype=np.int64)*40_000_000
    def ro(x):
        x.flags.writeable = False
        return x
    return ObservationBatch(
        frame_id=ro(np.arange(n, dtype=np.int64)), source_frame_id=ro(np.arange(n, dtype=np.int64)),
        period_id=ro(np.r_[np.ones(62), np.zeros(3), np.full(n-65, 2)].astype(np.int16)),
        positions=ro(np.arange(n*6, dtype=np.float32).reshape(n,3,2)/100),
        ball_xy=ro(np.arange(n*2, dtype=np.float32).reshape(n,2)/10),
        team_of_slot=ro(np.array([0,0,1], dtype=np.int8)), slot_ids=ids,
        slot_ids_digest=hashlib.sha256(json.dumps(list(ids),ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),
        source_time_frame_index=ro(np.arange(n,dtype=np.int64)),
        source_time_slot=ro(np.full(n,3,dtype=np.int32)), source_time_utc_ns=ro(times),
        period_origins=(PeriodOrigin(1,0,0),PeriodOrigin(2,65,2_600_000_000)),
        fps=25., pitch=(105.,68.), fixture_id='invented', source_digest='a'*64)


class CorruptionTests(unittest.TestCase):
    def test_combined_full_draw_oracle(self):
        obs=invented(); before=obs.positions.tobytes(); seeds={k:i+7 for i,k in enumerate(('jitter','player_dropout','ball_gap','teleport'))}
        spec={'id':'combined','kind':'combined','ball_block_seconds':4,'ball_block_probability':.4,'player_block_seconds':1,'player_slot_probability':.3,'jitter_std_metres':.25,'teleport_probability_per_frame':.004,'teleport_metres':20,'order':['fixed_shape_jitter','player_dropout','ball_gap','observed_ball_teleport']}
        got=condition_observations(obs,spec,seeds)
        allxy=np.concatenate((obs.positions,obs.ball_xy[:,None]),axis=1).astype(np.float64)
        noise=np.random.Generator(np.random.PCG64(seeds['jitter'])).standard_normal(allxy.shape,dtype=np.float64)*.25
        active=obs.period_id>0; allxy[active]+=noise[active]
        drop=np.random.Generator(np.random.PCG64(seeds['player_dropout'])); gap=np.random.Generator(np.random.PCG64(seeds['ball_gap']))
        for a,b in ((0,62),(65,137)):
            d=drop.random(((b-a+24)//25,3))<.3
            for j in range(len(d)):
                allxy[a+j*25:min(b,a+(j+1)*25),:3][:,d[j]]=np.nan
            g=gap.random(((b-a+99)//100,))<.4
            for j in range(len(g)):
                if g[j]: allxy[a+j*100:min(b,a+(j+1)*100),3]=np.nan
        tele=np.random.Generator(np.random.PCG64(seeds['teleport'])).random((137,2))
        chosen=(tele[:,0]<.004)&active&np.isfinite(allxy[:,3]).all(axis=1)
        angles=tele[:,1]*(2*np.pi)
        allxy[chosen,3]+=20*np.stack((np.cos(angles[chosen]),np.sin(angles[chosen])),axis=1)
        expected=allxy.astype(np.float32)
        np.testing.assert_array_equal(got.positions,expected[:,:3]); np.testing.assert_array_equal(got.ball_xy,expected[:,3])
        self.assertEqual(before,obs.positions.tobytes()); self.assertFalse(got.positions.flags.writeable)

    def test_stale_original_anchor_and_period_reset(self):
        obs=invented(); seed=38
        got=condition_observations(obs,{'id':'stale_players','kind':'stale_player','block_seconds':2,'per_slot_probability':.15,'anchor':'original coordinate at block_start-1; missing or first block gives NaN; no searchback or cross-period borrowing','ball':'unchanged'},{'stale_players':seed})
        rng=np.random.Generator(np.random.PCG64(seed)); expected=obs.positions.copy()
        for a,b in ((0,62),(65,137)):
            draws=rng.random(((b-a+49)//50,3))<.15
            for j,row in enumerate(draws):
                start=a+50*j
                expected[start:min(start+50,b),row]=np.nan if j==0 else obs.positions[start-1,row]
        np.testing.assert_array_equal(got.positions,expected); self.assertEqual(got.ball_xy.tobytes(),obs.ball_xy.tobytes())

    def test_noncanonical_and_dtype_rejected(self):
        obs=invented()
        with self.assertRaises(ValueError): validate_observations(dataclasses.replace(obs,slot_ids=('h2','h1','a1')))
        with self.assertRaises(ValueError): validate_observations(dataclasses.replace(obs,period_id=obs.period_id.astype(np.int64)))

    def test_feature_types_and_immutability(self):
        obs=invented(); before=obs.ball_xy.tobytes(); f=build_features(obs)
        self.assertEqual(f.period_id.dtype,np.dtype('int16')); self.assertEqual(f.tracked_counts.dtype,np.dtype('int16'))
        self.assertFalse(f.ball_speed.flags.writeable); self.assertEqual(before,obs.ball_xy.tobytes())

    def test_all_six_deterministic_and_target_free_namespace(self):
        obs=invented(701)
        for name,spec in CONDITIONS.items():
            with self.subTest(name=name):
                seeds=seed_streams('0'*64,'train','invented',name)
                a=condition_observations(obs,spec,seeds)
                b=condition_observations(dataclasses.replace(obs,source_digest='f'*64),spec,seeds)
                self.assertEqual(a.positions.tobytes(),b.positions.tobytes()); self.assertEqual(a.ball_xy.tobytes(),b.ball_xy.tobytes())
                self.assertEqual(a.positions[62:65].tobytes(),obs.positions[62:65].tobytes())
                self.assertEqual(a.source_time_utc_ns.tobytes(),obs.source_time_utc_ns.tobytes())
                self.assertEqual(condition_receipt(obs,spec,seeds),condition_receipt(obs,spec,seeds))
    def test_scalar_block_conditions_independent_oracle(self):
        obs=invented(701)
        for name,width,prob,stream in [('ball4',100,.4,'ball_gap'),('ball12',300,.4,'ball_gap'),('view_gap',50,.2,'view_gap')]:
            seed=917; gen=np.random.Generator(np.random.PCG64(seed)); expected_ball=obs.ball_xy.copy(); expected_positions=obs.positions.copy()
            for a,b in ((0,62),(65,701)):
                selected=gen.random(((b-a+width-1)//width,))<prob
                for j,chosen in enumerate(selected):
                    if chosen:
                        sl=slice(a+j*width,min(b,a+(j+1)*width)); expected_ball[sl]=np.nan
                        if name=='view_gap': expected_positions[sl]=np.nan
            result=condition_observations(obs,CONDITIONS[name],{stream:seed})
            np.testing.assert_array_equal(result.ball_xy,expected_ball); np.testing.assert_array_equal(result.positions,expected_positions)
    def test_natural_missing_jitter_draws_and_nan_payload(self):
        obs=invented(); p=obs.positions.copy(); b=obs.ball_xy.copy(); p[5]=np.nan; b[8]=np.nan
        missing=dataclasses.replace(obs,positions=p,ball_xy=b); seeds=seed_streams('a'*64,'test','invented','combined')
        result=condition_observations(missing,CONDITIONS['combined'],seeds)
        whole=condition_observations(obs,CONDITIONS['combined'],seeds)
        np.testing.assert_array_equal(result.positions[6:],whole.positions[6:])
        self.assertTrue(np.isnan(result.positions[5]).all()); self.assertTrue(np.isnan(result.ball_xy[8]).all())
        self.assertTrue(np.all(result.positions.view(np.uint32)[np.isnan(result.positions)]==0x7fc00000))
    def test_nonprotocol_parameters_and_partial_pairs_fail(self):
        obs=invented(); spec={**CONDITIONS['ball4'],'block_probability':.41}
        with self.assertRaises(ValueError): condition_observations(obs,spec,{'ball_gap':1})
        p=obs.positions.copy(); p[0,0,0]=np.nan
        with self.assertRaises(ValueError): dataclasses.replace(obs,positions=p)
    def test_interior_integer_row_cap(self):
        eligible=np.arange(30002,dtype=np.int64)*5
        expected=np.array([eligible[j*30001//29999] for j in range(30000)],dtype=np.int64)
        actual=capped_row_ids(eligible)
        self.assertEqual(actual.tobytes(),expected.tobytes()); self.assertEqual(actual[15000],eligible[15001])
    def test_recipe_exact_nested_types_and_seed_allowlist(self):
        obs=invented(); from unittest.mock import patch
        for name,key,value in [('ball4','block_seconds',4.0),('combined','player_block_seconds',True),('combined','teleport_metres',20.0)]:
            bad={**CONDITIONS[name],key:value}; seeds=seed_streams('a'*64,'train','invented',name)
            for call in (condition_observations,condition_receipt):
                with self.assertRaises(ValueError): call(obs,bad,seeds)
        for seeds in ({'ball_gap':1,'unknown':2},{'ball_gap':1,1:2},{'ball_gap':1,'row_sampling':True}):
            for call in (condition_observations,condition_receipt):
                with self.assertRaises(ValueError): call(obs,CONDITIONS['ball4'],seeds)


class FeatureFinalizerTests(unittest.TestCase):
    names=('period_id','ball_xy','ball_observed','nearest','tracked_counts','collective_speed','ball_speed')
    marker='accepted-streaming-v1+noise-v2-local-linear-1.2s'
    def base(self,obs):
        # Independent accepted extractor invocation; no v3 feature constructor.
        blocks=[(1,0,62),(2,65,len(obs.frame_id))]
        acc=FeatureAccumulator(len(obs.frame_id),obs.team_of_slot,obs.fps,obs.pitch,blocks)
        for i in range(len(obs.frame_id)): acc.push(i,obs.positions[i],obs.ball_xy[i],int(obs.period_id[i]))
        return acc.finish()
    def test_six_conditions_equal_prior_body_bytes(self):
        obs=invented(701); p=obs.positions.copy(); b=obs.ball_xy.copy(); p[110:121]=np.nan; b[189:223]=np.nan
        obs=dataclasses.replace(obs,positions=p,ball_xy=b)
        for name,spec in CONDITIONS.items():
            with self.subTest(condition=name):
                conditioned=condition_observations(obs,spec,seed_streams('7'*64,'train','invented',name))
                base=self.base(conditioned)
                # Frozen pre-refactor transformation uses accepted standalone
                # motion transform directly; v3 helper never enters this oracle.
                expected=robustify_ball_motion(base)
                actual=build_features(conditioned)
                for field in self.names:
                    dtype=np.int16 if field in ('period_id','tracked_counts') else bool if field=='ball_observed' else np.float32
                    self.assertEqual(getattr(actual,field).tobytes(),np.asarray(getattr(expected,field),dtype=dtype).tobytes())
                self.assertEqual(actual.metadata['v3_feature_transform'],self.marker)
    def test_single_transform_raw_immutable_and_optional_digest(self):
        from unittest.mock import patch
        base=self.base(invented(701)); before={name:getattr(base,name).tobytes() for name in self.names}; metadata=dict(base.metadata)
        with patch('experiments.v3.corruption.robustify_ball_motion',wraps=robustify_ball_motion) as transform:
            plain=finalize_features(base); identified=finalize_features(base,'a'*64)
            self.assertEqual(transform.call_count,2)
            with self.assertRaises(ValueError): finalize_features(plain)
            self.assertEqual(transform.call_count,2)
        self.assertEqual(before,{name:getattr(base,name).tobytes() for name in self.names}); self.assertEqual(metadata,base.metadata)
        self.assertNotIn('slot_ids_digest',plain.metadata)
        self.assertEqual({**plain.metadata,'slot_ids_digest':'a'*64},identified.metadata)
        for name in self.names:
            left,right=getattr(plain,name),getattr(identified,name)
            self.assertEqual(left.tobytes(),right.tobytes()); self.assertFalse(left.flags.writeable)
            self.assertFalse(np.shares_memory(left,getattr(base,name)))
    def test_validation_overflow_mask_and_marker(self):
        base=self.base(invented())
        counts=base.tracked_counts.astype(np.int64); counts[0,0]=32768
        with self.assertRaises(ValueError): finalize_features(dataclasses.replace(base,tracked_counts=counts))
        nearest=base.nearest.astype(np.float64); nearest[0,0]=1e100
        with self.assertRaises(ValueError): finalize_features(dataclasses.replace(base,nearest=nearest))
        observed=base.ball_observed.copy(); observed[0]=False
        with self.assertRaises(ValueError): finalize_features(dataclasses.replace(base,ball_observed=observed))
        with self.assertRaises(ValueError): finalize_features(dataclasses.replace(base,metadata={'v3_feature_transform':'different'}))
        with self.assertRaises(ValueError): finalize_features(base,'bad-digest')
    def test_metadata_deep_ownership_pitch_and_target_key_refusal(self):
        base=self.base(invented()); diagnostic={'outer':{'inner':[1,2]}}
        raw=dataclasses.replace(base,metadata={**base.metadata,'diagnostic':diagnostic},pitch=[105.,68.])
        result=finalize_features(raw); diagnostic['outer']['inner'].append(3); raw.pitch[0]=120.
        self.assertEqual(result.metadata['diagnostic'],{'outer':{'inner':[1,2]}}); self.assertEqual(result.pitch,(105.,68.))
        for metadata in ({'targets':[0,1]},{'diagnostic':{'BallPossession':[1]}},{'diagnostic':{'bad':float('nan')}},{'diagnostic':np.array([1])}):
            with self.assertRaises(ValueError): finalize_features(dataclasses.replace(base,metadata=metadata))
        with self.assertRaises(ValueError): finalize_features(dataclasses.replace(base,pitch=(True,68.)))

if __name__=='__main__': unittest.main()
