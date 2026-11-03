"""Contract fixtures, not claims of a native PLCSIM or CBMC acceptance run."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from plc_agent import dataset, tia, tia_tests, tia_workflow, tia_formal
from plc_agent.config import ModelConfig
from plc_agent.dataset_formal import attach
from plc_agent.ltl_adapter import Adapter, Unsupported
from plc_probe.backend import BackendError
from tests.test_tia import FakeProvider, SAMPLE, TASK


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        template=self.root/'template';template.mkdir();(template/'p.ap21').write_bytes(b'project')
        exe=self.root/'bridge.exe';exe.write_bytes(b'fixture')
        api=self.root/'Siemens.Simatic.Simulation.Runtime.Api.x64.dll';api.write_bytes(b'fixture')
        self.config={'executable':str(exe),'template_project':str(template/'p.ap21'),
                     'simulation_api':str(api),'simulation_timeout_seconds':600}
        self.source=self.root/'candidate.scl';self.source.write_bytes(SAMPLE.read_bytes())
        self.task={**TASK,'adapter_format':'complete_input_trace','scenarios':[{'name':'start_stop','trace':[
            {'time_ms':0,'inputs':{'StartBtn':True,'StopBtn':False,'EStop':False},'expected':{'Motor':True}},
            {'time_ms':10,'inputs':{'StartBtn':False,'StopBtn':True,'EStop':False},'expected':{'Motor':False}}]}],
            'ltl':{'properties':[{'id':'stop','formula':'G(StopBtn -> !Motor)'}]}}
    def tearDown(self): self.tmp.cleanup()

    def test_same_frozen_scheduling_supports_arrays_structs_analog_and_reports_variant(self):
        from plc_agent.behavior_plan import harness
        for row in dataset.catalog()['tasks']:
            task=dataset.load(row['id'])
            if task['adapter_format']=='fifo_reference_rows':
                with self.assertRaises(BackendError):tia_tests.harness(task)
                continue
            try:a=harness(task)
            except BackendError:
                with self.assertRaises(BackendError):tia_tests.harness(task)
                continue
            b=tia_tests.harness(task)
            for key in ('row_count','output_names','output_types','simulation_timeout_seconds'):
                self.assertEqual(a[key],b[key],row['id'])
            self.assertIn('PT := T#1h',b['harness_source'])
            self.assertNotIn('#WB_Clock.TON(IN := FALSE);',b['harness_source'])
            self.assertNotIn('PROGRAM PLC_PRG',b['harness_source'])

    def response(self, rows=None, times=None):
        return {'status':'simulation_completed','simulation':True,'instance_name':'WB_fixture',
                'actual_rows':rows or [{'Motor':True},{'Motor':False}],
                'actual_scan_times_ms':times or [0,10],'execution_fingerprint':{'fixture':True}}

    def test_native_rows_use_shared_predicates_and_keep_wrong_output_as_failure(self):
        for values,status in [([{'Motor':True},{'Motor':False}],'pass'),([{'Motor':True},{'Motor':True}],'fail')]:
            with patch('plc_agent.tia.simulate_scl',return_value=self.response(values)):
                result=tia_tests.evaluate(self.source,self.task,self.config,directory=self.root/status)
            self.assertEqual(result['status'],status);self.assertTrue(result['behavior_tested'])
            self.assertEqual(result['summary']['scans'],2);self.assertEqual(result['test_backend'],'tia')

    def test_incomplete_or_false_native_results_never_pass(self):
        for response in [self.response([{'Motor':True}]),self.response([{'Motor':True},{'Motor':1}]),
                         self.response(times=[0]),{'status':'harness_error','message':'bad driver'}]:
            with patch('plc_agent.tia.simulate_scl',return_value=response), self.assertRaises(BackendError):
                tia_tests.evaluate(self.source,self.task,self.config,directory=self.root/'invalid')

    def test_timer_scheduling_drift_is_infrastructure_feedback(self):
        self.source.write_text(self.source.read_text(encoding='utf-8-sig').replace('BEGIN','VAR\n timer : TON_TIME;\nEND_VAR\nBEGIN'),encoding='utf-8')
        with patch('plc_agent.tia.simulate_scl',return_value=self.response(times=[0,20])):
            result=tia_tests.evaluate(self.source,self.task,self.config,directory=self.root/'timer')
        self.assertEqual(result['status'],'behavior_not_supported');self.assertFalse(result['behavior_tested'])
        from plc_agent.run_output import metrics
        self.assertIsNone(metrics(result,self.task)['test_cases_passed'])

    def test_simulator_request_excludes_expected_and_uses_disposable_project(self):
        plan=tia_tests.harness(self.task)
        def launch(command,stdout,stderr,shell):
            self.assertFalse(shell);self.assertEqual(command[1],'--simulate')
            req=json.loads(Path(command[2]).read_text(encoding='utf-8'))
            self.assertNotIn('expected',json.dumps(req));self.assertNotEqual(req['project'],self.config['template_project'])
            receipt=self.response();stdout.write(('WB_RESULT_JSON='+json.dumps(receipt)+'\n').encode());stdout.flush()
            class Process:
                returncode=0
                def poll(self):return 0
            return Process()
        with patch('plc_agent.tia.subprocess.Popen',side_effect=launch):
            result=tia.simulate_scl(self.source,plan,self.config,directory=self.root/'boundary')
        self.assertEqual(result['status'],'simulation_completed')
        self.assertEqual(Path(self.config['template_project']).read_bytes(),b'project')

    def test_missing_simulator_uses_same_formal_stage_gate_as_codesys(self):
        compiled={'status':'compile_passed','target_compile':'passed'}
        with patch('plc_agent.tia_workflow.compile_candidate',return_value=compiled), \
             patch('plc_agent.tia_tests.evaluate',side_effect=BackendError({'status':'behavior_not_configured','message':'Missing API'})), \
             patch('plc_agent.plcverif_backend.verify',return_value={'status':'bounded_pass','properties':[]}) as formal:
            result=tia_workflow.evaluate_candidate(self.source,self.task,self.config,directory=self.root/'full',formal_config={'engine':'cbmc'})
        self.assertEqual(result['status'],'behavior_not_configured');self.assertFalse(result['behavior_tested'])
        self.assertEqual(result['ltl_status'],'not_executed');formal.assert_not_called()

    def test_compile_or_behavior_failure_blocks_formal_and_preserves_each_stage(self):
        for compile_status,behavior in [('compile_failed',None),('compile_passed',{'status':'fail','behavior_tested':True})]:
            compiled={'status':compile_status,'target_compile':'passed' if compile_status=='compile_passed' else 'failed'}
            with patch('plc_agent.tia_workflow.compile_candidate',return_value=compiled), \
                 patch('plc_agent.tia_tests.evaluate',return_value=behavior) as sim, patch('plc_agent.plcverif_backend.verify') as formal:
                result=tia_workflow.evaluate_candidate(self.source,self.task,self.config,directory=self.root/compile_status)
            formal.assert_not_called()
            self.assertEqual(result['ltl_status'],'not_executed')
            self.assertEqual(sim.call_count,int(compile_status=='compile_passed'))

    def test_real_behavior_failure_enters_repair_but_formal_counterexample_stops(self):
        code=self.source.read_text(encoding='utf-8-sig')
        provider=FakeProvider([code,code.replace('#Motor := TRUE','#Motor := NOT FALSE')])
        failure={'status':'fail','target_compile':'passed','behavior_tested':True,'message':'Native output differs'}
        success={'status':'pass','target_compile':'passed','behavior_tested':True,'ltl_status':'bounded_pass'}
        with patch('plc_agent.tia_workflow.evaluate_candidate',side_effect=[failure,success]):
            r=tia_workflow.run(self.task,self.root/'generated.scl',self.root/'repair',ModelConfig(),vendor_config=self.config,
                               provider=provider,verification='full',notify=lambda _:None)
        self.assertEqual(r['status'],'pass');self.assertTrue(r['behavior_tested']);self.assertEqual(r['model_calls'],2)
        self.assertIn('Native output differs',provider.messages[1][1]['content'])
        provider=FakeProvider([])
        with patch('plc_agent.tia_workflow.evaluate_candidate',return_value={**success,'status':'formal_blocked'}):
            r=tia_workflow.run(self.task,self.source,self.root/'blocked',ModelConfig(),vendor_config=self.config,
                               provider=provider,verification='full',notify=lambda _:None)
        self.assertEqual(r['status'],'formal_blocked');self.assertEqual(r['model_calls'],0)

    def test_scl_lexical_adapter_keeps_typed_literals_and_models_fresh_temporaries(self):
        code='''FUNCTION_BLOCK "Demo"
{ S7_Optimized_Access := 'TRUE' }
VERSION : 0.1
VAR_INPUT x : DWORD; END_VAR
VAR_OUTPUT y : DWORD; END_VAR
VAR_TEMP t : DWORD; END_VAR
BEGIN
// #untouched
#t := DWORD#16#FF;
#y := #x XOR #t;
END_FUNCTION_BLOCK
'''
        converted,notes=tia_formal.adapt(code,block='Demo')
        self.assertIn('DWORD#16#FF',converted);self.assertIn('// #untouched',converted)
        self.assertIn('t := WBTEMP_0;',converted);self.assertNotIn('VAR_TEMP',converted)
        extra=[p for n in notes for p in n.get('interface_additions',[])]
        task={**self.task,'block':'Demo','interface':[{'direction':'Input','name':'x','type':'DWORD'},{'direction':'Output','name':'y','type':'DWORD'}]+extra,'ltl':{'text':'G(y = x)'}}
        wrapped=Adapter(task,3).prepare().instrument(converted)
        self.assertIn('WBTEMP_0 := WBTEMP_0',wrapped)
        for fragment in ('VARIANT','TON_TIME','ARRAY[*] OF BOOL'):
            with self.assertRaises(Unsupported):tia_formal.adapt(code.replace('t : DWORD','t : '+fragment),block='Demo')
        with self.assertRaises(Unsupported):tia_formal.adapt(code.replace('#x','"ExternalDB".x'),block='Demo')

    def test_scl_normalizes_only_syntax_and_delegates_verification(self):
        code='FUNCTION_BLOCK "A"\nVAR_OUTPUT y : USINT; END_VAR\nBEGIN\n#y := USINT#16#FF;\nEND_FUNCTION_BLOCK'
        converted,notes=tia_formal.adapt(code,block='A')
        self.assertIn('USINT#16#FF',converted)
        self.assertNotIn('WBSCL_LITERAL',converted)
        shifted,_=tia_formal.adapt(code.replace('USINT#16#FF','SHL(IN := DWORD#1, N := 3)'),block='A')
        self.assertIn('SHL(DWORD#1, 3)',shifted)
        timer=code.replace('VAR_OUTPUT','VAR timer : TON_TIME; END_VAR\nVAR_OUTPUT').replace('#y := USINT#16#FF;','#timer.TON(IN := TRUE, PT := T#1s);')
        normalized,_=tia_formal.adapt(timer,block='A')
        self.assertIn('timer : TON;',normalized);self.assertIn('timer(IN := TRUE, PT := T#1s)',normalized)
        self.assertNotIn('FUNCTION_BLOCK TON',normalized)
        report={'status':'bounded_pass','properties':[],'source_sha256':'model-fixture','bounded_verified_property_ids':[]}
        with patch('plc_agent.plcverif_backend.verify',return_value=report) as shared:
            result=tia_formal.verify(self.task,self.source,self.root/'delegate',config={'engine':'cbmc'},timeout_seconds=12)
        shared.assert_called_once()
        self.assertEqual(shared.call_args.args[1].name,'normalized.st')
        self.assertEqual(shared.call_args.kwargs['timeout_seconds'],12)
        self.assertEqual(result['model_source_sha256'],'model-fixture')
        self.assertEqual(result['source_sha256'],hashlib.sha256(self.source.read_bytes()).hexdigest())


if __name__=='__main__':unittest.main()
