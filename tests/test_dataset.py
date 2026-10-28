import copy
import json
from pathlib import Path
import tempfile
import unittest
from plc_agent import dataset
from plc_agent.dataset_cli import perform
from plc_agent.config import ModelConfig,ROOT
from plc_agent.storage import Project,Session
from plc_agent.toolbox import Toolbox
from plc_probe.config import cache_dir

class DatasetTests(unittest.TestCase):
    def test_frozen_catalog_has_exact_32_complete_tasks(self):
        tasks=[dataset.load(t['id']) for t in dataset.catalog()['tasks']]
        self.assertEqual(len(tasks),32);self.assertEqual(sum(len(t['scenarios']) for t in tasks),348)
        for task in tasks:
            self.assertTrue(task['requirements']);self.assertTrue(task['ltl']['properties'])
    def test_plan_and_model_tools_cannot_run_in_plan_mode(self):
        with tempfile.TemporaryDirectory(dir=cache_dir()) as folder:
            project=Project.create('dataset fixture',Path(folder));session=Session.create(project)
            result=perform(session,ModelConfig(),'run','CUSTOM_01')
            self.assertEqual(result['status'],'planned');self.assertFalse(list(project.workspace.rglob('*.st')))
            self.assertEqual(Toolbox(session).call('plc_dataset_run',{'task_id':'CUSTOM_01'})['status'],'blocked_by_plan_mode')
            self.assertEqual(Toolbox(session).call('plc_dataset_show',{'task_id':'CUSTOM_01'})['status'],'dataset_plan')
    def test_fixed_array_bridge_keeps_declared_lower_bounds(self):
        bridge,inputs,outputs=dataset.trace_driver(dataset.load('CUSTOM_01'))
        self.assertIn('uut->CABREQ.at(1)',bridge);self.assertIn('uut->HALLREQ.at(6)',bridge)
        self.assertEqual(len(inputs),16);self.assertTrue(any(n=='@input.CabReq[1]' for n,_ in outputs))
    def test_float_tolerance_uses_declared_type_but_integer_is_exact(self):
        task=dataset.load('CUSTOM_04')
        self.assertTrue(dataset.equal(.0005,0,task,'Diameter'))
        self.assertFalse(dataset.equal(.002,0,task,'Diameter'))
        self.assertFalse(dataset.equal(1.0001,1,dataset.load('CUSTOM_01'),'TargetFloor'))
    def test_public_response_windows_accept_one_complete_row_not_split_fields(self):
        task=dataset.load('CUSTOM_10');default={'RequestBtn':False,'ServiceReady':False,'Busy':False,'Cancel':False}
        task['scenarios']=[{'name':'split_window','trace':[{'time_ms':0,'inputs':{**default,'RequestBtn':True}},
            {'time_ms':1,'inputs':{**default,'ServiceReady':True}}],
            'response_windows':[{'start_scan':0,'end_scan':1,'expected':{'Pending':True,'RequestLamp':True}}]}]
        with tempfile.TemporaryDirectory(dir=cache_dir()) as folder:
            p=Path(folder)/'fixture.st';p.write_text('FUNCTION_BLOCK FB_InventoryRequest\nVAR_INPUT RequestBtn,ServiceReady,Busy,Cancel : BOOL; END_VAR\nVAR_OUTPUT Pending,RequestLamp,Dispatched : BOOL; END_VAR\nPending:=RequestBtn; RequestLamp:=ServiceReady; Dispatched:=FALSE;\nEND_FUNCTION_BLOCK',encoding='utf-8')
            self.assertEqual(dataset.evaluate(p,task)['status'],'fail')
            task['scenarios'][0]['response_windows'][0]['expected']={'Pending':True}
            self.assertEqual(dataset.evaluate(p,task)['status'],'pass')
    def test_reference_drivers_and_interface_guard_preserve_original_types(self):
        task=dataset.load('PUBLIC_18');source=ROOT/'experiments/backend_r4/tasks/18/final.st'
        dataset.validate_source(source,task)
        with tempfile.TemporaryDirectory(dir=cache_dir()) as folder:
            p=Path(folder)/'bad.st';p.write_text(source.read_text(encoding='utf-8').replace('VARIANT','DINT'),encoding='utf-8')
            with self.assertRaises(ValueError):dataset.validate_source(p,task)

if __name__=='__main__':unittest.main()
