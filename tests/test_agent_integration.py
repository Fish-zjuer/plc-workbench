from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from plc_agent.config import ModelConfig
from plc_agent.engine import Engine
from plc_agent.review import adjudicate, audit
from plc_agent.provider import ProviderError,Cancelled
from plc_agent.storage import Project, Session
from plc_probe.config import ROOT, cache_dir
from test_agent_core import ScriptedProvider
from test_agent_provider import LocalAPI


def message(text="", name=None, arguments=None, ident="c1"):
    content = {"content": text or None}
    if name:
        content["tool_calls"] = [{"id": ident, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]
    return (200, "application/json", json.dumps({"choices": [{"message": content, "finish_reason": "tool_calls" if name else "stop"}]}))


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=cache_dir())
        self.addCleanup(self.temp.cleanup)
        self.project = Project.create("集成", Path(self.temp.name))
        self.session = Session.create(self.project)
        self.session.data["mode"] = "execute"

    def test_actual_http_model_protocol_drives_compile_failure_repair_loop(self):
        bad = (ROOT / "examples/motor/mutants/start_over_stop.st").read_text(encoding="utf-8")
        good = (ROOT / "examples/motor/correct.st").read_text(encoding="utf-8")
        responses = [message(name="write_file", arguments={"path": "candidate.st", "content": bad}, ident="1"),
                     message(name="plc_probe", arguments={"source": "candidate.st", "profile": "motor", "shrink_budget": 10}, ident="2"),
                     message(name="write_file", arguments={"path": "candidate.st", "content": good, "expected_sha256": hashlib.sha256(bad.encode()).hexdigest()}, ident="3"),
                     message(name="plc_probe", arguments={"source": "candidate.st", "profile": "motor"}, ident="4"),
                     message(text="根据实际工具结果，修复后通过当前离线回归。")]
        with LocalAPI(responses) as api:
            engine = Engine(self.session, api.provider(stream=False).config)
            engine.run("检查停止优先级并修复")
            self.assertEqual(len(api.requests), 5)
            failure = api.requests[2]["body"]["messages"][-1]
            self.assertEqual(failure["role"], "tool")
            self.assertEqual(json.loads(failure["content"])["status"], "fail")
            self.assertEqual(json.loads(api.requests[4]["body"]["messages"][-1]["content"])["status"], "pass")
        self.assertEqual(self.session.data["status"], "idle")

    def test_independent_review_omits_author_history_and_requires_user_adjudication(self):
        source = self.project.workspace / "candidate.st"
        source.write_text((ROOT / "examples/motor/mutants/start_over_stop.st").read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        (self.project.workspace / "requirements.md").write_text("StopBtn or EStop must dominate StartBtn.", encoding="utf-8")
        cfg = ModelConfig(base_url="http://localhost:1/v1", model="custom-author", review_model="custom-reviewer")
        engine = Engine(self.session, cfg, provider=ScriptedProvider([]))
        engine.messages = [{"role": "user", "content": "AUTHOR_HISTORY_SENTINEL"}]
        finding = {"id": "ADV-001", "profile": "motor", "title": "Conflicting buttons", "claim": "Stop should dominate", "scope": "specified",
                   "requirement_basis": "StopBtn or EStop must dominate StartBtn.", "rationale": "Start branch executes first",
                   "scenario": {"name": "simultaneous", "trace": [{"time_ms": 0, "inputs": {"StartBtn": 1, "StopBtn": 1, "EStop": 0}}]},
                   "assertions": [{"scan": 0, "output": "Motor", "expected": 0}]}
        reviewer = ScriptedProvider([{"text": json.dumps({"findings": [finding]})}])
        with patch("plc_agent.review.ChatProvider", return_value=reviewer) as factory:
            result = audit(engine, "motor", "candidate.st", "requirements.md")
            self.assertEqual(factory.call_args.args[0].model, "custom-reviewer")
        self.assertNotIn("AUTHOR_HISTORY_SENTINEL", json.dumps(reviewer.requests))
        self.assertEqual(result["findings"][0]["status"], "pending_adjudication")
        round_id = Path(result["report_path"]).parent.name
        confirmed = adjudicate(engine, round_id, "ADV-001", "requirement", "题面明确规定停止优先级")
        self.assertEqual(confirmed["findings"][0]["status"], "confirmed_requirement_violation")
        self.assertEqual(confirmed["counts"]["confirmed"], 1)

    def test_review_failure_and_cancellation_keep_error_receipts_and_status(self):
        source=self.project.workspace/'candidate.st'
        source.write_text((ROOT/'examples/motor/correct.st').read_text(encoding='utf-8'),encoding='utf-8')
        (self.project.workspace/'requirements.md').write_text('Stop dominates start.',encoding='utf-8')
        cfg=ModelConfig(base_url='http://localhost:1/v1',model='author')
        engine=Engine(self.session,cfg,ScriptedProvider([]))
        for error,status in [(ProviderError('injected failure'),'error'),(Cancelled('stopped'),'interrupted')]:
            with patch('plc_agent.review.ChatProvider',return_value=ScriptedProvider([error])):
                with self.assertRaises(type(error)):audit(engine,'motor','candidate.st','requirements.md')
            self.assertEqual(self.session.data['status'],status)
            self.assertEqual(engine.scoped_provider.calls,1)
        self.assertEqual(len(list((self.project.workspace/'reviews').glob('*/error.json'))),2)

    def test_oversized_review_is_archived_without_a_network_request(self):
        (self.project.workspace/'candidate.st').write_text((ROOT/'examples/motor/correct.st').read_text(encoding='utf-8'),encoding='utf-8')
        (self.project.workspace/'requirements.md').write_text('x'*50000,encoding='utf-8')
        cfg=ModelConfig(base_url='http://localhost:1/v1',model='author',context_window=8000,max_output_tokens=1024)
        engine=Engine(self.session,cfg,ScriptedProvider([]));reviewer=ScriptedProvider([])
        with patch('plc_agent.review.ChatProvider',return_value=reviewer):
            with self.assertRaisesRegex(ProviderError,'窗口'):audit(engine,'motor','candidate.st','requirements.md')
        self.assertEqual(reviewer.requests,[])
        self.assertEqual(self.session.data['status'],'error')
        self.assertTrue(list((self.project.workspace/'reviews').glob('*/packet.json')))


if __name__ == "__main__":
    unittest.main()
