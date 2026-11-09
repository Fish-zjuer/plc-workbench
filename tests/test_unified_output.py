import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from plc_agent import dataset; from plc_agent import campaign; from plc_agent import codesys_dataset; from plc_agent import task_formal
from plc_agent.config import ModelConfig
from plc_agent.run_output import metrics
from plc_agent.web import Workbench


class UnifiedOutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name);self.task=dataset.load('CUSTOM_09')
        self.cfg=ModelConfig.dmxapi(model='fixture',api_key='never-log-this-key')

    def test_web_uses_same_checker_and_budget_and_persists_logs(self):
        app=Workbench(self.path);self.cfg.save(self.path)
        result={'status':'pass','target_compile':'passed','summary':{'scenarios':4,'failed':1},
                'formal_verification':{'status':'proved','mapped_assertions_total':2,'proved_property_ids':['P1','P2']},'ltl_status':'proved'}
        done=threading.Event()
        def evaluate(*args,**kwargs):
            self.assertNotIn('formal_mode',kwargs);done.set();return result
        with patch.object(campaign,'evaluate_candidate',side_effect=evaluate):
            started=app.start({'task_id':'CUSTOM_09','action':'check','code':'FUNCTION_BLOCK X\nEND_FUNCTION_BLOCK',
                               'codesys':False})
            self.assertTrue(done.wait(5))
            import time
            for _ in range(100):
                view=app.read_job(started['id'])
                if view['status'] not in ('running','queued'):break
                time.sleep(.02)
        output=Path(view['output_path'])
        self.assertIn('outputs',output.parts)
        for name in ('run.log','SUMMARY.md','final.st'):
            self.assertTrue((output/name).exists(),name)
        for name in ('events.jsonl','metrics.json','receipt.json'):
            self.assertTrue((output/'details'/name).exists(),name)
        self.assertNotIn(self.cfg.api_key,(output/'run.log').read_text(encoding='utf-8'))
        self.assertEqual(view['receipt']['model_calls'],0)
        self.assertEqual(view['receipt']['metrics_summary']['test_cases_passed'],3)

    def test_compilation_failure_never_claims_test_or_formal_success(self):
        m=metrics({'status':'compile_error','target_compile':'failed'},self.task)
        self.assertEqual(m['formal_status'],'not_executed');self.assertIsNone(m['test_case_pass_rate'])

    def test_managed_workflow_keeps_one_canonical_copy_per_submission(self):
        trial=campaign.Trial(self.path/'run/details',self.task,self.cfg,None,threading.Event())
        parts=['FUNCTION_BLOCK '+self.task['block']]
        for direction,kind in [('Input','VAR_INPUT'),('Output','VAR_OUTPUT'),('Input/Output','VAR_IN_OUT')]:
            fields=[p for p in self.task['interface'] if p['direction']==direction]
            if fields:parts += [kind]+[p['name']+':'+p['type']+';' for p in fields]+['END_VAR']
        code='\n'.join(parts+['END_FUNCTION_BLOCK'])
        def respond(*args,**kwargs):
            trial.provider.metrics.append({'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}})
            return {'text':json.dumps({'code':code,'summary':'fixture'})}
        with patch.object(trial.provider,'complete',side_effect=respond),patch.object(campaign,'evaluate_candidate',return_value={'status':'pass','target_compile':'passed'}):
            result=campaign.run_self(trial)
        self.assertEqual(result['status'],'finite_pass')
        for name in ('author_01.json','proposal_01.st','task.json','final.st','evaluation_01.json'):
            self.assertFalse((trial.path/name).exists(),name)
        self.assertTrue((trial.path/'requests/01/output.json').exists())
        self.assertTrue((trial.path/'submissions/1/candidate.st').exists())
        self.assertEqual((trial.path.parent/'final.st').read_text(encoding='utf-8'),code)

    def test_compile_only_keeps_zero_api_usage_and_no_proof_claim(self):
        app=Workbench(self.path);self.cfg.save(self.path)
        with patch('plc_agent.web.codesys.validate_config'),patch('plc_agent.web.codesys.load_config',return_value={}), \
                patch('plc_agent.web.compile_dataset',return_value={'status':'compiled_unit','target_compile':'passed'}):
            job=app.start({'task_id':'CUSTOM_09','action':'codesys','code':'fixture'})
            import time
            for _ in range(200):
                view=app.read_job(job['id'])
                if view['status'] not in ('running','queued'):break
                time.sleep(.01)
        self.assertEqual(view['receipt']['model_calls'],0)
        self.assertEqual(view['receipt']['target_compile'],'passed')
        self.assertEqual(view['receipt']['ltl_status'],'not_executed')

    def test_summary_denominators_include_all_frozen_tasks(self):
        result={'status':'finite_pass','framework':'self','model':'A','target_compile':'passed',
            'submissions':[{'target_compile':'passed','status':'pass'}],
            'final_evaluation':{'summary':{'scenarios':2,'failed':0},'formal_verification':{'status':'timeout','mapped_assertions_total':3}}}
        tasks=[{'scenarios':[{},{}],'ltl':{'properties':[{},{}]}},{'scenarios':[{}],'ltl':{'properties':[{}]}}]
        row=campaign.summarize([result],[('self','A')],tasks)[0]
        self.assertEqual(row['codesys_compile_rate'],.5)
        self.assertEqual(row['test_case_pass_rate'],2/3)
        self.assertEqual(row['formal_statuses'],{'timeout':1})

    def test_empty_native_replay_cannot_confirm_counterexample(self):
        source=self.path/'candidate.st';source.write_text('fixture')
        import hashlib
        report={'status':'counterexample','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                'properties':[{'status':'counterexample','id':'P1','counterexample':{},'symbolic_rows':[]}]}
        class Backend:
            def replay(self,*args):return {'cases':[]}
        artifact=type('Artifact',(),{'execution_fingerprint':'fixture'})()
        with patch.object(task_formal,'verify',return_value=report):
            checked=task_formal.check(source,{'formal':{}},self.path/'formal',backend=Backend(),artifact=artifact)
        self.assertEqual(checked['status'],'semantics_mismatch')


if __name__=='__main__':unittest.main()
