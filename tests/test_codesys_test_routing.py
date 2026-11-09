"""CODESYS testing must never silently fall back to local execution."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from plc_agent import codesys_dataset; from plc_agent import codesys_tests; from plc_agent import dataset; from plc_agent import campaign
from plc_agent.config import ModelConfig
from plc_probe.backend import BackendError


class CodesysTestRouting(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.source=Path(self.tmp.name)/'candidate.st';self.source.write_text('fixture')
        self.task=dataset.load('CUSTOM_09')

    def evaluate(self, vendor):
        return codesys_dataset.evaluate_candidate(self.source,self.task,vendor,formal_directory=Path(self.tmp.name)/'formal')

    def test_vendor_runs_native_tests_without_local_compiler(self):
        with patch.object(codesys_dataset,'compile_dataset',return_value={'target_compile':'passed'}), \
             patch.object(codesys_tests,'evaluate',return_value={'status':'pass','test_backend':'codesys'}) as native, \
             patch.object(dataset,'evaluate',side_effect=AssertionError('Local execution forbidden')), \
             patch('plc_agent.dataset_formal.attach',side_effect=lambda result,*a,**k:result):
            result=self.evaluate({'profile':'fixture'})
        native.assert_called_once();self.assertEqual(result['test_backend'],'codesys')

    def test_failed_simulation_cannot_fall_back_or_claim_test_pass(self):
        with patch.object(codesys_dataset,'compile_dataset',return_value={'target_compile':'passed'}), \
             patch.object(codesys_tests,'evaluate',side_effect=BackendError({'status':'tool_error','message':'simulation failed'})), \
             patch.object(dataset,'evaluate',side_effect=AssertionError('Local execution forbidden')), \
             patch('plc_agent.dataset_formal.attach',side_effect=lambda result,*a,**k:result):
            result=self.evaluate({})
        self.assertEqual(result['status'],'tool_error');self.assertEqual(result['target_compile'],'passed')

    def test_optional_mode_remains_explicit(self):
        with patch.object(dataset,'evaluate',return_value={'status':'pass','test_backend':'optional_local'}) as local, \
             patch.object(codesys_tests,'evaluate',side_effect=AssertionError('Native execution forbidden')), \
             patch('plc_agent.dataset_formal.attach',side_effect=lambda result,*a,**k:result):
            result=self.evaluate(None)
        local.assert_called_once();self.assertEqual(result['target_compile'],'not_executed')

    def test_moved_local_adapters_still_load_their_shared_drivers(self):
        from optional_local_tests import dataset_backend
        for ident in ('PUBLIC_07','PUBLIC_08','PUBLIC_17','PUBLIC_18'):
            with self.subTest(ident=ident), \
                 patch.object(dataset_backend,'validate_source'), \
                 patch.object(dataset_backend,'fingerprint',return_value='fixture'), \
                 patch.object(dataset_backend,'cache_dir',return_value=Path(self.tmp.name)), \
                 patch.object(dataset_backend,'toolchain_dir',return_value=Path(self.tmp.name)):
                with self.assertRaises(BackendError) as raised:
                    dataset_backend.compile_task(self.source,dataset.load(ident))
                self.assertEqual(raised.exception.result['status'],'missing_dependency')

    def test_deleting_optional_package_does_not_affect_vendor_preflight(self):
        cfg=ModelConfig.dmxapi(model='fixture',api_key='fixture')
        with patch.object(ModelConfig,'load',return_value=cfg), \
             patch.object(campaign,'codex_path',return_value=Path('fixture.exe')), \
             patch.object(campaign.subprocess,'check_output',return_value='codex-cli 0.80.0'), \
             patch.object(campaign.codesys,'validate_config'), \
             patch('plc_agent.local_test_support.backend',side_effect=AssertionError('Optional package must not be imported')):
            result=campaign.preflight(Path(self.tmp.name),True)
        self.assertEqual(result['errors'],[]);self.assertEqual(result['test_backend'],'codesys')

    def test_open_arrays_keep_distinct_bounds_and_real_reference_bindings(self):
        plan=codesys_tests.harness(dataset.load('PUBLIC_08'))
        self.assertIn('ARRAY[-5..-5] OF INT',plan['harness_declaration'])
        self.assertIn('ARRAY[4..4] OF ST_ANALOGCHANNEL',plan['harness_declaration'])
        self.assertIn('analogValues := WB_C0_analogValues',plan['harness_body'])
        self.assertIn('channels := WB_C0_channels',plan['harness_body'])

    def test_native_timers_are_scheduled_on_runtime_clock(self):
        plan=codesys_tests.harness(dataset.load('PUBLIC_05'))
        self.assertIn('WB_Clock : TON;',plan['harness_declaration'])
        self.assertIn('WB_Clock.ET >= T#4999ms',plan['harness_body'])
        self.assertIn('TIME_TO_DINT(WB_Clock.ET)',plan['harness_body'])

    def test_recipe_inputs_use_the_declared_int_width(self):
        plan=codesys_tests.harness(dataset.load('PUBLIC_17'))
        self.assertIn('WB_C0_recipe[1].recipeID := INT#0;',plan['harness_body'])
        self.assertIn('WB_Uut0.recipeIn.recipeID := INT#7;',plan['harness_body'])
        self.assertNotIn('recipeID := DINT#',plan['harness_body'])

    def test_local_variant_abi_is_not_presented_as_vendor_execution(self):
        with self.assertRaises(BackendError) as raised:codesys_tests.harness(dataset.load('PUBLIC_18'))
        self.assertEqual(raised.exception.result['status'],'behavior_not_supported')

    def test_timer_schedule_error_is_not_a_candidate_failure(self):
        self.source.write_text('FUNCTION_BLOCK T\nVAR_INPUT Enable : BOOL; END_VAR\nVAR_OUTPUT Active : BOOL; END_VAR\nVAR timer : TON; END_VAR\nActive := Enable;\nEND_FUNCTION_BLOCK')
        task={'id':'TIMING','block':'T','dataset_sha256':'test','adapter_format':'bank_trace',
            'interface':[{'direction':'Input','name':'Enable','type':'BOOL'},{'direction':'Output','name':'Active','type':'BOOL'}],
            'scenarios':[{'name':'clock','trace':[{'time_ms':0,'inputs':{'Enable':True},'expected':{'Active':True}},
                {'time_ms':10,'inputs':{'Enable':False},'expected':{'Active':False}}]}]}
        response={'target_compile':'passed','simulation':True,'vendor_version':'fixture',
            'actual_rows':[{'Active':'TRUE'},{'Active':'FALSE'}],'actual_scan_times_ms':[0,30]}
        with patch.object(codesys_tests.codesys,'work_root',return_value=Path(self.tmp.name)), \
             patch.object(codesys_tests.codesys,'fingerprint',return_value='fixture'), \
             patch.object(codesys_tests.codesys,'invoke',return_value=response):
            result=codesys_tests.evaluate(self.source,task,{'template_project':'fixture'})
        self.assertEqual(result['status'],'behavior_not_supported')
        self.assertEqual(result['timing']['max_deviation_ms'],20)


if __name__=='__main__':unittest.main()
