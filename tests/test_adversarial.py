from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from plc_probe.adversarial import review, validate_proposals
from plc_probe.backend import BackendError
from plc_probe.config import ROOT, cache_dir, save_json
from plc_probe.fixtures import prepare_fixtures
from plc_probe.server import call_tool
from plc_probe.model_evaluation import evaluate


class AdversarialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prepare_fixtures()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=cache_dir())
        self.directory = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def plan(self, variant="mutants/start_over_stop", expected=0):
        source = ROOT / "examples/motor" / (variant + ".st")
        return {"schema": "plc-probe-review-v1", "reviewer": {"model": "test_fixture"},
                "candidates": [{"profile": "motor", "source": str(source),
                                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}],
                "findings": [{"id": "TEST-1", "profile": "motor", "title": "Simultaneous start and stop",
                              "claim": "Stop must dominate", "scope": "specified",
                              "requirement_basis": "Stop has priority", "rationale": "Exercise conflicting requests",
                              "scenario": {"name": "conflicting_buttons", "trace": [{"time_ms": 0, "inputs": {
                                  "StartBtn": 1, "StopBtn": 1, "EStop": 0}}]},
                              "assertions": [{"scan": 0, "output": "Motor", "expected": expected}]}]}

    def execute(self, plan, decision="accept_requirement", mcp=False):
        proposals = self.directory / "proposals.json"
        save_json(proposals, plan)
        kwargs = {"proposals_path": str(proposals)}
        if decision:
            adjudication = self.directory / "adjudication.json"
            save_json(adjudication, {"schema": "plc-probe-adjudication-v1", "decisions": [
                {"id": "TEST-1", "decision": decision, "reason": "Synthetic fixture: known stop-priority contract."}]})
            kwargs["adjudication_path"] = str(adjudication)
        return call_tool("plc_adversarial_review", kwargs) if mcp else review(**kwargs)

    def test_known_fault_is_confirmed_by_two_fresh_replays(self):
        result = self.execute(self.plan())
        self.assertEqual(result["status"], "fail")
        finding = result["findings"][0]
        self.assertEqual(finding["status"], "confirmed_requirement_violation")
        evidence = json.loads(Path(finding["evidence_path"]).read_text(encoding="utf-8"))
        self.assertEqual(len(evidence["runs"]), 2)
        self.assertEqual([r["rows"][0]["actual"]["Motor"] for r in evidence["runs"]], [1, 1])
        self.assertTrue(finding["stable"])

    def test_correct_source_refutes_hypothesis(self):
        result = self.execute(self.plan("correct"))
        self.assertEqual(result["status"], "no_confirmed_counterexample")
        self.assertEqual(result["findings"][0]["status"], "not_reproduced")

    def test_contract_dependent_failure_stays_distinct_from_requirement_failure(self):
        result = self.execute(self.plan(), "accept_contract")
        self.assertEqual(result["findings"][0]["status"], "confirmed_contract_violation")

    def test_ambiguity_does_not_become_a_bug_despite_mismatch(self):
        result = self.execute(self.plan(), "ambiguous")
        self.assertEqual(result["counts"]["confirmed"], 0)
        self.assertTrue(result["findings"][0]["assertion_mismatch_reproduced"])
        self.assertEqual(result["findings"][0]["status"], "needs_requirement_clarification")

    def test_model_cannot_approve_its_own_hypothesis(self):
        result = self.execute(self.plan(), None)
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["findings"][0]["status"], "pending_adjudication")

    def test_assertion_disagreement_with_frozen_oracle_is_flagged(self):
        result = self.execute(self.plan("correct", expected=1))
        self.assertTrue(result["findings"][0]["assertion_mismatch_reproduced"])
        self.assertEqual(result["findings"][0]["status"], "oracle_disagreement")
        self.assertEqual(result["counts"]["confirmed"], 0)

    def test_stale_source_is_rejected_before_any_compile(self):
        plan = self.plan()
        plan["candidates"][0]["source_sha256"] = "0" * 64
        with patch("plc_probe.adversarial.compile_source") as compiler:
            with self.assertRaisesRegex(ValueError, "Stale source"):
                self.execute(plan)
            compiler.assert_not_called()

    def test_bad_domain_unknown_output_and_nonfinite_assertions_rejected(self):
        base = self.plan()
        for mutation in ("domain", "output", "nan", "duplicate", "timestamp"):
            plan = copy.deepcopy(base)
            finding = plan["findings"][0]
            if mutation == "domain":
                finding["scenario"]["trace"][0]["inputs"]["StartBtn"] = 2
            elif mutation == "output":
                finding["assertions"][0]["output"] = "imaginary"
            elif mutation == "nan":
                finding["assertions"][0]["expected"] = float("nan")
            elif mutation == "duplicate":
                plan["findings"].append(copy.deepcopy(finding))
            else:
                finding["scenario"]["trace"].append(copy.deepcopy(finding["scenario"]["trace"][0]))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_proposals(plan)

    def test_backend_failure_is_not_a_program_defect(self):
        with patch("plc_probe.adversarial.compile_source", side_effect=BackendError({"status": "compile_error"})):
            result = self.execute(self.plan())
        self.assertEqual(result["findings"][0]["status"], "backend_error")
        self.assertEqual(result["counts"]["confirmed"], 0)

    def test_new_mcp_tool_returns_saved_evidence(self):
        result = self.execute(self.plan(), mcp=True)
        self.assertEqual(result["counts"]["confirmed"], 1)
        self.assertTrue(Path(result["full_evidence_path"]).is_file())
        self.assertTrue(Path(result["report_path"]).is_file())

    def test_wrong_generation_stage_cannot_use_unrelated_review_manifest(self):
        proposals = self.directory / "proposals.json"
        save_json(proposals, self.plan())
        with patch("plc_probe.model_evaluation.compile_source") as compiler:
            with self.assertRaisesRegex(ValueError, "evaluated generation stage"):
                evaluate("repair_2", proposals_path=str(proposals))
            compiler.assert_not_called()

    def test_report_cannot_overwrite_review_input(self):
        proposals = self.directory / "proposals.json"
        save_json(proposals, self.plan())
        with self.assertRaisesRegex(ValueError, "separate"):
            review(str(proposals), output=str(proposals))

    def test_malformed_nested_objects_are_rejected(self):
        for field in ("candidates", "findings", "scenario", "assertions"):
            plan = self.plan()
            if field in ("candidates", "findings"):
                plan[field] = ["invalid"]
            elif field == "scenario":
                plan["findings"][0][field] = "invalid"
            else:
                plan["findings"][0][field] = ["invalid"]
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_proposals(plan)


if __name__ == "__main__":
    unittest.main()
