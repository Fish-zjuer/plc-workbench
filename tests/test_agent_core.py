from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from plc_agent.attachments import attach
from plc_agent.config import ModelConfig
from plc_agent.engine import Engine
from plc_agent.provider import ProviderError
from plc_agent.storage import Project, Session, atomic_json
from plc_agent.toolbox import Toolbox
from plc_probe.config import ROOT, cache_dir


class ScriptedProvider:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []
        self.cancel_event = threading.Event()

    def complete(self, messages, tools=None, on_delta=None, **kwargs):
        self.requests.append(copy.deepcopy((messages, tools)))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        if on_delta and response.get("text"):
            on_delta(response["text"])
        return {"text": "", "calls": [], "usage": {}, **response}

    def cancel(self):
        self.cancel_event.set()


def call(name, arguments, ident="test_call"):
    return {"calls": [{"id": ident, "name": name, "arguments": arguments}]}


class AgentTests(unittest.TestCase):
    def setUp(self):
        cache_dir().mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=cache_dir())
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.project = Project.create("测试项目", self.home)
        self.session = Session.create(self.project)
        self.config = ModelConfig(base_url="http://localhost:1234/v1", model="fixture-model")

    def engine(self, *responses):
        provider = ScriptedProvider(responses)
        engine = Engine(self.session, self.config, provider=provider)
        return engine, provider

    def test_plan_mode_enforced_even_if_model_requests_write(self):
        engine, provider = self.engine(call("write_file", {"path": "candidate.st", "content": "forbidden"}), {"text": "仅讨论计划"})
        engine.run("请先计划")
        self.assertFalse((self.project.workspace / "candidate.st").exists())
        self.assertIn("blocked_by_plan_mode", provider.requests[1][0][-1]["content"])
        exposed = [t["function"]["name"] for t in provider.requests[0][1]]
        self.assertNotIn("write_file", exposed)
        self.assertNotIn("plc_probe", exposed)

    def test_plan_update_is_persistent_and_only_one_active_step(self):
        tools = Toolbox(self.session)
        steps = [{"step": "解析附件", "status": "in_progress"}, {"step": "测试", "status": "pending"}]
        self.assertEqual(tools.call("update_plan", {"steps": steps})["status"], "plan_updated")
        self.assertEqual(Session.load(self.project, self.session.data["id"]).data["plan"], steps)
        self.assertEqual(tools.call("update_plan", {"steps": [steps[0], steps[0]]})["status"], "tool_error")

    def test_write_requires_fresh_hash_and_keeps_versions(self):
        self.session.data["mode"] = "execute"
        tools = Toolbox(self.session)
        first = tools.call("write_file", {"path": "code/a.st", "content": "first"})
        self.assertEqual(first["status"], "written")
        stale = tools.call("write_file", {"path": "code/a.st", "content": "second"})
        self.assertEqual(stale["status"], "tool_error")
        second = tools.call("write_file", {"path": "code/a.st", "content": "second", "expected_sha256": first["sha256"]})
        self.assertEqual(second["status"], "written")
        self.assertIn("-first", second["diff"])
        versions = list((self.project.path / "versions").glob("*.json"))
        self.assertEqual(len(versions), 2)

    def test_paths_cannot_escape_and_uploads_are_immutable(self):
        self.session.data["mode"] = "execute"
        tools = Toolbox(self.session)
        for path in ("../../outside.st", str(self.home / "outside.st"), "uploads/original.st"):
            with self.subTest(path=path):
                self.assertEqual(tools.call("write_file", {"path": path, "content": "x"})["status"], "tool_error")

    def test_unknown_arguments_and_boolean_in_place_of_line_are_rejected(self):
        tools = Toolbox(self.session)
        self.assertEqual(tools.call("list_files", {"unexpected": 1})["status"], "tool_error")
        self.assertEqual(tools.call("read_file", {"path": "a.txt", "start_line": True})["status"], "tool_error")

    def test_attach_unicode_text_docx_zip_and_original_snapshot(self):
        text = self.home / "中文 题面.txt"
        text.write_text("停止优先\n第二行", encoding="utf-8")
        records = attach(self.project, text)
        self.assertEqual(records[0]["sha256"], hashlib.sha256(text.read_bytes()).hexdigest())
        text.write_text("已修改外部原件", encoding="utf-8")
        read = Toolbox(self.session).call("read_attachment", {"attachment_id": records[0]["id"]})
        self.assertIn("停止优先", read["content"])
        doc = self.home / "sample.docx"
        with zipfile.ZipFile(doc, "w") as archive:
            archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>文档正文</w:t></w:r></w:p></w:body></w:document>')
        doc_record = attach(self.project, doc)[0]
        self.assertEqual(doc_record["status"], "ready")
        self.assertIn("文档正文", Toolbox(self.session).call("read_attachment", {"attachment_id": doc_record["id"]})["content"])
        zip_path = self.home / "bank.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("a/question.json", '{"question":"停机"}')
            archive.writestr("b/question.json", '{"question":"启动"}')
        zipped = attach(self.project, zip_path)
        self.assertEqual(len(zipped), 3)
        self.assertNotEqual(zipped[1]["path"], zipped[2]["path"])

    def test_zip_traversal_is_rejected_before_any_copy(self):
        path = self.home / "bad.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("../escape.st", "bad")
        with self.assertRaisesRegex(ValueError, "不安全"):
            attach(self.project, path)
        self.assertEqual(self.project.data["attachments"], [])
        self.assertFalse((self.project.workspace / "escape.st").exists())

    def test_image_only_pdf_is_marked_for_ocr_even_with_many_pages(self):
        from pypdf import PdfWriter
        writer = PdfWriter()
        for _ in range(20):
            writer.add_blank_page(width=100, height=100)
        path = self.home / "scanned.pdf"
        writer.write(path)
        self.assertEqual(attach(self.project, path)[0]["status"], "no_text_ocr_needed")

    def test_configuration_has_no_default_vendor_and_keys_do_not_leak(self):
        self.assertEqual(ModelConfig().base_url, "")
        self.assertEqual(ModelConfig().model, "")
        config = ModelConfig(base_url="https://provider.example/v1", model="custom", api_key="private-secret")
        config.save(self.home)
        self.assertNotIn("private-secret", (self.home / "config.json").read_text())
        self.assertNotIn("private-secret", repr(config))
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(ModelConfig.load(self.home).api_key, "private-secret")
            with patch.dict("os.environ", {"PLC_AGENT_BASE_URL": "https://other.example/v1"}):
                self.assertEqual(ModelConfig.load(self.home).api_key, "")

    def test_environment_key_is_not_copied_into_private_config(self):
        cfg = ModelConfig(base_url="https://provider.example/v1", model="custom", api_key="env-only-key")
        with patch.dict("os.environ", {"PLC_AGENT_API_KEY": "env-only-key"}):
            cfg.save(self.home)
            self.assertEqual(ModelConfig.load(self.home).api_key, "env-only-key")
        self.assertNotIn("env-only-key", (self.home / "private/credentials.json").read_text())

    def test_unknown_interface_can_compile_without_claiming_behavior(self):
        self.session.data["mode"] = "execute"
        path = self.project.workspace / "custom.st"
        path.write_text('FUNCTION_BLOCK CustomValve\nVAR_INPUT OpenCmd : BOOL; END_VAR\nVAR_OUTPUT Valve : BOOL; END_VAR\nValve := OpenCmd;\nEND_FUNCTION_BLOCK', encoding="utf-8")
        result = Toolbox(self.session).call("plc_compile_unit", {"source": "custom.st"})
        self.assertEqual(result["status"], "compiled_unit")
        self.assertFalse(result["behavior_tested"])
        self.assertEqual(result["codesys_compile"], "not_executed")
        self.assertTrue((self.project.workspace / result["project_evidence_path"]).is_file())

    def test_summary_preserves_latest_turns_plan_pins_and_archive(self):
        memory = {"objective": "完成PLC", "constraints": ["停止优先"], "decisions": [], "progress": [], "pending": ["回归"], "evidence": ["evidence/check.json"]}
        engine, provider = self.engine({"text": json.dumps(memory, ensure_ascii=False)})
        engine.messages = [{"role": "user", "content": "旧问题" + "x" * 12000}, {"role": "assistant", "content": "旧回答"},
                           {"role": "user", "content": "第二轮"}, {"role": "assistant", "content": "回答2"},
                           {"role": "user", "content": "第三轮"}, {"role": "assistant", "content": "回答3"}]
        self.session.data["pinned_notes"] = ["不要改原件"]
        self.session.data["plan"] = [{"step": "测试", "status": "pending"}]
        before = engine.context_stats()["estimated_tokens"]
        self.assertTrue(engine.compact())
        self.assertLess(engine.context_stats()["estimated_tokens"], before)
        self.assertTrue(engine.messages[0]["content"].startswith("[历史摘要]"))
        self.assertEqual([m["content"] for m in engine.messages[-4:]], ["第二轮", "回答2", "第三轮", "回答3"])
        self.assertIn("不要改原件", engine.system()["content"])
        self.assertIn("测试", engine.system()["content"])
        archive = json.loads(next((self.session.path / "compactions").glob("*.json")).read_text(encoding="utf-8"))
        self.assertIn("旧问题", archive["before"][0]["content"])

    def test_bad_compression_leaves_original_context_intact(self):
        engine, _ = self.engine({"text": '{"incomplete":true}'})
        engine.messages = [{"role": "user", "content": str(i) + "x" * 2000} for i in range(3)]
        original = copy.deepcopy(engine.messages)
        with self.assertRaises(ProviderError):
            engine.compact()
        self.assertEqual(engine.messages, original)
        self.assertEqual(self.session.data["compactions"], 0)

    def test_auto_compaction_happens_before_next_model_request(self):
        self.config.context_window = 8000
        self.config.max_output_tokens = 1024
        memory = {"objective": "任务", "constraints": [], "decisions": [], "progress": [], "pending": [], "evidence": []}
        engine, provider = self.engine({"text": json.dumps(memory)}, {"text": json.dumps(memory)}, {"text": "继续处理"})
        engine.messages = [{"role": "user", "content": "旧历史" + "x" * 16000}, {"role": "assistant", "content": "完成旧阶段"},
                           {"role": "user", "content": "上一轮"}, {"role": "assistant", "content": "已记录"}]
        engine.run("本轮继续")
        self.assertEqual(self.session.data["compactions"], 1)
        self.assertEqual(len(provider.requests), 3)
        self.assertTrue(any(m.get("content", "").startswith("[历史摘要]") for m in provider.requests[-1][0]))

    def test_resume_reconciles_unanswered_tool_calls_without_reexecuting(self):
        atomic_json(self.session.path / "context.json", {"messages": [{"role": "assistant", "content": None, "tool_calls": [
            {"id": "interrupted-call", "type": "function", "function": {"name": "write_file", "arguments": "{}"}}]}]})
        engine, _ = self.engine()
        self.assertEqual(engine.messages[1]["tool_call_id"], "interrupted-call")
        self.assertIn("interrupted", engine.messages[1]["content"])
        self.assertFalse(list(self.project.workspace.glob("*.st")))

    def test_exclusive_session_lease_releases_on_exit(self):
        with self.session.lease():
            other = Session.load(self.project, self.session.data["id"])
            with self.assertRaises(RuntimeError):
                with other.lease():
                    pass
        with self.session.lease():
            pass

    def test_json_instruction_mode_executes_same_validated_tools(self):
        self.config.tool_mode = "json"
        engine, provider = self.engine({"text": '{"type":"tool","name":"write_file","arguments":{"path":"x.st","content":"bad"}}'},
                                      {"text": '{"type":"final","text":"仅规划"}'})
        self.assertEqual(engine.run("先计划"), "仅规划")
        self.assertIsNone(provider.requests[0][1])
        self.assertIn("blocked_by_plan_mode", provider.requests[1][0][-1]["content"])
        self.assertFalse((self.project.workspace / "x.st").exists())

    def test_step_limit_is_not_reported_as_completed(self):
        self.config.max_steps = 1
        engine, _ = self.engine(call("list_files", {}))
        engine.run("查看项目")
        self.assertEqual(self.session.data["status"], "step_limit")

    def test_repeat_guard_distinguishes_changed_file_content(self):
        engine, _ = self.engine()
        path = self.project.workspace / "candidate.st"
        operation = {"name": "plc_bank_test", "arguments": {"source": "candidate.st", "question_id": "10"}}
        path.write_text("version one", encoding="utf-8")
        before = engine.call_signature(operation)
        self.assertEqual(before, engine.call_signature(operation))
        path.write_text("version two", encoding="utf-8")
        self.assertNotEqual(before, engine.call_signature(operation))

    def test_cancellation_prevents_pending_write_and_preserves_protocol(self):
        self.session.data["mode"] = "execute"
        engine, _ = self.engine({"text": "准备写入", **call("write_file", {"path": "never.st", "content": "x"})})
        engine.notify = lambda kind, payload: engine.cancel() if kind == "delta" else None
        engine.run("执行")
        self.assertFalse((self.project.workspace / "never.st").exists())
        self.assertEqual(self.session.data["status"], "interrupted")
        self.assertEqual(engine.messages[-1]["role"], "tool")
        self.assertIn("cancelled", engine.messages[-1]["content"])

    def test_actual_st_failure_repair_and_regression_loop(self):
        self.session.data["mode"] = "execute"
        bad = (ROOT / "examples/motor/mutants/start_over_stop.st").read_text(encoding="utf-8")
        good = (ROOT / "examples/motor/correct.st").read_text(encoding="utf-8")
        bad_hash = hashlib.sha256(bad.encode("utf-8")).hexdigest()
        engine, provider = self.engine(call("write_file", {"path": "candidate.st", "content": bad}, "1"),
                                      call("plc_probe", {"source": "candidate.st", "profile": "motor", "suite": "focused", "shrink_budget": 10}, "2"),
                                      call("write_file", {"path": "candidate.st", "content": good, "expected_sha256": bad_hash}, "3"),
                                      call("plc_probe", {"source": "candidate.st", "profile": "motor", "suite": "focused"}, "4"),
                                      {"text": "已修复并回归；离线测试通过"})
        engine.run("修复停止优先级")
        results = [e["result"] for e in self.session.events() if e["kind"] == "tool" and e["name"] == "plc_probe"]
        self.assertEqual([r["status"] for r in results], ["fail", "pass"])
        for result in results:
            self.assertTrue((self.project.workspace / result["project_evidence_path"]).is_file())
        self.assertEqual(self.session.data["status"], "idle")
        self.assertTrue(self.session.export().is_file())


if __name__ == "__main__":
    unittest.main()
