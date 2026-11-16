"""Independent invented-fixture acceptance; no challenge assets or saved models.

Run: .venv/Scripts/python.exe tests/test_blind_final_contracts.py
"""
from __future__ import annotations
import copy
import csv
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from possession_model.decoder import decode_scores
from possession_model.features import FeatureAccumulator, load_atd
from possession_model.evidence import feature_matrix, rolling_mean
from possession_model.pipeline import write_submission, source_fingerprints
from possession_model.trees import TreeModel
from validation.metrics import measure
from validation.sportec import load_sportec, truth_code, make_ball_gap_mask

WORK = ROOT / "local/blind-final-contracts"
REPORT = ROOT / "reports/blind-final-contracts.json"
DETAIL = {}
FROZEN_START = source_fingerprints(ROOT)

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def tree_document():
    return {"format":"numeric-hgb-v1", "feature_names":["invented"],
            "baseline":[0.,0.,0.], "trees":[{"class":0,"nodes":{
            "value":[0.,2.,-3.],"feature_idx":[0,0,0],
            "num_threshold":[1.5,0.,0.],"missing_go_to_left":[1,0,0],
            "left":[1,0,0],"right":[2,0,0],"is_leaf":[0,1,1]}}]}

def sportec_fixture(folder, variant="A"):
    folder.mkdir(parents=True, exist_ok=True)
    meta = folder/"meta.xml"
    raw = folder/"raw.xml"
    meta.write_text('<Root><General MatchId="SYNTHETIC" HomeTeamId="HOME" GuestTeamId="AWAY"/>'
        '<Environment PitchX="100" PitchY="60"/>'
        '<Team TeamId="HOME"><Player PersonId="P1"/></Team>'
        '<Team TeamId="AWAY"><Player PersonId="P2"/></Team></Root>')
    sets = []
    for section, numbers in [("firstHalf",[10,11,13]),("secondHalf",[90,91])]:
        for person, team, x in [("P1","HOME","-10"),("P2","AWAY","10"),(None,"BALL","0")]:
            attrs = f'MatchId="SYNTHETIC" GameSection="{section}" TeamId="{team}"'
            if person: attrs += f' PersonId="{person}"'
            frames=[]
            for n in numbers:
                t = n-numbers[0]
                pos = "1" if variant == "A" else "2"
                frames.append(f'<Frame N="{n}" T="2020-01-01T00:00:00.{t*40:03d}" X="{x}" Y="0" BallStatus="1" BallPossession="{pos}"/>')
            sets.append(f'<FrameSet {attrs}>'+"".join(frames)+'</FrameSet>')
    raw.write_text('<Root>'+"".join(sets)+'</Root>')
    return meta,raw

class Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        WORK.mkdir(parents=True, exist_ok=True)
        cls.folder=Path(tempfile.mkdtemp(prefix="run-",dir=WORK))

    def test_csv_lossless_and_official_validator(self):
        n=199319
        codes=np.resize(np.array([-1,0,1,2],dtype=np.int8),n)
        first=self.folder/"valid.csv"; second=self.folder/"valid-again.csv"
        got=write_submission(first,codes)
        self.assertEqual(got,write_submission(second,codes))
        self.assertEqual(got,digest(first))
        with first.open(newline="") as f:
            rows=list(csv.reader(f))
        self.assertEqual(rows[0],["frame","label"])
        self.assertEqual(len(rows),n+1)
        names={-1:"X",0:"H",1:"A",2:"D"}
        self.assertTrue(all(row==[str(i),names[int(codes[i])]] for i,row in enumerate(rows[1:])))
        proc=subprocess.run([sys.executable,str(ROOT/"more-than-a-hack-2027-main/evaluation/validate_submission.py"),str(first)],capture_output=True,text=True,timeout=45)
        self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
        DETAIL["csv"]={"frames":n,"sha256":got,"official_validator_exit":proc.returncode}

    def test_csv_rejects_invalid_without_replacing(self):
        path=self.folder/"preserve.csv"; path.write_bytes(b"ORIGINAL")
        for codes in [[0.5],[256],[-2],[np.nan],[np.inf],[True],["1"],[[0]]]:
            with self.subTest(codes=str(codes)),self.assertRaises(ValueError):
                write_submission(path,codes)
            self.assertEqual(path.read_bytes(),b"ORIGINAL")

    def test_numeric_tree_independent_routing_and_missingness(self):
        model=TreeModel(tree_document())
        x=np.array([[-np.inf],[-3],[1.5],[1.5001],[np.inf],[np.nan]],dtype=np.float32)
        want=np.zeros((len(x),3));want[:,0]=[2,2,2,-3,-3,2]
        np.testing.assert_array_equal(model.raw_scores(x,["invented"],chunk_size=2),want)
        self.assertTrue(np.isfinite(model.scores(x,["invented"])).all())

    def test_numeric_tree_malformed_graphs_fail_bounded(self):
        cases=[]
        for field,value in [("left",[0,0,0]),("right",[1,0,0]),("feature_idx",[2,0,0]),("is_leaf",[0,0,0]),("value",[0,np.nan,1])]:
            doc=tree_document();doc["trees"][0]["nodes"][field]=value;cases.append(doc)
        doc=tree_document();doc["baseline"]=["0","0","0"];cases.append(doc)
        doc=tree_document();doc["trees"][0]["class"]=True;cases.append(doc)
        for i,doc in enumerate(cases):
            with self.subTest(case=i),self.assertRaises(ValueError):TreeModel(doc)

    def test_numeric_tree_finite_artifact_cannot_produce_nonfinite_scores(self):
        doc=tree_document()
        doc["baseline"]=[1.7e308,0.,0.]
        doc["trees"][0]["nodes"]["value"][1]=1.7e308
        try:
            with np.errstate(over="ignore", invalid="ignore"):
                score=TreeModel(doc).scores([[0.]],["invented"])
        except ValueError:
            return
        self.assertTrue(np.isfinite(score).all(),"Finite JSON artifact returned nonfinite class scores instead of a safe rejection")

    def test_decoder_exhaustive_objective_with_period_boundaries(self):
        rng=np.random.default_rng(9027)
        checks=0
        for n in range(1,7):
            for _ in range(12):
                s=rng.normal(size=(n,3));cost=rng.uniform(0,2,size=(3,3));np.fill_diagonal(cost,0)
                pred=decode_scores(s,np.ones(n,dtype=np.int8),cost)
                val=lambda p:sum(s[i,p[i]] for i in range(n))-sum(cost[p[i-1],p[i]] for i in range(1,n))
                oracle=max(val(p) for p in itertools.product(range(3),repeat=n))
                self.assertAlmostEqual(val(pred),oracle,places=10);checks+=1
        s=np.array([[9,0,0],[9,0,0],[0,9,0],[0,9,0],[0,0,9]],float)
        np.testing.assert_array_equal(decode_scores(s,np.array([1,1,0,2,2]),np.full((3,3),99)-np.eye(3)*99),[0,0,-1,1,1])
        DETAIL["decoder_bruteforce_cases"]=checks

    def test_rolling_mean_independent_windows(self):
        x=np.array([1,np.nan,7,100,200,np.nan,-3,5.],float);p=np.array([1,1,1,0,2,2,2,1])
        out=rolling_mean(x,p,2)
        want=[]
        for i in range(len(x)):
            lo=i;hi=i+1
            while lo>0 and p[lo-1]==p[i]:lo-=1
            while hi<len(x) and p[hi]==p[i]:hi+=1
            vals=x[max(lo,i-2):min(hi,i+3)]
            want.append(np.nanmean(vals) if p[i]>0 and np.isfinite(vals).any() else np.nan)
        np.testing.assert_allclose(out,want,equal_nan=True)

    def test_features_no_motion_bridge_over_missing_ball_or_half(self):
        acc=FeatureAccumulator(8,[0,1],fps=5,blocks=[(1,0,4),(2,4,8)])
        balls=[[0,0],[.1,0],[np.nan,1],[.3,0],[20,0],[20.1,0],[20.2,0],[20.3,0]]
        for i,b in enumerate(balls):acc.push(i,[[0,0],[10,0]],b)
        f=acc.finish()
        self.assertFalse(f.ball_observed[2]);self.assertTrue(np.isnan(f.nearest[2]).all())
        self.assertTrue(np.isnan(f.ball_speed[[0,2,3,4,5]]).all())
        self.assertAlmostEqual(float(f.ball_speed[6]),.5,places=3)
        matrix,names,_=feature_matrix(f)
        self.assertTrue(np.isnan(matrix[2,names.index("distance_m_H")]))

    def test_atd_permuted_metadata_coordinates_missingness_and_strict_records(self):
        folder=self.folder/"atd";folder.mkdir()
        meta=folder/"meta.xml";raw=folder/"raw.txt"
        channels=''.join(f'<Channel id="{c}"><Name>{name}</Name><Unit>{unit}</Unit></Channel>' for c,name,unit in [("x","position_x","normalized"),("y","position_y","normalized"),("s","speed_mps","m/s")])
        links=''.join(f'<PlayerChannel id="{p}{c}" playerId="{p}" channelId="{c}"/>' for p in ["h","a"] for c in ["x","y","s"])
        players=''.join('<SplitRegister separator=",">'+''.join(f'<PlayerChannelRef playerChannelId="{p}{c}"/>' for c in ["s","y","x"] )+'</SplitRegister>' for p in ["h","a"])
        ball=''.join(f'<BallChannelRef channelId="{c}"/>' for c in ["y","s","x"])
        meta.write_text('<Root><Team id="HOME"/><Team id="AWAY"/><Score idLocalTeam="HOME" idVisitingTeam="AWAY"/><Player id="h" teamId="HOME"/><Player id="a" teamId="AWAY"/><FrameRate>25</FrameRate>'+channels+links+'<DataFormatSpecification separator=":" startFrame="1" endFrame="5"><StringRegister name="frameCount"/><SplitRegister separator=";">'+players+'</SplitRegister><SplitRegister separator=",">'+ball+'</SplitRegister></DataFormatSpecification></Root>')
        lines=[f'{i}:999,0.5,0.25;999,0.5,0.75:0.5,999,0.3' for i in range(1,6)]
        lines[2]='3:999,0.5,0.25;999,0.5,0.75:nan,999,0.3'
        raw.write_text('\n'.join(lines)+'\n')
        f=load_atd(meta,raw,5,25,(100,60),[(1,0,5)])
        np.testing.assert_allclose(f.nearest[[0,1,3,4]],[[5,45]]*4,atol=1e-5)
        self.assertFalse(f.ball_observed[2]);self.assertTrue(np.isnan(f.nearest[2]).all())
        for bad in [lines[:-1],lines+[lines[-1]], [lines[0],lines[0],*lines[2:]], [lines[0].replace('0.3','0.3junk'),*lines[1:]]]:
            raw.write_text('\n'.join(bad)+'\n')
            with self.assertRaises(ValueError):load_atd(meta,raw,5,25,(100,60),[(1,0,5)])

    def test_generated_missing_blocks_exact_count_period_safe_and_deterministic(self):
        blocks=[{"start":0,"end":7},{"start":7,"end":19}]
        for frac in [0,.05,.2,.5,1]:
            a=make_ball_gap_mask(19,blocks,5,frac,.6,7)
            b=make_ball_gap_mask(19,blocks,5,frac,.6,7)
            np.testing.assert_array_equal(a,b)
            self.assertEqual(int(a.sum()),round(frac*19))

    def test_metrics_independent_frame_f1_and_half_spell_count(self):
        truth=np.array([0,0,2,1,1,1,0,2,-1]);pred=np.array([0,-1,2,1,0,-1,0,1,2]);period=np.array([1,1,1,1,2,2,2,2,0])
        result=measure(truth,pred,period)
        fs=[]
        for label in range(3):
            tp=sum((truth==label)&(pred==label)&(period>0));fp=sum((truth!=label)&(pred==label)&(truth>=0)&(period>0));fn=sum((truth==label)&(pred!=label)&(period>0))
            fs.append(2*tp/(2*tp+fp+fn))
        self.assertAlmostEqual(result["macro_f1"],sum(fs)/3)
        self.assertEqual(result["graded_frames"],8)
        self.assertEqual(measure([0,0],[0,0],[1,2])["n_truth_spells"],2)
        self.assertEqual(measure([0,0],[0,-1],[1,2])["n_predicted_spells"],1)

    def test_metrics_rejects_noninteger_period_ids(self):
        for periods in [[1.5,1.5],[np.nan,np.nan],["1","1"],[True,True]]:
            with self.subTest(periods=str(periods)),self.assertRaises(ValueError):measure([0,1],[0,1],periods)

    def test_sportec_independent_truth_holes_and_label_isolation(self):
        meta,raw=sportec_fixture(self.folder/"sportec")
        f,t,prov=load_sportec(meta,raw)
        self.assertEqual(f.n_frames,6)
        np.testing.assert_array_equal(f.period_id,[1,1,1,1,2,2])
        np.testing.assert_array_equal(t,[0,0,-1,0,0,0])
        self.assertFalse(f.ball_observed[2])
        before=raw.stat();old=raw.read_bytes();new=old.replace(b'BallPossession="1"',b'BallPossession="2"')
        self.assertEqual(len(old),len(new));raw.write_bytes(new);os.utime(raw,ns=(before.st_atime_ns,before.st_mtime_ns))
        f2,t2,p2=load_sportec(meta,raw)
        self.assertNotEqual(prov["layout"]["signature"]["raw_sha256"],p2["layout"]["signature"]["raw_sha256"])
        np.testing.assert_array_equal(t2,[1,1,-1,1,1,1])
        for name in ["ball_xy","nearest","ball_observed","ball_speed","collective_speed","tracked_counts"]:
            np.testing.assert_array_equal(getattr(f,name),getattr(f2,name))
        self.assertEqual(truth_code({"BallStatus":"0","BallPossession":"1"}),2)
        self.assertEqual(truth_code({"BallStatus":"1","BallPossession":"0"}),-1)

    def test_source_provenance_covers_executed_csv_validator(self):
        covered=set(source_fingerprints(ROOT))
        required={"tools/run_candidate.py","possession_model/pipeline.py","possession_model/__init__.py",
                  "more-than-a-hack-2027-main/evaluation/possession_metrics.py"}
        missing=sorted(required-covered)
        DETAIL["unfingerprinted_runtime_dependencies"]=missing
        self.assertFalse(missing,"Executed local dependency absent from frozen source fingerprints: "+", ".join(missing))

    @classmethod
    def cli_fixture(cls,name):
        ws=cls.folder/name;ws.mkdir()
        for rel in source_fingerprints(ROOT):
            dst=ws/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/rel,dst)
        model=ws/"invented-model.json";model.write_text('{}')
        cfg={"model":"invented-model.json","model_sha256":digest(model),"source_sha256":source_fingerprints(ws),"emitter":"heuristic","transition_seconds":0}
        config=ws/"invented-config.json";config.write_text(json.dumps(cfg))
        data=ws/"data/tactical";data.mkdir(parents=True)
        (data/"BAR-ATH_tactical_atd.xml").write_text('invented metadata')
        (data/"BAR-ATH_tactical_atd.txt").write_text('0')
        wrapper=ws/"invoke.py"
        wrapper.write_text('''import importlib.util, sys, pathlib, numpy as np
sys.path.insert(0, %r)
spec=importlib.util.spec_from_file_location("actual_candidate", %r)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.ROOT=pathlib.Path(__file__).parent
def invented_load(meta,raw,n,fps,pitch,blocks):
    from possession_model.features import FeatureAccumulator
    # Stub only extraction/inference for CLI transaction and cache boundaries.
    from possession_model.schema import FeatureSet
    marker=int(pathlib.Path(raw).read_text())
    z=np.zeros
    return FeatureSet(25.,pitch,np.ones(n,dtype=np.uint8),z((n,2),dtype=np.float32),z(n,dtype=bool),np.full((n,2),marker,dtype=np.float32),z((n,2),dtype=np.uint16),z((n,2),dtype=np.float32),z(n,dtype=np.float32))
m.load_atd=invented_load
m.predict=lambda f,*a,**kw: np.full(f.n_frames,int(f.nearest[0,0]),dtype=np.int8)
m.main()
'''%(str(ROOT),str(ROOT/"tools/run_candidate.py")))
        return ws,wrapper,config

    def cli_run(self,wrapper,config,out,report,*extra):
        cmd=[sys.executable,str(wrapper),"--config",str(config),"--data-dir",str(wrapper.parent/"data"),"--out",str(out),"--report",str(report),*extra]
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
        return p

    def test_cli_actual_orchestration_cache_content_identity_and_determinism(self):
        ws,w,c=self.cli_fixture("cli-cache");out=ws/"answer.csv";report=ws/"run.json"
        p=self.cli_run(w,c,out,report);self.assertEqual(p.returncode,0,p.stderr)
        first=digest(out);r1=json.loads(report.read_text());self.assertFalse(r1["cache_hit"])
        p=self.cli_run(w,c,out,report);self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(first,digest(out));self.assertTrue(json.loads(report.read_text())["cache_hit"])
        raw=ws/"data/tactical/BAR-ATH_tactical_atd.txt";stat=raw.stat();raw.write_text('1');os.utime(raw,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        p=self.cli_run(w,c,out,report);self.assertEqual(p.returncode,0,p.stderr)
        self.assertFalse(json.loads(report.read_text())["cache_hit"]);self.assertNotEqual(first,digest(out))
        DETAIL["cli_stub_boundary"]={"fresh_processes":3,"deterministic_cache_hit":True,"same_size_mtime_content_change_invalidated":True,"peak_memory_bytes":r1["peak_process_working_set_bytes"]}

    def test_cli_input_and_output_report_aliases_are_rejected_intact(self):
        ws,w,c=self.cli_fixture("cli-alias");raw=ws/"data/tactical/BAR-ATH_tactical_atd.txt"
        out=ws/"existing.csv";report=ws/"existing.json";out.write_bytes(b"OLD CSV");report.write_bytes(b"OLD REPORT")
        rawhash=digest(raw)
        for target in [raw,c,ws/"invented-model.json",out]:
            p=self.cli_run(w,c,out if target==out else target,out if target==out else report)
            self.assertNotEqual(p.returncode,0)
            self.assertEqual(digest(raw),rawhash);self.assertEqual(out.read_bytes(),b"OLD CSV");self.assertEqual(report.read_bytes(),b"OLD REPORT")
        for kind in ["hardlink","symlink"]:
            alias=ws/(kind+".csv")
            try:
                os.link(raw,alias) if kind=="hardlink" else alias.symlink_to(raw)
            except OSError as e:
                DETAIL[kind+"_unsupported"]=str(e);continue
            p=self.cli_run(w,c,alias,report);self.assertNotEqual(p.returncode,0);self.assertEqual(digest(raw),rawhash)

    def test_cli_failed_report_publication_preserves_existing_output(self):
        ws,w,c=self.cli_fixture("cli-failed-report");out=ws/"existing.csv";report=ws/"report-is-directory";report.mkdir()
        out.write_bytes(b"PREVIOUS SUCCESSFUL CSV")
        p=self.cli_run(w,c,out,report)
        self.assertNotEqual(p.returncode,0)
        DETAIL["failed_report_publication"]={"exit":p.returncode,"error_tail":p.stderr.splitlines()[-1:],"csv_replaced":out.read_bytes()!=b"PREVIOUS SUCCESSFUL CSV"}
        self.assertEqual(out.read_bytes(),b"PREVIOUS SUCCESSFUL CSV","Unsuccessful run replaced the prior output before report publication failed")

    def test_cli_nested_output_report_paths_fail_before_replacement(self):
        ws,w,c=self.cli_fixture("cli-nested");out=ws/"existing.csv";out.write_bytes(b"ORIGINAL CSV")
        p=self.cli_run(w,c,out,out/"report.json")
        self.assertNotEqual(p.returncode,0)
        self.assertEqual(out.read_bytes(),b"ORIGINAL CSV","Nested report destination was discovered only after replacing the CSV")

    def test_cli_experimental_tags_input_is_protected(self):
        ws,w,c=self.cli_fixture("cli-tags");out=ws/"answer.csv"
        tags=ws/"data/tactical/BAR-ATH_tactical_smart_tagging.xml"
        original=b'<Root><instance><code>BUILD UP</code><start>1</start><end>2</end><label><group>Team</group><text>Barcelona</text></label></instance></Root>'
        tags.write_bytes(original)
        p=self.cli_run(w,c,out,tags,"--experimental-tag-weight","0.1")
        DETAIL["experimental_tags_destination"]={"exit":p.returncode,"input_replaced":tags.read_bytes()!=original}
        self.assertNotEqual(p.returncode,0,"CLI accepted report destination equal to the automatic-tagging input")
        self.assertEqual(tags.read_bytes(),original)

    def test_sportec_extra_periods_are_supported_consistently(self):
        meta,raw=sportec_fixture(self.folder/"sportec-extra")
        raw.write_bytes(raw.read_bytes().replace(b'secondHalf',b'firstHalfExtra'))
        # The public task is football possession; adapter explicitly declares
        # extra-time period names. The two-frame extra period must stay distinct.
        f,t,_=load_sportec(meta,raw)
        np.testing.assert_array_equal(f.period_id,[1,1,1,1,3,3])

class EvidenceResult(unittest.TextTestResult):
    def startTest(self,test):
        self.started=time.perf_counter();self.subtest_errors=[];super().startTest(test)
    def addSubTest(self,test,subtest,err):
        if err is not None:self.subtest_errors.append(self._exc_info_to_string(err,test))
        super().addSubTest(test,subtest,err)
    def stopTest(self,test):
        key=test.id().rsplit('.',1)[-1]
        outcome="passed"
        errors=[(t,s) for t,s in self.failures+self.errors if t==test]
        if errors or self.subtest_errors:outcome="failed"
        RECORDS.append({"test":key,"status":outcome,"seconds":round(time.perf_counter()-self.started,4),"failures":[s for _,s in errors]+self.subtest_errors})
        super().stopTest(test)

if __name__ == "__main__":
    RECORDS=[];start=time.perf_counter()
    result=unittest.TextTestRunner(verbosity=2,resultclass=EvidenceResult).run(unittest.defaultTestLoader.loadTestsFromTestCase(Contracts))
    document={"scope":"independent invented-fixture contract acceptance; no challenge assets, prior tests, models, reports or labels read", "source_fingerprints":FROZEN_START,"source_unchanged_during_test":FROZEN_START==source_fingerprints(ROOT),"additional_executed_dependency_sha256":{p:digest(ROOT/p) for p in ["possession_model/__init__.py","more-than-a-hack-2027-main/evaluation/possession_metrics.py"]},"public_requirements":["more-than-a-hack-2027-main/CHALLENGE.md","more-than-a-hack-2027-main/DATA.md","more-than-a-hack-2027-main/SUBMISSION.md","more-than-a-hack-2027-main/RULES.md","more-than-a-hack-2027-main/FAQ.md"],"reproduction_command":".\\.venv\\Scripts\\python.exe tests\\test_blind_final_contracts.py","invented_fixture_workspace":str(Contracts.folder),"test_file_sha256":digest(__file__),"python":sys.version,"seconds":round(time.perf_counter()-start,4),"tests_run":result.testsRun,"passed_test_methods":sum(r["status"]=="passed" for r in RECORDS),"failed_test_methods":sum(r["status"]=="failed" for r in RECORDS),"failure_count":len(result.failures),"error_count":len(result.errors),"details":DETAIL,"results":RECORDS,"limits":["CLI extraction and inference stubbed only to test orchestration boundaries; this is not full candidate-model E2E acceptance","No model quality claims; all data invented","Existing cached-array tampering and adversarial filesystem races are not covered","Extra-time and malformed-period checks are general robustness findings; the organiser reference match uses two halves"]}
    REPORT.parent.mkdir(parents=True,exist_ok=True);REPORT.write_text(json.dumps(document,indent=2)+"\n")
    print("Blind report:",REPORT)
    sys.exit(not result.wasSuccessful())
