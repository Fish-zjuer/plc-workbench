import unittest
from plc_agent.q20_contract import scenarios
from plc_agent.legacy.bank_runner import response_window_failures

class Q20ContractTests(unittest.TestCase):
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
