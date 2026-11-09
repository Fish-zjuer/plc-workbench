"""LTL translation, bounded semantics and process failures must not create proof claims."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from plc_agent import dataset, dataset_formal, plcverif_backend
from plc_agent.ltl_adapter import Adapter, Unsupported, parse, properties
from plc_agent.plcverif_st import adapt
from plc_agent.provider import Cancelled
from plc_agent.run_output import metrics


class FormalConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.project=self.root/'project';self.project.mkdir()
        self.home=self.project/'agent_data'
        self.patch_root=patch.object(plcverif_backend,'ROOT',self.project);self.patch_root.start();self.addCleanup(self.patch_root.stop)
        self.patch_which=patch.object(plcverif_backend.shutil,'which',return_value=None);self.patch_which.start();self.addCleanup(self.patch_which.stop)
        self.patch_env=patch.dict('os.environ',{'ProgramFiles':str(self.root/'apps'),'JAVA_HOME':''});self.patch_env.start();self.addCleanup(self.patch_env.stop)

    def executable(self,path):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture');return str(path.resolve())

    def test_fresh_checkout_discovers_tools_without_a_config_file(self):
        base=self.project/'tools/plcverif'
        cli=self.executable(base/'plcverif-clic.exe')
        java=self.executable(base/'jre/bin/java.exe')
        cbmc=self.executable(base/'tools/cbmc/bin/cbmc.exe')
        state=plcverif_backend.environment(self.home)
        self.assertEqual(state['status'],'tools_ready');self.assertFalse(state['saved'])
        self.assertEqual(state['path_sources']['plcverif'],'auto')
        self.assertEqual((state['plcverif'],state['java'],state['cbmc']),(cli,java,cbmc))
        self.assertFalse((self.home/'formal_config.json').exists())

    def test_missing_tools_keep_editable_defaults_and_list_every_missing_path(self):
        state=plcverif_backend.environment(self.home)
        self.assertEqual(state['status'],'not_configured');self.assertEqual(state['bound'],20)
        self.assertEqual(state['config_file'],'agent_data/formal_config.json')
        self.assertNotIn(str(self.root),state['config_file'])
        self.assertEqual({item['key'] for item in state['missing_tools']},{'plcverif','java','cbmc'})
        for name in ('plcverif','java','cbmc'):self.assertIn(name,state)
        self.assertIn('填写',state['message'])

    def test_custom_paths_create_config_and_reload_on_another_location(self):
        base=self.root/'Other Software'
        cli=self.executable(base/'PLCverif/plcverif-clic.exe')
        java=self.executable(base/'Java/bin/java.exe')
        cbmc=self.executable(base/'CBMC/bin/cbmc.exe')
        state=plcverif_backend.save_configuration({'plcverif':'"'+cli+'"','java':java,'cbmc':cbmc,'bound':12},self.home)
        self.assertTrue(state['saved']);self.assertEqual(state['status'],'tools_ready')
        self.assertEqual(state['path_sources']['cbmc'],'saved')
        saved=json.loads((self.home/'formal_config.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['plcverif'],cli);self.assertEqual(saved['bound'],12)
        self.assertEqual(plcverif_backend.configuration(self.home)['cbmc'],cbmc)

    def test_missing_executable_is_not_saved_as_ready(self):
        with self.assertRaisesRegex(ValueError,'PLCverif'):
            plcverif_backend.save_configuration({'plcverif':str(self.root/'missing.exe')},self.home)
        self.assertFalse((self.home/'formal_config.json').exists())


class LtlAdapterTests(unittest.TestCase):
    def task(self,formula):
        return {'id':'IMPORTED_71','block':'FB_Demo','interface':[
            {'direction':'Input','name':'x','type':'BOOL'},
            {'direction':'Output','name':'y','type':'BOOL'}],
            'ltl':{'properties':[{'id':'P1','formula':formula}]}}

    def test_any_imported_task_uses_original_ltl(self):
        task=self.task('G(x -> y)');saved=copy.deepcopy(task)
        a=Adapter(task,3).prepare()
        self.assertEqual(a.properties[0]['status'],'not_executed')
        text=a.instrument('FUNCTION_BLOCK FB_Demo\nVAR_INPUT x:BOOL; END_VAR\nVAR_OUTPUT y:BOOL; END_VAR\ny:=x; RETURN;\nEND_FUNCTION_BLOCK')
        self.assertIn('FUNCTION_BLOCK PVL_Harness',text)
        self.assertIn('y:=x; RETURN;',text)
        self.assertIn('PVL_Scan <= 3',text)
        self.assertEqual(task,saved)

    def test_temporal_next_waits_for_next_scan_not_next_instruction(self):
        a=Adapter(self.task('G(x -> X(y))'),2).prepare()
        f=a.formula(a.properties[0],lambda s:s,'EoC')
        self.assertIn('X((!EoC) U (EoC & PVL_Active',f)
        self.assertTrue(a.properties[0]['temporal_boundary_sensitive'])

    def test_unknown_observer_is_not_replaced_by_true(self):
        a=Adapter(self.task('G(unknown -> y)'),2).prepare()
        self.assertEqual(a.properties[0]['status'],'unsupported')
        self.assertIn('unknown',a.properties[0]['message'])
        self.assertEqual(a.atoms,{})

    def test_untrusted_syntax_is_rejected(self):
        with self.assertRaises(Unsupported):parse('G(x); y:=TRUE')

    def test_all_32_tasks_are_read_and_model_dependencies_are_explicit(self):
        tasks=dataset.catalog()['tasks'];total=0;adapted=0;blocked=[]
        self.assertEqual(len(tasks),32)
        for item in tasks:
            task=dataset.load(item['id']);total+=len(properties(task['ltl']))
            if task['ltl']['execution'].get('requires_model'):
                blocked.append(task['id']);continue
            a=Adapter(task,20).prepare()
            self.assertTrue(all('ast' in p for p in a.properties),task['id'])
            from plc_agent.cbmc_model import monitor
            monitor(a)
            adapted+=len(a.properties)
        self.assertEqual(total,233);self.assertEqual(adapted,216)
        self.assertEqual(blocked,['PUBLIC_08','PUBLIC_18'])

    def test_observer_cannot_change_candidate_or_scan_bound(self):
        for step in ('y := TRUE;','PVL_Uut.y := TRUE;','PVL_Scan := 0;','PVL_Uut();'):
            task=self.task('G(y)');task['ltl']['execution']={'before':[step]}
            with self.assertRaises(Unsupported,msg=step):Adapter(task,2)

    def test_text_file_and_json_share_property_reader(self):
        self.assertEqual(properties({'text':'# comment\nP1: G(x -> y)\n\nG(y)'}),
                         [{'id':'P1','formula':'G(x -> y)'},{'id':'P2','formula':'G(y)'}])
        self.assertTrue(Adapter({**self.task('G(y)'),'ltl':'G(y)'},2).prepare().properties[0].get('ast'))

    def test_enum_lowering_preserves_case_labels_comments_and_strings(self):
        source="""TYPE E_State : (Idle := 0, Running := 7); END_TYPE
FUNCTION_BLOCK Demo
VAR s : E_State := E_State.Idle; msg : STRING := 'END_IF Running'; END_VAR
(* Running END_IF *)
CASE s OF
Idle: s := Running;
END_CASE
END_FUNCTION_BLOCK"""
        converted,notes=adapt(source)
        self.assertIn('s : INT := INT#0',converted)
        self.assertIn('INT#0: s := INT#7;',converted)
        self.assertIn("'END_IF Running'",converted)
        self.assertIn('(* Running END_IF *)',converted)
        self.assertIn('END_CASE;',converted)
        self.assertTrue(notes)

    def test_unsupported_enum_default_is_not_silently_zero_initialized(self):
        with self.assertRaises(Unsupported):adapt('TYPE E : (A:=3,B:=4); END_TYPE')

    def test_full_original_state_machine_and_conditional_liveness_parse(self):
        for ident,count in [('CUSTOM_09',10),('CUSTOM_10',8),('CUSTOM_08',5),('CUSTOM_12',9),('CUSTOM_02',7),('CUSTOM_03',7),('CUSTOM_07',5)]:
            adapter=Adapter(dataset.load(ident),20).prepare()
            self.assertEqual(len(adapter.properties),count)
            self.assertFalse([p for p in adapter.properties if p['status']=='unsupported'],ident)


class BackendPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/'candidate.st';self.source.write_text('fixture')
        self.task=dataset.load('CUSTOM_09')

    def test_missing_engine_preserves_all_properties_without_success(self):
        cfg={'bound':20,'timeout_seconds':1,'plcverif':'','java':'','nuxmv':''}
        r=plcverif_backend.verify(self.task,self.source,self.root/'formal',config=cfg)
        self.assertEqual(r['status'],'not_configured')
        self.assertEqual(len(r['properties']),10)
        self.assertEqual(r['bounded_verified_property_ids'],[])

    def test_compile_and_test_failures_do_not_invoke_formal_engine(self):
        for status in ('compile_error','fail','tool_error'):
            with patch.object(plcverif_backend,'verify') as verify:
                r=dataset_formal.attach({'status':status},self.task,self.source,self.root/'formal')
            verify.assert_not_called();self.assertEqual(r['status'],status)
            self.assertEqual(r['ltl_status'],'not_executed')

    def test_source_model_counterexample_stops_unconfirmed_repair(self):
        formal={'status':'counterexample','bound':20,'properties':[], 'message':'trace'}
        with patch.object(plcverif_backend,'verify',return_value=formal):
            r=dataset_formal.attach({'status':'pass'},self.task,self.source,self.root/'formal')
        self.assertEqual(r['status'],'formal_blocked')
        self.assertEqual(r['finite_test_status'],'pass')

    def test_bad_spec_does_not_request_candidate_repair(self):
        task=copy.deepcopy(self.task)
        task['ltl']['properties']=[{'id':'P','formula':'G(true)'},{'id':'P','formula':'G(false)'}]
        r=dataset_formal.attach({'status':'pass'},task,self.source,self.root/'formal')
        self.assertEqual(r['status'],'pass');self.assertEqual(r['ltl_status'],'invalid_spec')

    def test_float_abstraction_never_becomes_a_verified_result(self):
        self.source.write_text('FUNCTION_BLOCK FB_SpectrometerQualification\nVAR r:REAL; END_VAR\nEND_FUNCTION_BLOCK')
        cfg={k:str(self.source) for k in ('plcverif','java','nuxmv')};cfg.update(bound=2,timeout_seconds=1)
        with patch.object(plcverif_backend,'_run') as run:
            result=plcverif_backend.verify(self.task,self.source,self.root/'formal',config=cfg)
        run.assert_not_called();self.assertEqual(result['status'],'unsupported')
        self.assertFalse(result['bounded_verified_property_ids'])
        self.assertTrue(all(p['status']=='unsupported_model' for p in result['properties']))

    def test_bounded_success_is_not_unbounded_proof(self):
        r={'status':'pass','formal_verification':{'status':'bounded_pass','bound':20,
           'declared_ltl_total':10,'bounded_verified_property_ids':['P1'],
           'properties':[{'status':'bounded_pass'}]}}
        m=metrics(r,self.task)
        self.assertFalse(m['formal_full_ltl_proved'])
        self.assertEqual(m['formal_property_pass_rate'],.1)
        self.assertEqual(m['formal_bound'],20)

    def test_cancel_leaves_explicit_interrupted_evidence(self):
        cancel=threading.Event();cancel.set()
        cfg={k:str(self.source) for k in ('plcverif','java','nuxmv')};cfg.update(bound=2,timeout_seconds=1)
        with self.assertRaises(Cancelled):
            plcverif_backend.verify(self.task,self.source,self.root/'formal',config=cfg,cancel_event=cancel)
        saved=json.loads((self.root/'formal/formal.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['status'],'interrupted')


if __name__=='__main__':unittest.main()
