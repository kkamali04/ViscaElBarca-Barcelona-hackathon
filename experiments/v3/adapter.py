"""Guarded public Sportec schema adapter; no legacy loaders or target features."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import numpy as np

from .contracts import AccessCapability, ObservationBatch, TargetBatch, PeriodOrigin
from .cache import (ReadLease, verify_cache, write_cache_atomic, canonical_json,
                    digest_json, confined_path, OBSERVATION_ARRAYS)

PERIODS={'firstHalf':1,'secondHalf':2,'firstHalfExtra':3,'secondHalfExtra':4}
TIME=re.compile(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})\Z')
INTEGER=re.compile(r'[0-9]+\Z')
NAN=np.array(0x7fc00000,dtype=np.uint32).view(np.float32)


def parse_timestamp_ns(text: str) -> int:
    if type(text) is not str or not (m:=TIME.fullmatch(text)):
        raise ValueError('timezone-aware nanosecond timestamp required')
    year,month,day,hour,minute,second=(int(x) for x in m.groups()[:6])
    if hour>23 or minute>59 or second>59: raise ValueError('invalid timestamp clock')
    days=(date(year,month,day)-date(1970,1,1)).days
    zone=m[8]; offset=0
    if zone!='Z':
        zh,zm=int(zone[1:3]),int(zone[4:6])
        if zh>23 or zm>59: raise ValueError('invalid UTC offset')
        offset=(zh*60+zm)*60*(1 if zone[0]=='+' else -1)
    ns=((days*86400+hour*3600+minute*60+second-offset)*1_000_000_000+int((m[7] or '').ljust(9,'0')))
    if not -(2**63)<=ns<2**63: raise ValueError('timestamp outside int64')
    return ns


def _name(node): return node.tag.rsplit('}',1)[-1]


def _frames(stream):
    """Remove completed children, including empty Frame nodes, bounded XML tree."""
    stream.seek(0); stack=[]; current=None
    for event,node in ET.iterparse(stream,events=('start','end')):
        tag=_name(node)
        if event=='start':
            stack.append(node)
            if tag=='FrameSet':
                if current is not None: raise ValueError('nested FrameSet')
                current=dict(node.attrib)
        else:
            if tag=='Frame':
                if current is None: raise ValueError('Frame outside FrameSet')
                yield current,dict(node.attrib)
            if tag=='FrameSet': current=None
            if len(stack)>1: stack[-2].remove(node)
            node.clear(); stack.pop()


def _read_metadata(stream):
    stream.seek(0); root=ET.parse(stream).getroot()
    general=[x for x in root.iter() if _name(x)=='General']; env=[x for x in root.iter() if _name(x)=='Environment']
    if len(general)!=1 or len(env)!=1: raise ValueError('one General/Environment required')
    general=general[0]; env=env[0]
    home,away=general.get('HomeTeamId'),general.get('GuestTeamId'); match=general.get('MatchId')
    if not home or not away or home==away or not match: raise ValueError('invalid match/team IDs')
    try: pitch=(float(env.attrib['PitchX']),float(env.attrib['PitchY']))
    except (KeyError,ValueError,TypeError): raise ValueError('invalid pitch') from None
    if not all(np.isfinite(x) and x>0 for x in pitch): raise ValueError('positive finite pitch required')
    roster={}; team_seen=set()
    for team in (x for x in root.iter() if _name(x)=='Team'):
        tid=team.get('TeamId')
        if tid not in (home,away): continue
        if tid in team_seen: raise ValueError('duplicate team roster')
        team_seen.add(tid)
        for player in (x for x in team.iter() if _name(x)=='Player'):
            pid=player.get('PersonId')
            if not pid or pid in roster: raise ValueError('missing/duplicate PersonId')
            roster[pid]=(0 if tid==home else 1,tid)
    if team_seen!={home,away} or {x[0] for x in roster.values()}!={0,1}: raise ValueError('both rosters required')
    ids=tuple(sorted(roster,key=lambda p:(roster[p][0],p.encode('utf-8'))))
    if len(ids)>32767: raise ValueError('roster count exceeds feature int16')
    for node in root.iter():
        for key,value in node.attrib.items():
            if key in ('FrameRate','FramesPerSecond','Fps','FPS'):
                try: declared=float(value)
                except (TypeError,ValueError): raise ValueError('invalid declared fps') from None
                if not np.isfinite(declared) or abs(declared-25)>1e-6: raise ValueError('native25Hz required')
        if _name(node) in ('FrameRate','FramesPerSecond','Fps','FPS'):
            try: fps=float(node.text)
            except (TypeError,ValueError): raise ValueError('invalid declared fps') from None
            if not np.isfinite(fps) or abs(fps-25)>1e-6: raise ValueError('native25Hz required')
    return match,pitch,ids,roster


def _record_info(frameset,frame,match,lookup,roster):
    period=PERIODS.get(frameset.get('GameSection'))
    if period is None: raise ValueError('unsupported GameSection')
    if frameset.get('MatchId')!=match: raise ValueError('tracking/metadata match mismatch')
    n=frame.get('N')
    if type(n) is not str or not INTEGER.fullmatch(n): raise ValueError('nonnegative integer source frame required')
    n=int(n)
    if n>=2**63: raise ValueError('source frame outside int64')
    if frameset.get('TeamId')=='BALL': slot=len(lookup)
    else:
        pid=frameset.get('PersonId')
        if pid not in lookup:
            if frameset.get('TeamId') in {x[1] for x in roster.values()}: raise ValueError('unknown team player')
            return None
        if frameset.get('TeamId')!=roster[pid][1]: raise ValueError('contradictory player side')
        slot=lookup[pid]
    return period,n,slot


def _pair(frame,pitch,stats):
    try: x,y=float(frame['X']),float(frame['Y'])
    except (KeyError,ValueError,TypeError):
        stats['normalized_coordinate_pairs']+=1; return (NAN,NAN)
    if not np.isfinite(x) or not np.isfinite(y):
        stats['normalized_coordinate_pairs']+=1; return (NAN,NAN)
    shifted=np.array((x+pitch[0]/2,y+pitch[1]/2),dtype=np.float64)
    if not np.isfinite(shifted).all() or (np.abs(shifted)>np.finfo(np.float32).max).any():
        raise ValueError('coordinate exceeds float32')
    return shifted.astype(np.float32)


def _target(frame):
    status,owner=frame.get('BallStatus'),frame.get('BallPossession')
    if any(x is not None and type(x) is not str for x in (status,owner)): raise ValueError('target attributes must be lexical strings')
    if status=='0': return 2
    return {'1':0,'2':1}.get(owner,-1) if status=='1' else -1


def parse_sportec(metadata_stream,raw_stream,fixture_id: str,source_digest: str,stats=None):
    """Parse already-authorized held streams. Public for invented schema tests.

    Production entry is load_match, which authorizes before discovery and retains
    ReadLeases for both passes. This helper never opens filesystem paths.
    """
    stats={} if stats is None else stats; stats.update(normalized_coordinate_pairs=0,unknown_target_records=0)
    match,pitch,ids,roster=_read_metadata(metadata_stream); lookup={p:i for i,p in enumerate(ids)}
    limits={}; count=0
    for fs,frame in _frames(raw_stream):
        info=_record_info(fs,frame,match,lookup,roster)
        if info is None: continue
        period,n,slot=info; lo,hi=limits.get(period,(n,n)); limits[period]=(min(lo,n),max(hi,n)); count+=1
    if not {1,2}.issubset(limits): raise ValueError('both normal halves required')
    spans={}; offset=0
    for period in sorted(limits):
        lo,hi=limits[period]; spans[period]=(offset,lo,hi); offset+=hi-lo+1
    n=offset; s=len(ids)
    if n<=0 or n>10_000_000 or n*s>500_000_000: raise ValueError('unreasonable dense timeline')
    positions=np.full((n,s,2),NAN,dtype=np.float32); ball=np.full((n,2),NAN,dtype=np.float32)
    labels=np.full(n,-1,dtype=np.int8); source=np.empty(n,dtype=np.int64); periods=np.empty(n,dtype=np.int16)
    seen=np.zeros((n,s+1),dtype=bool)
    time_frames=np.empty(count,dtype=np.int64); time_slots=np.empty(count,dtype=np.int32); times=np.empty(count,dtype=np.int64)
    for period,(off,lo,hi) in spans.items():
        source[off:off+hi-lo+1]=np.arange(lo,hi+1,dtype=np.int64); periods[off:off+hi-lo+1]=period
    row=0
    for fs,frame in _frames(raw_stream):
        info=_record_info(fs,frame,match,lookup,roster)
        if info is None: continue
        period,source_n,slot=info; off,lo,hi=spans[period]; index=off+source_n-lo
        if seen[index,slot]: raise ValueError('duplicate object/frame in period')
        seen[index,slot]=True
        time_frames[row]=index; time_slots[row]=slot; times[row]=parse_timestamp_ns(frame.get('T')); row+=1
        point=_pair(frame,pitch,stats)
        if slot==s:
            ball[index]=point; labels[index]=_target(frame); stats['unknown_target_records']+=int(labels[index]<0)
        else: positions[index,slot]=point
    order=np.lexsort((time_slots,time_frames)); time_frames=time_frames[order]; time_slots=time_slots[order]; times=times[order]
    origins=[]
    for period,(off,lo,hi) in spans.items():
        rows=np.flatnonzero((time_frames>=off)&(time_frames<off+hi-lo+1))
        first=rows[time_frames[rows]==off]; balls=first[time_slots[first]==s]
        origin_index=int(balls[0] if len(balls) else first[0]); origin=int(times[origin_index])
        origins.append(PeriodOrigin(period,lo,origin))
        # Python integer arithmetic prevents signed int64 overflow at extreme
        # dates/IDs before checking the inclusive millisecond consistency rule.
        for j in rows:
            expected=origin+(int(source[time_frames[j]])-lo)*40_000_000
            if abs(int(times[j])-expected)>1_000_000: raise ValueError('inconsistent25Hz timestamp')
    digest=hashlib.sha256(json.dumps(list(ids),ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest()
    obs=ObservationBatch(np.arange(n,dtype=np.int64),source,periods,positions,ball,
        np.array([roster[p][0] for p in ids],dtype=np.int8),ids,digest,time_frames,time_slots,times,tuple(origins),25.,pitch,fixture_id,source_digest)
    from .corruption import validate_observations
    validate_observations(obs)
    observation_digest=hashlib.sha256(b''.join(getattr(obs,name).tobytes() for name in OBSERVATION_ARRAYS)+canonical_json({'slot_ids':ids,'origins':[asdict(x) for x in origins],'source_digest':source_digest})).hexdigest()
    return obs,TargetBatch(labels,observation_digest)


def _from_cache(observation_path,target_path,obs_meta,target_meta,cap):
    with verify_cache(observation_path,obs_meta,cap) as observations, verify_cache(target_path,target_meta,cap) as targets:
        arrays={name:np.array(value,copy=True) for name,value in observations.arrays.items()}
        labels=np.array(targets.arrays['labels'],copy=True)
        obs=ObservationBatch(**arrays,slot_ids=tuple(obs_meta['slot_ids']),slot_ids_digest=obs_meta['slot_ids_digest'],
            period_origins=tuple(PeriodOrigin(**x) for x in obs_meta['period_origins']),fps=obs_meta['fps'],pitch=tuple(obs_meta['pitch']),
            fixture_id=obs_meta['fixture_id'],source_digest=obs_meta['source_digest'])
        return obs,TargetBatch(labels,digest_json(observations.manifest))


def load_match(study: Path,cap: AccessCapability,fixture: str):
    if type(cap) is not AccessCapability or fixture in ('J03WR9','J03WMX') or fixture not in cap.fixture_ids:
        raise PermissionError('exact live allocated study capability required')
    from .guard import assert_access
    assert_access(cap,fixture,'raw')
    from .fetch import registered_sources
    manifest,catalog=registered_sources(study)
    item=catalog['fixtures'][fixture]
    if item['role']!=cap.role: raise PermissionError('fixture role mismatch')
    if hashlib.sha256(Path(study).read_bytes()).hexdigest()!=cap.study_digest: raise PermissionError('study bytes mismatch')
    raw_root=Path(manifest['raw_root']); source_digest=digest_json({'metadata':item['metadata'],'tracking':item['tracking']})
    # The attempt namespace prevents accidental revival under a new capability.
    key=digest_json({'study':cap.study_digest,'attempt':cap.attempt_id,'fixture':fixture,'source':source_digest})
    folder=Path(study).parent/'caches'/key; observation_path=folder/'observations'; target_path=folder/'targets'
    common=dict(domain='study',fixture_id=fixture,role=cap.role,attempt_id=cap.attempt_id,study_digest=cap.study_digest,
                source_digest=source_digest,protocol_digest=manifest['protocol_digest'],dependency_digest=manifest['scientific_closure_digest'],
                environment_digest=manifest['environment_digest'],config_digest=manifest['protocol_digest'],condition='clean',seeds={})
    if observation_path.exists() or target_path.exists():
        if not observation_path.exists() or not target_path.exists(): raise ValueError('partial observation/target publication')
        # Read only schema metadata under its immutable handle; verify_cache then
        # reacquires and verifies full members against independently bound fields.
        from .cache import strict_json
        with ReadLease(observation_path/'cache.json') as held:
            if held.size>1_048_576: raise ValueError('oversized manifest')
            doc=strict_json(held.read())
        obs_meta=doc['metadata']
        if any(obs_meta.get(k)!=v for k,v in common.items()): raise ValueError('observation cache source binding mismatch')
        target_meta={**common,'kind':'targets','n_frames':obs_meta['n_frames']}
        assert_access(cap,fixture,'observations'); assert_access(cap,fixture,'targets')
        return _from_cache(observation_path,target_path,obs_meta,target_meta,cap)
    assert_access(cap,fixture,'raw')
    with ReadLease(confined_path(raw_root,item['metadata']['relative_path'])) as meta, ReadLease(confined_path(raw_root,item['tracking']['relative_path'])) as raw:
        meta.verify(item['metadata']); raw.verify(item['tracking']); assert_access(cap,fixture,'raw')
        stats={}; obs,truth=parse_sportec(meta.file,raw.file,fixture,source_digest,stats)
    obs_meta={**common,'kind':'observations','n_frames':len(obs.frame_id),'n_slots':len(obs.slot_ids),'slot_ids':list(obs.slot_ids),
        'slot_ids_digest':obs.slot_ids_digest,'period_origins':[asdict(x) for x in obs.period_origins],'fps':obs.fps,'pitch':list(obs.pitch),
        'normalization_counts':{'coordinate_pairs':stats['normalized_coordinate_pairs']}}
    target_meta={**common,'kind':'targets','n_frames':len(obs.frame_id)}
    write_cache_atomic(observation_path,{name:getattr(obs,name) for name in OBSERVATION_ARRAYS},obs_meta,cap)
    write_cache_atomic(target_path,{'labels':truth.labels},target_meta,cap)
    return _from_cache(observation_path,target_path,obs_meta,target_meta,cap)
