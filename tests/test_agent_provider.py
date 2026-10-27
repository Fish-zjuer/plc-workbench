from __future__ import annotations

from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import unittest

from plc_agent.config import ModelConfig
from plc_agent.provider import ChatProvider, ProviderError


class LocalAPI:
    """An actual local HTTP/SSE service, not a replacement for model quality tests."""
    def __init__(self, responses):
        self.responses, self.requests = deque(responses), []
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                owner.requests.append({"path": self.path, "auth": self.headers.get("Authorization"),
                                       "body": json.loads(self.rfile.read(int(self.headers["Content-Length"])))})
                status, content_type, content = owner.responses.popleft()
                content = content.encode("utf-8") if isinstance(content, str) else content
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                # Flush byte-sized chunks to exercise line framing and Unicode.
                for i in range(0, len(content), 7):
                    self.wfile.write(content[i:i+7])
                    self.wfile.flush()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def provider(self, **overrides):
        return ChatProvider(ModelConfig(base_url=f"http://127.0.0.1:{self.server.server_port}/custom/v1",
                                        model="a-provider-specific-name", api_key="fixture-key", **overrides))


def event(value):
    return "data: " + json.dumps(value, ensure_ascii=False) + "\n\n"


class ProviderTests(unittest.TestCase):
    def test_custom_endpoint_bearer_auth_and_nonstream_response(self):
        data = {"choices": [{"message": {"content": "连接成功"}, "finish_reason": "stop"}], "usage": {"total_tokens": 9}}
        with LocalAPI([(200, "application/json", json.dumps(data))]) as api:
            result = api.provider(stream=False).complete([{"role": "user", "content": "你好"}])
            request = api.requests[0]
            self.assertEqual(request["path"], "/custom/v1/chat/completions")
            self.assertEqual(request["auth"], "Bearer fixture-key")
            self.assertEqual(request["body"]["model"], "a-provider-specific-name")
            self.assertFalse(request["body"]["stream"])
            self.assertEqual(result["text"], "连接成功")
            self.assertEqual(result["usage"]["total_tokens"], 9)

    def test_stream_fragmented_function_arguments_and_unicode_content(self):
        stream = ": keepalive\n\n" + event({"choices": [{"delta": {"content": "检查中"}}]})
        stream += event({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "read_", "arguments": '{"pa'}}]}}]})
        stream += event({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "file", "arguments": 'th":"中文.st"}'}}]}, "finish_reason": "tool_calls"}]})
        stream += event({"choices": [], "usage": {"prompt_tokens": 40}}) + "data: [DONE]\n\n"
        with LocalAPI([(200, "text/event-stream; charset=utf-8", stream)]) as api:
            deltas = []
            result = api.provider().complete([{"role": "user", "content": "检查"}], on_delta=deltas.append)
            self.assertEqual("".join(deltas), "检查中")
            self.assertEqual(result["calls"], [{"id": "c1", "name": "read_file", "arguments": {"path": "中文.st"}}])
            self.assertEqual(result["usage"]["prompt_tokens"], 40)

    def test_incomplete_stream_never_returns_executable_calls(self):
        stream = event({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "write_file", "arguments": '{"path":"x.st","content":"x"}'}}]}}]})
        with LocalAPI([(200, "text/event-stream", stream)]) as api:
            with self.assertRaisesRegex(ProviderError, "提前中断"):
                api.provider().complete([])

    def test_http_errors_redact_credentials(self):
        with LocalAPI([(401, "application/json", '{"error":"bad fixture-key"}')]) as api:
            with self.assertRaises(ProviderError) as caught:
                api.provider().complete([])
            self.assertNotIn("fixture-key", str(caught.exception))
            self.assertIn("[redacted]", str(caught.exception))

    def test_length_truncation_is_not_executed(self):
        data = {"choices": [{"message": {"content": "partial"}, "finish_reason": "length"}]}
        with LocalAPI([(200, "application/json", json.dumps(data))]) as api:
            with self.assertRaisesRegex(ProviderError, "未完成"):
                api.provider().complete([])

    def test_empty_tools_are_not_forced_on_services(self):
        data = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
        with LocalAPI([(200, "application/json", json.dumps(data))]) as api:
            api.provider(tool_mode="json").complete([])
            self.assertNotIn("tools", api.requests[0]["body"])
            self.assertNotIn("tool_choice", api.requests[0]["body"])

    def test_retry_is_bounded_to_failed_http_before_any_response(self):
        data = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
        with LocalAPI([(503, "application/json", '{}'), (200, "application/json", json.dumps(data))]) as api:
            self.assertEqual(api.provider().complete([])["text"], "ok")
            self.assertEqual(len(api.requests), 2)


if __name__ == "__main__":
    unittest.main()
