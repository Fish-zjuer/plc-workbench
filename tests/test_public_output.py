import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from plc_agent.public_output import export
from scripts.run_tia_matrix import task_matrix, prepare


class PublicOutputTests(unittest.TestCase):
    def test_exports_evidence_and_redacts_secrets_without_rewriting_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); raw=root/'raw'; raw.mkdir(); public=root/'public'
            code=b'FUNCTION_BLOCK Demo\r\nEND_FUNCTION_BLOCK\r\n'
            (raw/'final.scl').write_bytes(code)
            (raw/'receipt.json').write_text(json.dumps({'api_key':'unknown-secret','usage':{'total_tokens':123},
                'source_sha256':hashlib.sha256(code).hexdigest(),'local':'C:/private/task','message':'known-secret'}))
            (raw/'run.log').write_text('known-secret C:/private/task ' + json.dumps(r'C:\private\task'))
            (raw/'project').mkdir();(raw/'project'/'customer.xml').write_text('not publishable')
            (raw/'simulator.exe').write_bytes(b'binary')
            result=export(raw,public,secrets=['known-secret'],path_replacements={'C:/private':'<LOCAL>', r'C:\private':'<LOCAL>'})
            value=json.loads((public/'receipt.json').read_text())
            self.assertEqual(value['api_key'],'[redacted]')
            self.assertEqual(value['usage']['total_tokens'],123)
            self.assertEqual(value['local'],'<LOCAL>/task')
            self.assertEqual((public/'final.scl').read_bytes(),code)
            self.assertNotIn('known-secret',(public/'run.log').read_text())
            self.assertNotIn('private',(public/'run.log').read_text())
            self.assertEqual(len(result['omitted']),2)
            for name,record in result['files'].items():
                self.assertEqual(hashlib.sha256((public/name).read_bytes()).hexdigest(),record['public_sha256'])

    def test_refuses_source_credentials_and_does_not_leave_partial_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); raw=root/'raw';raw.mkdir()
            (raw/'candidate.scl').write_text('known-secret')
            with self.assertRaises(ValueError):export(raw,root/'public',secrets=['known-secret'])
            self.assertFalse((root/'public').exists())

    def test_refuses_to_overwrite_or_nest_public_snapshots(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);raw=root/'raw';raw.mkdir();(raw/'SUMMARY.md').write_text('evidence')
            export(raw,root/'public')
            with self.assertRaises(ValueError):export(raw,root/'public')
            with self.assertRaises(ValueError):export(raw,raw/'public')

    def test_same_model_matrix_has_independent_framework_repeat_addresses(self):
        ids=['PUBLIC_%02d'%i for i in range(1,21)]+['CUSTOM_%02d'%i for i in range(1,13)]
        rows=task_matrix(ids)
        self.assertEqual(len(rows),128)
        self.assertEqual(len({(r['task_id'],r['group']) for r in rows}),128)
        self.assertEqual({r['group'] for r in rows},{'self_r1','self_r2','codex_r1','codex_r2'})
        self.assertTrue(all(r['status']=='not_started' for r in rows))

    def test_missing_vendor_tools_blocks_before_models_or_compilers(self):
        from plc_agent.config import ModelConfig
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder);ModelConfig(base_url='http://localhost:9911/v1',model='deepseek-flash').save(home)
            with patch('scripts.run_tia_matrix.preflight',return_value={'errors':['TIA missing']}), \
                 patch('plc_agent.provider.ChatProvider.complete',side_effect=AssertionError('Must not call model')), \
                 patch('plc_agent.tia.compile_scl',side_effect=AssertionError('Must not compile')):
                cfg,tasks,ready,rows=prepare(['CUSTOM_09'],'deepseek-flash',2,home)
            self.assertEqual(ready['status'],'setup_required')
            self.assertEqual(len(rows),4)

    def test_four_finished_repetitions_keep_distinct_evidence_and_model_counts(self):
        from plc_agent.config import ModelConfig
        from plc_agent import dataset
        from scripts import run_tia_matrix as runner
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);home=root/'home';home.mkdir()
            cfg=ModelConfig(base_url='http://localhost:9911/v1',model='deepseek-flash')
            tasks=[dataset.load('CUSTOM_09')]
            ready={'status':'ready','errors':[],'runtime':{'vendor_config':{},'codex_path':'fixture'},'formal':{}}
            def finish(trial,*args):
                trial.calls=1
                (trial.path/'candidate.scl').write_text('test executor source')
                return trial.receipt('finite_pass',{'final_evaluation':{'status':'pass','summary':{'scenarios':1,'failed':0}}})
            def git_output(args,**kwargs):return 'test-revision\n' if 'rev-parse' in args else b''
            with patch.object(runner,'ROOT',root),patch.dict(runner.os.environ),patch.object(runner.tempfile,'tempdir'), \
                 patch.object(runner,'configure_temporary'), \
                 patch.object(runner,'prepare',return_value=(cfg,tasks,ready,task_matrix(['CUSTOM_09']))), \
                 patch.object(runner,'probe',return_value={'status':'probe_passed'}), \
                 patch.object(runner,'run_self',finish),patch.object(runner,'run_codex',finish), \
                 patch.object(runner.subprocess,'check_output',side_effect=git_output):
                code=runner.main(['--home',str(home),'--ids','CUSTOM_09'])
            self.assertEqual(code,0)
            public=next((root/'outputs/published').iterdir())
            matrix=json.loads((public/'matrix.json').read_text(encoding='utf-8'))
            self.assertEqual((matrix['completed'],matrix['model_calls']),(4,4))
            self.assertEqual(len(list((public/'tasks').glob('*/**/receipt.json'))),4)


if __name__ == '__main__':unittest.main()
