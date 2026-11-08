"""TIA plugs into the existing Trial/Campaign machinery; no paid/native calls."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from io import StringIO
from unittest.mock import patch

from plc_agent import campaign, dataset
from plc_agent.config import ModelConfig
from plc_agent.provider import ProviderError


class TiaPlatformTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.cfg=ModelConfig.dmxapi(model='model-A',api_key='fixture-key')
        self.task=dataset.load('PUBLIC_02')
    def tearDown(self):self.tmp.cleanup()
    def trial(self):return campaign.Trial(self.root/'trial',self.task,self.cfg,{},threading.Event(),target='tia',formal_config={'engine':'cbmc'})

    def test_same_budget_and_source_version_limits(self):
        trial=self.trial()
        with patch.object(trial.provider,'complete',side_effect=ProviderError('fixture failure')):
            for _ in range(campaign.LIMITS['model_requests']):
                with self.assertRaises(ProviderError):trial.complete([])
            with self.assertRaisesRegex(ProviderError,'model_call_limit'):trial.complete([])
        self.assertEqual(trial.calls,24)
        with patch('plc_agent.tia_workflow.evaluate_candidate',return_value={'status':'fail','target_compile':'passed'}) as execute:
            for i in range(6):trial.check('SCL #local '+str(i))
            trial.check('SCL #local 0')
            self.assertEqual(execute.call_count,6)
            self.assertEqual(trial.check('seventh')['status'],'revision_limit')
        self.assertTrue((trial.path/'candidate.scl').is_file());self.assertFalse((trial.path/'candidate.st').exists())
        result=trial.receipt('fail')
        self.assertEqual(result['limits'],campaign.LIMITS);self.assertEqual(result['target'],'tia')

    def test_self_routes_through_trial_checker(self):
        trial=self.trial()
        def workflow(task,source,directory,cfg,**options):
            self.assertIs(options['provider'],trial)
            source.write_text('SCL #local',encoding='utf-8')
            value=options['evaluator'](source,task)
            return {'status':value['status'],'final_evaluation':value,'target_compile':'passed','behavior_tested':True}
        with patch('plc_agent.tia_workflow.run',side_effect=workflow), \
             patch('plc_agent.tia_workflow.evaluate_candidate',return_value={'status':'pass','target_compile':'passed','behavior_tested':True}) as execute:
            result=campaign.run_self(trial)
        execute.assert_called_once();self.assertEqual(result['status'],'finite_pass')
        self.assertEqual(len(result['submissions']),1)

    def test_four_way_campaign_preserves_target_hash_and_platform_metrics(self):
        self.cfg.save(self.root);runner=campaign.Campaigns(self.root);seen=[]
        ready={'errors':[],'vendor_config':{'fixture':True},'codesys':{},'codex_path':'fixture'}
        def run(trial,*args):
            seen.append((trial.target,trial.cfg.model,trial.task['dataset_sha256']))
            (trial.path/'candidate.scl').write_text('SCL fixture',encoding='utf-8')
            return trial.receipt('finite_pass',{'target_compile':'passed','final_evaluation':
                {'status':'pass','target_compile':'passed','behavior_tested':True,'summary':{'scenarios':1,'failed':0}}})
        with patch.object(campaign,'preflight',return_value=ready) as preflight, \
             patch('plc_agent.tia_cli.probe',return_value={'status':'probe_passed'}), \
             patch.object(campaign,'run_self',side_effect=run),patch.object(campaign,'run_codex',side_effect=run):
            job=runner.start({'models':['A','B'],'task_ids':['PUBLIC_02'],'target':'tia','codesys':False})
            deadline=time.monotonic()+5
            while job['id'] in runner.active and time.monotonic()<deadline:time.sleep(.01)
        record=runner.read(job['id'])
        self.assertEqual(record['status'],'completed');self.assertEqual(record['completed'],4)
        self.assertEqual({r[0] for r in seen},{'tia'});self.assertEqual(sorted(r[1] for r in seen),['A','A','B','B'])
        self.assertEqual(len({r[2] for r in seen}),1)
        self.assertEqual(preflight.call_args.kwargs,{'target':'tia'})
        self.assertTrue(all(r['target_compiled']==1 and r['codesys_compiled']==0 for r in record['summary']))
        self.assertNotIn('fixture-key',json.dumps(record))
        self.assertEqual(len(list(runner.root.rglob('final.scl'))),4)

    def test_codex_uses_same_relay_with_scl_file_and_no_expected_tables(self):
        trial=self.trial();captured={}
        class Process:
            returncode=0
            class Input(StringIO):
                def close(self):captured['prompt']=self.getvalue();super().close()
            def __init__(self):self.stdin=self.Input()
            def poll(self):return 0
            def wait(self):return 0
        def launch(argv,**options):
            workspace=Path(options['cwd'])
            packet=json.loads((workspace/'requirements.json').read_text(encoding='utf-8'))
            self.assertEqual(packet['dialect'],'siemens_scl');self.assertNotIn('scenarios',packet)
            self.assertIn('candidate.scl',(workspace/'check.py').read_text(encoding='utf-8'))
            (workspace/'candidate.scl').write_text('SCL fixture',encoding='utf-8')
            return Process()
        with patch.object(campaign.subprocess,'Popen',side_effect=launch), \
             patch.object(trial,'check',return_value={'status':'pass','target_compile':'passed'}) as check:
            receipt=campaign.run_codex(trial,Path('codex.exe'))
        check.assert_called_once_with('SCL fixture')
        self.assertIn('candidate.scl',captured['prompt']);self.assertNotIn('candidate.st',captured['prompt'])
        self.assertEqual(receipt['target'],'tia');self.assertEqual(receipt['status'],'finite_pass')


if __name__=='__main__':unittest.main()
