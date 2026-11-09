import unittest
import subprocess
import sys
from unittest.mock import patch
from plc_agent import __main__ as entry


class EntryTests(unittest.TestCase):
    def test_no_arguments_uses_the_single_web_entry(self):
        with patch('sys.argv',['plc_agent']),patch('plc_agent.web.main',return_value=0) as web:
            self.assertEqual(entry.main(),0)
        web.assert_called_once_with(['--port','18765','--open-browser'])

    def test_explicit_web_command_keeps_custom_port(self):
        with patch('sys.argv',['plc_agent','web','--port','18888']),patch('plc_agent.web.main',return_value=0) as web:
            self.assertEqual(entry.main(),0)
        web.assert_called_once_with(['--port','18888'])

    def test_old_ui_is_not_a_second_main_application_entry(self):
        with patch('sys.argv',['plc_agent','ui']),patch('sys.stderr'):
            with self.assertRaises(SystemExit) as error:entry.main()
        self.assertEqual(error.exception.code,2)

    def test_native_app_imports_without_optional_or_legacy_directories(self):
        script='''import importlib.abc, sys
class ExcludeOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'optional_local_tests' or fullname.startswith('optional_local_tests.') or fullname == 'plc_agent.legacy' or fullname.startswith('plc_agent.legacy.'):
            raise ModuleNotFoundError(fullname)
sys.meta_path.insert(0, ExcludeOptional())
import plc_agent.web
print('native-import-ok')
'''
        result=subprocess.run([sys.executable,'-B','-c',script],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('native-import-ok',result.stdout)

    def test_author_notes_follow_the_selected_backend(self):
        from plc_agent.bank32 import author_packet
        from plc_agent.dataset import load
        task=load('CUSTOM_09')
        native=author_packet(task,backend='codesys')['backend_notes']
        local=author_packet(task,backend='optional_local')['backend_notes']
        self.assertIn('functional test executor are CODESYS',native)
        self.assertNotIn('Local behavior backend is STruC++',native)
        self.assertIn('Local behavior backend is STruC++',local)
