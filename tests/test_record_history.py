import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from plc_agent.web import Workbench
from plc_agent.storage import atomic_json

class RecordHistoryTests(unittest.TestCase):
    def test_clear_hides_both_histories_and_preserves_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=Workbench(Path(tmp));rid='a'*32;cid='b'*32
            atomic_json(app.root/rid/'run.json',{'id':rid,'status':'error'})
            atomic_json(app.campaigns.root/cid/'campaign.json',{'id':cid,'status':'error'})
            source=app.root/rid/'candidate.st';source.write_text('evidence')
            self.assertEqual(len(app.runs()),1)
            self.assertEqual(app.clear_records()['cleared'],2)
            self.assertEqual(app.runs(),[]);self.assertEqual(app.campaigns.list(),[])
            self.assertEqual(source.read_text(),'evidence')
            self.assertEqual(app.clear_records()['cleared'],0)

    def test_active_work_cannot_be_cleared(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=Workbench(Path(tmp));app.campaigns.active['a']=object()
            with self.assertRaises(ValueError):app.clear_records()

    def test_atomic_save_retries_transient_access_denial(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'progress.json'
            import os
            replace=os.replace;calls=[]
            def transient(a,b):
                calls.append(1)
                if len(calls)<3:raise PermissionError('busy reader')
                replace(a,b)
            with patch('plc_agent.storage.os.replace',side_effect=transient),patch('plc_agent.storage.time.sleep'):
                atomic_json(path,{'completed':16})
            self.assertEqual(json.loads(path.read_text())['completed'],16)
            self.assertEqual(list(Path(tmp).glob('*.tmp')),[])

    def test_read_retries_transient_access_denial(self):
        from plc_agent.storage import read_json
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'campaign.json';atomic_json(path,{'completed':3})
            original=Path.read_text;calls=[]
            def transient(p,*args,**kwargs):
                calls.append(1)
                if len(calls)<3:raise PermissionError('busy replacement')
                return original(p,*args,**kwargs)
            with patch.object(Path,'read_text',transient),patch('plc_agent.storage.time.sleep'):
                self.assertEqual(read_json(path),{'completed':3})

    def test_concurrent_progress_read_write(self):
        from concurrent.futures import ThreadPoolExecutor
        from plc_agent.storage import read_json
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'campaign.json';atomic_json(path,{'completed':0})
            def writer():
                for i in range(30):atomic_json(path,{'completed':i})
            def reader():
                for i in range(60):self.assertIsInstance(read_json(path)['completed'],int)
            with ThreadPoolExecutor(max_workers=5) as pool:
                futures=[pool.submit(writer)]+[pool.submit(reader) for _ in range(4)]
                for f in futures:f.result()

if __name__=='__main__':unittest.main()
