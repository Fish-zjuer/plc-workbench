"""Vendor-neutral Chat Completions transport: native tools or JSON fallback."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
import uuid
import time

from .config import ModelConfig


class ProviderError(RuntimeError):
    pass


class Cancelled(RuntimeError):
    pass


def json_value(text: str):
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text, parse_constant=lambda s: (_ for _ in ()).throw(ValueError("非有限 JSON 数值")))


class ChatProvider:
    def __init__(self, config: ModelConfig):
        self.config = config
        self.cancel_event = threading.Event()
        self._response = None
        self.metrics = []

    def cancel(self):
        self.cancel_event.set()
        response = self._response
        if response:
            try:
                response.close()
            except OSError:
                pass

    def _clean_error(self, text):
        return str(text).replace(self.config.api_key, "[redacted]") if self.config.api_key else str(text)

    def complete(self, messages: list[dict], tools: list[dict] | None = None, on_delta=None) -> dict:
        self.config.validate()
        if self.cancel_event.is_set():
            raise Cancelled("已停止")
        body = {"model": self.config.model, "messages": messages, "stream": self.config.stream,
                "max_tokens": self.config.max_output_tokens}
        body.update(self.config.extra_body)
        started = time.monotonic()
        if tools:
            body.update(tools=tools, tool_choice="auto")
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream, application/json"}
        if self.config.api_key:
            headers["Authorization"] = "Bearer " + self.config.api_key
        request = urllib.request.Request(self.config.endpoint,
                                         data=json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                                         headers=headers, method="POST")
        for attempt in range(3):
            try:
                self._response = urllib.request.urlopen(request, timeout=self.config.timeout)
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 502, 503, 504) and attempt < 2:
                    exc.close()
                    if self.cancel_event.wait(2 ** attempt):
                        raise Cancelled("已停止")
                    continue
                details = exc.read(1500).decode("utf-8", errors="replace")
                exc.close()
                raise ProviderError(self._clean_error(f"模型服务 HTTP {exc.code}: {details}")) from None
            except (OSError, urllib.error.URLError) as exc:
                if self.cancel_event.is_set():
                    raise Cancelled("已停止") from None
                raise ProviderError(self._clean_error(f"模型连接失败: {exc}")) from None
        try:
            response = self._response
            if "text/event-stream" not in response.headers.get("Content-Type", ""):
                raw = response.read(8_000_001)
                if len(raw) > 8_000_000:
                    raise ProviderError("模型响应超过 8 MB")
                data = json.loads(raw.decode("utf-8"))
                if data.get("error"):
                    raise ProviderError(self._clean_error(json.dumps(data["error"], ensure_ascii=False)))
                message = data["choices"][0]["message"]
                self.metrics.append({"model": data.get("model", self.config.model), "usage": data.get("usage", {}),
                                     "seconds": round(time.monotonic() - started, 3)})
                if on_delta and isinstance(message.get("content"), str):
                    on_delta(message["content"])
                return self._normalize(message, data.get("usage", {}), data["choices"][0].get("finish_reason"))
            text, reasoning, calls, usage, finish, size = [], [], {}, {}, None, 0
            model_name = self.config.model
            # SSE events may have multiple data lines and arbitrary network chunking.
            event_lines = []
            done = False
            while not done:
                if self.cancel_event.is_set():
                    raise Cancelled("已停止")
                line = response.readline(1_000_001)
                if not line:
                    break
                size += len(line)
                if len(line) > 1_000_000 or size > 8_000_000:
                    raise ProviderError("模型流超过大小限制")
                line = line.decode("utf-8").rstrip("\r\n")
                if line.startswith("data:"):
                    event_lines.append(line[5:].lstrip())
                if line != "" or not event_lines:
                    continue
                payload = "\n".join(event_lines)
                event_lines = []
                if payload == "[DONE]":
                    done = True
                    continue
                data = json.loads(payload)
                model_name = data.get("model", model_name)
                if data.get("error"):
                    raise ProviderError(self._clean_error(json.dumps(data["error"], ensure_ascii=False)))
                usage = data.get("usage") or usage
                for choice in data.get("choices", [])[:1]:
                    finish = choice.get("finish_reason") or finish
                    delta = choice.get("delta", {})
                    if isinstance(delta.get("reasoning_content"), str):
                        reasoning.append(delta["reasoning_content"])
                    if isinstance(delta.get("content"), str):
                        text.append(delta["content"])
                        if on_delta:
                            on_delta(delta["content"])
                    for call in delta.get("tool_calls", []):
                        index = call.get("index", 0)
                        current = calls.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        if call.get("id"):
                            current["id"] = call["id"]
                        function = call.get("function", {})
                        for key in ("name", "arguments"):
                            current["function"][key] += function.get(key) or ""
            if not done and finish is None:
                raise ProviderError("模型流提前中断；未执行其中的工具调用，可重试")
            self.metrics.append({"model": model_name, "usage": usage, "seconds": round(time.monotonic() - started, 3)})
            message = {"content": "".join(text), "tool_calls": [calls[i] for i in sorted(calls)]}
            if reasoning:
                message["reasoning_content"] = "".join(reasoning)
            return self._normalize(message, usage, finish)
        except (KeyError, TypeError, ValueError, OSError) as exc:
            if self.cancel_event.is_set():
                raise Cancelled("已停止") from None
            raise ProviderError(self._clean_error(f"模型响应格式/传输错误: {exc}")) from None
        finally:
            if self._response:
                self._response.close()
                self._response = None

    def _normalize(self, message: dict, usage: dict, finish) -> dict:
        if finish in ("length", "content_filter"):
            raise ProviderError(f"模型响应未完成（{finish}），未执行任何工具；请调整输出上限或任务范围")
        text = message.get("content") or ""
        if not isinstance(text, str):
            raise ProviderError("仅支持文本 Chat Completions 响应")
        calls = []
        for call in message.get("tool_calls") or []:
            function = call["function"]
            if len(function.get("arguments", "")) > 200_000:
                raise ProviderError("工具参数过长")
            arguments = json_value(function.get("arguments") or "{}")
            if not isinstance(arguments, dict):
                raise ProviderError("工具参数必须为 JSON 对象")
            calls.append({"id": call.get("id") or "call_" + uuid.uuid4().hex[:12],
                          "name": function["name"], "arguments": arguments})
        result = {"text": text, "calls": calls, "usage": usage}
        if isinstance(message.get("reasoning_content"), str):
            result["reasoning_content"] = message["reasoning_content"]
        return result
