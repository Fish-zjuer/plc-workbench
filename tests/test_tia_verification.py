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
        lease=patch('plc_agent.tia.vendor_lease');lease.start();self.addCleanup(lease.stop)
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        template=self.root/'template';template.mkdir();(template/'p.ap21').write_bytes(b'project')
        exe=self.root/'bridge.exe';exe.write_bytes(b'fixture')
        (self.root/'TiaRuntime.exe').write_bytes(b'runtime-fixture')
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

    def prepare_receipt(self, command, stdout):
        req=json.loads(Path(command[2]).read_text(encoding='utf-8'))
        identity=req['execution_fingerprint']
        manifest={'schema':'tia-prepared-card-v1','source_sha256':req['source_sha256'],
                  'source_bundle_sha256':tia.sha256(req['source']),
                  'bridge_sha256':identity['bridge_sha256'],'runtime_host_sha256':identity['runtime_host_sha256']}
        Path(req['evidence_directory'],'prepared_card.json').write_text(json.dumps(manifest),encoding='utf-8')
        stdout.write(b'WB_RESULT_JSON={"status":"simulation_prepared"}\n');stdout.flush()

    def test_native_rows_use_shared_predicates_and_keep_wrong_output_as_failure(self):
        for values,status in [([{'Motor':True},{'Motor':False}],'pass'),([{'Motor':True},{'Motor':True}],'fail')]:
            with patch('plc_agent.tia.simulate_scl',return_value=self.response(values)):
                result=tia_tests.evaluate(self.source,self.task,self.config,directory=self.root/status)
            self.assertEqual(result['status'],status);self.assertTrue(result['behavior_tested'])
            self.assertEqual(result['summary']['scans'],2);self.assertEqual(result['test_backend'],'tia')

    def analog_response(self, task, plan):
        case = task['scenarios'][0]
        rows = []
        for row in case['rows']:
            values = [*row['raw'], *[v for record in row['expected'] for v in record]]
            rows.append({name: bool(value) if dtype=='BOOL' else value
                         for name, dtype, value in zip(plan['output_names'], plan['output_types'], values)})
        return {'status':'simulation_completed','simulation':True,'actual_rows':rows,
                'actual_scan_times_ms':[0]*len(rows),'execution_fingerprint':{'bridge':'same'},
                'cpu_order_number':'CPU1511','source_sha256':hashlib.sha256(self.source.read_bytes()).hexdigest()}

    def test_open_array_default_batches_all_frozen_rows_then_judges_once(self):
        task = dataset.load('PUBLIC_08')
        original = deepcopy(task)
        plans = [tia_tests.harness({**task,'scenarios':[case]}) for case in task['scenarios']]
        responses = [self.analog_response({**task,'scenarios':[case]},plan)
                     for case,plan in zip(task['scenarios'],plans)]
        for negative in (False, True):
            actual = deepcopy(responses)
            if negative: actual[3]['actual_rows'][0]['channel7.outputValue'] += 100
            directory = self.root/('analog_negative' if negative else 'analog_positive')
            with patch('plc_agent.tia.simulate_scl',side_effect=actual) as simulate, \
                 patch('plc_agent.tia_tests.time.monotonic',side_effect=[0,1,70,140,210]), \
                 patch('plc_agent.tia_tests.dataset.judge_output',wraps=dataset.judge_output) as judge:
                result = tia_tests.evaluate(self.source,task,self.config,directory=directory)
            self.assertEqual(result['status'],'fail' if negative else 'pass')
            self.assertEqual(result['summary']['scans'],320)
            self.assertEqual(result['summary']['scenarios'],4)
            judge.assert_called_once()
            self.assertEqual(task,original)
            self.assertEqual([c.args[1]['row_count'] for c in simulate.call_args_list],[80]*4)
            self.assertEqual([c.args[2]['simulation_timeout_seconds'] for c in simulate.call_args_list],[599,530,460,390])
            self.assertEqual([c.kwargs['deadline'] for c in simulate.call_args_list],[600]*4)
            self.assertEqual([c.args[1]['harness_source'] for c in simulate.call_args_list],
                             [p['harness_source'] for p in plans])
            manifest=json.loads((directory/'batch_manifest.json').read_text())
            self.assertEqual([b['row_offset'] for b in manifest['batches']],[0,80,160,240])
            self.assertEqual(manifest['status'],'simulation_completed')

    def test_open_array_incomplete_or_changed_batch_never_reaches_judge(self):
        task=dataset.load('PUBLIC_08')
        plan=tia_tests.harness({**task,'scenarios':[task['scenarios'][0]]})
        first=self.analog_response({**task,'scenarios':[task['scenarios'][0]]},plan)
        second_task={**task,'scenarios':[task['scenarios'][1]]}
        second=self.analog_response(second_task,tia_tests.harness(second_task))
        changed=deepcopy(second);changed['execution_fingerprint']={'bridge':'changed'}
        wrong_source=deepcopy(second);wrong_source['source_sha256']='changed-candidate'
        incomplete=deepcopy(second);incomplete['actual_rows'].pop()
        for index, response in enumerate(({'status':'simulation_error','message':'vendor failed'},changed,wrong_source,incomplete)):
            with patch('plc_agent.tia.simulate_scl',side_effect=[first,response]) as simulate, \
                 patch('plc_agent.tia_tests.dataset.judge_output') as judge, self.assertRaises(BackendError):
                tia_tests.evaluate(self.source,task,self.config,directory=self.root/f'partial_{index}')
            self.assertEqual(simulate.call_count,2);judge.assert_not_called()
        with patch('plc_agent.tia.simulate_scl') as simulate, \
             patch('plc_agent.tia_tests.time.monotonic',side_effect=[0,500]), self.assertRaises(BackendError):
            tia_tests.evaluate(self.source,task,self.config,directory=self.root/'exhausted')
        simulate.assert_not_called()

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

    def test_insufficient_total_timeout_stops_before_starting_owned_simulator(self):
        with patch('plc_agent.tia.simulate_scl') as simulate, self.assertRaises(BackendError) as error:
            tia_tests.evaluate(self.source,self.task,{**self.config,'simulation_timeout_seconds':150},
                               directory=self.root/'short-timeout')
        self.assertEqual(error.exception.result['status'],'behavior_not_supported')
        simulate.assert_not_called()

    def test_absolute_batch_deadline_stops_before_any_vendor_process(self):
        with patch('plc_agent.tia.subprocess.Popen') as launch:
            result=tia.simulate_scl(self.source,tia_tests.harness(self.task),self.config,
                                    directory=self.root/'expired',deadline=0)
        self.assertEqual(result['status'],'timeout')
        launch.assert_not_called()

    def test_simulator_request_excludes_expected_and_uses_disposable_project(self):
        plan=tia_tests.harness(self.task)
        bridge_exited=[]
        def launch(command,stdout,stderr,shell):
            self.assertFalse(shell)
            req=json.loads(Path(command[2]).read_text(encoding='utf-8'))
            self.assertNotIn('expected',json.dumps(req));self.assertNotEqual(req['project'],self.config['template_project'])
            if command[1]=='--prepare-simulation':self.prepare_receipt(command,stdout)
            else:
                self.assertEqual(command[1],'--run-simulation-card');self.assertTrue(bridge_exited)
                receipt=self.response();stdout.write(('WB_RESULT_JSON='+json.dumps(receipt)+'\n').encode());stdout.flush()
            class Process:
                returncode=0
                def poll(self):bridge_exited.append(True);return 0
            return Process()
        with patch('plc_agent.tia.subprocess.Popen',side_effect=launch):
            result=tia.simulate_scl(self.source,plan,self.config,directory=self.root/'boundary')
        self.assertEqual(result['status'],'simulation_completed')
        self.assertEqual(Path(self.config['template_project']).read_bytes(),b'project')

    def test_runtime_host_change_invalidates_native_evidence(self):
        def launch(command,stdout,stderr,shell):
            request=json.loads(Path(command[2]).read_text(encoding='utf-8'))
            self.assertEqual(request['execution_fingerprint']['runtime_host_sha256'],
                             hashlib.sha256(b'runtime-fixture').hexdigest())
            (self.root/'TiaRuntime.exe').write_bytes(b'changed-runtime')
            self.prepare_receipt(command,stdout)
            class Process:
                returncode=0
                def poll(self):return 0
            return Process()
        with patch('plc_agent.tia.subprocess.Popen',side_effect=launch):
            result=tia.simulate_scl(self.source,tia_tests.harness(self.task),self.config,
                                    directory=self.root/'changed-host')
        self.assertEqual(result['status'],'stale_evidence')

    def test_startup_timeout_keeps_vendor_failure_and_explains_conditional_trial_recovery(self):
        failure='PowerOn(UInt32): Error Code: -11, Timeout'
        def launch(command,stdout,stderr,shell):
            prepare=command[1]=='--prepare-simulation'
            if prepare:self.prepare_receipt(command,stdout)
            else:
                stdout.write(('WB_RESULT_JSON='+json.dumps({'status':'simulation_error','message':failure})+'\n').encode())
                stdout.flush()
            class Process:
                returncode=0 if prepare else 2
                def poll(self):return 0
            return Process()
        with patch('plc_agent.tia.subprocess.Popen',side_effect=launch) as native:
            result=tia.simulate_scl(self.source,tia_tests.harness(self.task),self.config,
                                    directory=self.root/'startup-timeout')
        self.assertEqual(result['status'],'simulation_error')
        self.assertTrue(result['message'].startswith(failure))
        self.assertIn('若出现',result['recovery_hint'])
        self.assertIn('OK',result['recovery_hint'])
        self.assertEqual(native.call_count,2)

    def test_prepared_status_without_bound_manifest_never_starts_runtime(self):
        def launch(command,stdout,stderr,shell):
            self.assertEqual(command[1],'--prepare-simulation')
            stdout.write(b'WB_RESULT_JSON={"status":"simulation_prepared"}\n');stdout.flush()
            class Process:
                returncode=0
                def poll(self):return 0
            return Process()
        with patch('plc_agent.tia.subprocess.Popen',side_effect=launch) as native:
            result=tia.simulate_scl(self.source,tia_tests.harness(self.task),self.config,directory=self.root/'missing-handoff')
        self.assertEqual(result['status'],'bridge_protocol_error');native.assert_called_once()

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
