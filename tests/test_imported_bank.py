import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from plc_agent import dataset, bank32, dataset_workflow
from plc_agent.imported_bank import ImportedBank

class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.bank=ImportedBank(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def file(self,value,name='bank.json'):
        return {'name':name,'content':json.dumps(value,ensure_ascii=False)}
    def test_roundtrip_isolated_version_and_digest(self):
        before=dataset.load('CUSTOM_01')
        task={**before,'title':'Imported title','constraints':['Keep interface']}
        out=self.bank.import_files([self.file({'tasks':[task]})])
        imported=self.bank.load(out['tasks'][0]['id'])
        self.assertEqual(dataset.load('CUSTOM_01'),before)
        self.assertEqual(imported['title'],'Imported title')
        self.assertNotEqual(imported['dataset_sha256'],before['dataset_sha256'])
        self.assertEqual(len(self.bank.catalog()['tasks']),33)
        self.assertEqual(ImportedBank(self.temp.name).load(imported['id']),imported)
        packet=bank32.author_packet(imported)
        self.assertNotIn('scenarios',packet)
        self.assertEqual(packet['additional_constraints'],['Keep interface'])
    def test_teammate_separate_tests_specs_inherit_requirements(self):
        original=dataset.load('CUSTOM_03')
        tests={k:v for k,v in original.items() if k not in ('requirements','ltl','dataset_sha256')}
        spec={'id':'CUSTOM_03','properties':[{'id':'P1','formula':'G(test)'}]}
        out=self.bank.import_files([self.file({'schema':'plc-standalone-tests-v1','tasks':[tests]}),self.file({'schema':'plc-ltl-requirements-v1','tasks':[spec]},'spec.json')])
        imported=self.bank.load(out['tasks'][0]['id'])
        self.assertEqual(imported['requirements'],original['requirements'])
        self.assertEqual(imported['ltl']['properties'],spec['properties'])
    def test_ltl_only_and_plain_constraints_create_versions(self):
        out=self.bank.import_files([{'name':'CUSTOM_01.ltl','content':'G(Enable -> HasTarget)'}])
        key=out['tasks'][0]['id']
        self.assertEqual(self.bank.load(key)['ltl']['status'],'specification_not_proved')
        out2=self.bank.import_files([{'name':'constraints.txt','content':'Preserve inputs'}],target=key)
        self.assertEqual(self.bank.load(out2['tasks'][0]['id'])['constraints'],['Preserve inputs'])
    def test_duplicate_and_bad_interface_no_partial_write(self):
        t=dataset.load('CUSTOM_01')
        with self.assertRaises(ValueError): self.bank.import_files([self.file({'tasks':[t,t]})])
        t['interface'][0]['name']='bad; injected'
        with self.assertRaises(ValueError): self.bank.import_files([self.file(t)])
        self.assertEqual(len(self.bank.catalog()['tasks']),32)
    def test_import_160_arbitrary_tasks(self):
        from copy import deepcopy
        rows=[]
        for index in range(160):
            task=deepcopy(dataset.load('CUSTOM_02'))
            task['id']='TASK_'+str(index)
            task['block']='FB_Task_'+str(index)
            rows.append(task)
        result=self.bank.import_files([self.file({'tasks':rows})])
        self.assertEqual(result['count'],160)
        self.assertEqual(len({t['id'] for t in result['tasks']}),160)
        self.assertEqual(self.bank.load(result['tasks'][-1]['id'])['original_id'],'TASK_99')

    def test_missing_tests_compile_only(self):
        source=Path(self.temp.name)/'candidate.st'; source.write_text('placeholder')
        task={'scenarios':[],'id':'DEMO_01','title':'demo','block':'Demo','requirements':'demo','interface':[], 'dataset_sha256':'test'}
        from plc_agent.config import ModelConfig
        from plc_agent.provider import ChatProvider
        cfg=ModelConfig(base_url='http://127.0.0.1',model='fake')
        with patch.object(dataset,'compile_task',return_value={'source_sha256':'test'}),patch.object(dataset,'evaluate') as evaluate:
            result=dataset_workflow.run('DEMO_01',source,Path(self.temp.name)/'run',cfg,task_override=task,provider=ChatProvider(cfg),review=False)
        self.assertEqual(result['status'],'compiled_without_tests')
        evaluate.assert_not_called()
        self.assertTrue((Path(self.temp.name)/'run'/'task.json').exists())

if __name__=='__main__': unittest.main()
