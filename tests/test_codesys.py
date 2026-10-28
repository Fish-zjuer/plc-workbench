"""Transport/worker fixtures, NOT evidence of real CODESYS compilation or simulation."""
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from plc_agent import codesys
from plc_agent.provider import Cancelled
from plc_agent.storage import Project,Session
from plc_agent.toolbox import Toolbox
from plc_probe.backend import BackendError
from plc_probe.config import cache_dir
from test_general_tasks import contract,GOOD

class CodesysTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=cache_dir());self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.exe=self.root/'CODESYS.exe';self.exe.write_bytes(b'transport fixture only')
        self.template=self.root/'template.project';self.template.write_bytes(b'template fixture only')
        self.cfg={'executable':str(self.exe),'profile':'CODESYS V3.5 SP22','template_project':str(self.template)}
    def test_configuration_is_host_owned_and_missing_installation_is_explicit(self):
        with patch.object(codesys,'load_config',return_value={}):
            result=codesys.CodesysBackend().capabilities(contract(),GOOD)
            self.assertEqual(result['status'],'blocked');self.assertEqual(result['target_compile'],'not_executed')
        bad={**self.cfg,'template_project':str(self.root/'missing.project')}
        with self.assertRaises(ValueError):codesys.validate_config(bad)
        project=Project.create('CODESYS fixture',self.root);session=Session.create(project)
        self.assertEqual(Toolbox(session).call('plc_codesys_compile',{'task_id':'a'*12})['status'],'blocked_by_plan_mode')
    def test_harness_keeps_case_states_separate_and_preserves_output_order(self):
        spec=contract();spec['outputs']={'z':'BOOL','a':'BOOL'}
        cases=copy.deepcopy(spec['scenarios']);cases[0]['trace'][0]['expect']={'z':False};cases[0]['trace'][1]['expect']={'z':True}
        declaration,body=codesys.harness(spec,cases*2)
        self.assertIn('WB_Uut0 :',declaration);self.assertIn('WB_Uut1 :',declaration)
        self.assertIn('WB_Out0[0] := WB_Uut0.z;',body);self.assertIn('WB_Out1[0] := WB_Uut0.a;',body)
    def test_split_source_respects_nested_comments_and_keeps_declared_interface(self):
        source=GOOD.replace('y := x;','(* END_VAR (* nested *) *)\ny := x;')
        declaration,body=codesys.split_source(source,'Mapping')
        self.assertIn('VAR_INPUT',declaration);self.assertNotIn('y := x;',declaration);self.assertIn('y := x;',body)
        string_source=GOOD.replace('VAR_OUTPUT',"VAR label : STRING := 'END_VAR $\' END_FUNCTION_BLOCK'; END_VAR\nVAR_OUTPUT")
        declaration,body=codesys.split_source(string_source,'Mapping')
        self.assertIn('VAR_OUTPUT',declaration);self.assertIn('y := x;',body)
        with self.assertRaises(ValueError):codesys.split_source('TYPE Foo : BOOL; END_TYPE\n'+GOOD,'Mapping')
    def test_output_decoding_handles_typed_bool_and_bitstrings(self):
        self.assertTrue(codesys.parse_value('BOOL#TRUE','BOOL'))
        self.assertEqual(codesys.parse_value('WORD#16#FFFF','WORD'),65535)
        self.assertEqual(codesys.parse_value('INT#-42','INT'),-42)
        with self.assertRaises(ValueError):codesys.parse_value('unavailable','BOOL')
    def test_profile_lock_is_released_and_never_runs_same_profile_twice(self):
        with codesys.profile_lease(self.cfg):
            with self.assertRaises(BackendError):
                with codesys.profile_lease(self.cfg):pass
        with codesys.profile_lease(self.cfg):pass
    def transport(self,edit=None):
        root=self.root
        class Process:
            returncode=0;pid=123
            def __init__(self,args,**kwargs):
                self.args=args;self.kwargs=kwargs
                request=json.loads(Path(kwargs['env']['PLC_WORKBENCH_REQUEST']).read_text(encoding='utf-8'))
                value={'nonce':request['nonce'],'source_sha256':request.get('source_sha256'),
                    'status':'probed','vendor':'CODESYS','vendor_version':'fixture only'}
                if edit:edit(value)
                Path(request['output']).write_text(json.dumps(value),encoding='utf-8')
            def communicate(self,timeout=None):return b'fixture stdout',b''
            def poll(self):return 0
        return Process
    def test_transport_uses_official_profile_flags_and_checks_identity(self):
        constructor=self.transport()
        with patch.object(codesys.subprocess,'Popen',side_effect=constructor) as launch:
            result=codesys.invoke({'action':'probe','source_sha256':None},self.root/'run',self.cfg)
            args=launch.call_args.args[0]
            if isinstance(args,str):
                self.assertIn('--profile="'+self.cfg['profile']+'"',args);self.assertIn('--runscript="',args)
            else:
                self.assertIn('--profile='+self.cfg['profile'],args);self.assertTrue(any(a.startswith('--runscript=') for a in args))
            self.assertIn('--noUI',args)
            self.assertEqual(result['status'],'probed')
        for key,value in [('nonce','wrong'),('source_sha256','wrong'),('vendor','fake'),('vendor_version','')]:
            with self.subTest(key=key),patch.object(codesys.subprocess,'Popen',side_effect=self.transport(lambda r:r.update({key:value}))):
                with self.assertRaises(BackendError):codesys.invoke({'action':'probe','source_sha256':None},self.root/key,self.cfg)
    def test_timer_program_cannot_enter_clock_independent_simulation(self):
        code=GOOD.replace('VAR_OUTPUT','VAR t : TON; END_VAR\nVAR_OUTPUT')
        with patch.object(codesys,'load_config',return_value=self.cfg):
            result=codesys.CodesysBackend().capabilities(contract(),code)
        self.assertTrue(any(b['feature']=='clock_independent_scan_bridge' for b in result['blockers']))
    def test_replay_behavior_comparison_ignores_only_vendor_file_locations(self):
        from plc_agent.task_backend import replay_identity
        first={'status':'pass','cases':[{'rows':[{'actual':{'y':True}}]}],'vendor_evidence':'one','vendor_evidence_files':{'one':'hash'}}
        second={**first,'vendor_evidence':'two','vendor_evidence_files':{'two':'hash'}}
        self.assertEqual(replay_identity(first),replay_identity(second))
        second=copy.deepcopy(second);second['cases'][0]['rows'][0]['actual']['y']=False
        self.assertNotEqual(replay_identity(first),replay_identity(second))

if __name__=='__main__':unittest.main()
