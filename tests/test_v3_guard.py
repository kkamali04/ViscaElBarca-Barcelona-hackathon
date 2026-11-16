"""Synthetic-only guard contract tests; independent acceptance is a separate gate."""
import unittest
import numpy as np
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

from experiments.v3 import guard


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="v3-t02-", dir=guard.ROOT / "local")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.original_protocol = guard.read_json(guard.ROOT / "specs/003-possession-improvements/protocol.json")
        self.patch = patch.object(guard, "ROOT", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        guard._LOCATIONS.clear()
        guard._CONTROL_BY_PATH.clear()
        self.control = self.root / "local/v3-control"
        self.protocol = self.root / "specs/003-possession-improvements/protocol.json"
        self.catalog = self.control / "catalog-complete.json"
        self.fallback = self.root / "reports/fallback.json"
        for name in self.original_protocol["fit"]["source_closure"]["scientific_new_modules"]:
            self.put("experiments/v3/" + name, b"# invented scientific source\n")
        for name in ("experiments/__init__.py", "experiments/noise_v2/__init__.py", "experiments/noise_v2/features.py",
                     "validation/sportec.py", "validation/metrics.py", "tools/train_and_validate.py", "tools/run_candidate.py",
                     "more-than-a-hack-2027-main/evaluation/validate_submission.py", "more-than-a-hack-2027-main/games.py",
                     "more-than-a-hack-2027-main/FAQ.md"):
            self.put(name, b"# invented public/dependency source\n")
        for name in ("__init__", "features", "schema", "evidence", "trees", "decoder", "pipeline"):
            self.put("possession_model/" + name + ".py", b"# invented accepted scientific dependency\n")
        for name in ("PRD-TURNOVER.md", "PRD-MULTIMATCH.md", "contracts.md"):
            self.put("specs/003-possession-improvements/" + name, b"invented requirement\n")
        for name in ("requirements-lock.txt", "requirements-training-lock.txt", "tools/v3_prepare_catalog.py",
                     "more-than-a-hack-2027-main/evaluation/possession_metrics.py"):
            self.put(name, b"# invented dependency\n")
        self.put("reports/v3-metadata-overlap.json", b"{}\n")
        self.put("reports/v3-source-attribution.json", b"{}\n")
        self.original_protocol["study_id"] = "synthetic-one"
        self.dump(self.protocol, self.original_protocol)
        files = {}
        for i in range(29):
            path = self.put(f"fallback/{i}.txt", f"invented-{i}".encode())
            files[f"fallback/{i}.txt"] = {"bytes": path.stat().st_size, "sha256": guard.sha256(path)}
        self.dump(self.fallback, {"files": files})
        fixtures = {}
        for role in ("train", "selection", "test"):
            for fixture in self.original_protocol["split"][role]:
                record = {"fixture_id": fixture, "canonical_fixture_id": "IDSSE:" + fixture,
                          "duplicate_group": hashlib.sha256(fixture.encode()).hexdigest(), "role": role, "fps": 25,
                          "license": {"spdx": "CC-BY-4.0", "attribution_receipt_digest": guard.sha256(self.root / "reports/v3-source-attribution.json")}}
                for kind in ("metadata", "tracking"):
                    content = ("invented opaque " + fixture + kind).encode()
                    relative = f"{fixture}/{kind}.bin"
                    self.put("local/v3-data/originals/" + relative, content)
                    record[kind] = {"kind": kind, "relative_path": relative, "source_url": "https://example.org/invented",
                                    "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(), "md5": hashlib.md5(content).hexdigest()}
                fixtures[fixture] = record
        self.dump(self.catalog, {"schema_version": 1, "provider": "IDSSE", "raw_root": str(self.root / "local/v3-data/originals"),
                                "metadata_overlap_receipt_digest": guard.sha256(self.root / "reports/v3-metadata-overlap.json"), "fixtures": fixtures})

    def put(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def dump(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(guard.canonical(value) + b"\n")

    def register(self):
        return guard.register_study(self.protocol, self.catalog, self.fallback, self.control)

    def train(self, study):
        return guard.reserve_attempt(study, "train", tuple(self.original_protocol["split"]["train"]), self.control)

    def seal(self, study, cap, mutate=None):
        models, receipts = {}, {}
        value = guard.load_registered_study(study)
        for name in ("C0", "C1", "boundary"):
            model = study.parent / f"models/{name}.json"
            receipt = study.parent / f"models/{name}-parity.json"
            expected = guard.expected_model_provenance(study, name)
            order = expected.pop("training_input_order")
            inputs = [{**r, **{k: hashlib.sha256((name + r["fixture_id"] + r["condition"] + k).encode()).hexdigest()
                       for k in ("observation_digest", "target_digest", "sampling_digest")}} for r in order]
            provenance = {**expected, "training_input_digests": inputs}
            node = {"value": [0.], "feature_idx": [0], "num_threshold": [0.], "missing_go_to_left": [0],
                    "left": [0], "right": [0], "is_leaf": [1]}
            document = {"format": "numeric-hgb-v1", "feature_names": ["invented_feature"], "baseline": [0., 0., 0.],
                        "trees": [{"class": c, "nodes": node} for c in range(3)], "provenance": provenance}
            if name == "boundary":
                from experiments.v3.boundary import BOUNDARY_NAMES
                provenance.update(weight_recipe=self.original_protocol["fit"]["boundary_weights"], feature_version="v3-boundary-28-v1",
                                  fps=25, windows_frames=[5, 15], coverage=.8, temperature=1,
                                  tree_parameters=self.original_protocol["fit"]["boundary"], random_state=20261116)
                document.update(format="numeric-boundary-hgb-v1", class_names=["NONE", "TEAM_CHANGE", "LIVE_DEAD"],
                                feature_names=list(BOUNDARY_NAMES))
            self.dump(model, document)
            self.dump(receipt, {"study_digest": cap.study_digest, "scientific_closure_digest": value["scientific_closure_digest"],
                                "model_sha256": guard.sha256(model), "passed": True, "numeric_export_passed": True, "parity_passed": True,
                                "training_input_digests": inputs})
            models[name], receipts[name] = model, receipt
        if mutate is not None:
            mutate(models, receipts)
        return guard.seal_fitted_models(study, cap, models, receipts)

    def test_train_live_access_and_firstaccess_then_completion_refusal(self):
        study = self.register()
        cap = self.train(study)
        guard.assert_access(cap, cap.fixture_ids[0], "raw")
        guard.assert_access(cap, cap.fixture_ids[1], "targets")
        events = guard._replay(self.control)
        self.assertEqual(sum(e["kind"] == "first_access" for e in events), 1)
        result = study.parent / "train/result.json"
        self.dump(result, {"study_digest": cap.study_digest, "attempt_id": cap.attempt_id, "status": "complete"})
        guard.finish_attempt(cap, result, "complete")
        with self.assertRaises(guard.AccessError):
            guard.assert_access(cap, cap.fixture_ids[0], "observations")
        with self.assertRaises(guard.AccessError):
            self.train(study)

    def test_whole_cohort_and_models_seal_required(self):
        study = self.register()
        with self.assertRaises(guard.AccessError):
            guard.reserve_attempt(study, "test", ("J03WN1",), self.control)
        with self.assertRaises(guard.AccessError):
            guard.reserve_attempt(study, "selection", ("J03WPY",), self.control)
        cap = self.train(study)
        self.seal(study, cap)
        selection = guard.reserve_attempt(study, "selection", ("J03WPY",), self.control)
        guard.assert_access(selection, "J03WPY", "targets")
        with self.assertRaises(guard.AccessError):
            guard.reserve_attempt(study, "selection", ("J03WPY",), self.control)

    def test_fabricated_and_changed_process_capability_rejected(self):
        study = self.register()
        cap = self.train(study)
        for bad in (replace(cap, process_id=cap.process_id + 1000000), replace(cap, process_creation_time="0"),
                    replace(cap, reservation_event_digest="f" * 64), replace(cap, fixture_ids=("J03WR9",))):
            with self.assertRaises(guard.AccessError):
                guard.assert_access(bad, bad.fixture_ids[0], "targets")

    def test_scientific_tamper_blocks_but_management_updates_do_not(self):
        study = self.register()
        cap = self.train(study)
        for name in ("PROJECT_STATE.md", "AGENTIC_GOAL.md", "specs/003-possession-improvements/tasks.md",
                     "specs/003-possession-improvements/WORKFLOW.md"):
            self.put(name, b"mutable progress update")
        guard.assert_access(cap, cap.fixture_ids[0], "observations")
        for name in ("specs/003-possession-improvements/protocol.json", "experiments/v3/core.py", "fallback/0.txt",
                     "more-than-a-hack-2027-main/evaluation/possession_metrics.py", "local/v3-control/catalog-complete.json"):
            path = self.root / name
            previous = path.read_bytes()
            path.write_bytes(previous + b" ")
            with self.assertRaises(guard.IntegrityError):
                guard.assert_access(cap, cap.fixture_ids[0], "raw")
            path.write_bytes(previous)

    def test_partial_tail_and_changed_snapshot_fail_closed(self):
        study = self.register()
        cap = self.train(study)
        ledger = self.control / "consumption.jsonl"
        previous = ledger.read_bytes()
        with ledger.open("ab") as stream:
            stream.write(b'{"partial":')
        with self.assertRaises(guard.IntegrityError):
            guard.assert_access(cap, cap.fixture_ids[0], "targets")
        self.assertTrue(ledger.read_bytes().endswith(b'{"partial":'))
        # Synthetic restoration only, production guard never repairs a tail.
        ledger.write_bytes(previous)
        snapshot = study.parent / "prior-access-snapshot.json"
        snapshot.write_bytes(snapshot.read_bytes() + b" ")
        with self.assertRaises(guard.IntegrityError):
            guard.assert_access(cap, cap.fixture_ids[0], "targets")

    def test_ledger_growth_does_not_invalidate_owner(self):
        study = self.register()
        cap = self.train(study)
        self.seal(study, cap)
        selection = guard.reserve_attempt(study, "selection", ("J03WPY",), self.control)
        guard.assert_access(cap, cap.fixture_ids[0], "raw")
        guard.assert_access(selection, "J03WPY", "observations")

    def test_child_capability_exact_identity_and_terminal_lifetime(self):
        study = self.register()
        cap = self.train(study)
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(15)"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        def stop_child():
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)
        self.addCleanup(stop_child)
        created = guard.process_creation_time(child.pid)
        child_cap = guard.authorize_child(cap, child.pid, created)
        self.assertEqual(child_cap.process_id, child.pid)
        with self.assertRaises(guard.AccessError):
            guard.assert_access(child_cap, cap.fixture_ids[0], "raw")
        result = study.parent / "train/failed.json"
        self.dump(result, {"study_digest": cap.study_digest, "attempt_id": cap.attempt_id, "status": "failed"})
        guard.finish_attempt(cap, result, "failed")
        with self.assertRaises(guard.AccessError):
            guard.authorize_child(cap, child.pid, created)

    def test_two_stale_studies_race_one_consumes_full_selection_cohort(self):
        first = self.register()
        self.seal(first, self.train(first))
        second_protocol = self.root / "specs/second/protocol.json"
        second_config = dict(self.original_protocol, study_id="synthetic-two")
        self.dump(second_protocol, second_config)
        for name in ("PRD-TURNOVER.md", "PRD-MULTIMATCH.md", "contracts.md"):
            self.put("specs/second/" + name, b"independently invented requirement\n")
        second = guard.register_study(second_protocol, self.catalog, self.fallback, self.control)
        self.seal(second, self.train(second))
        script = r'''
import json, sys, time
from pathlib import Path
from experiments.v3 import guard
guard.ROOT=Path(sys.argv[1])
study, control, barrier, result=map(Path,sys.argv[2:])
while not barrier.exists(): time.sleep(.01)
parses=0
try:
    cap=guard.reserve_attempt(study,"selection",("J03WPY",),control)
    guard.assert_access(cap,"J03WPY","targets")
    parses+=1
    outcome="reserved"
except guard.AccessError:
    outcome="refused"
result.write_text(json.dumps({"outcome":outcome,"parser_count":parses}))
time.sleep(.2)
'''
        barrier = self.root / "race-go"
        outputs = [self.root / f"race-{i}.json" for i in range(2)]
        children = [subprocess.Popen([sys.executable, "-c", script, str(self.root), str(study), str(self.control), str(barrier), str(output)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    for study, output in zip((first, second), outputs)]
        barrier.write_text("go")
        for child in children:
            out, err = child.communicate(timeout=30)
            self.assertEqual(child.returncode, 0, err.decode())
        actual = [json.loads(p.read_text()) for p in outputs]
        self.assertEqual(sorted(x["outcome"] for x in actual), ["refused", "reserved"])
        self.assertEqual(sorted(x["parser_count"] for x in actual), [0, 1])
        events = guard._replay(self.control)
        reservations = [e for e in events if e["kind"] == "reserve" and e["role"] == "selection"]
        self.assertEqual(len(reservations), 1)
        self.assertEqual(reservations[0]["fixture_ids"], ["J03WPY"])
        # Reservation consumes even though worker exited without final report.
        for study in (first, second):
            with self.assertRaises(guard.AccessError):
                guard.reserve_attempt(study, "selection", ("J03WPY",), self.control)
        self.assertTrue(any(e["kind"] == "interrupted" for e in guard._replay(self.control)))

    def test_output_preflight_and_lazy_help(self):
        from experiments.v3 import cli
        root = self.root / "local/v3-review/runs"
        root.mkdir(parents=True)
        valid = (root / "run-one/pred.csv", root / "run-one/report.json")
        self.assertEqual(cli.validate_generation_paths(*valid), valid)
        invalid = [((valid[0], valid[0])), ((valid[0], root / "other/report.json")),
                   ((root / "run/commit.json", root / "run/report.json"))]
        for paths in invalid:
            with self.assertRaises(guard.AccessError):
                cli.validate_generation_paths(*paths)
        valid[0].parent.mkdir()
        with self.assertRaises(guard.AccessError):
            cli.validate_generation_paths(*valid)
        with patch.object(cli, "_module", side_effect=AssertionError("heavy import before preflight")):
            self.assertEqual(cli.main(["run", "--release", "missing", "--data-dir", "missing", "--out", str(valid[0]), "--report", str(valid[1])]), 2)

    def test_complete_seal_tamper_and_no_reseal(self):
        study = self.register()
        cap = self.train(study)
        seal = self.seal(study, cap)
        actual = guard.load_model_seal(study)
        self.assertEqual([m["name"] for m in actual["models"]], ["C0", "C1", "boundary"])
        model = study.parent / actual["models"][0]["relative_path"]
        model.write_bytes(model.read_bytes() + b" ")
        with self.assertRaises(guard.IntegrityError):
            guard.reserve_attempt(study, "selection", ("J03WPY",), self.control)

    def test_changed_environment_rejected_before_access(self):
        study = self.register()
        cap = self.train(study)
        with patch.object(guard, "_environment", return_value={"changed": True}):
            with self.assertRaises(guard.IntegrityError):
                guard.assert_access(cap, cap.fixture_ids[0], "raw")

    def test_fabricated_model_provenance_rejected_even_with_matching_parity_hash(self):
        study = self.register()
        cap = self.train(study)
        for kind in ("source", "order", "receipt"):
            with self.subTest(kind=kind):
                def mutate(models, receipts):
                    model, receipt = models["C0"], receipts["C0"]
                    document, parity = guard.read_json(model), guard.read_json(receipt)
                    if kind == "source":
                        document["provenance"]["scientific_source_digest"] = "0" * 64
                    elif kind == "order":
                        document["provenance"]["training_input_digests"].reverse()
                        parity["training_input_digests"] = document["provenance"]["training_input_digests"]
                    else:
                        parity["training_input_digests"][0]["target_digest"] = "0" * 64
                    self.dump(model, document)
                    parity["model_sha256"] = guard.sha256(model)
                    self.dump(receipt, parity)
                with self.assertRaises(guard.IntegrityError):
                    self.seal(study, cap, mutate)
                self.assertFalse((study.parent / "models/models.json").exists())

    def test_two_test_fixtures_reserved_together_after_bound_finalist(self):
        study = self.register()
        train_cap = self.train(study)
        seal_path = self.seal(study, train_cap)
        selection = guard.reserve_attempt(study, "selection", ("J03WPY",), self.control)
        result = study.parent / "selection/result.json"
        self.dump(result, {"schema_version": 1, "study_digest": selection.study_digest, "attempt_id": selection.attempt_id,
                           "status": "complete", "eligible": True})
        guard.finish_attempt(selection, result, "complete")
        value, seal = guard.load_registered_study(study), guard.load_model_seal(study)
        candidate = next(c for c in self.original_protocol["candidates"] if c["id"] == "C1")
        self.dump(study.parent / "finalist.json", {"schema_version": 1, "study_digest": selection.study_digest,
                  "model_seal_digest": guard.sha256(seal_path), "protocol_digest": value["protocol_digest"],
                  "scientific_closure_digest": value["scientific_closure_digest"], "comparator_digest": value["comparator_digest"],
                  "selection_receipt_digest": guard.sha256(result), "candidate_id": "C1", "config": candidate, "models": seal["models"]})
        cap = guard.reserve_attempt(study, "test", ("J03WN1", "J03WQQ"), self.control)
        events = guard._replay(self.control)
        event = next(e for e in events if e["event_digest"] == cap.reservation_event_digest)
        self.assertEqual(event["fixture_ids"], ["J03WN1", "J03WQQ"])
        self.assertEqual(event["role"], "test")
        guard.assert_access(cap, "J03WQQ", "targets")
        with self.assertRaises(guard.AccessError):
            guard.reserve_attempt(study, "test", ("J03WN1", "J03WQQ"), self.control)

    def test_fresh_child_reads_only_after_explicit_grant_until_owner_finishes(self):
        study = self.register()
        cap = self.train(study)
        exchange = self.root / "child-exchange"
        exchange.mkdir()
        self.dump(exchange / "cap.json", {**cap.__dict__, "fixture_ids": list(cap.fixture_ids)})
        script = r'''
import json, os, sys, time
from pathlib import Path
from experiments.v3 import guard
from experiments.v3.contracts import AccessCapability
guard.ROOT=Path(sys.argv[1]); exchange=Path(sys.argv[2])
doc=json.loads((exchange/"cap.json").read_text()); doc["fixture_ids"]=tuple(doc["fixture_ids"])
doc["process_id"]=os.getpid(); doc["process_creation_time"]=guard.process_creation_time()
cap=AccessCapability(**doc)
def attempt():
    try: guard.assert_access(cap,cap.fixture_ids[0],"targets"); return "allowed"
    except guard.AccessError: return "refused"
outcomes=[attempt()]; (exchange/"ready").write_text(json.dumps({"pid":os.getpid(),"created":guard.process_creation_time()}))
for gate in ("granted","finished"):
    while not (exchange/gate).exists(): time.sleep(.01)
    outcomes.append(attempt()); (exchange/(gate+"-done")).write_text("done")
(exchange/"outcomes.json").write_text(json.dumps(outcomes))
'''
        child = subprocess.Popen([sys.executable, "-c", script, str(self.root), str(exchange)], stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        def stop():
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)
        self.addCleanup(stop)
        def await_file(name):
            limit = time.monotonic() + 15
            while not (exchange / name).exists():
                if child.poll() is not None or time.monotonic() > limit:
                    self.fail("synthetic child handshake failed")
                time.sleep(.01)
        await_file("ready")
        actual_worker = json.loads((exchange / "ready").read_text())
        guard.authorize_child(cap, actual_worker["pid"], actual_worker["created"])
        (exchange / "granted").write_text("go")
        await_file("granted-done")
        result = study.parent / "train/result.json"
        self.dump(result, {"study_digest": cap.study_digest, "attempt_id": cap.attempt_id, "status": "complete"})
        guard.finish_attempt(cap, result, "complete")
        (exchange / "finished").write_text("go")
        out, err = child.communicate(timeout=15)
        self.assertEqual(child.returncode, 0, err.decode())
        self.assertEqual(json.loads((exchange / "outcomes.json").read_text()), ["refused", "allowed", "refused"])

    def test_restart_metadata_finalization_never_reopens_reserved_inputs(self):
        study = self.register()
        script = r'''
import json, sys
from pathlib import Path
from experiments.v3 import guard
guard.ROOT=Path(sys.argv[1]); study=Path(sys.argv[2]); control=Path(sys.argv[3])
cap=guard.reserve_attempt(study,"train",("J03WOH","J03WOY"),control)
value=guard.load_registered_study(study)
artifact=study.parent/"train/frozen.json"; artifact.parent.mkdir(); guard._write_once(artifact,{"synthetic":True})
guard._write_once(study.parent/"train/result.json",{"schema_version":1,"study_digest":cap.study_digest,
"attempt_id":cap.attempt_id,"status":"complete","sealed":True,"role":"train","fixture_ids":list(cap.fixture_ids),
"fixture_count":2,"artifact_count":1,**{k:value[k] for k in ("protocol_digest","catalog_digest","scientific_closure_digest","environment_digest","comparator_digest")},
"artifacts":[{"relative_path":"train/frozen.json",
"bytes":artifact.stat().st_size,"sha256":guard.sha256(artifact)}]})
guard._write_once(study.parent/"cap.json",cap.__dict__)
'''
        child = subprocess.run([sys.executable, "-c", script, str(self.root), str(study), str(self.control)],
                               capture_output=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(child.returncode, 0, child.stderr.decode())
        result = study.parent / "train/result.json"
        original = result.read_bytes()
        for key, wrong in (("scientific_closure_digest", "0" * 64), ("fixture_count", 1), ("fixture_ids", ["J03WOH"]),
                           ("artifact_count", 2), ("sealed", False), ("study_digest", "0" * 64), ("attempt_id", "invented")):
            bad = json.loads(original)
            bad[key] = wrong
            self.dump(result, bad)
            with self.assertRaises(guard.AccessError):
                guard.finalize_recorded_result(study, result)
            self.assertFalse(any(e["kind"] == "finalize" for e in guard._replay(self.control)))
        result.write_bytes(original)
        guard.finalize_recorded_result(study, result)
        before = (self.control / "consumption.jsonl").read_bytes()
        guard.finalize_recorded_result(study, result)
        self.assertEqual((self.control / "consumption.jsonl").read_bytes(), before)
        events = guard._replay(self.control)
        self.assertEqual([e["kind"] for e in events[-2:]], ["interrupted", "finalize"])
        with self.assertRaises(guard.AccessError):
            self.train(study)
        document = guard.read_json(study.parent / "cap.json")
        document["fixture_ids"] = tuple(document["fixture_ids"])
        from experiments.v3.contracts import AccessCapability
        with self.assertRaises(guard.AccessError):
            guard.assert_access(AccessCapability(**document), "J03WOH", "targets")


class Round3RepairTests(unittest.TestCase):
    setUp = GuardTests.setUp
    put = GuardTests.put
    dump = GuardTests.dump
    register = GuardTests.register
    train = GuardTests.train
    seal = GuardTests.seal

    def test_preparation_and_fallback_python_roots_have_transitive_binding(self):
        self.put("tools/v3_prepare_catalog.py", b"from . import catalog_dependency\n")
        self.put("tools/catalog_dependency.py", b"from helpers import opaque_identity\n")
        self.put("helpers/opaque_identity.py", b"VALUE=1\n")
        fallback = guard.read_json(self.fallback)
        del fallback["files"]["fallback/0.txt"]
        script = self.put("fallback/accepted.py", b"from helpers import comparator_dependency\n")
        self.put("helpers/comparator_dependency.py", b"VALUE=2\n")
        fallback["files"]["fallback/accepted.py"] = {"bytes": script.stat().st_size, "sha256": guard.sha256(script)}
        self.dump(self.fallback, fallback)
        study = self.register()
        cap = self.train(study)
        names = {b["relative_path"] for b in guard.load_registered_study(study)["artifact_bindings"]}
        for name in ("tools/catalog_dependency.py", "helpers/opaque_identity.py", "helpers/comparator_dependency.py"):
            self.assertIn(name, names)
            path = self.root / name
            original = path.read_bytes()
            path.write_bytes(original + b"# mutation\n")
            with self.assertRaises(guard.IntegrityError):
                guard.assert_access(cap, cap.fixture_ids[0], "targets")
            path.write_bytes(original)

    def test_exact_fallback_byte_identity_and_digest(self):
        path = self.put("fallback/0.txt", b"x")
        original = guard.read_json(self.fallback)
        for size, digest in ((True, guard.sha256(path)), (1.0, guard.sha256(path)), (-1, guard.sha256(path)), (1, "G" * 64)):
            value = json.loads(json.dumps(original))
            value["files"]["fallback/0.txt"] = {"bytes": size, "sha256": digest}
            self.dump(self.fallback, value)
            with self.subTest(size=size, digest=digest[:1]), self.assertRaises(guard.AccessError):
                self.register()

    def test_observation_mutable_metadata_and_origin_scalar_types(self):
        from experiments.v3.contracts import ObservationBatch, PeriodOrigin
        original, _, _ = TimestampOrderingRepairTests.batch([0, 1], [0, 0])
        values = dict(original.__dict__)
        for key in ("slot_ids", "pitch", "period_origins"):
            trial = dict(values)
            trial[key] = list(trial[key])
            with self.subTest(key=key), self.assertRaises(ValueError):
                ObservationBatch(**trial)
        for trial in ((True, 0, 0), (1, False, 0), (1, 0, 1.0)):
            with self.subTest(origin=trial), self.assertRaises(ValueError):
                PeriodOrigin(*trial)
        for key, value in (("source_digest", "not-a-digest"), ("slot_ids_digest", True), ("fixture_id", False),
                           ("pitch", (True, 60.)), ("period_origins", ({"period_id": 1},))):
            with self.subTest(key=key), self.assertRaises(ValueError):
                ObservationBatch(**{**values, key: value})

    def test_binding_seal_and_parity_identities_reject_bool_float_and_bad_digests(self):
        study = self.register()
        cap = self.train(study)
        seal_path = self.seal(study, cap)
        for path, loader, select in (
            (study, guard.load_registered_study, lambda d: d["artifact_bindings"][0]),
            (seal_path, guard.load_model_seal, lambda d: d["models"][0]),
            (seal_path, guard.load_model_seal, lambda d: d["models"][0]["parity_receipt"])):
            original = path.read_bytes()
            for key, value in (("bytes", True), ("bytes", 1.0), ("bytes", -1), ("sha256", "z" * 64)):
                document = json.loads(original)
                select(document)[key] = value
                self.dump(path, document)
                with self.subTest(path=str(path), key=key, value=value), self.assertRaises(guard.IntegrityError):
                    loader(study, verify=False)
                path.write_bytes(original)
        self.assertFalse(guard._same({"alpha": False}, {"alpha": 0}))
        self.assertTrue(guard._same({"alpha": 0.0}, {"alpha": 0}))


class G02RepairTests(unittest.TestCase):
    setUp = GuardTests.setUp
    put = GuardTests.put
    dump = GuardTests.dump
    register = GuardTests.register
    train = GuardTests.train
    seal = GuardTests.seal

    def test_required_public_tool_prefit_roots_are_bound_before_export(self):
        required = ("more-than-a-hack-2027-main/FAQ.md", "more-than-a-hack-2027-main/games.py",
                    "more-than-a-hack-2027-main/evaluation/validate_submission.py", "tools/run_candidate.py", "tools/train_and_validate.py")
        study = self.register()
        cap = self.train(study)
        names = {b["relative_path"] for b in guard.load_registered_study(study)["artifact_bindings"]}
        self.assertTrue(set(required) <= names)
        for name in required:
            path = self.root / name
            original = path.read_bytes()
            path.write_bytes(original + b"# mutation\n")
            with self.subTest(name=name), self.assertRaises(guard.IntegrityError):
                guard.assert_access(cap, cap.fixture_ids[0], "observations")
            path.write_bytes(original)

    def test_protocol_exact_version_and_closed_recursive_schema(self):
        scenarios = [("version_bool", lambda p: p.update(schema_version=True)),
                     ("version_float", lambda p: p.update(schema_version=1.0)),
                     ("unknown_root", lambda p: p.update(unreviewed=True)),
                     ("unknown_nested", lambda p: p["fit"]["emitter"].update(unreviewed=True)),
                     ("malformed_nested", lambda p: p["fit"].update(boundary_conditions="clean")),
                     ("bool_integer", lambda p: p["resource"].update(heavy_workers=True))]
        for label, mutate in scenarios:
            config = json.loads(json.dumps(self.original_protocol))
            mutate(config)
            self.dump(self.protocol, config)
            with self.subTest(label=label), self.assertRaises(guard.AccessError):
                self.register()

    def test_relative_alias_packages_submodules_and_parent_initializers_bound(self):
        sources = {
            "experiments/__init__.py": "from . import framework\n",
            "experiments/framework.py": "VALUE=1\n",
            "experiments/v3/core.py": "from . import supplementary_science as local_alias\nimport toy_science as package_alias\nfrom toy_science import submodule as nested_alias\nfrom toy_science.inner import leaf\n",
            "experiments/v3/supplementary_science.py": "from toy_science.inner import leaf as deeper_alias\n",
            "toy_science/__init__.py": "from . import support\n",
            "toy_science/support.py": "VALUE=2\n",
            "toy_science/submodule.py": "from .inner import leaf\n",
            "toy_science/inner/__init__.py": "VALUE=3\n",
            "toy_science/inner/leaf.py": "VALUE=4\n"}
        for name, text in sources.items():
            self.put(name, text.encode())
        study = self.register()
        cap = self.train(study)
        bindings = {b["relative_path"] for b in guard.load_registered_study(study)["artifact_bindings"]}
        self.assertTrue(set(sources) <= bindings, sorted(set(sources) - bindings))
        for name in sources:
            path = self.root / name
            before = path.read_bytes()
            path.write_bytes(before + b"# mutation\n")
            with self.subTest(name=name), self.assertRaises(guard.IntegrityError):
                guard.assert_access(cap, cap.fixture_ids[0], "targets")
            path.write_bytes(before)

    def test_ancestry_stale_unavailable_sibling_and_valid_multihop(self):
        times = {11: "100", 22: "200", 33: "300", 44: "400"}
        parents = {33: 22, 22: 11, 44: 22}
        with patch.object(guard, "process_creation_time", side_effect=lambda pid=None: times[pid]), \
                patch.object(guard, "_parent_process_id", side_effect=lambda pid: parents[pid], create=True):
            guard._assert_descendant(11, "100", 33, "300")
            with self.assertRaises(guard.AccessError):
                guard._assert_descendant(33, "300", 44, "400")
            with self.assertRaises(guard.AccessError):
                guard._assert_descendant(11, "999", 33, "300")
        with patch.object(guard, "process_creation_time", side_effect=lambda pid=None: times[pid]), \
                patch.object(guard, "_parent_process_id", side_effect=guard.AccessError("unavailable")):
            with self.assertRaises(guard.AccessError):
                guard._assert_descendant(11, "100", 33, "300")
        with patch.object(guard, "process_creation_time", side_effect=lambda pid=None: {11: "100", 22: "400", 33: "300"}[pid]), \
                patch.object(guard, "_parent_process_id", return_value=22):
            with self.assertRaises(guard.AccessError):
                guard._assert_descendant(11, "100", 33, "300")

    def test_new_parent_initializer_or_optional_submodule_invalidates_closure(self):
        self.put("experiments/v3/core.py", b"from namespace_science import attribute\n")
        self.put("namespace_science/existing.py", b"VALUE=1\n")
        study = self.register()
        cap = self.train(study)
        self.put("namespace_science/attribute.py", b"VALUE=2\n")
        with self.assertRaises(guard.IntegrityError):
            guard.assert_access(cap, cap.fixture_ids[0], "targets")

    def test_local_source_alias_reparse_refused(self):
        target = self.root / "storage"
        target.mkdir()
        (target / "__init__.py").write_text("VALUE=1\n")
        try:
            (self.root / "aliased_science").symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest("Windows symlink privilege unavailable")
        self.put("experiments/v3/core.py", b"import aliased_science\n")
        with self.assertRaises(guard.AccessError):
            self.register()

    def test_own_manifest_and_model_seal_versions_reject_bool_even_diagnostic(self):
        study = self.register()
        cap = self.train(study)
        seal = self.seal(study, cap)
        for path, loader in ((seal, guard.load_model_seal), (study, guard.load_registered_study)):
            original = path.read_bytes()
            document = json.loads(original)
            document["schema_version"] = True
            self.dump(path, document)
            with self.subTest(path=str(path)), self.assertRaises(guard.IntegrityError):
                loader(study, verify=False)
            path.write_bytes(original)

    def test_actual_sibling_of_owner_is_refused(self):
        study = self.register()
        sibling_script = "import json,os,sys; from experiments.v3 import guard; print(json.dumps({'pid':os.getpid(),'created':guard.process_creation_time()}),flush=True); sys.stdin.read()"
        sibling = subprocess.Popen([sys.executable, "-c", sibling_script], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        def stop():
            sibling.communicate(input=b"", timeout=10)
        self.addCleanup(stop)
        identity = json.loads(sibling.stdout.readline())
        owner_script = r'''
import json,sys
from pathlib import Path
from experiments.v3 import guard
guard.ROOT=Path(sys.argv[1]); study=Path(sys.argv[2]); control=Path(sys.argv[3])
cap=guard.reserve_attempt(study,"train",("J03WOH","J03WOY"),control)
try:
    guard.authorize_child(cap,int(sys.argv[4]),sys.argv[5]); result="allowed"
except guard.AccessError:
    result="refused"
print(json.dumps({"sibling":result}))
'''
        owner = subprocess.run([sys.executable, "-c", owner_script, str(self.root), str(study), str(self.control),
                                str(identity["pid"]), identity["created"]], capture_output=True, timeout=30,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(owner.returncode, 0, owner.stderr.decode())
        self.assertEqual(json.loads(owner.stdout), {"sibling": "refused"})


class DynamicImportRepairTests(unittest.TestCase):
    setUp = GuardTests.setUp
    put = GuardTests.put
    dump = GuardTests.dump
    register = GuardTests.register

    def closure(self, source):
        self.put("experiments/v3/core.py", source.encode())
        return {p.relative_to(self.root).as_posix() for p in
                guard._scientific_paths(self.root, self.original_protocol)}

    def test_literal_importers_aliases_relative_package_and_fromlist_bind(self):
        for name in ("literal_dep", "alias_dep", "assigned_dep", "builtin_dep", "builtin_alias_dep"):
            self.put(name + ".py", b"VALUE=17\n")
        self.put("dynamic_pkg/__init__.py", b"from . import recursive\n")
        self.put("dynamic_pkg/recursive.py", b"VALUE=18\n")
        self.put("dynamic_pkg/relative.py", b"VALUE=19\n")
        self.put("dynamic_pkg/child/__init__.py", b"VALUE=20\n")
        self.put("dynamic_pkg/child/leaf.py", b"VALUE=21\n")
        paths = self.closure('''import importlib as il
from importlib import import_module as load
from builtins import __import__ as builtin_load
import builtins as bi
assigned = il.import_module
second = assigned
module_alias = il
builtin_module_alias = bi
assigned_builtin = builtin_module_alias.__import__
il.import_module('literal_dep')
load(name='alias_dep')
module_alias.import_module('assigned_dep')
second('assigned_dep', package=None)
__import__('builtin_dep')
builtin_load(name='builtin_alias_dep', fromlist=(), level=0)
assigned_builtin('builtin_alias_dep')
bi.__import__('dynamic_pkg.child', fromlist=['leaf'])
load('.relative', package='dynamic_pkg')
load('..recursive', 'dynamic_pkg.child')
''')
        expected = {name + ".py" for name in
                    ("literal_dep", "alias_dep", "assigned_dep", "builtin_dep", "builtin_alias_dep")}
        expected |= {"dynamic_pkg/__init__.py", "dynamic_pkg/recursive.py", "dynamic_pkg/relative.py",
                     "dynamic_pkg/child/__init__.py", "dynamic_pkg/child/leaf.py"}
        self.assertTrue(expected <= paths, expected - paths)

    def test_fresh_process_behavior_dependency_mutation_refused(self):
        self.put("experiments/v3/core.py", b"import invented_dynamic_entry\n")
        self.put("invented_dynamic_entry.py", b"import importlib\nVALUE=importlib.import_module('invented_dynamic_leaf').VALUE\n")
        dependency = self.put("invented_dynamic_leaf.py", b"VALUE=17\n")
        study = self.register()
        worker = "import sys; sys.dont_write_bytecode=True; sys.path.insert(0,sys.argv[1]); import invented_dynamic_entry; print(invented_dynamic_entry.VALUE)"
        def execute():
            result = subprocess.run([sys.executable, "-c", worker, str(self.root)], capture_output=True, timeout=20,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            return int(result.stdout)
        self.assertEqual(execute(), 17)
        dependency.write_bytes(b"VALUE=901\n")
        self.assertEqual(execute(), 901)
        with self.assertRaises(guard.IntegrityError):
            guard.load_registered_study(study)

    def test_new_dynamic_local_shadow_invalidates_study(self):
        self.put("experiments/v3/core.py", b"from importlib import import_module as load\nload('invented_later_shadow')\n")
        study = self.register()
        self.put("invented_later_shadow.py", b"VALUE=23\n")
        with self.assertRaises(guard.IntegrityError):
            guard.load_registered_study(study)

    def test_computed_import_arguments_refused(self):
        for source in (
            "import importlib\nimportlib.import_module(name)",
            "import importlib as il\nil.import_module('prefix.' + suffix)",
            "from importlib import import_module as load\nload('.child', package=package)",
            "from importlib import import_module as load\nload(*args)",
            "import importlib\nimportlib.import_module(**kwargs)",
            "__import__(name)",
            "__import__('pkg', fromlist=members)",
            "__import__('pkg', level=True)",
            "__import__('child', globals(), locals(), ['leaf'], 1)",
            "import importlib\nimportlib.import_module('.child', 'pkg..bad')",
        ):
            with self.subTest(source=source), self.assertRaises(guard.AccessError):
                self.closure(source)

    def test_importer_escape_and_indirect_computed_lookup_refused(self):
        for source in (
            "import importlib\ncallback(importlib.import_module)",
            "from importlib import import_module as load\ncallbacks = [load]",
            "import importlib\ngetattr(importlib, 'import_module')(name)",
            "import importlib as il\ngetattr(il, attribute)(name)",
            "import builtins as bi\ngetattr(bi, '__import__')(name)",
            "import importlib\nimportlib.__dict__['import_module'](name)",
            "import importlib\nimportlib.__getattribute__('import_module')(name)",
            "from importlib import import_module as load\nload = unknown\nload('pkg')",
        ):
            with self.subTest(source=source), self.assertRaises(guard.AccessError):
                self.closure(source)

    def test_closed_cli_dispatch_and_release_exclusion(self):
        helper = 'import importlib\ndef _module(name):\n    return importlib.import_module("experiments.v3." + name)\n'
        closure = self.original_protocol["fit"]["source_closure"]
        names = [Path(n).stem for key in ("scientific_new_modules", "release_only_modules") for n in closure[key]]
        cli = self.put("experiments/v3/cli.py", (helper + "\n".join(f"_module({name!r})" for name in names)
                                               + "\n_module('training' if condition else 'evaluate')\n").encode())
        paths = self.closure("# invented\n")
        for name in closure["scientific_new_modules"]:
            self.assertIn("experiments/v3/" + name, paths)
        for name in closure["release_only_modules"]:
            self.assertNotIn("experiments/v3/" + name, paths)
        for source in (helper + "_module(user_input)\n", helper + "_module('undeclared')\n",
                       helper + "importlib.import_module(other)\n",
                       helper.replace('"experiments.v3."', '"elsewhere."') + "_module('core')\n"):
            cli.write_bytes(source.encode())
            with self.subTest(source=source), self.assertRaises(guard.AccessError):
                self.closure("# invented\n")

    def test_dynamic_local_parent_missing_and_reparse_refused(self):
        self.put("dynamic_local/__init__.py", b"VALUE=1\n")
        with self.assertRaises(guard.AccessError):
            self.closure("import importlib\nimportlib.import_module('dynamic_local.missing')\n")
        target = self.root / "dynamic_storage"
        target.mkdir()
        (target / "__init__.py").write_text("VALUE=2\n")
        try:
            (self.root / "dynamic_alias").symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest("Windows symlink privilege unavailable")
        with self.assertRaises(guard.AccessError):
            self.closure("__import__('dynamic_alias')\n")


class TimestampOrderingRepairTests(unittest.TestCase):
    @staticmethod
    def batch(frames, slots, readonly=False):
        from experiments.v3.contracts import ObservationBatch
        frames = np.array(frames, dtype=np.int64)
        slots = np.array(slots, dtype=np.int32)
        n = max(1, int(frames.max(initial=-1)) + 1)
        s = max(1, int(slots.max(initial=-1)) + 1)
        ids = tuple(f"p{i:08d}" for i in range(s))
        if readonly:
            frames.flags.writeable = False
            slots.flags.writeable = False
        values = dict(frame_id=np.arange(n, dtype=np.int64), source_frame_id=np.arange(n, dtype=np.int64),
                      period_id=np.ones(n, dtype=np.int16), positions=np.zeros((n, s, 2), dtype=np.float32),
                      ball_xy=np.zeros((n, 2), dtype=np.float32), team_of_slot=np.zeros(s, dtype=np.int8), slot_ids=ids,
                      slot_ids_digest=hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest(),
                      source_time_frame_index=frames, source_time_slot=slots,
                      source_time_utc_ns=np.zeros(len(frames), dtype=np.int64), period_origins=(), fps=25., pitch=(100., 60.),
                      fixture_id="invented", source_digest="a" * 64)
        return ObservationBatch(**values), frames, slots

    def test_empty_and_singleton(self):
        for frames, slots in (([], []), ([0], [0])):
            batch, _, _ = self.batch(frames, slots)
            self.assertEqual(len(batch.source_time_slot), len(slots))

    def test_frame_increase_allows_slot_reset_and_same_frame_requires_increase(self):
        for frames, slots in (([0, 0, 0], [0, 1, 2]), ([0, 1, 1, 2], [3, 0, 2, 0])):
            self.batch(frames, slots)

    def test_inblock_duplicate_and_descending_rows(self):
        for frames, slots in (([0, 0], [0, 0]), ([0, 0], [1, 0]), ([1, 0], [0, 1])):
            with self.subTest(frames=frames, slots=slots), self.assertRaises(ValueError):
                self.batch(frames, slots)

    def test_cross_boundary_duplicate_and_descending_frame(self):
        for changed in (4095, 4094):
            frames = np.arange(4097, dtype=np.int64)
            frames[-1] = changed
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.batch(frames, np.zeros(len(frames), dtype=np.int32))

    def test_cross_boundary_descending_slot_and_valid_frame_reset(self):
        slots = np.arange(4097, dtype=np.int32)
        slots[-1] = 4094
        with self.assertRaises(ValueError):
            self.batch(np.zeros(4097, dtype=np.int64), slots)
        frames = np.repeat(np.arange(2050, dtype=np.int64), 2)
        self.batch(frames, np.tile(np.array([0, 1], dtype=np.int32), 2050))

    def test_readonly_owned_adoption_and_writeable_copy_unchanged(self):
        owned, frames, slots = self.batch([0, 1], [0, 0], readonly=True)
        self.assertIs(owned.source_time_frame_index, frames)
        self.assertIs(owned.source_time_slot, slots)
        copied, frames, slots = self.batch([0, 1], [0, 0])
        self.assertTrue(frames.flags.writeable)
        self.assertTrue(slots.flags.writeable)
        frames[0] = 1
        self.assertEqual(copied.source_time_frame_index[0], 0)
        self.assertFalse(copied.source_time_frame_index.flags.writeable)


class ContractTests(unittest.TestCase):
    def test_readonly_owned_adoption_and_view_copy(self):
        from experiments.v3.contracts import TargetBatch
        owned = np.array([0, 1], dtype=np.int8)
        owned.flags.writeable = False
        snapshot = TargetBatch(owned, "a" * 64).labels
        self.assertIsNot(snapshot, owned)
        self.assertFalse(np.shares_memory(snapshot, owned))
        np.testing.assert_array_equal(snapshot, owned)
        view = owned[:]
        copied = TargetBatch(view, "a" * 64).labels
        self.assertIsNot(copied, view)
        self.assertFalse(np.shares_memory(copied, view))
    def test_boundaries_own_readonly_arrays(self):
        from experiments.v3.contracts import TargetBatch
        source = np.array([0, 1, -1], dtype=np.int8)
        batch = TargetBatch(source, "a" * 64)
        self.assertFalse(batch.labels.flags.writeable)
        self.assertTrue(source.flags.writeable)
        source[0] = 2
        self.assertEqual(batch.labels[0], 0)

    def test_target_dtype_and_value_rejected(self):
        from experiments.v3.contracts import TargetBatch
        for values in (np.array([0], dtype=np.int64), np.array([4], dtype=np.int8)):
            with self.assertRaises(ValueError):
                TargetBatch(values, "a" * 64)

    def test_guard_api_exists(self):
        from experiments.v3 import guard
        for name in ("register_study", "load_registered_study", "reserve_attempt",
                     "assert_access", "authorize_child", "finish_attempt",
                     "seal_fitted_models", "load_model_seal"):
            self.assertTrue(callable(getattr(guard, name)))


if __name__ == "__main__":
    unittest.main()
