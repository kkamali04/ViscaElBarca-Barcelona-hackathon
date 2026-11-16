"""Pure, label-free v3 coordinate conditions and accepted dense features.

Logical full Generator calls are deliberate: changing chunk partitions, normal
generators, stream names or intermediate casts changes the declared experiment.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from typing import Mapping
import numpy as np

from .contracts import ObservationBatch,PeriodOrigin
from possession_model.features import FeatureAccumulator
from possession_model.schema import FeatureSet
from experiments.noise_v2.features import robustify_ball_motion

STREAMS = ('ball_gap', 'player_dropout', 'jitter', 'teleport', 'stale_players',
           'view_gap', 'row_sampling', 'boundary_none_sampling')
CONDITIONS = {
    'clean': {'id':'clean','kind':'identity'},
    'ball4': {'id':'ball4','kind':'ball_gap','block_seconds':4,'block_probability':.4},
    'ball12': {'id':'ball12','kind':'ball_gap','block_seconds':12,'block_probability':.4},
    'combined': {'id':'combined','kind':'combined','ball_block_seconds':4,'ball_block_probability':.4,
                 'player_block_seconds':1,'player_slot_probability':.3,'jitter_std_metres':.25,
                 'teleport_probability_per_frame':.004,'teleport_metres':20,
                 'order':['fixed_shape_jitter','player_dropout','ball_gap','observed_ball_teleport']},
    'stale_players': {'id':'stale_players','kind':'stale_player','block_seconds':2,'per_slot_probability':.15,
                      'anchor':'original coordinate at block_start-1; missing or first block gives NaN; no searchback or cross-period borrowing',
                      'ball':'unchanged'},
    'view_gap': {'id':'view_gap','kind':'joint_missing','block_seconds':2,'block_probability':.2,
                 'channels':['ball','all_players']},
}
REQUIRED_STREAMS={'clean':frozenset(),'ball4':frozenset({'ball_gap'}),'ball12':frozenset({'ball_gap'}),
    'combined':frozenset({'jitter','player_dropout','ball_gap','teleport'}),
    'stale_players':frozenset({'stale_players'}),'view_gap':frozenset({'view_gap'})}


def plain_diagnostic_metadata(metadata: dict) -> dict:
    """Validate/copy plain JSON diagnostics, with no target-bearing keys.

    Raw extractors may attach additional diagnostics. Cache wire metadata has a
    separate, closed producer allowlist; neither boundary permits labels/targets.
    Recursive copying ensures finalized metadata never aliases caller containers.
    """
    def copy(value):
        if value is None or type(value) in (bool,int,str): return value
        if type(value) is float:
            if not np.isfinite(value): raise ValueError('nonfinite diagnostic number')
            return value
        if type(value) is list: return [copy(x) for x in value]
        if type(value) is dict:
            result={}
            for key,item in value.items():
                if type(key) is not str or any(token in key.casefold() for token in ('label','target','truth','ballpossession','ballstatus')):
                    raise ValueError('invalid/target-bearing diagnostic key')
                result[key]=copy(item)
            return result
        raise ValueError('diagnostics require plain JSON values')
    if type(metadata) is not dict: raise ValueError('diagnostic metadata must be a plain dict')
    return copy(metadata)


def _exact_recipe(value,reference):
    if type(value) is not type(reference): return False
    if type(reference) is dict:
        return set(value)==set(reference) and all(_exact_recipe(value[k],reference[k]) for k in reference)
    if type(reference) is list:
        return len(value)==len(reference) and all(_exact_recipe(x,y) for x,y in zip(value,reference))
    return value==reference


def validate_condition_inputs(spec: dict,seeds: Mapping[str,int]) -> str:
    """Closed recipe types and known stream identities; no RNG calls here."""
    if type(spec) is not dict or type(spec.get('id')) is not str or spec['id'] not in CONDITIONS or not _exact_recipe(spec,CONDITIONS[spec['id']]):
        raise ValueError('condition must exactly match frozen protocol types/values')
    if not isinstance(seeds,Mapping) or any(type(k) is not str or k not in STREAMS or type(v) is not int or not 0<=v<2**64 for k,v in seeds.items()):
        raise ValueError('known string streams and exact uint64 seed integers required')
    if not REQUIRED_STREAMS[spec['id']].issubset(seeds): raise ValueError('missing active stream seeds')
    return spec['id']


def seed_streams(protocol_sha256: str, role: str, fixture_id: str, condition: str) -> dict[str,int]:
    if type(protocol_sha256) is not str or len(protocol_sha256)!=64 or any(c not in '0123456789abcdef' for c in protocol_sha256):
        raise ValueError('invalid protocol digest')
    if type(role) is not str or role not in ('train','selection','test') or type(condition) is not str or condition not in CONDITIONS or type(fixture_id) is not str or not fixture_id or '|' in fixture_id:
        raise ValueError('invalid random namespace')
    return {s:int.from_bytes(hashlib.sha256(f'v3|{protocol_sha256}|{role}|IDSSE|{fixture_id}|{condition}|0|{s}'.encode('utf-8')).digest()[:8],'little') for s in STREAMS}


def positive_runs(periods):
    """Timeline-order contiguous positive runs, including repeated period codes."""
    p=np.asarray(periods)
    edges=np.r_[0,np.flatnonzero(p[1:]!=p[:-1])+1,len(p)]
    return [(int(a),int(b)) for a,b in zip(edges[:-1],edges[1:]) if b>a and p[a]>0]


def capped_row_ids(eligible_ids: np.ndarray,cap: int=30000) -> np.ndarray:
    """Exact integer-only protocol cap; dense features are computed beforehand."""
    if not isinstance(eligible_ids,np.ndarray) or eligible_ids.dtype!=np.dtype('int64') or eligible_ids.ndim!=1 or np.any(eligible_ids<0) or np.any(eligible_ids[1:]<=eligible_ids[:-1]) or type(cap) is not int or cap!=30000:
        raise ValueError('ascending int64 IDs and fixed30000 cap required')
    size=len(eligible_ids)
    if size<=cap: result=eligible_ids.copy()
    else: result=eligible_ids[np.arange(cap,dtype=np.int64)*(size-1)//(cap-1)].copy()
    result.flags.writeable=False
    return result


def validate_observations(obs: ObservationBatch) -> None:
    if type(obs) is not ObservationBatch:
        raise ValueError('ObservationBatch required')
    n=len(obs.frame_id); s=len(obs.slot_ids); r=len(obs.source_time_slot)
    for name,dtype,shape in (
        ('frame_id','int64',(n,)),('source_frame_id','int64',(n,)),('period_id','int16',(n,)),
        ('positions','float32',(n,s,2)),('ball_xy','float32',(n,2)),('team_of_slot','int8',(s,)),
        ('source_time_frame_index','int64',(r,)),('source_time_slot','int32',(r,)),('source_time_utc_ns','int64',(r,))):
        a=getattr(obs,name)
        if not isinstance(a,np.ndarray) or a.dtype!=np.dtype(dtype) or a.shape!=shape:
            raise ValueError('invalid observation array '+name)
    if n==0 or s==0 or not np.array_equal(obs.frame_id,np.arange(n,dtype=np.int64)):
        raise ValueError('empty or nondense observations')
    if not np.isin(obs.period_id,[0,1,2,3,4]).all() or (obs.source_frame_id<0).any():
        raise ValueError('invalid period/source frame')
    for a,b in positive_runs(obs.period_id):
        if not np.array_equal(np.diff(obs.source_frame_id[a:b]),np.ones(b-a-1,dtype=np.int64)):
            raise ValueError('source frame axis is not dense within period')
    if not np.isfinite(obs.fps) or abs(obs.fps-25)>1e-6 or len(obs.pitch)!=2 or not all(np.isfinite(x) and x>0 for x in obs.pitch):
        raise ValueError('invalid fps/pitch')
    if set(obs.team_of_slot.tolist())!={0,1} or any(type(x) is not str or not x for x in obs.slot_ids) or len(set(obs.slot_ids))!=s:
        raise ValueError('invalid roster')
    order=sorted(range(s),key=lambda i:(int(obs.team_of_slot[i]),obs.slot_ids[i].encode('utf-8')))
    digest=hashlib.sha256(json.dumps(list(obs.slot_ids),ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest()
    if order!=list(range(s)) or digest!=obs.slot_ids_digest:
        raise ValueError('noncanonical slots/digest')
    for arr in (obs.positions,obs.ball_xy):
        finite=np.isfinite(arr)
        if np.isinf(arr).any() or np.any(finite.any(axis=-1)!=finite.all(axis=-1)):
            raise ValueError('nonfinite/partial pair in typed observations')
    if r:
        f=obs.source_time_frame_index; slots=obs.source_time_slot
        if (f<0).any() or (f>=n).any() or (slots<0).any() or (slots>s).any():
            raise ValueError('invalid sparse timestamps')
        if np.any((f[1:]<f[:-1])|((f[1:]==f[:-1])&(slots[1:]<=slots[:-1]))):
            raise ValueError('noncanonical sparse timestamps')
    runs=positive_runs(obs.period_id)
    if len(obs.period_origins)!=len(runs): raise ValueError('one origin per positive run required')
    for (a,b),origin in zip(runs,obs.period_origins):
        if type(origin) is not PeriodOrigin or origin.period_id!=int(obs.period_id[a]) or origin.source_frame_id!=int(obs.source_frame_id[a]) or type(origin.utc_ns) is not int:
            raise ValueError('period origin mismatch')
        rows=np.flatnonzero((obs.source_time_frame_index>=a)&(obs.source_time_frame_index<b))
        if not len(rows): raise ValueError('positive period has no timestamps')
        earliest=rows[obs.source_time_frame_index[rows]==a]
        if not len(earliest): raise ValueError('period origin frame missing')
        ball=earliest[obs.source_time_slot[earliest]==s]
        chosen=int(ball[0] if len(ball) else earliest[0])
        if int(obs.source_time_utc_ns[chosen])!=origin.utc_ns: raise ValueError('noncanonical timestamp origin')
        for j in rows:
            expected=origin.utc_ns+(int(obs.source_frame_id[obs.source_time_frame_index[j]])-origin.source_frame_id)*40_000_000
            if abs(int(obs.source_time_utc_ns[j])-expected)>1_000_000: raise ValueError('timestamp outside25Hz tolerance')


def condition_observations(obs: ObservationBatch, spec: dict, seeds: Mapping[str,int]) -> ObservationBatch:
    validate_observations(obs)
    name=validate_condition_inputs(spec,seeds); n,s=obs.positions.shape[:2]; runs=positive_runs(obs.period_id)
    def rng(stream):
        seed=seeds.get(stream)
        if type(seed) is not int or not 0<=seed<2**64:
            raise ValueError('missing/invalid stream seed: '+stream)
        return np.random.Generator(np.random.PCG64(seed))
    positions=obs.positions.copy(); ball=obs.ball_xy.copy()
    if name=='combined':
        noise=rng('jitter').standard_normal((n,s+1,2),dtype=np.float64)
        noise*=.25
        work=np.concatenate((positions,ball[:,None,:]),axis=1).astype(np.float64)
        active=(obs.period_id>0)[:,None]&np.isfinite(work).all(axis=-1)
        work[active]+=noise[active]
        del noise
        drop=rng('player_dropout'); gaps=rng('ball_gap')
        for a,b in runs:
            mask=drop.random(((b-a+24)//25,s),dtype=np.float64)<.3
            for j,row in enumerate(mask):
                work[a+j*25:min(b,a+(j+1)*25),:s][:,row]=np.nan
            mask=gaps.random(((b-a+99)//100,),dtype=np.float64)<.4
            for j,chosen in enumerate(mask):
                if chosen: work[a+j*100:min(b,a+(j+1)*100),s]=np.nan
        tele=rng('teleport').random((n,2),dtype=np.float64)
        chosen=(tele[:,0]<.004)&(obs.period_id>0)&np.isfinite(work[:,s]).all(axis=1)
        angle=tele[:,1]*(2*np.pi)
        work[chosen,s,0]+=20*np.cos(angle[chosen]); work[chosen,s,1]+=20*np.sin(angle[chosen])
        if np.isinf(work).any() or np.any(np.abs(work[np.isfinite(work)])>np.finfo(np.float32).max):
            raise ValueError('corruption exceeds float32 range')
        positions=work[:,:s].astype(np.float32); ball=work[:,s].astype(np.float32)
    elif name in ('ball4','ball12'):
        gen=rng('ball_gap'); width=100 if name=='ball4' else 300
        for a,b in runs:
            masks=gen.random(((b-a+width-1)//width,),dtype=np.float64)<.4
            for j,chosen in enumerate(masks):
                if chosen: ball[a+j*width:min(b,a+(j+1)*width)]=np.nan
    elif name=='stale_players':
        gen=rng('stale_players')
        for a,b in runs:
            masks=gen.random(((b-a+49)//50,s),dtype=np.float64)<.15
            for j,row in enumerate(masks):
                start=a+j*50
                positions[start:min(b,start+50),row]=np.nan if j==0 else obs.positions[start-1,row]
    elif name=='view_gap':
        gen=rng('view_gap')
        for a,b in runs:
            masks=gen.random(((b-a+49)//50,),dtype=np.float64)<.2
            for j,chosen in enumerate(masks):
                if chosen:
                    positions[a+j*50:min(b,a+(j+1)*50)]=np.nan
                    ball[a+j*50:min(b,a+(j+1)*50)]=np.nan
    # Assigned NaNs always have one canonical float32 payload. Existing missing
    # values are normalized too; valid raw ingestion has already canonicalized.
    for arr in (positions,ball):
        missing=~np.isfinite(arr).all(axis=-1)
        arr[missing]=np.array(0x7fc00000,dtype=np.uint32).view(np.float32)
        arr.flags.writeable=False
    return replace(obs,positions=positions,ball_xy=ball)


def build_features(obs: ObservationBatch) -> FeatureSet:
    validate_observations(obs)
    blocks=[(int(obs.period_id[a]),a,b) for a,b in positive_runs(obs.period_id)]
    accumulator=FeatureAccumulator(len(obs.frame_id),obs.team_of_slot,obs.fps,obs.pitch,blocks)
    for i in range(len(obs.frame_id)):
        accumulator.push(i,obs.positions[i],obs.ball_xy[i],int(obs.period_id[i]))
    return finalize_features(accumulator.finish(),obs.slot_ids_digest)


def finalize_features(base: FeatureSet,slot_ids_digest: str|None=None) -> FeatureSet:
    """Finalize a raw accepted accumulator result exactly once for v3.

    External Sportec and observation-only ATD extractors share this entry point.
    The core consumes its marked output directly; it must never smooth again.
    Input arrays/metadata are not mutated or aliased by the owned final arrays.
    """
    marker='accepted-streaming-v1+noise-v2-local-linear-1.2s'
    if type(base) is not FeatureSet or type(base.metadata) is not dict:
        raise ValueError('raw FeatureSet and metadata required')
    metadata_copy=plain_diagnostic_metadata(base.metadata)
    if 'v3_feature_transform' in base.metadata or base.metadata.get('ball_motion_transform')=='noise-v2-local-linear-1.2s':
        raise ValueError('features are already transformed')
    if slot_ids_digest is not None and (type(slot_ids_digest) is not str or len(slot_ids_digest)!=64 or any(c not in '0123456789abcdef' for c in slot_ids_digest)):
        raise ValueError('invalid optional slot digest')
    if not isinstance(base.period_id,np.ndarray) or base.period_id.ndim!=1 or len(base.period_id)==0:
        raise ValueError('nonempty one-dimensional periods required')
    n=len(base.period_id)
    if type(base.fps) not in (float,int) or not np.isfinite(base.fps) or abs(base.fps-25)>1e-6 or type(base.pitch) not in (tuple,list) or len(base.pitch)!=2 or not all(type(x) in (int,float) and np.isfinite(x) and x>0 for x in base.pitch):
        raise ValueError('native25Hz and positive finite pitch required')
    for name,shape,kind in (
        ('period_id',(n,),'iu'),('ball_xy',(n,2),'f'),('ball_observed',(n,),'b'),('nearest',(n,2),'f'),
        ('tracked_counts',(n,2),'iu'),('collective_speed',(n,2),'f'),('ball_speed',(n,),'f')):
        arr=getattr(base,name)
        if not isinstance(arr,np.ndarray) or arr.shape!=shape or arr.dtype.kind not in kind:
            raise ValueError('invalid raw feature shape/dtype: '+name)
        if arr.dtype.kind=='f' and (np.isinf(arr).any() or np.any(np.abs(arr[np.isfinite(arr)])>np.finfo(np.float32).max)):
            raise ValueError('raw feature exceeds finite float32: '+name)
    if not np.isin(base.period_id,[0,1,2,3,4]).all() or (base.tracked_counts<0).any() or (base.tracked_counts>np.iinfo(np.int16).max).any():
        raise ValueError('period/count conversion range invalid')
    finite=np.isfinite(base.ball_xy)
    if np.any(finite.any(axis=-1)!=finite.all(axis=-1)) or not np.array_equal(finite.all(axis=-1),base.ball_observed):
        raise ValueError('raw ball coordinate/mask mismatch')
    if any(np.any(getattr(base,name)[np.isfinite(getattr(base,name))]<0) for name in ('nearest','collective_speed','ball_speed')):
        raise ValueError('negative raw distance/speed')
    features=robustify_ball_motion(replace(base,metadata=metadata_copy,pitch=tuple(base.pitch)))
    fields={name:np.array(getattr(features,name),dtype=dtype,copy=True,order='C') for name,dtype in (
        ('period_id','int16'),('ball_xy','float32'),('ball_observed','bool'),('nearest','float32'),
        ('tracked_counts','int16'),('collective_speed','float32'),('ball_speed','float32'))}
    for arr in fields.values(): arr.flags.writeable=False
    metadata=plain_diagnostic_metadata(features.metadata)
    metadata.pop('slot_ids_digest',None)
    metadata['v3_feature_transform']=marker
    if slot_ids_digest is not None: metadata['slot_ids_digest']=slot_ids_digest
    return FeatureSet(fps=base.fps,pitch=tuple(base.pitch),metadata=metadata,**fields)


def condition_receipt(obs: ObservationBatch,spec: dict,seeds: Mapping[str,int]) -> dict:
    """Aggregate-only reproducibility receipt, independent of all target values.

    Replays the declared streams to hash their logical masks. No observation
    records or arrays are returned. Callers may save this alongside their study
    result. Its computation is outside the feature graph and the RNG root.
    """
    validate_observations(obs)
    name=validate_condition_inputs(spec,seeds); n,s=obs.positions.shape[:2]; runs=positive_runs(obs.period_id); masks={}; counts={}
    selected_ball=np.zeros(n,dtype=bool); selected_players=np.zeros((n,s),dtype=bool)
    def generator(stream):
        seed=seeds.get(stream)
        if type(seed) is not int or not 0<=seed<2**64: raise ValueError('missing stream seed')
        return np.random.Generator(np.random.PCG64(seed))
    def blocks(stream,width,prob,players=False):
        gen=generator(stream); digest=hashlib.sha256(); chosen=0
        for a,b in runs:
            shape=((b-a+width-1)//width,s) if players else ((b-a+width-1)//width,)
            mask=gen.random(shape,dtype=np.float64)<prob; digest.update(mask.tobytes()); chosen+=int(mask.sum())
            for j,row in enumerate(mask):
                if players: selected_players[a+j*width:min(b,a+(j+1)*width)]|=row
                elif row: selected_ball[a+j*width:min(b,a+(j+1)*width)]=True
        masks[stream]=digest.hexdigest(); counts[stream+'_selected_blocks']=chosen
    if name in ('ball4','ball12','combined'): blocks('ball_gap',300 if name=='ball12' else 100,.4)
    if name=='combined':
        blocks('player_dropout',25,.3,True)
        # Full noise draw is hashed once and released, not stored in a receipt.
        noise=generator('jitter').standard_normal((n,s+1,2),dtype=np.float64)
        masks['jitter_draws']=hashlib.sha256(noise.tobytes()).hexdigest(); del noise
        draw=generator('teleport').random((n,2),dtype=np.float64)
        chosen=(draw[:,0]<.004)&(obs.period_id>0)
        masks['teleport_draws']=hashlib.sha256(draw.tobytes()).hexdigest()
        counts['teleport_drawn_active_frames']=int(chosen.sum())
        counts['teleport_applied_observed_frames']=int((chosen&~selected_ball&np.isfinite(obs.ball_xy).all(axis=1)).sum())
    if name=='stale_players': blocks('stale_players',50,.15,True)
    if name=='view_gap': blocks('view_gap',50,.2)
    counts['selected_ball_frames']=int(selected_ball.sum()); counts['selected_player_slot_frames']=int(selected_players.sum())
    return {'schema_version':1,'condition':name,'seeds':dict(seeds),'numpy_version':np.__version__,'mask_hashes':masks,'counts':counts}
