"""Counterexamples for time-adapter and normalization regressions."""
import unittest
from plc_agent.bank_contracts import questions, scenarios
from plc_agent.duration_checks import cases
from plc_agent.workflow import normalize_candidate
from experiments.public20.run import FORMAL_SETTINGS, SETTINGS
from experiments.public20.service import normalize_response_items, PRICES


class HandoffProtocolTests(unittest.TestCase):
    def test_invocation_intervals_agree_with_clock_in_q04_and_q12_hold_cases(self):
        for qid in ('04','12'):
            question=next(q for q in questions() if q['id']==qid)
            for case in scenarios(question)+cases(qid):
                rows=case['trace']
                for previous,row in zip(rows,rows[1:]):
                    self.assertEqual(row['inputs']['CycleTime'],row['time_ms']-previous['time_ms'],(qid,case['name']))

    def test_packaging_preserves_strings_and_comments_with_fake_tokens(self):
        q={'id':'03'}
        for value in ("'VAR END_VAR'", "'END_FUNCTION_BLOCK'", "'(*'"):
            code='FUNCTION_BLOCK Q03\nVAR s:STRING; END_VAR\ns := '+value+';\nEND_FUNCTION_BLOCK'
            self.assertEqual(normalize_candidate(code,q),code)
        code="FUNCTION_BLOCK Q03\nVAR END_VAR\n(* END_FUNCTION_BLOCK *)\nx:=1;"
        fixed=normalize_candidate(code,q)
        self.assertIn('(* END_FUNCTION_BLOCK *)',fixed)
        self.assertTrue(fixed.endswith('\nEND_FUNCTION_BLOCK'))

    def test_unfinished_comment_cannot_hide_an_unfinished_body(self):
        code='FUNCTION_BLOCK Q03\nVAR x:INT; END_VAR\n(* x:=2; END_FUNCTION_BLOCK'
        self.assertEqual(normalize_candidate(code,{'id':'03'}),code)
        code='FUNCTION_BLOCK Q03\nEND_FUNCTION_BLOCK\n(* trailing explanation'
        self.assertEqual(normalize_candidate(code,{'id':'03'}),code+'\n*)')

    def test_parallel_tool_batch_keeps_genuine_reasoning_and_all_results(self):
        r={'type':'reasoning','summary':[{'type':'summary_text','text':'synthetic fixture reasoning'}]}
        a={'type':'function_call','call_id':'a','name':'shell','arguments':'{}'}
        b={**a,'call_id':'b'}
        msg={'type':'message','role':'assistant','content':'checking'}
        oa={'type':'function_call_output','call_id':'a','output':'real result a'}
        ob={**oa,'call_id':'b','output':'real result b'}
        self.assertEqual(normalize_response_items([r,a,b,msg,oa,ob]),[r,msg,a,b,oa,ob])

    def test_formal_matrix_has_two_frameworks_for_each_fixed_model_and_correct_max_price(self):
        self.assertEqual(len(FORMAL_SETTINGS),4)
        selected=[SETTINGS[n] for n in FORMAL_SETTINGS]
        for model in ('deepseek-flash','qwen3.8-max'):
            self.assertEqual({x['framework'] for x in selected if x['model']==model},{'self','codex'})
        self.assertEqual(PRICES['qwen3.8-max'],{'input':12.,'cached':1.5,'output':36.})
