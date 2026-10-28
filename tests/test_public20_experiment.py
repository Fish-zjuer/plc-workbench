from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from experiments.public20.service import ExperimentService, normalize_usage, normalize_response_items
from experiments.public20.run import safe_name, SETTINGS
from plc_agent.q20_contract import scenarios
from plc_agent.bank_runner import response_window_failures


class FakePipeline:
    def __init__(self, *_):
        pass

    def preflight(self, _):
        return None

    def evaluate(self, source, qid):
        return {'status':'pass','question_id':qid,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                'stages':{'codesys':{'status':'pass'},'behavior':{'status':'pass'}}}


class Public20ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        p=patch('experiments.public20.service.ValidationPipeline',FakePipeline);p.start();self.addCleanup(p.stop)
        p=patch.object(ExperimentService,'current_identity',return_value={'evaluation_fingerprint':'frozen','validation_fingerprint':'target'});p.start();self.addCleanup(p.stop)
        self.service=ExperimentService(self.root,10)

    def task(self):
        return self.service.register({'question_id':'03','setting':'codex-deepseek','model':'deepseek-flash',
                                      'timeout':900,'evidence':str(self.root/'task')})

    def test_same_source_recheck_does_not_spend_another_version_and_raw_bytes_are_preserved(self):
        task=self.task();raw=b'FUNCTION_BLOCK Q03\r\nEND_FUNCTION_BLOCK\r\n'
        a=self.service.check(task['task_id'],raw);b=self.service.check(task['task_id'],raw)
        self.assertEqual(a['source_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(a,b);self.assertEqual(len(task['submissions']),1)
        self.assertEqual((self.root/'task/submissions/01/source.st').read_bytes(),raw)

    def test_initial_candidate_plus_five_repairs_are_a_hard_checker_limit(self):
        task=self.task()
        for n in range(6):self.assertEqual(self.service.check(task['task_id'],str(n).encode())['status'],'pass')
        self.assertEqual(self.service.check(task['task_id'],b'seventh')['status'],'repair_limit')
        self.assertEqual(len(task['submissions']),6)

    def test_budget_reservation_survives_restart_and_unknown_usage_does_not_become_zero(self):
        task=self.task();record=self.service.reserve(task['task_id'],{'model':'deepseek-flash','messages':[]})
        before=self.service.budget()['accounted_upper_cny'];self.assertGreater(before,0)
        self.service.settle(record,{},'deepseek-flash','transport_disconnect')
        self.assertEqual(self.service.budget()['accounted_upper_cny'],before)
        restarted=ExperimentService(self.root,10)
        self.assertEqual(restarted.budget(),self.service.budget())

    def test_reported_cache_tokens_are_charged_without_double_counting(self):
        task=self.task();r=self.service.reserve(task['task_id'],{'model':'deepseek-flash'})
        self.service.settle(r,{'input_tokens':1000,'input_tokens_details':{'cached_tokens':900},'output_tokens':100},'served')
        self.assertAlmostEqual(r['charged_cny'],(100*2+900*.04+100*8)/1e6)
        self.assertEqual(r['served_model'],'served')

    def test_expired_task_cannot_generate_or_add_new_candidate(self):
        task=self.task();task['deadline']=time.time()-1
        with self.assertRaisesRegex(ValueError,'task_timeout'):
            self.service.reserve(task['task_id'],{'model':'deepseek-flash'})
        self.assertEqual(self.service.check(task['task_id'],b'new')['status'],'task_timeout')

    def test_rejects_path_traversal_and_existing_evidence(self):
        for name in ('../other','a/b','a\\b','..'):
            with self.assertRaises(ValueError):safe_name(name)
        self.task()
        with self.assertRaises(ValueError):self.task()
        self.assertTrue({'codex-deepseek','codex-qwen','self-deepseek','self-qwen'} <= set(SETTINGS))

    def test_both_api_usage_shapes_and_missing_usage(self):
        self.assertIsNone(normalize_usage({}))
        self.assertIsNone(normalize_usage({'input_tokens':0,'output_tokens':0}))
        self.assertEqual(normalize_usage({'prompt_tokens':5,'completion_tokens':7,'prompt_cache_hit_tokens':3})['cached_input_tokens'],3)
        self.assertEqual(normalize_usage({'input_tokens':5,'output_tokens':7})['output_tokens'],7)

    def test_q20_windows_have_a_full_following_scan_and_no_kick_duration_assertion(self):
        cases=scenarios();self.assertEqual(len(cases),6)
        for case in cases:
            for w in case['response_windows']:
                self.assertEqual(w['end_scan'],w['start_scan']+1)
                self.assertLess(w['end_scan'],len(case['trace']))
            if case['name'] in ('weight_boundary_99','weight_boundary_201'):
                kicks=[w for w in case['response_windows'] if 'kick' in w['expected']]
                self.assertEqual(len(kicks),1)
                self.assertEqual(kicks[0]['expected'],{'kick':1})
                self.assertFalse(any('kick' in row['expected'] for row in case['trace']))

    def test_temporal_monitor_accepts_either_pulse_position_but_rejects_late_or_split_response(self):
        w=[{'name':'kick','start_scan':0,'end_scan':1,'expected':{'kick':1}}]
        def rows(values):return [{'time_ms':i*10,'actual':{'kick':v}} for i,v in enumerate(values)]
        self.assertFalse(response_window_failures(rows([1,0,0]),w,{'kick':'BOOL'}))
        self.assertFalse(response_window_failures(rows([0,1,0]),w,{'kick':'BOOL'}))
        self.assertTrue(response_window_failures(rows([0,0,1]),w,{'kick':'BOOL'}))
        w=[{'name':'joint','start_scan':0,'end_scan':1,'expected':{'a':1,'b':1}}]
        r=[{'time_ms':0,'actual':{'a':1,'b':0}},{'time_ms':10,'actual':{'a':0,'b':1}}]
        self.assertTrue(response_window_failures(r,w,{'a':'BOOL','b':'BOOL'}))

    def test_responses_tool_pairing_preserves_all_messages_and_all_real_results(self):
        call={'type':'function_call','call_id':'a','name':'shell','arguments':'{}'}
        msg={'type':'message','role':'assistant','content':'checking'}
        output={'type':'function_call_output','call_id':'a','output':'path policy rejected'}
        items=[call,msg,output]
        self.assertEqual(normalize_response_items(items),[msg,call,output])
        self.assertEqual(items,[call,msg,output])
        with self.assertRaisesRegex(ValueError,'missing_real_tool_output'):
            normalize_response_items([call,msg])

    def test_parallel_and_repeated_ids_keep_the_matching_tool_results(self):
        a={'type':'function_call','call_id':'a','arguments':'1'}
        b={'type':'function_call','call_id':'b','arguments':'2'}
        oa={'type':'function_call_output','call_id':'a','output':'first'}
        ob={'type':'function_call_output','call_id':'b','output':'second'}
        a2={'type':'function_call','call_id':'a','arguments':'3'}
        oa2={'type':'function_call_output','call_id':'a','output':'third'}
        self.assertEqual(normalize_response_items([a,b,oa,ob,a2,oa2]),[a,b,oa,ob,a2,oa2])


if __name__=='__main__':unittest.main()
