"""Readable outputs and pause/continue must preserve finished work and history."""
from datetime import datetime
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from plc_agent import campaign
from plc_agent.config import ModelConfig
from plc_agent.run_output import reserve_run, valid_run_id, trial_path, details_path
from plc_agent.web import Workbench


class OutputLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)
        ModelConfig.dmxapi(model='A',api_key='fixture-key').save(self.home)

    def wait_for(self,predicate):
        until=time.monotonic()+8
        while time.monotonic()<until:
            if predicate():return
            time.sleep(.02)
        self.fail('Timed out waiting for lifecycle transition')

    def test_timestamp_names_are_readable_unique_and_safe(self):
        first=reserve_run(self.home,when=datetime(2026,11,1,12,34,56))
        second=reserve_run(self.home,when=datetime(2026,11,1,12,34,56))
        self.assertEqual(first.name,'2026-11-01_12-34-56')
        self.assertEqual(second.name,'2026-11-01_12-34-56_02')
        self.assertTrue(valid_run_id(first.name));self.assertTrue(valid_run_id('a'*32))
        for value in ('../2026-11-01_12-34-56','x/y',None):self.assertFalse(valid_run_id(value))

    def test_vendor_evidence_follows_its_source_version(self):
        from plc_agent.codesys import evidence_directory
        source=self.home/'details/submissions/1/candidate.st';source.parent.mkdir(parents=True)
        a=evidence_directory(source,'codesys_compile');b=evidence_directory(source,'codesys_compile')
        self.assertEqual(a,source.parent/'codesys_compile/attempt_01')
        self.assertEqual(b,source.parent/'codesys_compile/attempt_02')

    def test_pause_drain_resume_and_history_after_restart(self):
        runner=campaign.Campaigns(self.home);entered=threading.Event();release=threading.Event();seen=[]
        def fake(trial,*_):
            seen.append((trial.task['id'],trial.cfg.model))
            if len(seen)==1:entered.set();release.wait(5)
            (trial.path/'candidate.st').write_text('FUNCTION_BLOCK Demo\nEND_FUNCTION_BLOCK')
            return trial.receipt('finite_pass',{'target_compile':'passed'})
        ready={'errors':[],'codesys':{},'codex_path':'fixture'}
        with patch.object(campaign,'preflight',return_value=ready),patch.object(campaign,'run_self',side_effect=fake),patch.object(campaign,'run_codex',side_effect=fake):
            job=runner.start({'models':['A','B'],'task_ids':['CUSTOM_09','CUSTOM_10'],'codesys':False,'concurrency':1})
            self.assertTrue(entered.wait(3));runner.pause(job['id']);release.set()
            self.wait_for(lambda:runner.read(job['id'])['status']=='paused')
            paused=runner.read(job['id']);self.assertEqual(len(seen),1);self.assertEqual(paused['completed'],1)
            runner.resume(job['id']);self.wait_for(lambda:job['id'] not in runner.active)
        record=runner.read(job['id']);self.assertEqual(record['status'],'completed');self.assertEqual(len(seen),8)
        self.assertEqual(len(set(seen)),4)  # each pair appears once per framework
        root=runner.root/job['id'];self.assertTrue((root/'results.csv').exists());self.assertTrue((root/'SUMMARY.md').exists())
        self.assertFalse((root/'campaign.json').exists());self.assertTrue((root/'details/campaign.json').exists())
        folder=trial_path(root,record,'self',0,0)
        self.assertEqual(folder.relative_to(root).as_posix(),'tasks/01_CUSTOM_09/self_A')
        for name in ('SUMMARY.md','final.st','run.log','details'):self.assertTrue((folder/name).exists(),name)
        self.assertFalse((details_path(folder)/'task_snapshot.json').exists())
        self.assertIn(job['id'],[r['id'] for r in campaign.Campaigns(self.home).list()])
        app=Workbench(self.home);view=app.read_trial({'campaign_id':job['id'],'framework':'self','model_index':0,'task_index':0})
        self.assertEqual(view['task']['id'],'CUSTOM_09');self.assertIn('FUNCTION_BLOCK',view['code'])

    def test_stop_while_paused_finishes_without_new_tasks(self):
        runner=campaign.Campaigns(self.home);entered=threading.Event();release=threading.Event();seen=[]
        def fake(trial,*_):
            seen.append(1);entered.set();release.wait(4)
            return trial.receipt('finite_pass')
        with patch.object(campaign,'preflight',return_value={'errors':[],'codesys':{},'codex_path':'fixture'}),patch.object(campaign,'run_self',side_effect=fake),patch.object(campaign,'run_codex',side_effect=fake):
            job=runner.start({'models':['A','B'],'task_ids':['CUSTOM_09'],'codesys':False,'concurrency':1})
            self.assertTrue(entered.wait(2));runner.pause(job['id']);release.set()
            self.wait_for(lambda:runner.read(job['id'])['status']=='paused')
            runner.stop(job['id']);self.wait_for(lambda:job['id'] not in runner.active)
        self.assertEqual(seen,[1]);self.assertEqual(runner.read(job['id'])['status'],'interrupted')
        with self.assertRaises(ValueError):runner.resume(job['id'])


if __name__=='__main__':unittest.main()
