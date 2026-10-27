from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from plc_agent.config import ModelConfig,ROOT
from plc_agent.storage import Project,Session
from plc_agent.task_spec import validate_spec,validate_source,capability_report
from plc_agent.task_store import TaskStore
from plc_agent.task_runner import evaluate_task,monitor,execute_task,compile_task
from plc_agent.task_workflow import TaskWorkflow
from plc_agent.toolbox import Toolbox
from plc_probe.config import cache_dir
from plc_agent.provider import Cancelled

GOOD="""FUNCTION_BLOCK Mapping
VAR_INPUT x : BOOL; gate : BOOL; END_VAR
VAR_OUTPUT y : BOOL; END_VAR
y := x;
END_FUNCTION_BLOCK
"""
BAD=GOOD.replace("y := x;","IF gate THEN y := FALSE; ELSE y := x; END_IF;")

def contract():
    return validate_spec({"schema":"plc-task-v1","title":"arbitrary-name mapping fixture","block":"Mapping","target":"offline",
        "requirements":[{"id":"R1","text":"y follows x on each scan regardless of gate."}],
        "inputs":{"x":"BOOL","gate":"BOOL"},"outputs":{"y":"BOOL"},
        "scenarios":[{"name":"baseline","covers":["R1"],"trace":[
            {"time_ms":0,"inputs":{"x":False,"gate":False},"expect":{"y":False}},
            {"time_ms":10,"inputs":{"x":True,"gate":False},"expect":{"y":True}}]}],
        "properties":[{"id":"P_TRUE","requirement":"R1","when":{"inputs.x":True},"then":{"outputs.y":True}},
                      {"id":"P_FALSE","requirement":"R1","when":{"inputs.x":False},"then":{"outputs.y":False}}]})

def scenario(expected=True):
    return {"name":"gate_boundary","covers":["R1"],"basis":"R1 explicitly states regardless of gate","scope":"specified",
            "trace":[{"time_ms":0,"inputs":{"x":True,"gate":True},"expect":{"y":expected}}]}

def proposal(code):
    return {"text":json.dumps({"summary":"fixture proposal","code":code,"assumptions":[]})}

def review(cases=(),questions=()):
    return {"text":json.dumps({"summary":"isolated review fixture","scenarios":list(cases),"questions":list(questions)})}

class Provider:
    def __init__(self,answers):
        self.answers=list(answers);self.requests=[];self.cancel_event=threading.Event()
    def complete(self,messages,**kwargs):
        self.requests.append(copy.deepcopy(messages))
        return self.answers.pop(0)
    def cancel(self):self.cancel_event.set()

class GeneralTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=cache_dir());self.addCleanup(self.temp.cleanup)
        self.project=Project.create("generic task tests",Path(self.temp.name))
        self.session=Session.create(self.project)
        self.store=TaskStore(self.session)
        self.cfg=ModelConfig(base_url="http://localhost:1/v1",model="test-fixture",max_steps=12)

    def plan(self,spec=None,accept=True):
        result=self.store.create(spec or contract());task_id=result["task_id"]
        if accept:self.store.accept(task_id)
        return task_id

    def run_model(self,answers,spec=None):
        task_id=self.plan(spec);self.session.data["mode"]="execute"
        provider=Provider(answers)
        result=TaskWorkflow(self.session,self.cfg,provider).run(task_id)
        return task_id,provider,result

    def test_strict_contract_rejects_unsafe_or_unverifiable_data(self):
        for mutate in [
            lambda s:s["inputs"].update({"x);system(": "BOOL"}),
            lambda s:s["inputs"].update({"X":"BOOL"}),
            lambda s:s["inputs"].update({"TO":"BOOL"}),
            lambda s:s["scenarios"][0]["trace"][0]["inputs"].pop("x"),
            lambda s:s["scenarios"][0]["trace"][1].update(time_ms=0),
            lambda s:s["scenarios"][0].update(covers=["UNKNOWN"]),
            lambda s:s["scenarios"][0]["trace"][0]["inputs"].update(x=1),
            lambda s:s.update(tolerance=float("nan")),
            lambda s:s["properties"][0]["when"].update({"__import__('os')":True}),
        ]:
            spec=contract();mutate(spec)
            with self.assertRaises((ValueError,TypeError)):validate_spec(spec)

    def test_source_guard_preserves_name_type_and_direction(self):
        spec=contract();validate_source(GOOD,spec)
        for code in (GOOD.replace("x : BOOL","x : INT"),GOOD.replace("VAR_INPUT","VAR_IN_OUT"),
                     GOOD.replace("Mapping","Other"),GOOD.replace("END_FUNCTION_BLOCK","")):
            with self.assertRaises(ValueError):validate_source(code,spec)

    def test_plan_and_unaccepted_execution_do_not_call_model_or_write_code(self):
        task_id=self.plan(accept=False);provider=Provider([])
        result=TaskWorkflow(self.session,self.cfg,provider).run(task_id)
        self.assertEqual(result["status"],"planned")
        self.session.data["mode"]="execute"
        result=TaskWorkflow(self.session,self.cfg,provider).run(task_id)
        self.assertEqual(result["status"],"requires_contract_confirmation")
        self.assertEqual(provider.requests,[]);self.assertFalse((self.project.workspace/"code").exists())

    def test_model_tools_cannot_accept_or_overwrite_frozen_contract(self):
        task_id=self.plan(accept=False);tools=Toolbox(self.session)
        self.assertEqual(tools.call("plc_task_accept",{"task_id":task_id})["status"],"tool_error")
        self.assertEqual(tools.call("plc_task_run",{"task_id":task_id})["status"],"blocked_by_plan_mode")
        self.session.data["mode"]="execute"
        result=tools.call("write_file",{"path":str(self.store.directory(task_id)/"contract.json"),"content":"{}"})
        self.assertEqual(result["status"],"tool_error")

    def test_unresolved_questions_block_confirmation(self):
        spec=contract();spec["questions"]=["What should the reset priority be?"]
        task_id=self.plan(spec,accept=False)
        with self.assertRaisesRegex(ValueError,"Resolve questions"):self.store.accept(task_id)

    def test_capability_block_is_actionable_and_does_not_spend_model_budget(self):
        spec=contract();spec["target"]="codesys";spec["inputs"]["x"]="VARIANT"
        task_id=self.plan(spec);provider=Provider([]);self.session.data["mode"]="execute"
        result=TaskWorkflow(self.session,self.cfg,provider).run(task_id)
        self.assertEqual(result["status"],"capability_blocked");self.assertEqual(provider.requests,[])
        self.assertTrue(result["capabilities"]["blockers"][0]["actions"])
        self.assertEqual(result["target_compile"],"not_executed")

    def test_pv_extension_is_rejected_for_portable_target_but_comments_are_ignored(self):
        spec=contract();spec["target"]="portable"
        self.assertEqual(capability_report(spec,GOOD+"(* PV_READ(a,b,c) *)")["status"],"ready_for_offline_checks")
        self.assertEqual(capability_report(spec,GOOD+"PV_READ(a,b,c);")["status"],"blocked")

    def test_generic_real_native_execution_and_isolated_review(self):
        task_id,provider,result=self.run_model([proposal(GOOD),review([scenario()])])
        self.assertEqual(result["status"],"reviewed_offline_pass")
        self.assertTrue(result["final_evaluation"]["behavior_tested"])
        self.assertEqual(result["reviews"][0]["replayed_processes"],2)
        packet=json.loads(provider.requests[1][1]["content"])
        self.assertNotIn("scenarios",packet);self.assertNotIn("latest_evidence",packet);self.assertNotIn("properties",packet)
        self.assertEqual(result["target_compile"],"not_executed")
        self.assertTrue(Path(result["delivery"]["path"]).is_file())
        tools=Toolbox(self.session)
        page=tools.call('plc_task_evidence',{'task_id':task_id,'filename':'receipt.json','max_lines':5})
        self.assertTrue(page['truncated']);self.assertLess(len(page['content']),18001)
        self.assertEqual(tools.call('plc_task_evidence',{'task_id':task_id,'filename':'../acceptance.json'})['status'],'tool_error')

    def test_confirmed_property_counterexample_is_repaired_and_retained(self):
        task_id,provider,result=self.run_model([proposal(BAD),review([scenario()]),proposal(GOOD),review()])
        self.assertEqual(result["status"],"reviewed_offline_pass")
        self.assertEqual(len(result["attempts"]),2);self.assertEqual(len(provider.requests),4)
        self.assertEqual(result["reviews"][0]["findings"][0]["verdict"],"confirmed_by_frozen_property")
        self.assertEqual(result["final_evaluation"]["summary"]["scans"],3)
        repair_packet=json.loads(provider.requests[2][1]["content"])
        self.assertEqual(repair_packet["latest_evidence"]["counterexample"]["first_failure"]["property"],"P_TRUE")

    def test_reviewer_wrong_expectation_is_not_promoted_to_truth(self):
        task_id,provider,result=self.run_model([proposal(GOOD),review([scenario(False)])])
        self.assertEqual(result["status"],"review_disagreement")
        self.assertEqual(len(result["attempts"]),1);self.assertEqual(len(provider.requests),2)
        self.assertEqual(result["reviews"][0]["findings"][0]["verdict"],"requires_requirement_decision")
        self.assertEqual(result["reviews"][0]["regression_cases"],[])

    def test_confirmed_counterexamples_survive_run_limits_and_session_resume(self):
        task_id=self.plan();self.session.data['mode']='execute'
        first=TaskWorkflow(self.session,self.cfg,Provider([proposal(BAD),review([scenario()])])).run(task_id,max_revisions=1)
        self.assertEqual(first['status'],'repair_limit')
        self.assertEqual(len(self.store.regressions(task_id)['cases']),1)
        provider=Provider([proposal(GOOD),review()])
        second=TaskWorkflow(self.session,self.cfg,provider).run(task_id)
        self.assertEqual(second['status'],'reviewed_offline_pass')
        self.assertEqual(second['regression_scenarios'],1)
        self.assertEqual(second['final_evaluation']['summary']['scans'],3)
        packet=json.loads(provider.requests[0][1]['content'])
        self.assertEqual(packet['latest_evidence']['counterexample']['first_failure']['property'],'P_TRUE')

    def test_new_model_assumption_cannot_silently_change_accepted_contract(self):
        response=proposal(GOOD);value=json.loads(response["text"]);value["assumptions"]=["Ignore gate-high scans"]
        response["text"]=json.dumps(value)
        _,_,result=self.run_model([response,response,response])
        self.assertEqual(result["status"],"new_assumptions_require_plan")
        self.assertFalse((self.project.workspace/result["source"]).exists())

    def test_human_rejection_replays_same_source_without_a_new_model_request(self):
        task_id,_,first=self.run_model([proposal(GOOD),review([scenario(False)])])
        self.assertEqual(first['status'],'review_disagreement')
        rejected=self.store.reject_review_item(task_id,'F1','R1 explicitly requires y=x, so this expected FALSE is wrong')
        self.assertEqual(rejected['status'],'review_item_rejected')
        provider=Provider([])
        second=TaskWorkflow(self.session,self.cfg,provider).run(task_id)
        self.assertEqual(second['status'],'reviewed_offline_pass')
        self.assertEqual(provider.requests,[])
        self.assertEqual(second['source_sha256'],first['source_sha256'])
        self.assertTrue(second['reviews'][0]['reused_with_user_decisions'])
        self.assertEqual(second['reviews'][0]['findings'][0]['verdict'],'rejected_by_user')
        self.assertEqual(second['reviews'][0]['replayed_processes'],2)

    def test_review_decision_is_invalid_after_source_changes(self):
        task_id,_,first=self.run_model([proposal(GOOD),review([scenario(False)])])
        self.store.reject_review_item(task_id,'F1','R1 defines a different expectation')
        (self.project.workspace/first['source']).write_text(GOOD+'\n(* new version *)',encoding='utf-8')
        self.assertIsNone(self.store.review_override(task_id))
        provider=Provider([review()])
        result=TaskWorkflow(self.session,self.cfg,provider).run(task_id)
        self.assertEqual(result['status'],'reviewed_offline_pass')
        self.assertEqual(len(provider.requests),1)

    def test_review_question_can_be_rejected_but_model_has_no_rejection_tool(self):
        task_id,_,first=self.run_model([proposal(GOOD),review(questions=['Should x=2 be allowed?'])])
        self.assertEqual(first['status'],'review_questions')
        self.assertEqual(Toolbox(self.session).call('plc_task_reject',{'task_id':task_id})['status'],'tool_error')
        self.store.reject_review_item(task_id,'Q1','BOOL input validation only accepts true/false')
        result=TaskWorkflow(self.session,self.cfg,Provider([])).run(task_id)
        self.assertEqual(result['status'],'reviewed_offline_pass')
        self.assertEqual(result['reviews'][0]['unresolved_questions'],[])

    def test_restatement_can_be_retracted_without_mutating_the_frozen_contract(self):
        response=proposal(GOOD);raw=json.loads(response['text']);raw['assumptions']=['An unconfirmed restatement'];response['text']=json.dumps(raw)
        task_id,provider,result=self.run_model([response,proposal(GOOD),review()])
        self.assertEqual(result['status'],'reviewed_offline_pass')
        self.assertEqual(len(result['proposal_rejections']),1)
        self.assertEqual(len(result['attempts']),1)
        self.assertEqual(len(provider.requests),3)

    def test_existing_source_edited_during_generation_is_preserved(self):
        task_id=self.plan();path=self.project.workspace/"user.st";path.write_text(BAD,encoding="utf-8")
        self.session.data["mode"]="execute"
        class EditingProvider(Provider):
            def complete(inner,*args,**kwargs):
                path.write_text("EXTERNAL USER EDIT",encoding="utf-8")
                return super().complete(*args,**kwargs)
        provider=EditingProvider([proposal(GOOD)])
        fake=lambda *args:({"status":"fail"},None)
        result=TaskWorkflow(self.session,self.cfg,provider,evaluator=fake).run(task_id,"user.st")
        self.assertEqual(result["status"],"task_error")
        self.assertEqual(path.read_text(),"EXTERNAL USER EDIT")

    def test_stale_receipt_and_export_keep_the_evaluated_source_snapshot(self):
        task_id,_,result=self.run_model([proposal(GOOD),review()])
        path=self.project.workspace/result["source"];path.write_text("CHANGED BY USER",encoding="utf-8")
        self.assertEqual(self.store.latest(task_id)["status"],"stale_evidence")
        exported=self.store.export(task_id)
        with zipfile.ZipFile(exported["path"]) as z:
            self.assertEqual(z.read("candidate.st").decode(),GOOD)
            self.assertEqual(json.loads(z.read("receipt.json"))["status"],"stale_evidence")
            manifest=json.loads(z.read("manifest.json"))
            for name,sha in manifest.items():self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),sha)

    def test_changed_contract_loses_acceptance(self):
        task_id=self.plan();spec=self.store.load(task_id);spec["assumptions"].append("new unconfirmed assumption")
        (self.store.directory(task_id)/"contract.json").write_text(json.dumps(spec),encoding="utf-8")
        self.assertFalse(self.store.accepted(task_id))
        self.session.data["mode"]="execute"
        self.assertEqual(TaskWorkflow(self.session,self.cfg,Provider([])).run(task_id)["status"],"requires_contract_confirmation")

    def test_vacuous_property_is_reported_as_coverage_gap(self):
        spec=contract();spec["properties"].append({"id":"P_GATE","requirement":"R1","when":{"inputs.gate":True},"then":{"outputs.y":True}})
        task_id=self.plan(spec);self.session.data["mode"]="execute"
        result=TaskWorkflow(self.session,self.cfg,Provider([proposal(GOOD)])).run(task_id)
        self.assertEqual(result["status"],"coverage_gap")
        self.assertEqual(result["final_evaluation"]["summary"]["property_activations"]["P_GATE"],0)

    def test_signed_integer_float_and_time_are_transported_without_coercion(self):
        spec=validate_spec({"schema":"plc-task-v1","title":"scalar protocol fixture","block":"ScalarMap","target":"offline",
            "requirements":[{"id":"R1","text":"Copy scalar inputs exactly."}],
            "inputs":{"v":"DINT","f":"REAL","t":"TIME"},"outputs":{"vo":"DINT","fo":"REAL","copiedTime":"TIME"},
            "scenarios":[{"name":"types","covers":["R1"],"trace":[
                {"time_ms":0,"inputs":{"t":1500,"f":1.25,"v":-3},"expect":{"vo":-3,"fo":1.25,"copiedTime":1500}},
                {"time_ms":10,"inputs":{"v":-200,"f":-2.5,"t":20},"expect":{"vo":-200,"fo":-2.5,"copiedTime":20}}]}]})
        path=self.project.workspace/"types.st"
        path.write_text("FUNCTION_BLOCK ScalarMap\nVAR_INPUT v:DINT; f:REAL; t:TIME; END_VAR\n"
                        "VAR_OUTPUT vo:DINT; fo:REAL; copiedTime:TIME; END_VAR\nvo:=v; fo:=f; copiedTime:=t;\nEND_FUNCTION_BLOCK",encoding="utf-8")
        result,_=evaluate_task(path,spec)
        self.assertEqual(result["status"],"pass");self.assertEqual(result["cases"][0]["rows"][0]["actual"]["vo"],-3)

    def test_cancel_prevents_native_execution(self):
        path=self.project.workspace/"candidate.st";path.write_text(GOOD,encoding="utf-8")
        artifact=compile_task(path,contract());event=threading.Event();event.set()
        with self.assertRaises(Cancelled):execute_task(artifact,contract(),contract()["scenarios"],event)

    def test_properties_can_check_previous_scan_without_python_eval(self):
        spec=contract();spec["properties"]=[{"id":"P_PREV","requirement":"R1",
            "when":{"previous.inputs.x":False,"inputs.x":True},"then":{"outputs.y":True}}]
        result=monitor(spec,spec["scenarios"],[{"y":False},{"y":False}])
        self.assertEqual(result["cases"][0]["first_failure"]["scan"],1)
        self.assertEqual(result["summary"]["property_activations"]["P_PREV"],1)

    def test_examples_are_valid_contracts_for_new_tasks(self):
        for path in (ROOT/"examples/tasks").glob("*.json"):
            self.assertEqual(validate_spec(json.loads(path.read_text(encoding="utf-8")))["target"],"portable")

    def test_native_execution_of_a_nonterminating_candidate_is_bounded(self):
        path=self.project.workspace/'loop.st'
        path.write_text(GOOD.replace('y := x;','WHILE TRUE DO y := x; END_WHILE;'),encoding='utf-8')
        artifact=compile_task(path,contract())
        from plc_probe.backend import BackendError
        with self.assertRaises(BackendError) as caught:
            execute_task(artifact,contract(),contract()['scenarios'],timeout=.1)
        self.assertEqual(caught.exception.result['status'],'timeout')

    def test_unknown_adapter_is_blocked_without_silent_offline_fallback(self):
        spec=contract();spec['executor']='missingVendorAdapter'
        task_id=self.plan(spec);self.session.data['mode']='execute';provider=Provider([])
        result=TaskWorkflow(self.session,self.cfg,provider).run(task_id)
        self.assertEqual(result['status'],'capability_blocked')
        self.assertEqual(result['capabilities']['blockers'][0]['feature'],'adapter_not_installed')
        self.assertEqual(provider.requests,[])

    def test_requirement_snapshots_are_immutable_and_bound_to_confirmation(self):
        source=self.project.workspace/'requirement.md';source.write_text('Original requirement',encoding='utf-8')
        task_id=self.store.create(contract(),['requirement.md'])['task_id'];self.store.accept(task_id)
        source.write_text('Changed upload',encoding='utf-8')
        self.assertTrue(self.store.accepted(task_id))
        snapshot=next((self.store.directory(task_id)/'sources').glob('*'))
        self.assertEqual(snapshot.read_text(),'Original requirement')
        snapshot.write_text('Corrupted snapshot',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'snapshot'):self.store.accepted(task_id)

    def test_backend_changes_invalidate_a_passing_receipt(self):
        task_id,_,_=self.run_model([proposal(GOOD),review()])
        with patch('plc_agent.task_backend.OfflineBackend.fingerprint',return_value='changed backend'):
            receipt=self.store.latest(task_id)
        self.assertEqual(receipt['status'],'stale_evidence')
        self.assertIn('backend_or_evaluator_changed',receipt['stale_reasons'])

    def test_review_model_budget_exhaustion_cannot_produce_a_pass(self):
        self.cfg.max_steps=1
        _,provider,result=self.run_model([proposal(GOOD)])
        self.assertEqual(result['status'],'task_error')
        self.assertEqual(len(provider.requests),1)

    def test_outer_chat_uses_general_receipt_when_shared_budget_is_exhausted(self):
        from plc_agent.engine import Engine
        from test_agent_core import ScriptedProvider,call
        task_id=self.plan();self.session.data['mode']='execute';self.cfg.max_steps=3
        provider=ScriptedProvider([call('plc_task_run',{'task_id':task_id}),proposal(GOOD),review()])
        engine=Engine(self.session,self.cfg,provider)
        answer=engine.run('执行已确认的通用PLC任务')
        self.assertEqual(len(provider.requests),3)
        self.assertEqual(self.session.data['status'],'idle')
        self.assertIn('reviewed_offline_pass',answer)
        self.assertIn('not_executed',answer)

    def test_outer_model_claim_cannot_override_general_task_failure(self):
        from plc_agent.engine import Engine
        from test_agent_core import ScriptedProvider,call
        task_id=self.plan();self.session.data['mode']='execute'
        provider=ScriptedProvider([call('plc_task_run',{'task_id':task_id}),proposal(GOOD),review([scenario(False)]),
                                   {'text':'全部成功，已完成。'}])
        answer=Engine(self.session,self.cfg,provider).run('执行已确认的通用PLC任务')
        self.assertIn('review_disagreement',answer)
        self.assertEqual(self.session.data['status'],'workflow_blocked')

    def test_malformed_review_retains_files_and_reports_an_error(self):
        task_id,_,result=self.run_model([proposal(GOOD),review([None])])
        self.assertEqual(result['status'],'task_error')
        self.assertEqual((self.project.workspace/result['source']).read_text(),GOOD)

if __name__=="__main__":unittest.main()
