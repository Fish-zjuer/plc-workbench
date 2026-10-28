"""Vendor API fixtures verify control flow only; an installed IDE is still required."""
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import patch
from plc_agent import codesys_worker
from plc_probe.config import cache_dir

class WorkerTests(unittest.TestCase):
    def run_worker(self,simulation=True,compiler_error=False,read_error=False):
        with tempfile.TemporaryDirectory(dir=cache_dir()) as folder:
            root=Path(folder);template=root/'template.project';template.write_bytes(b'fixture')
            request={'action':'simulate','nonce':'fixture','source_sha256':'fixture',
                'output':str(root/'response.json'),'template_project':str(template),'block':'Mapping',
                'declaration':'fixture','implementation':'fixture','harness_declaration':'fixture',
                'harness_body':'fixture','output_names':['z','a'],'row_count':1}
            (root/'request.json').write_text(json.dumps(request),encoding='utf-8');calls=[]
            def text():return NS(replace=lambda value:None)
            device=NS(set_simulation_mode=lambda value:calls.append(('simulation',value)),get_simulation_mode=lambda:simulation)
            class Application:
                is_application=True;parent=device
                def find(self,name,recursive):return [NS(textual_declaration=text(),textual_implementation=text())] if name=='PLC_PRG' else []
                def create_function_block(self,name):calls.append(('create',name));return NS(textual_declaration=text(),textual_implementation=text())
                def rebuild(self):calls.append(('rebuild',))
                def generate_code(self):calls.append(('generate',))
                def create_boot_application(self,path):Path(path).write_bytes(b'fixture compiled image')
            app=Application()
            project=NS(get_children=lambda recursive:[app],save=lambda:None,close=lambda:calls.append(('close',)))
            message=NS(severity='Error',text='fixture compiler error',position_text=None)
            system=NS(executable_filename='fixture.exe',get_message_categories=lambda:['fixture'],
                get_message_objects=lambda category,severity=None:[message] if compiler_error else [],
                clear_messages=lambda category:None,delay=lambda ms:None,exit=lambda code:calls.append(('exit',code)))
            class Connection:
                def __enter__(self):return self
                def __exit__(self,*args):calls.append(('dispose',))
                def login(self,*args):calls.append(('login',)+args)
                def reset(self,*args):calls.append(('reset',)+args)
                def start(self):calls.append(('start',))
                def stop(self):calls.append(('stop',))
                def logout(self):calls.append(('logout',))
                def read_value(self,name):
                    calls.append(('read',name))
                    if read_error:raise RuntimeError('fixture monitoring unavailable')
                    return 'TRUE' if name.endswith('WB_Done') or 'Out0' in name else 'FALSE'
            engine=NS(projects=NS(open=lambda path:project),system=system,
                online=NS(create_online_application=lambda app:Connection()),
                OnlineChangeOption=NS(Never='Never'),ResetOption=NS(Cold='Cold'),Severity=NS(Error='Error'))
            diagnostic=NS(FileVersionInfo=NS(GetVersionInfo=lambda path:NS(FileVersion='fixture only')))
            with patch.dict('sys.modules',{'scriptengine':engine,'System.Diagnostics':diagnostic}),patch.dict(os.environ,{'PLC_WORKBENCH_REQUEST':str(root/'request.json')}):
                codesys_worker.main()
            return json.loads((root/'response.json').read_text(encoding='utf-8')),calls
    def test_simulation_false_prevents_all_online_operations(self):
        result,calls=self.run_worker(simulation=False)
        self.assertEqual(result['status'],'error');self.assertFalse(any(c[0]=='login' for c in calls))
    def test_compiler_error_prevents_login_and_target_pass(self):
        result,calls=self.run_worker(compiler_error=True)
        self.assertEqual(result['target_compile'],'not_executed');self.assertFalse(any(c[0]=='login' for c in calls))
    def test_explicit_port_order_is_preserved_and_no_foreign_app_deletion(self):
        result,calls=self.run_worker()
        self.assertEqual(result['status'],'completed');self.assertEqual(result['actual_rows'],[{'z':'TRUE','a':'FALSE'}])
        self.assertIn(('login','Never',False),calls);self.assertIn(('logout',),calls)
        self.assertEqual(len(result['compiled_image_sha256']),64)
    def test_monitoring_error_always_stops_and_logs_out(self):
        result,calls=self.run_worker(read_error=True)
        self.assertEqual(result['status'],'error');self.assertIn(('stop',),calls);self.assertIn(('logout',),calls)

if __name__=='__main__':unittest.main()
