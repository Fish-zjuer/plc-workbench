"""Solver soundness boundaries and real native replay; fixtures are not model benchmarks."""
import copy
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
import z3

from plc_agent.config import ROOT,ModelConfig
from plc_agent.storage import Project,Session
from plc_agent.task_store import TaskStore
from plc_agent.task_spec import validate_spec
from plc_agent.task_runner import compile_task,execute_task
from plc_agent.task_workflow import TaskWorkflow
from plc_agent.formal_st import parse,UnsupportedST
from plc_agent.formal_verify import verify
from plc_agent.task_formal import check,standalone
from plc_agent.toolbox import Toolbox
from plc_probe.config import cache_dir
from test_general_tasks import contract,GOOD,Provider,proposal,review

HIDDEN=GOOD.replace("VAR_OUTPUT y : BOOL; END_VAR","VAR_OUTPUT y : BOOL; END_VAR\nVAR count : DINT; END_VAR").replace("y := x;","count := count + 1;\ny := x AND (count < 3);")

class FormalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=cache_dir());self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.spec=contract()
        self.path=self.root/"candidate.st";self.path.write_text(GOOD,encoding="utf-8")
    def solve(self,code=GOOD,bound=8,spec=None):
        self.path.write_text(code,encoding="utf-8")
        return verify(self.path,spec or self.spec,self.root/"proof",bound=bound)
    def test_source_derived_mapping_is_proved_by_induction(self):
        result=self.solve()
        self.assertEqual(result["status"],"proved")
        self.assertEqual(set(result["proved_property_ids"]),{"P_TRUE","P_FALSE"})
        query=next((self.root/"proof").glob("*induction*.smt2"))
        solver=z3.Solver();solver.from_string(query.read_text(encoding='utf-8'))
        self.assertEqual(solver.check(),z3.unsat)
    def test_existing_weak_model_programs_have_real_proofs(self):
        for name,properties in (("interlocked_start",{"P_STOP","P_INTERLOCK"}),("acknowledge_latch",{"P_FAULT"})):
            base=ROOT/"experiments/general_tasks_r6/final_recheck"/name
            spec=validate_spec(json.loads((base/"contract.json").read_text(encoding="utf-8")))
            result=verify(base/"candidate_final.st",spec,self.root/name,bound=8)
            self.assertEqual(result["status"],"proved")
            self.assertEqual(set(result["proved_property_ids"]),properties)
    def test_bounded_search_finds_late_failure_and_two_native_replays_confirm_it(self):
        self.path.write_text(HIDDEN,encoding="utf-8")
        result=check(self.path,self.spec,self.root/"replayed")
        self.assertEqual(result["status"],"counterexample_confirmed")
        failure=next(p for p in result["properties"] if p["status"]=="counterexample")
        self.assertEqual(failure["first_failing_scan"],2)
        self.assertEqual(result["replay_result"]["status"],"fail")
        self.assertTrue((self.root/"replayed/counterexample_replay_2.json").is_file())
    def test_induction_counterstate_is_not_reported_as_reachable_bug(self):
        result=self.solve(HIDDEN.replace("count < 3","count < 20"),bound=4)
        self.assertEqual(result["status"],"bounded_only")
        self.assertFalse(any(p["status"]=="counterexample" for p in result["properties"]))
    def test_signed_unsigned_overflow_matches_native_stored_width(self):
        code=HIDDEN.replace("count : DINT","count : USINT := 254").replace("count < 3","count >= 250")
        self.path.write_text(code,encoding="utf-8")
        result=check(self.path,self.spec,self.root/"wrap")
        self.assertEqual(result["status"],"counterexample_confirmed")
        p=next(p for p in result["properties"] if p["status"]=="counterexample")
        self.assertEqual(p["first_failing_scan"],1)
    def test_unsupported_whole_program_never_proves_a_supported_prefix(self):
        variants=[GOOD+"FUNCTION Other : BOOL\nOther:=TRUE;\nEND_FUNCTION",
                  GOOD.replace("y := x;","WHILE x DO y:=TRUE; END_WHILE;"),
                  GOOD.replace("y := x;","y := Mystery(x);"),
                  GOOD.replace("y := x;","y := x; RETURN;"),
                  GOOD.replace("VAR_OUTPUT","VAR retained : TIME; END_VAR\nVAR_OUTPUT"),
                  GOOD.replace("y := x;","y := x; {attribute 'foo'}"),
                  GOOD.replace("y := x;","y := 1.0 > 0.0;"),
                  GOOD.replace("y := x;","(* unterminated")]
        for code in variants:
            with self.subTest(code=code):
                self.assertEqual(self.solve(code)["status"],"unsupported")
    def test_target_dependent_intermediate_width_is_rejected(self):
        code=HIDDEN.replace("count < 3","count + 1 < 3")
        self.assertEqual(self.solve(code)["status"],"unsupported")
    def test_comments_nested_branches_and_declared_initializers(self):
        code=GOOD.replace("y := x;","(* outer (* nested *) ignored *)\nIF x THEN IF gate THEN y:=TRUE; ELSE y:=TRUE; END_IF; ELSE y:=FALSE; END_IF;")
        self.assertEqual(self.solve(code)["status"],"proved")
    def test_no_invariants_is_not_a_proof_of_scenarios(self):
        spec=contract();spec["properties"]=[]
        self.assertEqual(self.solve(spec=spec)["status"],"no_properties")
    def test_previous_input_and_output_state_are_modeled(self):
        base=ROOT/"experiments/general_tasks_r6/final_recheck/interlocked_start"
        spec=validate_spec(json.loads((base/"contract.json").read_text(encoding="utf-8")))
        spec["properties"]+=[
            {"id":"P_HOLD","requirement":"R1","when":{"previous.outputs.running":True,"inputs.stop":False,"inputs.permit":True},"then":{"outputs.running":True}},
            {"id":"P_HELD_START","requirement":"R3","when":{"previous.outputs.running":False,"previous.inputs.start":True,"inputs.start":True},"then":{"outputs.running":False}},
            {"id":"P_EDGE","requirement":"R1","when":{"previous.inputs.start":False,"inputs.start":True,"inputs.stop":False,"inputs.permit":True},"then":{"outputs.running":True}}]
        result=verify(base/"candidate_final.st",spec,self.root/"history",bound=8)
        self.assertEqual(result["status"],"proved")
        self.assertEqual(len(result["proved_property_ids"]),5)
    def test_all_boolean_sequences_of_length_three_match_actual_native_code(self):
        artifact=compile_task(self.path,self.spec);program=parse(GOOD)
        cases=[];expected=[]
        for i,sequence in enumerate(itertools.product(list(itertools.product((False,True),repeat=2)),repeat=3)):
            case={"name":"seq_"+str(i),"covers":["R1"],"trace":[]};state=program.initial_state(z3);outputs=[]
            for step,(x,gate) in enumerate(sequence):
                inputs={"x":x,"gate":gate};case["trace"].append({"time_ms":step,"inputs":inputs})
                env=program.execute({**state,"X":program.value(x,"BOOL",z3),"GATE":program.value(gate,"BOOL",z3)},z3)
                outputs.append(z3.is_true(z3.simplify(env["Y"].term)));state={n:env[n] for n in state}
            cases.append(case);expected.append(outputs)
        actual=execute_task(artifact,self.spec,cases)
        self.assertEqual([[r["actual"]["y"] for r in c["rows"]] for c in actual["cases"]],expected)
    def test_formal_mode_blocks_model_owned_approval_and_plan_execution(self):
        project=Project.create("formal fixture",self.root);session=Session.create(project)
        task_id=TaskStore(session).create(self.spec)["task_id"]
        self.assertEqual(Toolbox(session).call("plc_task_formal",{"task_id":task_id})["status"],"blocked_by_plan_mode")
        self.assertEqual(standalone(session,task_id)["status"],"planned")
    def test_required_formal_counterexample_drives_repair_and_export(self):
        project=Project.create("formal repair",self.root);session=Session.create(project);store=TaskStore(session)
        spec=contract();spec["formal"]={"mode":"required","bound":8}
        task_id=store.create(spec)["task_id"];store.accept(task_id);session.data["mode"]="execute"
        path=project.workspace/"code"/(task_id+".st");path.parent.mkdir();path.write_text(HIDDEN,encoding="utf-8")
        provider=Provider([proposal(GOOD),review()])
        result=TaskWorkflow(session,ModelConfig(base_url="http://localhost:1/v1",model="fixture"),provider).run(task_id)
        self.assertEqual(result["status"],"reviewed_offline_pass")
        self.assertEqual(result["formal_attempts"][0]["status"],"counterexample_confirmed")
        self.assertEqual(result["formal_verification"]["status"],"proved")
        self.assertEqual(result["regression_scenarios"],1)
        self.assertEqual(len(provider.requests),2)
        self.assertEqual(store.latest(task_id)["status"],"reviewed_offline_pass")
        import zipfile
        with zipfile.ZipFile(result["delivery"]["path"]) as z:self.assertTrue(any(n.endswith(".smt2") for n in z.namelist()))
        proof=Path(result['formal_verification']['evidence_path'])
        query=next(proof.glob('*.smt2'));query.write_text(query.read_text(encoding='utf-8')+'\n; tampered',encoding='utf-8')
        self.assertEqual(store.latest(task_id)['status'],'stale_evidence')
        self.assertIn('formal_evidence_changed',store.latest(task_id)['stale_reasons'])
    def test_separate_proof_status_invalidates_source_and_query_changes(self):
        project=Project.create('standalone proof',self.root);session=Session.create(project);store=TaskStore(session)
        task_id=store.create(self.spec)['task_id'];store.accept(task_id);session.data['mode']='execute'
        path=project.workspace/'code'/f'{task_id}.st';path.parent.mkdir();path.write_text(GOOD,encoding='utf-8')
        result=standalone(session,task_id)
        self.assertEqual(store.formal_status(task_id)['status'],'proved')
        path.write_text(GOOD+'\n',encoding='utf-8')
        self.assertEqual(store.formal_status(task_id)['status'],'stale_evidence')
        path.write_text(GOOD,encoding='utf-8')
        query=next(Path(result['evidence_path']).glob('*.smt2'));query.unlink()
        self.assertEqual(store.formal_status(task_id)['status'],'stale_evidence')
    def test_required_unsupported_library_blocks_without_wasting_model_calls(self):
        project=Project.create("unsupported proof",self.root);session=Session.create(project);store=TaskStore(session)
        spec=contract();spec["formal"]={"mode":"required"}
        task_id=store.create(spec)["task_id"];store.accept(task_id);session.data["mode"]="execute"
        path=project.workspace/"code"/(task_id+".st");path.parent.mkdir()
        path.write_text(GOOD.replace("y := x;","y := x;").replace("VAR_OUTPUT","VAR trig : R_TRIG; END_VAR\nVAR_OUTPUT"),encoding="utf-8")
        provider=Provider([])
        result=TaskWorkflow(session,ModelConfig(),provider).run(task_id)
        self.assertEqual(result["status"],"formal_unsupported");self.assertEqual(provider.requests,[])

if __name__=="__main__":unittest.main()
