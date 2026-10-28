import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from plc_agent.bank_contracts import questions
from plc_agent.config import ModelConfig, ROOT
from plc_agent.engine import Engine, source_hash_for_receipt
from plc_agent.storage import Project, Session, atomic_json
from plc_agent.toolbox import Toolbox
from plc_agent.validation import CodesysCompiler, ValidationConfig, ValidationPipeline, static_check
from plc_agent.workflow import PLCWorkflow
from test_agent_core import ScriptedProvider, call


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)
        self.exe=self.home/'CODESYS.exe';self.exe.write_bytes(b'fixture compiler')
        self.config=ValidationConfig(mode='codesys',executable=str(self.exe))
        self.project=Project.create('target validation',self.home)
        self.session=Session.create(self.project);self.session.data['mode']='execute'
        self.path=self.project.workspace/'candidate.st'
        self.code=(ROOT/'experiments/backend_r4/tasks/03/final.st').read_text(encoding='utf-8')
        self.path.write_text(self.code,encoding='utf-8')
        self.model=ModelConfig(base_url='http://fixture.invalid/v1',model='scripted-fixture')

    def pipeline(self,compiler_status='pass',behavior_status='pass',mutate=False,wrong_hash=False):
        parent=self
        class Compiler:
            calls=0
            def compile(self,source,qid,fingerprint):
                self.calls+=1
                digest=sha(source)
                if mutate:source.write_text('external edit',encoding='utf-8')
                return {'status':compiler_status,'source_sha256':'wrong' if wrong_hash else digest,
                        'errors':[{'number':46,'text':'Unknown function Example'}] if compiler_status!='pass' else []}
        calls=[]
        def behavior(source,qid):
            calls.append(qid)
            return {'status':behavior_status,'source_sha256':sha(source),'behavior_tested':True,
                    'summary':{'scenarios':1,'failed':int(behavior_status!='pass')}}
        compiler=Compiler()
        return ValidationPipeline(self.config,self.home,compiler,behavior),compiler,calls

    def test_vendor_compile_failure_cannot_be_replaced_by_behavior_pass(self):
        pipeline,compiler,behavior=self.pipeline(compiler_status='compile_error')
        result=pipeline.evaluate(self.path,'03')
        self.assertEqual(result['status'],'compile_error');self.assertEqual(result['failure_stage'],'codesys')
        self.assertEqual(compiler.calls,1);self.assertEqual(behavior,[])
        self.assertEqual(result['primary_diagnostics'][0]['number'],46)

    def test_vendor_pass_does_not_hide_behavior_failure(self):
        pipeline,_,behavior=self.pipeline(behavior_status='fail')
        result=pipeline.evaluate(self.path,'03')
        self.assertEqual(result['status'],'fail');self.assertEqual(result['failure_stage'],'behavior')
        self.assertEqual(result['stages']['codesys']['status'],'pass');self.assertEqual(behavior,['03'])

    def test_mismatched_compiler_hash_or_external_edit_stops_before_behavior(self):
        for kwargs in ({'wrong_hash':True},{'mutate':True}):
            self.path.write_text(self.code,encoding='utf-8')
            pipeline,_,behavior=self.pipeline(**kwargs)
            self.assertEqual(pipeline.evaluate(self.path,'03')['status'],'source_conflict')
            self.assertEqual(behavior,[])

    def test_static_reserved_word_is_detected_before_compilation(self):
        source=(ROOT/'experiments/backend_r4/tasks/20/final.st').read_text(encoding='utf-8')
        self.path.write_text(source,encoding='utf-8')
        pipeline,compiler,behavior=self.pipeline()
        result=pipeline.evaluate(self.path,'20')
        self.assertEqual(result['status'],'static_error')
        self.assertEqual(result['diagnostics'][0]['identifier'],'lint')
        self.assertEqual(result['diagnostics'][0]['line'],66)
        self.assertEqual(compiler.calls,0);self.assertEqual(behavior,[])
        self.assertEqual(self.path.read_text(encoding='utf-8'),source)

    def test_comments_strings_and_valid_type_names_do_not_trigger_keyword_error(self):
        question=next(q for q in questions() if q['id']=='03')
        code=self.code+'\n(* lint : REAL; *)\n'
        self.assertEqual(static_check(code,question,self.config)['status'],'pass')

    def test_platform_interface_is_a_blocker_and_consumes_no_model_request(self):
        self.config.save(self.home)
        self.path.write_bytes((ROOT/'experiments/backend_r4/tasks/18/final.st').read_bytes())
        provider=ScriptedProvider([])
        result=PLCWorkflow(self.session,self.model,provider).run('18')
        self.assertEqual(result['status'],'platform_blocked');self.assertEqual(provider.requests,[])

    def test_missing_compiler_blocks_generation_before_model_readiness(self):
        self.config.executable=str(self.home/'missing.exe');self.config.save(self.home)
        self.path.unlink()
        provider=ScriptedProvider([])
        result=PLCWorkflow(self.session,ModelConfig(),provider).run('03')
        self.assertEqual(result['status'],'backend_dependency_unavailable');self.assertEqual(provider.requests,[])

    def test_plan_mode_cannot_invoke_target_compiler(self):
        self.config.save(self.home);self.session.data['mode']='plan'
        with patch('plc_agent.validation.CodesysCompiler.compile') as compiler:
            result=PLCWorkflow(self.session,ModelConfig(),ScriptedProvider([])).run('03')
        self.assertEqual(result['status'],'planned');compiler.assert_not_called()

    def test_both_gates_required_in_receipt_and_config_changes_make_it_stale(self):
        self.config.save(self.home)
        pipeline,_,_=self.pipeline()
        with patch('plc_agent.validation.pipeline_for',return_value=pipeline):
            result=PLCWorkflow(self.session,ModelConfig(),ScriptedProvider([])).run('03')
        tools=Toolbox(self.session)
        self.assertTrue(source_hash_for_receipt(tools,result))
        forged=copy.deepcopy(result);forged['final_evaluation']['stages']['codesys']['status']='compile_error'
        self.assertFalse(source_hash_for_receipt(tools,forged))
        self.config.mode='offline';self.config.save(self.home)
        self.assertFalse(source_hash_for_receipt(tools,result))

    def test_compiler_diagnostics_reach_model_and_repair_uses_same_policy(self):
        self.config.save(self.home);pipeline,compiler,_=self.pipeline()
        calls=[]
        def compile(source,qid,fingerprint):
            calls.append(sha(source))
            return {'status':'compile_error' if len(calls)==1 else 'pass','source_sha256':sha(source),
                    'errors':[{'number':46,'text':'Missing target function'}] if len(calls)==1 else []}
        compiler.compile=compile
        provider=ScriptedProvider([{'text':json.dumps({'summary':'fixture repair','code':self.code+'\n(* fixture revision *)','assumptions':[]})}])
        with patch('plc_agent.validation.pipeline_for',return_value=pipeline):
            result=PLCWorkflow(self.session,self.model,provider).run('03')
        self.assertEqual(result['status'],'verified');self.assertEqual(result['model_calls'],1)
        packet=json.loads(provider.requests[0][0][1]['content'])
        self.assertEqual(packet['latest_evidence']['failure_stage'],'codesys')
        self.assertEqual(packet['latest_evidence']['primary_diagnostics'][0]['number'],46)
        self.assertEqual(packet['completion_policy']['required_gates'],['static','codesys','behavior'])

    def test_repeated_failed_candidate_stops_without_writing_versions(self):
        provider=ScriptedProvider([{'text':json.dumps({'summary':'no change','code':self.code,'assumptions':[]})}]*3)
        result=PLCWorkflow(self.session,self.model,provider,evaluator=lambda *_:{'status':'fail'}).run('03')
        self.assertEqual(result['status'],'no_progress');self.assertEqual(len(provider.requests),3)
        self.assertFalse(list((self.project.path/'versions').glob('*.json')))

    def test_compiler_cache_requires_same_source_environment_and_existing_evidence(self):
        compiler=CodesysCompiler(self.config,self.home)
        def measure(executable,profile,ids,inputs,output,timeout):
            source=inputs/ids[0]/'final.st'
            value={'summary':{'environment_validated':True,'not_measured':0},'seconds':1,
                   'results':[{'status':'pass','stage':'compiled','source_sha256':sha(source),'errors':[]}]}
            atomic_json(output/'results.json',value)
            return value
        with patch('plc_agent.codesys_bank.run_bank',side_effect=measure) as run:
            first=compiler.compile(self.path,'03','environment-a')
            second=compiler.compile(self.path,'03','environment-a')
            self.assertFalse(first['cached']);self.assertTrue(second['cached']);self.assertEqual(run.call_count,1)
            Path(first['evidence_path']).unlink()
            compiler.compile(self.path,'03','environment-a')
            self.assertEqual(run.call_count,2)
            self.path.write_text(self.code+'\n(* changed source *)',encoding='utf-8')
            compiler.compile(self.path,'03','environment-a')
            compiler.compile(self.path,'03','environment-b')
            self.assertEqual(run.call_count,4)

    def test_tool_call_obeys_the_same_target_policy(self):
        self.config.save(self.home)
        pipeline,compiler,_=self.pipeline(compiler_status='compile_error')
        with patch('plc_agent.validation.pipeline_for',return_value=pipeline):
            result=Toolbox(self.session).call('plc_bank_test',{'source':'candidate.st','question_id':'03'})
        self.assertEqual(result['status'],'compile_error');self.assertEqual(compiler.calls,1)

    def test_direct_bank_test_failure_overrides_model_success_claim(self):
        self.config.save(self.home)
        pipeline,_,_=self.pipeline(compiler_status='compile_error')
        provider=ScriptedProvider([call('plc_bank_test',{'source':'candidate.st','question_id':'03'}),
                                   {'text':'已经全部通过'}])
        with patch('plc_agent.validation.pipeline_for',return_value=pipeline):
            answer=Engine(self.session,self.model,provider).run('测试第03题')
        self.assertIn('尚无当前源码验证通过',answer)
        self.assertEqual(self.session.data['status'],'workflow_blocked')
