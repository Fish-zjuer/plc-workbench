"""Protocol, isolation, cancellation and repair tests; no Siemens/model dependency."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from plc_agent import tia, tia_workflow
from plc_agent.config import ModelConfig
from plc_agent.provider import Cancelled, ProviderError

SAMPLE = Path(__file__).resolve().parents[1]/'examples/tia/MotorControl.scl'
TASK = {'id': 'DEMO', 'title': 'Motor', 'block': 'WB_MotorControl', 'requirements': 'Stop has priority.',
        'dataset_sha256': 'frozen', 'scenarios': [{'expected': 'SECRET_EXPECTED'}],
        'interface': [{'direction': 'Input', 'name': n, 'type': 'BOOL'} for n in ('StartBtn', 'StopBtn', 'EStop')]+
                     [{'direction': 'Output', 'name': 'Motor', 'type': 'BOOL'}]}


class FakeProvider:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.messages = []
        self.metrics = []
        self.cancel_event = threading.Event()
    def complete(self, messages):
        self.messages.append(messages)
        self.metrics.append({'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}})
        return {'text': json.dumps({'code': next(self.answers), 'summary': 'repair'})}


class TiaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        template = self.root/'template'
        template.mkdir()
        (template/'test.ap21').write_bytes(b'template')
        (template/'System').mkdir()
        (template/'System'/'sidecar.bin').write_bytes(b'sidecar')
        (self.root/'bridge.exe').write_bytes(b'fixture')
        self.config = {'executable': str(self.root/'bridge.exe'), 'template_project': str(template/'test.ap21'), 'timeout_seconds': 5}
        self.code = SAMPLE.read_text(encoding='utf-8-sig')
    def tearDown(self):
        self.tmp.cleanup()

    def test_discovers_x64_api_in_v8_common_files_installation(self):
        api=self.root/'Common Files'/'Siemens'/'PLCSIMADV'/'API'/'8.0'/'Siemens.Simatic.Simulation.Runtime.Api.x64.dll'
        api.parent.mkdir(parents=True);api.write_bytes(b'fixture')
        with patch.dict('os.environ',{'ProgramFiles':str(self.root/'PF'),
                'ProgramFiles(x86)':str(self.root/'PF86'),'CommonProgramFiles':str(self.root/'CF'),
                'CommonProgramFiles(x86)':str(self.root/'Common Files')}):
            self.assertEqual(tia.discover_simulation_api(),str(api))

    def test_protocol_rejects_missing_duplicate_malformed_and_false_success(self):
        valid = 'WB_RESULT_JSON='+json.dumps({'status': 'compile_passed', 'errors': 0})
        self.assertEqual(tia.parse_result('\ufeff'+valid, 0)['status'], 'compile_passed')
        for stdout, rc in [('',0),(valid+'\n'+valid,0),('WB_RESULT_JSON={',0),(valid,1),
                           ('WB_RESULT_JSON={"status":"compile_passed","errors":2}',0)]:
            self.assertEqual(tia.parse_result(stdout,rc)['status'], 'bridge_protocol_error')

    def test_real_subprocess_boundary_copies_sidecars_and_retains_diagnostics(self):
        def launch(command, stdout, stderr, shell):
            self.assertFalse(shell)
            copied = Path(command[1])
            self.assertNotEqual(copied, Path(self.config['template_project']))
            self.assertEqual((copied.parent/'System'/'sidecar.bin').read_bytes(),b'sidecar')
            copied.write_bytes(b'changed copy')
            stdout.write(b'noise\nWB_RESULT_JSON={"status":"compile_passed","errors":0}\n')
            stdout.flush()
            class Process:
                returncode = 0
                def poll(self): return 0
            return Process()
        with patch('plc_agent.tia.subprocess.Popen', side_effect=launch):
            result = tia.compile_scl(SAMPLE, self.config, directory=self.root/'evidence')
        self.assertEqual(result['target_compile'], 'passed')
        self.assertFalse(result['behavior_tested'])
        self.assertEqual(Path(self.config['template_project']).read_bytes(), b'template')
        self.assertTrue((self.root/'evidence'/'stdout.txt').is_file())

    def test_timeout_and_cancel_stop_only_launched_process(self):
        class Process:
            returncode = None
            def poll(self): return None
        with patch('plc_agent.tia.subprocess.Popen', return_value=Process()), \
             patch('plc_agent.tia.time.monotonic', side_effect=[0, 10, 11]), \
             patch('plc_agent.tia.time.sleep'), patch('plc_agent.tia._stop') as stop:
            result = tia.compile_scl(SAMPLE, self.config, directory=self.root/'timeout')
            self.assertEqual(result['status'], 'timeout')
            self.assertEqual(result['target_compile'], 'not_executed')
            stop.assert_called_once()
        event = threading.Event()
        with patch('plc_agent.tia.subprocess.Popen', return_value=Process()), \
             patch.object(event, 'wait', return_value=True), patch('plc_agent.tia._stop') as stop:
            with self.assertRaises(Cancelled):
                tia.compile_scl(SAMPLE, self.config, directory=self.root/'cancel', cancel_event=event)
            stop.assert_called_once()

    def test_frozen_interface_and_siemens_packaging(self):
        tia_workflow.validate_scl(self.code, TASK)
        for code in [self.code.replace('Motor : Bool','Other : Bool'),
                     self.code.replace('END_FUNCTION_BLOCK',''), self.code.replace('BEGIN','')]:
            with self.assertRaises(ValueError): tia_workflow.validate_scl(code, TASK)
        string_task = {**TASK, 'interface': [{**p, 'type': 'STRING(12)'} if p['name']=='Motor' else p for p in TASK['interface']]}
        tia_workflow.validate_scl(self.code.replace('Motor : Bool','Motor : STRING[12]'),string_task)

    def test_real_diagnostic_flows_to_repair_without_expected_data(self):
        bad = self.code.replace('#Motor := TRUE', '#Undefined := TRUE')
        provider = FakeProvider([bad, self.code])
        failure = {'status': 'generation_failed', 'message': 'Siemens: Undefined tag', 'target_compile': 'failed'}
        success = {'status': 'compile_passed', 'target_compile': 'passed', 'behavior_tested': False}
        with patch('plc_agent.tia.compile_scl', side_effect=[failure,success]) as compile_scl:
            result = tia_workflow.run(TASK,self.root/'candidate.scl',self.root/'run',ModelConfig(),
                                      vendor_config=self.config,provider=provider,notify=lambda _:None)
        self.assertEqual(result['status'],'compile_passed')
        self.assertEqual(compile_scl.call_count,2)
        self.assertEqual(result['model_calls'],2)
        self.assertEqual(result['token_usage']['total_tokens'],60)
        payload = json.loads(provider.messages[1][1]['content'])
        self.assertEqual(payload['actual_failure']['message'],'Siemens: Undefined tag')
        self.assertNotIn('SECRET_EXPECTED',json.dumps(provider.messages))
        self.assertNotIn('STruC++',payload['backend_notes'])
        self.assertFalse(result['behavior_tested'])

    def test_infrastructure_error_stops_without_model_repair(self):
        source = self.root/'seed.scl'
        source.write_text(self.code,encoding='utf-8')
        provider = FakeProvider([])
        with patch('plc_agent.tia.compile_scl',return_value={'status':'bridge_error','target_compile':'not_executed'}):
            result=tia_workflow.run(TASK,source,self.root/'run',ModelConfig(),vendor_config=self.config,
                                    provider=provider,notify=lambda _:None)
        self.assertEqual(result['status'],'bridge_error')
        self.assertEqual(result['model_calls'],0)

    def test_failed_model_request_does_not_claim_zero_known_usage(self):
        provider = FakeProvider([])
        with patch.object(provider, 'complete', side_effect=ProviderError('HTTP 503 model_not_found')):
            result = tia_workflow.run(TASK,self.root/'candidate.scl',self.root/'run',ModelConfig(),
                                      vendor_config=self.config,provider=provider,notify=lambda _:None)
        self.assertEqual(result['model_calls'],1)
        self.assertFalse(result['token_usage']['complete'])
        self.assertEqual(result['token_usage']['usage_calls'],0)

    def test_duplicate_failure_terminates_and_cancel_is_durable(self):
        provider = FakeProvider([self.code,self.code])
        with patch('plc_agent.tia.compile_scl',return_value={'status':'compile_failed','target_compile':'failed'}) as compile_scl:
            result=tia_workflow.run(TASK,self.root/'candidate.scl',self.root/'run',ModelConfig(),vendor_config=self.config,
                                    provider=provider,notify=lambda _:None)
        self.assertEqual(result['status'],'repeated_candidate')
        self.assertEqual(compile_scl.call_count,1)
        provider.cancel_event.set()
        result=tia_workflow.run(TASK,self.root/'candidate.scl',self.root/'cancelled',ModelConfig(),vendor_config=self.config,
                                provider=provider,notify=lambda _:None)
        self.assertEqual(result['status'],'interrupted')
        self.assertTrue((self.root/'cancelled'/'receipt.json').exists())


if __name__ == '__main__': unittest.main()
