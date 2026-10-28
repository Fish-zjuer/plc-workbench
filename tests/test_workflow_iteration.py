from __future__ import annotations

import unittest

from plc_agent.backend_capabilities import candidate_warnings
from plc_agent.bank_contracts import questions
from plc_agent.workflow import (
    candidate_rank,
    normalize_candidate,
    requirement_checklist,
    timing_guidance,
)


QUESTIONS = {q["id"]: q for q in questions()}


class RequirementChecklistTests(unittest.TestCase):
    def test_field_clause_is_visible(self):
        items = requirement_checklist(QUESTIONS["08"])
        joined = "\n".join(items)
        self.assertIn("channels[].enable", joined)
        self.assertIn("READ-ONLY", joined)
        self.assertIn("R2:", joined)

    def test_numbered_requirements_are_listed(self):
        items = requirement_checklist(QUESTIONS["05"])
        self.assertTrue(any(item.startswith("R1:") for item in items))
        self.assertTrue(any(item.startswith("R5:") for item in items))


class TimingGuidanceTests(unittest.TestCase):
    def test_no_cycletime_uses_ton_not_fixed_step(self):
        for qid in ("05", "10"):
            notes = "\n".join(timing_guidance(QUESTIONS[qid]))
            self.assertIn("Do not increment a fixed per-scan step", notes)
            self.assertIn("TON", notes)
            self.assertIn("one scan late", notes)

    def test_no_timing_question_gets_no_notes(self):
        self.assertEqual(timing_guidance(QUESTIONS["08"]), [])

    def test_one_shot_initialization_note(self):
        notes = "\n".join(timing_guidance(QUESTIONS["05"]))
        self.assertIn("one-shot", notes)
        self.assertIn("must not restart", notes)


class CandidateRankTests(unittest.TestCase):
    def test_order(self):
        passing = {"status": "pass"}
        behavior_fail = {"status": "fail", "stages": {"codesys": {"status": "pass"}}}
        compile_error = {"status": "compile_error", "stages": {"codesys": {"status": "compile_error"}}}
        static_error = {"status": "static_error", "stages": {"static": {"status": "fail"}}}
        self.assertGreater(candidate_rank(passing), candidate_rank(behavior_fail))
        self.assertGreater(candidate_rank(behavior_fail), candidate_rank(compile_error))
        self.assertGreater(candidate_rank(compile_error), candidate_rank(static_error))
        self.assertEqual(candidate_rank(None), 0)


class NormalizeCandidateTests(unittest.TestCase):
    def test_case_else_colon_is_removed(self):
        source = (
            "FUNCTION_BLOCK Q05\n"
            "VAR x : INT; y : INT; END_VAR\n"
            "CASE x OF\n"
            "1: y := 1;\n"
            "ELSE: y := 2;\n"
            "END_CASE;\n"
            "END_FUNCTION_BLOCK\n"
        )
        out = normalize_candidate(source, QUESTIONS["05"])
        self.assertNotIn("ELSE:", out)
        self.assertIn("ELSE y := 2;", out)

    def test_string_literal_is_untouched(self):
        source = (
            "FUNCTION_BLOCK Q05\n"
            "VAR s : STRING; END_VAR\n"
            "s := 'ELSE:';\n"
            "END_FUNCTION_BLOCK\n"
        )
        out = normalize_candidate(source, QUESTIONS["05"])
        self.assertIn("'ELSE:'", out)


class CandidateWarningTests(unittest.TestCase):
    def test_continue_is_flagged(self):
        warnings = candidate_warnings(
            "FUNCTION_BLOCK Q05 VAR x : INT; END_VAR\n"
            "FOR x := 0 TO 2 DO IF x = 1 THEN CONTINUE; END_IF END_FOR\n"
            "END_FUNCTION_BLOCK\n",
            "05",
        )
        kinds = {warning["kind"] for warning in warnings}
        self.assertIn("unsupported_continue", kinds)


if __name__ == "__main__":
    unittest.main()
