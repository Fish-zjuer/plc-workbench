from pathlib import Path
import unittest
import tempfile

from plc_agent.bank_contracts import questions
from plc_agent.codesys_bank import caller, read_receipt, split_units, summarize
from plc_agent.config import ROOT


class CodesysBankTests(unittest.TestCase):
    def test_comments_and_strings_cannot_create_or_terminate_units(self):
        text = """(* TYPE Fake : INT; END_TYPE (* nested *) *)
TYPE Actual : STRUCT n : INT; END_STRUCT END_TYPE
FUNCTION_BLOCK Main
VAR s : STRING := 'END_VAR END_FUNCTION_BLOCK'; END_VAR
s := 'TYPE NotAType'; // END_FUNCTION_BLOCK
END_FUNCTION_BLOCK"""
        units = split_units(text)
        self.assertEqual([(u['kind'], u['name']) for u in units], [('TYPE', 'Actual'), ('FUNCTION_BLOCK', 'Main')])
        self.assertIn("s := 'TYPE NotAType';", units[1]['implementation'])
        self.assertIn("'END_VAR END_FUNCTION_BLOCK'", units[1]['declaration'])

    def test_unrecognized_top_level_code_is_not_silently_dropped(self):
        with self.assertRaises(ValueError):
            split_units('UNSUPPORTED TOP LEVEL;\nFUNCTION_BLOCK A\nVAR x : INT; END_VAR\nx := 1;\nEND_FUNCTION_BLOCK')

    def test_all_current_sources_import_and_keep_actual_implementation(self):
        for question in questions():
            source = (ROOT / 'experiments/backend_r4/tasks' / question['id'] / 'final.st').read_text(encoding='utf-8')
            with self.subTest(question=question['id']):
                units = split_units(source)
                self.assertTrue(any(u['kind'] == 'FUNCTION_BLOCK' for u in units))
                for unit in units:
                    self.assertIn(unit['declaration'], source)
                    if 'implementation' in unit:
                        self.assertIn(unit['declaration'] + unit['implementation'], source)

    def test_open_array_is_bound_without_rewriting_candidate_interface(self):
        q = next(q for q in questions() if q['id'] == '08')
        driver = caller(q)
        self.assertIn('ARRAY[0..2] OF ST_AnalogChannel', driver['declaration'])
        self.assertNotIn('ARRAY[*]', driver['declaration'])
        self.assertIn('channels', driver['implementation'].lower())

    def test_no_compiler_receipts_or_bad_environment_cannot_inflate_rate(self):
        env = {'status': 'pass', 'negative_control': {'rejected': True}}
        result = summarize([{'status': 'pass'}, {'status': 'compile_error'}, {'status': 'tool_error'}], env)
        self.assertEqual(result['compilation_pass_rate'], 1 / 3)
        self.assertEqual(result['not_measured'], 1)
        self.assertIsNone(summarize([{'status': 'pass'}], {})['compilation_pass_rate'])

    def test_partial_receipt_is_a_tool_error_instead_of_a_pass_or_crash(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'result.json'
            p.write_text('{"status":', encoding='utf-8')
            self.assertEqual(read_receipt(p)['status'], 'invalid_receipt')
