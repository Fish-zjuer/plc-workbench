"""Main flow preserves original LTL and never reports an unexecuted proof."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from plc_agent import dataset; from plc_agent import dataset_formal; from plc_agent import dataset_workflow
from plc_agent.config import ROOT,ModelConfig
from plc_agent.provider import Cancelled

class FormalFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name);self.task=dataset.load('CUSTOM_09')
        self.source=ROOT/'tests/fixtures/dataset_r8/model_runs/dataset-r8-custom-real/CUSTOM_09/final.st'
        from plc_agent import plcverif_backend
        self.backend=patch.object(plcverif_backend,'verify',return_value={
            'status':'not_configured','properties':[{**p,'status':'not_executed'} for p in self.task['ltl']['properties']],
            'proved_property_ids':[],'message':'Fixture: tool unavailable'})
        self.verify=self.backend.start();self.addCleanup(self.backend.stop)
    def test_main_flow_invokes_unified_backend(self):
        result=dataset_formal.attach({'status':'pass'},self.task,self.source,self.path)
        self.verify.assert_called_once()
        self.assertEqual(result['status'],'pass')
        self.assertEqual(result['ltl_status'],'not_configured')
        self.assertEqual(result['formal_verification']['proved_property_ids'],[])
    def test_original_formulas_are_saved_without_rewriting(self):
        dataset_formal.attach({'status':'pass'},self.task,self.source,self.path)
        saved=json.loads((self.path/'requirements.json').read_text(encoding='utf-8'))
        self.assertEqual(saved,self.task['ltl'])
        self.assertEqual(saved['properties'][1]['formula'],'G(Maintenance -> State=2)')
    def test_every_declared_property_is_marked_not_executed(self):
        result=dataset_formal.attach({'status':'pass'},self.task,self.source,self.path)
        props=result['formal_verification']['properties']
        self.assertEqual(len(props),len(self.task['ltl']['properties']))
        self.assertTrue(all(p['status']=='not_executed' for p in props))
    def test_failed_compile_is_preserved(self):
        result=dataset_formal.attach({'status':'compile_error','target_compile':'failed'},self.task,self.source,self.path)
        self.assertEqual(result['status'],'compile_error')
        self.assertEqual(result['target_compile'],'failed')
    def test_cancel_prevents_formal_stage(self):
        event=threading.Event();event.set()
        with self.assertRaises(Cancelled):dataset_formal.attach({'status':'pass'},self.task,self.source,self.path,cancel_event=event)
    def test_workflow_keeps_test_result_and_no_proof_claim(self):
        class Provider:
            cancel_event=threading.Event();metrics=[]
            def complete(self,*args,**kwargs):raise AssertionError('Unexpected model request')
        candidate=self.path/'candidate.st';candidate.write_bytes(self.source.read_bytes())
        with patch.object(dataset,'evaluate',return_value={'status':'pass'}):
            result=dataset_workflow.run(self.task['id'],candidate,self.path/'run',ModelConfig(),provider=Provider(),review=False)
        self.assertEqual(result['status'],'finite_pass')
        self.assertEqual(result['ltl_status'],'not_configured')
        self.assertEqual(result['model_calls'],0)
