from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from plc_agent.bank_contracts import questions
from plc_agent.config import ModelConfig,ROOT
from plc_agent.provider import ProviderError
from plc_agent.call_budget import CallBudget
from plc_agent.engine import Engine
from plc_agent.storage import Project,Session
from plc_agent.toolbox import Toolbox
from plc_agent.workflow import PLCWorkflow,validate_candidate,evidence_brief
from plc_probe.config import cache_dir
from test_agent_core import ScriptedProvider,call


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=cache_dir());self.addCleanup(self.temp.cleanup)
        self.project=Project.create('workflow fixture',Path(self.temp.name));self.session=Session.create(self.project)
        self.cfg=ModelConfig(base_url='http://localhost:1/v1',model='fixture')
        self.question=next(q for q in questions() if q['id']=='03')
        self.code=(ROOT/'experiments/deepseek_20/tasks/03/final.st').read_text(encoding='utf-8')

    def proposal(self,code=None):
        return {'text':json.dumps({'summary':'model-authored fixture','code':self.code if code is None else code,'assumptions':[]})}

    def test_plan_does_not_call_model_write_candidate_or_execute(self):
        provider=ScriptedProvider([])
        result=PLCWorkflow(self.session,self.cfg,provider,evaluator=lambda *_:self.fail('executed in plan mode')).run('03')
        self.assertEqual(result['status'],'planned');self.assertEqual(provider.requests,[])
        self.assertFalse((self.project.workspace/'candidate.st').exists())
        self.assertEqual(Toolbox(self.session).call('plc_solve_bank',{'question_id':'03'})['status'],'blocked_by_plan_mode')

    def test_incomplete_or_narrowed_interface_is_rejected_without_file_mutation(self):
        for code in [self.code.replace('END_FUNCTION_BLOCK',''),self.code.replace('Value       : REAL','Value       : INT')]:
            if code==self.code:continue
            with self.assertRaises(ValueError):validate_candidate(code,self.question)
        with self.assertRaises(ValueError):validate_candidate(self.code.replace('REAL','INT'),self.question)
        self.session.data['mode']='execute'
        provider=ScriptedProvider([self.proposal('FUNCTION_BLOCK Q03\nEND_FUNCTION_BLOCK')]*3)
        result=PLCWorkflow(self.session,self.cfg,provider).run('03',max_revisions=1)
        self.assertEqual(result['status'],'repair_limit');self.assertFalse((self.project.workspace/'candidate.st').exists())

    def test_generation_is_immediately_followed_by_real_test_and_receipt(self):
        self.session.data['mode']='execute';provider=ScriptedProvider([self.proposal()])
        result=PLCWorkflow(self.session,self.cfg,provider).run('03')
        self.assertEqual(result['status'],'verified');self.assertEqual(len(provider.requests),1)
        self.assertTrue((self.project.workspace/result['run_path']/'receipt.json').is_file())
        self.assertEqual(result['final_evaluation']['summary']['failed'],0)

    def test_repair_sees_only_latest_source_bound_failure(self):
        self.session.data['mode']='execute'
        path=self.project.workspace/'candidate.st';path.write_text(self.code,encoding='utf-8')
        calls=[]
        def evaluate(path,qid):
            calls.append(path.read_text(encoding='utf-8'))
            if len(calls)==1:return {'status':'fail','source_sha256':'old','first_failure':{'output':'hiAlarm','expected':1,'actual':0}}
            import hashlib
            return {'status':'pass','source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        provider=ScriptedProvider([self.proposal(self.code+'\n(* revision *)')])
        result=PLCWorkflow(self.session,self.cfg,provider,evaluator=evaluate).run('03')
        self.assertEqual(result['status'],'verified');self.assertEqual(len(calls),2)
        packet=json.loads(provider.requests[0][0][1]['content'])
        self.assertEqual(packet['latest_evidence']['first_failure']['output'],'hiAlarm')
        self.assertEqual(packet['current_source'],self.code)

    def test_real_backend_block_stops_without_wasting_model_calls(self):
        self.session.data['mode']='execute';(self.project.workspace/'candidate.st').write_text(self.code,encoding='utf-8')
        provider=ScriptedProvider([])
        result=PLCWorkflow(self.session,self.cfg,provider,evaluator=lambda *_:{'status':'compile_error','stderr':"Undefined type 'LTIME'"}).run('03')
        self.assertEqual(result['status'],'backend_ltime_unavailable');self.assertEqual(len(provider.requests),0)

    def test_external_edit_while_model_generates_is_not_overwritten(self):
        self.session.data['mode']='execute';path=self.project.workspace/'candidate.st';path.write_text(self.code,encoding='utf-8')
        parent=self
        class EditingProvider(ScriptedProvider):
            def complete(self,*args,**kwargs):
                path.write_text('USER EDIT',encoding='utf-8')
                return super().complete(*args,**kwargs)
        provider=EditingProvider([self.proposal()])
        with self.assertRaisesRegex(ValueError,'外部修改'):
            PLCWorkflow(self.session,self.cfg,provider,evaluator=lambda *_:{'status':'fail'}).run('03')
        self.assertEqual(path.read_text(),'USER EDIT')

    def test_model_claim_of_success_cannot_override_receipt(self):
        self.session.data['mode']='execute'
        provider=ScriptedProvider([call('plc_solve_bank',{'question_id':'03','max_revisions':1}),
                                   *([self.proposal('FUNCTION_BLOCK Q03\nEND_FUNCTION_BLOCK')]*3),{'text':'已经全部通过'}])
        engine=Engine(self.session,self.cfg,provider)
        answer=engine.run('完成03题')
        self.assertIn('尚无当前源码验证通过',answer)
        self.assertEqual(self.session.data['status'],'workflow_blocked')

    def test_benchmark_projects_are_hidden_from_normal_resume_selection(self):
        project=Project.create('experiment',Path(self.temp.name),kind='benchmark')
        visible=Project.list(Path(self.temp.name))
        self.assertNotIn(project.data['id'],[p['id'] for p in visible])
        self.assertIn(project.data['id'],[p['id'] for p in Project.list(Path(self.temp.name),include_benchmarks=True)])

    def test_provider_error_has_a_bound_receipt_and_preserves_source(self):
        self.session.data['mode']='execute'
        path=self.project.workspace/'candidate.st';path.write_text(self.code,encoding='utf-8')
        provider=ScriptedProvider([ProviderError('network unavailable')])
        result=PLCWorkflow(self.session,self.cfg,provider,evaluator=lambda *_:{'status':'fail'}).run('03')
        self.assertEqual(result['status'],'workflow_error')
        self.assertEqual(path.read_text(encoding='utf-8'),self.code)
        self.assertTrue((self.project.workspace/result['run_path']/'receipt.json').is_file())
        self.assertEqual(self.session.data['status'],'workflow_blocked')

    def test_invalid_json_does_not_consume_a_source_revision(self):
        self.session.data['mode']='execute'
        provider=ScriptedProvider([{'text':'not JSON'},self.proposal()])
        result=PLCWorkflow(self.session,self.cfg,provider).run('03',max_revisions=1)
        self.assertEqual(result['status'],'verified')
        self.assertEqual(result['attempts'][0]['status'],'rejected_packaging')
        self.assertEqual(result['attempts'][1]['revision'],1)

    def test_nested_model_requests_share_one_budget(self):
        base=ScriptedProvider([{'text':'one'},{'text':'two'}])
        shared=CallBudget(base,2)
        shared.complete([]);shared.complete([])
        with self.assertRaises(ProviderError):shared.complete([])
        self.assertEqual(len(base.requests),2)

    def test_explicit_task_scope_hides_unrelated_environment_tools(self):
        provider=ScriptedProvider([call('plc_profiles',{}),{'text':'仅分析当前题目'}])
        engine=Engine(self.session,self.cfg,provider)
        engine.run('请计划第05题')
        names={t['function']['name'] for t in provider.requests[0][1]}
        self.assertNotIn('plc_profiles',names)
        self.assertNotIn('plc_compile_unit',names)
        self.assertIn('read_bank_question',names)
        self.assertIn('本轮专注题05',provider.requests[1][0][-1]['content'])

    def test_budget_end_uses_verified_receipt_without_an_extra_model_call(self):
        self.session.data['mode']='execute';self.cfg.max_steps=1
        (self.project.workspace/'candidate.st').write_text(self.code,encoding='utf-8')
        provider=ScriptedProvider([call('plc_solve_bank',{'question_id':'03'})])
        engine=Engine(self.session,self.cfg,provider)
        answer=engine.run('完成第03题')
        self.assertEqual(len(provider.requests),1)
        self.assertEqual(self.session.data['status'],'idle')
        self.assertIn('当前源码通过',answer)

    def test_repair_memory_carries_previous_failed_constraint(self):
        import hashlib
        self.session.data['mode']='execute'
        path=self.project.workspace/'candidate.st';path.write_text(self.code,encoding='utf-8')
        checked=[]
        def evaluate(path,qid):
            checked.append(True)
            if len(checked)<3:return {'status':'fail','first_failure':{'output':'hiAlarm' if len(checked)==1 else 'status','expected':1,'actual':0}}
            return {'status':'pass','source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        provider=ScriptedProvider([self.proposal(self.code+'\n(* v1 *)'),self.proposal(self.code+'\n(* v2 *)')])
        result=PLCWorkflow(self.session,self.cfg,provider,evaluator=evaluate).run('03')
        self.assertEqual(result['status'],'verified')
        packet=json.loads(provider.requests[1][0][1]['content'])
        self.assertEqual(packet['previous_attempts'][0]['first_failure']['output'],'status')
        self.assertEqual([f['first_failure']['output'] for f in packet['observed_failure_constraints']],['hiAlarm','status'])


if __name__=='__main__':unittest.main()
