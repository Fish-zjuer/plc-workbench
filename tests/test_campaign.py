"""Campaign transport and vendor adapter tests: fixtures are not vendor evidence."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from plc_agent import campaign, codesys_dataset, dataset
from plc_agent.config import ModelConfig
from plc_agent.provider import ProviderError
from plc_probe.backend import BackendError

class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)
        self.cfg=ModelConfig.dmxapi(model='model-A',api_key='fixture-key')
        self.task=dataset.load('CUSTOM_02')
    def tearDown(self):self.tmp.cleanup()
    def trial(self):return campaign.Trial(self.path/'trial',self.task,self.cfg,None,threading.Event())
    def test_budget_counts_failed_requests_without_reset(self):
        t=self.trial()
        with patch.object(t.provider,'complete',side_effect=ProviderError('down')):
            for _ in range(24):
                with self.assertRaises(ProviderError):t.complete([])
            with self.assertRaisesRegex(ProviderError,'model_call_limit'):t.complete([])
        self.assertEqual(t.calls,24);self.assertEqual(len(t.metrics),24)
        self.assertFalse(t.receipt('agent_error')['token_usage']['complete'])
    def test_source_versions_dedup_and_limit(self):
        t=self.trial()
        with patch.object(campaign,'evaluate_candidate',return_value={'status':'fail'}) as evaluate:
            for n in range(6):t.check('FUNCTION_BLOCK X\nEND_FUNCTION_BLOCK\n'+str(n))
            t.check('FUNCTION_BLOCK X\nEND_FUNCTION_BLOCK\n0')
            self.assertEqual(evaluate.call_count,6)
            self.assertEqual(t.check('new')['status'],'revision_limit')
    def test_stop_prevents_new_model_request(self):
        t=self.trial();t.stop.set()
        with self.assertRaises(ProviderError):t.complete([])
        self.assertEqual(t.calls,0)
    def test_summary_separates_vendor_and_local(self):
        rows=[{'framework':'self','model':'A','status':'finite_pass','target_compile':'not_executed','metrics':[]},
              {'framework':'codex','model':'A','status':'fail','target_compile':'passed','metrics':[]}]
        result=campaign.summarize(rows,[('self','A'),('codex','A')])
        self.assertEqual(result[0]['passed'],1);self.assertEqual(result[0]['codesys_compiled'],0)
        self.assertEqual(result[1]['passed'],0);self.assertEqual(result[1]['codesys_compiled'],1)
    def test_web_preflight_blocks_paid_calls(self):
        runner=campaign.Campaigns(self.path)
        with patch.object(campaign,'preflight',return_value={'errors':['missing CODESYS']}):
            with self.assertRaisesRegex(ValueError,'missing CODESYS'):
                runner.start({'models':['A','B'],'task_ids':['PUBLIC_01']})
        self.assertFalse(runner.root.exists())
    def test_four_way_visits_every_pair_with_same_hash(self):
        runner=campaign.Campaigns(self.path)
        self.cfg.save(self.path)
        ready={'errors':[],'codesys':{},'codex_path':'fixture','codex_version':'codex-cli 0.80.0'}
        seen=[]
        def fake(t,*args):
            seen.append((t.cfg.model,t.task['dataset_sha256']))
            return t.receipt('finite_pass',{'target_compile':'passed'})
        with patch.object(campaign,'preflight',return_value=ready),patch.object(campaign,'run_self',side_effect=fake),patch.object(campaign,'run_codex',side_effect=fake):
            job=runner.start({'models':['A','B'],'task_ids':['PUBLIC_01'],'codesys':False})
            deadline=time.monotonic()+5
            while job['id'] in runner.active and time.monotonic()<deadline:time.sleep(.01)
            result=runner.read(job['id'])
        self.assertEqual(result['status'],'completed');self.assertEqual(result['completed'],4)
        self.assertEqual(sorted(x[0] for x in seen),['A','A','B','B'])
        self.assertEqual(len({x[1] for x in seen}),1)
        self.assertNotIn('fixture-key',json.dumps(result))
    def test_160_tasks_schedule_640_trials(self):
        runner=campaign.Campaigns(self.path)
        self.cfg.save(self.path)
        ready={'errors':[],'codesys':{},'codex_path':'fixture','codex_version':'codex-cli 0.80.0'}
        def task(ident):
            return {**self.task,'id':ident}
        def fake(trial,*_): return trial.receipt('finite_pass',{'target_compile':'passed'})
        with patch.object(campaign,'preflight',return_value=ready),patch.object(campaign.ImportedBank,'load',side_effect=task),patch.object(campaign,'run_self',side_effect=fake),patch.object(campaign,'run_codex',side_effect=fake):
            job=runner.start({'models':['A','B'],'task_ids':['TASK_'+str(i) for i in range(160)],'codesys':False})
            self.assertEqual(job['total'],640)
            runner.stop(job['id'])
            deadline=time.monotonic()+5
            while job['id'] in runner.active and time.monotonic()<deadline:time.sleep(.01)
        self.assertEqual(runner.read(job['id'])['task_count'],160)

    def test_concurrency_limit_and_complete_results(self):
        runner=campaign.Campaigns(self.path);self.cfg.save(self.path)
        ready={'errors':[],'codesys':{},'codex_path':'fixture'}
        lock=threading.Lock();running=0;peak=0
        def fake(trial,*_):
            nonlocal running,peak
            with lock:running+=1;peak=max(peak,running)
            time.sleep(.05)
            with lock:running-=1
            return trial.receipt('finite_pass')
        with patch.object(campaign,'preflight',return_value=ready),patch.object(campaign,'run_self',side_effect=fake),patch.object(campaign,'run_codex',side_effect=fake):
            job=runner.start({'models':['A','B'],'task_ids':['PUBLIC_01','CUSTOM_02'],'codesys':False,'concurrency':3})
            deadline=time.monotonic()+5
            while job['id'] in runner.active and time.monotonic()<deadline:time.sleep(.01)
        result=runner.read(job['id'])
        self.assertEqual(peak,3);self.assertEqual(result['completed'],8)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(len({(r['framework'],r['model'],r['task_id']) for r in result['results']}),8)

    def test_default_runs_four_tasks_with_four_configurations_concurrently(self):
        runner=campaign.Campaigns(self.path);self.cfg.save(self.path)
        ready={'errors':[],'codesys':{},'codex_path':'fixture'}
        barrier=threading.Barrier(16,timeout=8)
        lock=threading.Lock();seen=[]
        def task(ident):
            return {**self.task,'id':ident}
        def fake(trial,*_):
            with lock:seen.append((trial.task['id'],trial.cfg.model))
            barrier.wait()
            return trial.receipt('finite_pass')
        with patch.object(campaign,'preflight',return_value=ready),patch.object(campaign.ImportedBank,'load',side_effect=task),patch.object(campaign,'run_self',side_effect=fake),patch.object(campaign,'run_codex',side_effect=fake):
            job=runner.start({'models':['A','B'],'task_ids':['T1','T2','T3','T4'],'codesys':False,'concurrency':33})
            deadline=time.monotonic()+12
            while job['id'] in runner.active and time.monotonic()<deadline:time.sleep(.01)
        result=runner.read(job['id'])
        self.assertEqual(result['concurrency'],33)
        self.assertEqual(result['completed'],16)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(sum(r['status']=='finite_pass' for r in result['results']),16)
        self.assertEqual(len({(r['framework'],r['model'],r['task_id']) for r in result['results']}),16)

    def test_invalid_concurrency_rejected_before_preflight(self):
        runner=campaign.Campaigns(self.path)
        with patch.object(campaign,'preflight') as preflight:
            for n in (0,-1,True,1.5):
                with self.assertRaises(ValueError):
                    runner.start({'models':['A','B'],'task_ids':['PUBLIC_01'],'concurrency':n})
            preflight.assert_not_called()

    def test_stop_does_not_start_queued_tasks(self):
        runner=campaign.Campaigns(self.path);self.cfg.save(self.path)
        ready={'errors':[],'codesys':{},'codex_path':'fixture'}
        entered=threading.Event();seen=[]
        def fake(trial,*_):
            seen.append(trial);entered.set();trial.stop.wait(3)
            return trial.receipt('interrupted')
        with patch.object(campaign,'preflight',return_value=ready),patch.object(campaign,'run_self',side_effect=fake),patch.object(campaign,'run_codex',side_effect=fake):
            job=runner.start({'models':['A','B'],'task_ids':['PUBLIC_01','CUSTOM_02'],'codesys':False,'concurrency':2})
            self.assertTrue(entered.wait(2));runner.stop(job['id'])
            deadline=time.monotonic()+5
            while job['id'] in runner.active and time.monotonic()<deadline:time.sleep(.01)
        self.assertLessEqual(len(seen),2)
        self.assertEqual(runner.read(job['id'])['status'],'interrupted')

    def test_vendor_failure_not_relabelled_as_local_pass(self):
        with patch.object(codesys_dataset,'compile_dataset',side_effect=BackendError({'status':'compile_error','diagnostics':['bad']})),patch.object(dataset,'evaluate') as evaluate:
            result=codesys_dataset.evaluate_candidate('fixture',self.task,{'configured':True})
        self.assertEqual(result['target_compile'],'failed');evaluate.assert_not_called()
    def test_vendor_multiu_unit_import_and_digest(self):
        t={'block':'Foo','interface':[],'dataset_sha256':'test'}
        source=self.path/'candidate.st'
        source.write_text('TYPE Rec : STRUCT X : BOOL; END_STRUCT END_TYPE\nFUNCTION_BLOCK Foo\nVAR R : Rec; END_VAR\nR.X := TRUE;\nEND_FUNCTION_BLOCK')
        def invoke(request,directory,**kw):
            self.assertEqual([u['kind'] for u in request['units']],['TYPE','FUNCTION_BLOCK'])
            self.assertEqual(request['harness_body'],'WB_Uut();')
            return {'target_compile':'passed','vendor_version':'fixture','diagnostics':[]}
        with patch.object(codesys_dataset.codesys,'validate_config'),patch.object(codesys_dataset.codesys,'fingerprint',return_value='frozen'),patch.object(codesys_dataset.codesys,'work_root',return_value=self.path),patch.object(codesys_dataset.codesys,'invoke',side_effect=invoke):
            result=codesys_dataset.compile_dataset(source,t,{'template_project':'fixture.project'})
        self.assertEqual(result['target_compile'],'passed');self.assertFalse(result['behavior_tested'])

if __name__=='__main__':unittest.main()
