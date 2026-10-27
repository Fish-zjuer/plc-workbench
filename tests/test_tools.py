from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from plc_probe.backend import BackendError, compile_source, run_batch
from plc_probe.budget_study import cap_scans
from plc_probe.config import ROOT, cache_dir
from plc_probe.contracts import validate_trace
from plc_probe.fixtures import prepare_fixtures
from plc_probe.scenarios import generate
from plc_probe.server import call_tool
from plc_probe.tools import compare, minimize_failure, replay


class ExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prepare_fixtures()

    def test_two_independent_styles_per_contract_pass(self):
        for profile in ("motor", "blower", "edges"):
            scenarios = generate(profile, "focused") + generate(profile, "random", 2031)
            for variant in ("correct", "alternative"):
                with self.subTest(profile=profile, variant=variant):
                    actual = run_batch(compile_source(ROOT / "examples" / profile / (variant + ".st"), profile), scenarios)
                    self.assertTrue(all(r["status"] == "pass" for r in actual))

    def test_exact_timer_boundary_and_restart_are_not_off_by_one(self):
        a = compile_source(ROOT / "examples/blower/correct.st", "blower")
        times = [0, 4999, 5000, 5001, 6000, 6001, 11000, 11001]
        trace = [{"time_ms": t, "inputs": {"DO_LOW": int(t != 6000), "AERATION_E_STOP_NC": 1}} for t in times]
        result = run_batch(a, [{"name": "handwritten_boundaries", "trace": trace}])[0]
        self.assertEqual([r["actual"]["BLOWER_RUN"] for r in result["rows"]], [0, 0, 1, 1, 0, 0, 0, 1])
        self.assertEqual([r["actual"]["AERATION_BLOWER_CYCLE_COUNT"] for r in result["rows"]], [0, 0, 1, 1, 1, 1, 1, 2])

    def test_full_word_edges_count_32_not_16(self):
        a = compile_source(ROOT / "examples/edges/correct.st", "edges")
        trace = [{"time_ms": i, "inputs": {"value": value}} for i, value in enumerate([0, 0xFFFFFFFF, 0xFFFFFFFF, 0])]
        result = run_batch(a, [{"name": "all_bits", "trace": trace}])[0]
        self.assertEqual(result["rows"][1]["actual"]["noOfRisingBits"], 32)
        self.assertEqual(result["rows"][2]["actual"]["hasChanged"], 0)
        self.assertEqual(result["rows"][3]["actual"]["noOfFallingBits"], 32)

    def test_normal_path_can_miss_timer_reset_bug(self):
        a = compile_source(ROOT / "examples/blower/mutants/timer_not_reset.st", "blower")
        self.assertTrue(all(r["status"] == "pass" for r in run_batch(a, generate("blower", "normal"))))
        self.assertTrue(any(r["status"] == "fail" for r in run_batch(a, generate("blower", "focused"))))

    def test_reduced_failure_replays_and_fixed_source_passes(self):
        bad = ROOT / "examples/blower/mutants/timer_not_reset.st"
        a = compile_source(bad, "blower")
        failure = next(r for r in run_batch(a, generate("blower", "focused")) if r["status"] == "fail")
        record = minimize_failure(a, failure)
        self.assertLess(record["minimized_scans"], record["original_failure_prefix_scans"])
        self.assertTrue(replay(str(bad), record)["reproduced"])
        fixed = replay(str(ROOT / "examples/blower/correct.st"), record)
        self.assertFalse(fixed["reproduced"])
        self.assertEqual(fixed["status"], "pass")
        self.assertFalse(fixed["source_matches_record"])

    def test_regression_and_repair_directions(self):
        good = str(ROOT / "examples/motor/correct.st")
        bad = str(ROOT / "examples/motor/mutants/start_over_stop.st")
        self.assertGreater(compare(good, bad, "motor")["new_failures"], 0)
        repaired = compare(bad, good, "motor")
        self.assertGreater(repaired["resolved_failures"], 0)
        self.assertEqual(repaired["new_failures"], 0)

    def test_compile_errors_are_not_behavior_passes(self):
        with tempfile.TemporaryDirectory(dir=cache_dir()) as directory:
            path = Path(directory) / "broken.st"
            path.write_text("FUNCTION_BLOCK MotorControl\nMotor := unknown_name;\nEND_FUNCTION_BLOCK", encoding="utf-8")
            with self.assertRaises(BackendError) as caught:
                compile_source(path, "motor")
            self.assertEqual(caught.exception.result["status"], "compile_error")

    def test_hanging_program_is_killed_and_is_not_a_test_failure(self):
        with tempfile.TemporaryDirectory(dir=cache_dir()) as directory:
            path = Path(directory) / "infinite.st"
            good = (ROOT / "examples/motor/correct.st").read_text(encoding="utf-8")
            path.write_text(good.replace("IF StopBtn OR EStop THEN", "WHILE TRUE DO\n    Motor := FALSE;\nEND_WHILE;\nIF StopBtn OR EStop THEN"), encoding="utf-8")
            artifact = compile_source(path, "motor")
            with self.assertRaises(BackendError) as caught:
                run_batch(artifact, generate("motor", "normal"), timeout_seconds=0.25)
            self.assertEqual(caught.exception.result["status"], "timeout")

    def test_string_transport_preserves_spaces_quotes_and_backslashes(self):
        # Transport-only stub, deliberately not an implementation of the IPv4 task.
        source = """FUNCTION_BLOCK IPv4Parser
VAR_INPUT ipText : STRING(254); END_VAR
VAR_OUTPUT ipValue : UDINT; END_VAR
ipValue := INT_TO_UDINT(LEN(ipText));
END_FUNCTION_BLOCK"""
        values = ["", "1.2.3.4", " 1.2.3.4 ", '1.2.3."4', "1.2.3.\\4"]
        with tempfile.TemporaryDirectory(dir=cache_dir()) as directory:
            path = Path(directory) / "transport.st"
            path.write_text(source, encoding="utf-8")
            a = compile_source(path, "ipv4")
            result = run_batch(a, [{"name": "string_transport", "trace": [
                {"time_ms": i, "inputs": {"ipText": value}} for i, value in enumerate(values)
            ]}])[0]
            self.assertEqual([r["actual"]["ipValue"] for r in result["rows"]], [len(value) for value in values])

    def test_float_and_signed_integer_transport_is_not_truncated(self):
        # Transport-only stub; checks the native bridge rather than the task oracle.
        source = """FUNCTION_BLOCK MovingAverage
VAR_INPUT cyclicExecution : BOOL; trigger : BOOL; value : LREAL; windowSize : INT; reset : BOOL; END_VAR
VAR_OUTPUT average : LREAL; windowSizeReached : BOOL; error : BOOL; status : WORD; END_VAR
average := value + INT_TO_LREAL(windowSize);
END_FUNCTION_BLOCK"""
        with tempfile.TemporaryDirectory(dir=cache_dir()) as directory:
            path = Path(directory) / "transport.st"
            path.write_text(source, encoding="utf-8")
            a = compile_source(path, "moving_average")
            result = run_batch(a, [{"name": "float_transport", "trace": [{"time_ms": 0, "inputs": {
                "cyclicExecution": 0, "trigger": 0, "value": -3.125, "windowSize": -2, "reset": 0,
            }}]}])[0]
            self.assertEqual(result["rows"][0]["actual"]["average"], -5.125)


class InterfaceTests(unittest.TestCase):
    def test_equal_budget_is_exact_and_does_not_invent_samples(self):
        pool = generate("motor", "normal")
        capped = cap_scans(pool, 12)
        self.assertEqual(sum(len(s["trace"]) for s in capped), 12)
        for item in capped:
            self.assertEqual(item["trace"], pool[0]["trace"][:len(item["trace"])])
        with self.assertRaises(ValueError):
            cap_scans([{"trace": []}], 10)

    def test_trace_rejects_missing_inputs_out_of_range_and_clock_reversal(self):
        bad = [
            [{"time_ms": 0, "inputs": {"StartBtn": 0}}],
            [{"time_ms": 0, "inputs": {"StartBtn": 2, "StopBtn": 0, "EStop": 0}}],
            [{"time_ms": 2, "inputs": {"value": 0}}, {"time_ms": 1, "inputs": {"value": 0}}],
        ]
        for index, trace in enumerate(bad):
            with self.subTest(index=index), self.assertRaises(ValueError):
                validate_trace("edges" if index == 2 else "motor", trace)

    def test_seeded_generation_is_reproducible(self):
        self.assertEqual(generate("blower", "random", 7), generate("blower", "random", 7))
        self.assertNotEqual(generate("blower", "random", 7), generate("blower", "random", 8))

    def test_first_edge_sample_policy_is_not_invented(self):
        a = compile_source(ROOT / "examples/edges/correct.st", "edges")
        trace = [{"time_ms": 0, "inputs": {"value": 0xFFFFFFFF}}]
        row = run_batch(a, [{"name": "unspecified_first_sample", "trace": trace}])[0]["rows"][0]
        self.assertEqual(row["expected"], {})
        self.assertEqual(row["violations"], [])

    def test_agent_result_is_compact_with_full_evidence_saved(self):
        result = call_tool("plc_probe", {"source": str(ROOT / "examples/motor/correct.st"), "profile": "motor"})
        self.assertNotIn("cases", result["summary"])
        self.assertEqual(result["summary"]["scenarios"], 512)
        self.assertTrue(Path(result["full_evidence_path"]).is_file())
        self.assertLess(len(json.dumps(result)), 2500)

    def test_mcp_stdio_handshake_tool_call_and_error_response(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "plc_probe", "arguments": {
                "source": str(ROOT / "examples/motor/mutants/start_over_stop.st"), "profile": "motor", "shrink_budget": 20}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "plc_probe", "arguments": {"profile": "unknown"}}},
        ]
        process = subprocess.run([sys.executable, "-B", str(ROOT / "agent_tools.py")],
                                 input="\n".join(json.dumps(r) for r in requests) + "\n",
                                 capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        responses = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual([r["id"] for r in responses], [1, 2, 3, 4])
        self.assertEqual(len(responses[1]["result"]["tools"]), 7)
        # Detecting a program defect is a successful tool invocation, not a tool failure.
        self.assertFalse(responses[2]["result"]["isError"])
        payload = json.loads(responses[2]["result"]["content"][0]["text"])
        self.assertEqual(payload["status"], "fail")
        self.assertTrue(responses[3]["result"]["isError"])


if __name__ == "__main__":
    unittest.main()
