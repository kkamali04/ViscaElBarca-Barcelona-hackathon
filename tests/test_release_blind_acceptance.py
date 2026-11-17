"""Fresh blind source-contract acceptance. Synthetic fixtures only; no original model/data.
Run: .venv\\Scripts\\python.exe tests\\test_release_blind_acceptance.py
"""
from __future__ import annotations
import copy, csv, hashlib, importlib.abc, json, os, subprocess, sys, time, traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TMP = ROOT / 'local/release-blind-acceptance'
REPORT = ROOT / 'reports/release-blind-acceptance.json'
PY = ROOT / '.venv/Scripts/python.exe'
N = 199319
EVIDENCE = []

def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def check(name, fn):
    start=time.perf_counter()
    try:
        details=fn()
        EVIDENCE.append(dict(name=name, passed=True, seconds=time.perf_counter()-start, details=details))
    except Exception as exc:
        EVIDENCE.append(dict(name=name, passed=False, seconds=time.perf_counter()-start, error=repr(exc), traceback=traceback.format_exc()))
def reject(fn):
    try: fn()
    except (ValueError, TypeError, OverflowError): return
    raise AssertionError('Malformed input was accepted')
def run(args, timeout=240):
    command=[str(PY), *map(str,args)]
    started=time.perf_counter()
    cp=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=timeout)
    return cp, dict(command=command, returncode=cp.returncode, wall_seconds=time.perf_counter()-started,
                    stdout=cp.stdout[-1600:], stderr=cp.stderr[-2000:])

def fixture_features(n=140, fps=25):
    import numpy as np
    from possession_model.schema import FeatureSet
    t=np.arange(n)/fps
    xy=np.column_stack([10+3*t, 20+4*t])
    return FeatureSet(fps,(105.3,68),np.ones(n,dtype=np.int8),xy,np.ones(n,bool),
        np.tile([1.,9.],(n,1)),np.ones((n,2),dtype=np.uint16),np.ones((n,2)),np.zeros(n), {'fixture':'invented'})

def write_metadata(path,n):
    # Two anonymous slots, explicit home/away and deliberately reordered x/y/s channels.
    channels=''.join(f'<Channel id="{i}"><Name>{name}</Name><Unit>{unit}</Unit></Channel>' for i,name,unit in [('x','position_x','normalized'),('y','position_y','normalized'),('s','speed_kph','kph')])
    links=''.join(f'<PlayerChannel id="{p}{c}" playerId="{p}" channelId="{c}"/>' for p in ['h','a'] for c in ['x','y','s'])
    groups=''.join('<SplitRegister separator=",">'+''.join(f'<PlayerChannelRef playerChannelId="{p}{c}"/>' for c in ['s','y','x'])+'</SplitRegister>' for p in ['h','a'])
    ball=''.join(f'<BallChannelRef channelId="{c}"/>' for c in ['y','s','x'])
    path.write_text(f'<EPTS><Team id="home"/><Team id="away"/><Score idLocalTeam="home" idVisitingTeam="away"/><Player id="h" teamId="home"/><Player id="a" teamId="away"/><FrameRate>25</FrameRate>{channels}{links}<DataFormatSpecification separator=":" startFrame="1" endFrame="{n}"><StringRegister name="frameCount"/><SplitRegister separator=";">{groups}</SplitRegister><SplitRegister separator=",">{ball}</SplitRegister></DataFormatSpecification></EPTS>',encoding='utf8')

def pure_numpy_import():
    code="""import sys, importlib.abc
sys.path.insert(0, sys.argv[1])
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if fullname.split('.')[0] in {'scipy','sklearn','pandas','torch','numba','kloppy'}: raise ImportError('blocked acceptance import '+fullname)
sys.meta_path.insert(0,Block())
from experiments.noise_v2.features import robustify_ball_motion
print('NumPy-only transform import passed')
"""
    cp, ev=run(['-I','-c',code,ROOT],30)
    assert cp.returncode==0,ev
    return ev

def motion():
    import numpy as np
    from experiments.noise_v2.features import robustify_ball_motion
    f=fixture_features(); original={k:v.copy() for k,v in vars(f).items() if isinstance(v,np.ndarray)}
    result=robustify_ball_motion(f)
    # 3-4-5 m/s motion, independently calculated straight-line physical speed.
    assert np.isclose(result.ball_speed[30:110],5,rtol=1e-5).all()
    assert np.isnan(result.ball_speed[:15]).all() and np.isnan(result.ball_speed[-15:]).all()
    for k,v in original.items(): assert np.array_equal(getattr(f,k),v,equal_nan=True),k
    for k in original:
        if k!='ball_speed': assert getattr(result,k) is getattr(f,k),k
    assert result.metadata is not f.metadata and f.metadata=={'fixture':'invented'}
    # Missing observation: no window containing it can claim a slope.
    g=fixture_features();g.ball_observed[70]=False;g.ball_xy[70]=np.nan
    assert np.isnan(robustify_ball_motion(g).ball_speed[55:86]).all()
    # Adjacent independent periods may jump geometrically and must not mix.
    h=fixture_features();h.period_id[70:]=2;h.ball_xy[70:]+=40
    assert np.isnan(robustify_ball_motion(h).ball_speed[55:85]).all()
    # Deterministic alternating 2 cm measurement error: compare direct least-squares oracle.
    noisy=fixture_features();noisy.ball_xy[:,0]+=.02*(-1.)**np.arange(noisy.n_frames)
    s=robustify_ball_motion(noisy).ball_speed
    for i in [20,40,80,110]:
        ts=np.arange(-15,16)/25
        slopes=np.linalg.lstsq(np.column_stack([np.ones(31),ts]),noisy.ball_xy[i-15:i+16],rcond=None)[0][1]
        assert np.isclose(s[i],np.linalg.norm(slopes),rtol=1e-6)
    for bad in [0,-1,float('nan'),float('inf')]:
        q=fixture_features();q.fps=bad;reject(lambda:robustify_ball_motion(q))
    return {'known_speed_mps':5,'gap_unknown_frames':31,'period_boundary_unknown_frames':30,'least_squares_checks':4,'input_arrays_preserved':True}

def reader_and_numeric():
    import numpy as np
    from possession_model.features import load_atd, FeatureAccumulator
    from possession_model.trees import TreeModel
    from possession_model.decoder import decode_scores
    d=TMP/'small';d.mkdir(exist_ok=True)
    meta=d/'meta.xml';raw=d/'tracking.txt';write_metadata(meta,3)
    # Reordered channels must still recover normalized x/y, independent of exported speed.
    raw.write_text('1:999,0.5,0.1;888,0.5,0.9:0.5,777,0.2\n2:999,0.5,0.1;888,0.5,0.9:0.5,777,0.2\n3:999,0.5,0.1;888,0.5,0.9:0.5,777,0.2\n')
    f=load_atd(meta,raw,3)
    assert np.allclose(f.ball_xy,[21.06,34])
    assert np.allclose(f.nearest[:,0],10.53) and np.allclose(f.nearest[:,1],73.71)
    for bad in ['1:0,0,0;0,0,0:0,0,0\n3:0,0,0;0,0,0:0,0,0\n', '1:0,0,0;0,0,0:0,0,inf\n', '1:0,0,0;0,0,0:0,0,private-marker\n']:
        raw.write_text(bad);reject(lambda:load_atd(meta,raw,3))
    for blocks in [[(1,0,3),(2,2,3)],[(1,0,4)],[(1.5,0,3)]]:
        reject(lambda:FeatureAccumulator(3,[0,1],blocks=blocks))
    doc={'format':'numeric-hgb-v1','feature_names':['distance'],'baseline':[0.,0.,0.], 'trees':[{'class':1,'nodes':{'value':[0.,2.,-2.], 'feature_idx':[0,0,0], 'num_threshold':[4.,0.,0.], 'missing_go_to_left':[1,0,0], 'left':[1,0,0], 'right':[2,0,0], 'is_leaf':[0,1,1]}}]}
    model=TreeModel(doc)
    scores=model.raw_scores(np.array([[3.],[5.],[np.nan]]),['distance'])
    assert scores[:,1].tolist()==[2.,-2.,2.]
    for mutate in [lambda z:z.update(baseline=[0,float('nan'),0]),lambda z:z['trees'][0].update({'class':True}),lambda z:z['trees'][0]['nodes'].update(left=[0,0,0]),lambda z:z['trees'][0]['nodes'].update(feature_idx=[10,0,0]),lambda z:z.update(format='pickle')]:
        bad=copy.deepcopy(doc);mutate(bad);reject(lambda:TreeModel(bad))
    costs=np.full((3,3),100.);np.fill_diagonal(costs,0)
    decoded=decode_scores(np.array([[4,0,0],[4,0,0],[0,4,0],[0,4,0]]),np.array([1,1,2,2]),costs)
    assert decoded.tolist()==[0,0,1,1]
    for bad in [np.array([1.,1.]),np.array([True,True])]: reject(lambda:decode_scores(np.zeros((2,3)),bad,costs))
    return {'channel_order_and_metres':True,'malformed_records_rejected':3,'invalid_models_rejected':5,'period_decoder_reset':True}

def metrics():
    import numpy as np
    from validation.metrics import measure
    # Identical side labels on adjacent halves are two spells, not one.
    m=measure([0,0,0,0],[0,0,0,0],np.array([1,1,2,2]))
    assert m['n_truth_spells']==2 and m['n_predicted_spells']==2 and m['spell_f1']==1
    # Ending the first half as H must not fill a leading second-half X as H.
    m=measure([0,0,1,1],[0,0,-1,1],np.array([1,1,2,2]))
    assert m['n_truth_spells']==2 and m['n_predicted_spells']==2
    # Transitions physically close in concatenated time but in different halves cannot pair.
    m=measure([0,1,1,1],[0,0,0,1],np.array([1,1,2,2]))
    assert m['transitions_1s']['n_matched']==0
    reject(lambda:measure([0,0],[0,0],np.array([1.,2.])))
    return {'separate_half_spells':True,'cross_half_transition_matches':0,'leading_X_half_reset':True}

CONFIG=None

def cli_end_to_end():
    global CONFIG
    import numpy as np
    from possession_model.pipeline import source_fingerprints
    from possession_model.evidence import feature_matrix
    data=TMP/'data';tactical=data/'tactical';tactical.mkdir(parents=True,exist_ok=True)
    write_metadata(tactical/'BAR-ATH_tactical_atd.xml',N)
    raw=tactical/'BAR-ATH_tactical_atd.txt'
    with raw.open('w',encoding='utf8',newline='') as f:
        for i in range(1,N+1):f.write(f'{i}:0,0.5,0.1;0,0.5,0.9:0.5,0,0.2\n')
    model=TMP/'invented-model.json';names=feature_matrix(fixture_features())[1]
    model.write_text(json.dumps({'format':'numeric-hgb-v1','feature_names':names,'baseline':[4.,0.,0.],'trees':[],'provenance':{'source':'independent invented constant model; not a trained candidate'}}))
    CONFIG={'model':str(model),'model_sha256':digest(model),'source_sha256':source_fingerprints(ROOT),'emitter':'trees','transition_seconds':0.,'feature_transform':'identity'}
    cfg=TMP/'invented-config.json';cfg.write_text(json.dumps(CONFIG))
    commands=[];protected_before={str(p):digest(p) for p in [raw,tactical/'BAR-ATH_tactical_atd.xml',model,cfg]}
    csv_hashes=[];resources=[]
    for label in ['first','repeat']:
        out=TMP/f'{label}.csv';report=TMP/f'{label}.json'
        cp,ev=run([ROOT/'tools/run_candidate.py','--config',cfg,'--data-dir',data,'--out',out,'--report',report,'--no-cache']);commands.append(ev);assert cp.returncode==0,ev
        with out.open(newline='') as f:
            rows=csv.reader(f);assert next(rows)==['frame','label'];count=0
            for i,row in enumerate(rows):
                expected='H' if 11185<=i<90652 or 110808<=i<190198 else 'X'
                # No match-specific forced labels: synthetic evidence remains H throughout scored periods.
                assert row==[str(i),expected],(i,row,expected)
                count+=1
        assert count==N
        rp=json.loads(report.read_text());assert rp['csv_sha256']==digest(out)
        assert rp['input_signatures']['tracking_sha256']==digest(raw) and rp['input_signatures']['metadata_sha256']==digest(tactical/'BAR-ATH_tactical_atd.xml')
        assert rp['ground_truth_opened'] is False and rp['video_opened'] is False and rp['private_accuracy_measured'] is False
        assert rp['cache_hit'] is False and rp['official_format_validator']=='passed'
        assert rp['peak_process_working_set_bytes']>0 and rp['total_seconds']>0
        resources.append({k:rp[k] for k in ['peak_process_working_set_bytes','total_seconds','feature_seconds','inference_seconds','feature_array_bytes']})
        csv_hashes.append(digest(out))
    assert csv_hashes[0]==csv_hashes[1]
    assert protected_before=={p:digest(p) for p in protected_before}
    cp,ev=run([ROOT/'more-than-a-hack-2027-main/evaluation/validate_submission.py',TMP/'first.csv'],30);commands.append(ev);assert cp.returncode==0,ev
    return {'commands':commands,'csv_hashes':csv_hashes,'resources':resources,'full_real_input_inference':True,'stubs':False,'protected_synthetic_input_hashes_unchanged':True}

def cli_failures():
    cfg=TMP/'invented-config.json';data=TMP/'data';out=TMP/'preserved.csv';report=TMP/'preserved.json'
    out.write_bytes(b'old csv sentinel');report.write_bytes(b'old report sentinel')
    cases=[]
    def exercise(name,extra=None,config=None,expected_fail=True):
        chosen=cfg
        if config is not None:
            chosen=TMP/f'bad-{name}.json';chosen.write_text(json.dumps(config))
        args=[ROOT/'tools/run_candidate.py','--config',chosen,'--data-dir',data,'--out',out,'--report',report,'--no-cache']
        if extra:args+=extra
        before={str(p):digest(p) for p in [out,report,cfg,Path(CONFIG['model']),data/'tactical/BAR-ATH_tactical_atd.xml',data/'tactical/BAR-ATH_tactical_atd.txt']}
        cp,ev=run(args,60);assert cp.returncode!=0,ev
        assert before=={p:digest(p) for p in before},name
        cases.append({'name':name,**ev})
    exercise('same-output-report',['--report',out])
    exercise('output-is-input',['--out',data/'tactical/BAR-ATH_tactical_atd.txt'])
    exercise('report-is-model',['--report',CONFIG['model']])
    exercise('report-is-config',['--report',cfg])
    exercise('report-under-output',['--report',out/'child.json'])
    exercise('nonfinite-tag',['--experimental-tag-weight','nan'])
    bad=copy.deepcopy(CONFIG);bad['model_sha256']='0'*64;exercise('tampered-model',config=bad)
    bad=copy.deepcopy(CONFIG);bad['source_sha256']['possession_model/features.py']='0'*64;exercise('tampered-source',config=bad)
    hard=TMP/'hardlink.csv'
    if not hard.exists():os.link(data/'tactical/BAR-ATH_tactical_atd.txt',hard)
    exercise('hardlink-input',['--out',hard])
    # A malformed prediction sequence must preserve an already existing CSV.
    import numpy as np
    from possession_model.pipeline import write_submission
    for codes in [np.array([0,np.nan]),np.array([0,3]),np.array([[0,1]]),np.array([True])]:
        reject(lambda:write_submission(out,codes));assert out.read_bytes()==b'old csv sentinel'
    return {'bounded_cli_failures':cases,'invalid_prediction_preservation_cases':4,'costly_inference_stubbed':False}

def main():
    TMP.mkdir(parents=True,exist_ok=True)
    from possession_model.pipeline import source_fingerprints
    before=source_fingerprints(ROOT)
    for name,fn in [('numpy_only_import',pure_numpy_import),('coordinate_motion_transform',motion),('reader_numeric_model_period_contract',reader_and_numeric),('period_safe_metrics',metrics),('real_cli_input_to_csv_repeated',cli_end_to_end),('cli_safe_failures',cli_failures)]:check(name,fn)
    after=source_fingerprints(ROOT)
    EVIDENCE.append({'name':'runtime_source_freeze','passed':before==after,'source_sha256_before':before,'source_sha256_after':after})
    result={'kind':'fresh independent blind source-contract acceptance','created_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'passed':all(e['passed'] for e in EVIDENCE),'evidence':EVIDENCE,'invocation':[str(PY),'tests/test_release_blind_acceptance.py'],'public_oracles':['CHALLENGE.md','DATA.md','SUBMISSION.md','RULES.md','FAQ.md'],'limitations':['No challenge inputs, ground truth, original candidate model/config or prior reports were opened.','Invented constant model establishes orchestration and exact contract, not candidate accuracy or calibration.','Existing .venv used; fresh subprocesses and synthetic inputs, not fresh exported package/environment.','Finite path failures do not exhaust filesystem permission, disk-full or concurrent-writer conditions.','Motion fixture checks straight paths, gaps, periods and deterministic measurement error; it does not establish arbitrary-motion denoising quality.']}
    REPORT.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'passed':result['passed'],'checks':[{'name':e['name'],'passed':e['passed']} for e in EVIDENCE],'report':str(REPORT)}))
    return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
