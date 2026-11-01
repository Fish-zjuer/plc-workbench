"""Counterexamples for time-adapter and normalization regressions."""
import unittest
from plc_agent.bank_contracts import questions, scenarios
from optional_local_tests.duration_checks import cases
from plc_agent.legacy.workflow import normalize_candidate


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
