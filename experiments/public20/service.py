"""Shared checker and metered model relay for the public-20 experiment.

The relay forwards only to an existing local LiteLLM instance. Remote keys never
enter task workspaces. Reservations use peak uncached prices and a conservative
byte-based input bound; missing usage is charged at the full reservation.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
import re
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request
import uuid

from plc_agent.backend_r4 import info
from plc_agent.bank_contracts import questions
from plc_agent.extended_eval import evaluation_fingerprint
from plc_agent.storage import atomic_json
from plc_agent.validation import ValidationConfig, ValidationPipeline
from plc_agent.config import STATE_ROOT
from plc_agent.workflow import evidence_brief

PRICES = {"deepseek-flash": {"input": 2., "cached": .04, "output": 8.},
          "qwen3.8-flash": {"input": .8, "cached": .1, "output": 2.7},
          # Beijing public list prices; cache discount only with measured hits.
          "qwen3.8-max": {"input": 12., "cached": 1.5, "output": 36.}}
THINKING = os.environ.get('PLC_EXPERIMENT_THINKING', '0') == '1'
MAX_OUTPUT = int(os.environ.get('PLC_EXPERIMENT_MAX_OUTPUT', '16384'))
UPSTREAM_TIMEOUT = int(os.environ.get('PLC_EXPERIMENT_UPSTREAM_TIMEOUT', '180'))
OPTIONS = {
    "deepseek-flash": ({"thinking": {"type": "enabled"}, "reasoning_effort": "low"}
                       if THINKING else {"thinking": {"type": "disabled"}}),
    "qwen3.8-flash": ({"enable_thinking": True} if THINKING else {"enable_thinking": False}),
    "qwen3.8-max": {"enable_thinking": os.environ.get('PLC_EXPERIMENT_QWEN_MAX_THINKING','0') == '1'},
}
PRICE_SOURCES = ["https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
                 "https://help.aliyun.com/zh/model-studio/qwen3-8-flash",
                 "https://help.aliyun.com/zh/model-studio/qwen3-8-max"]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalize_response_items(items):
    """Keep every real item, pairing tool results before intervening messages.

    Responses permits messages between a call and its result; Chat providers
    require adjacent tool replies. No result is invented and no content edited.
    Repeated call IDs across completed turns are matched to their next result.
    """
    if not isinstance(items,list):return items
    call_types={'function_call':'function_call_output','custom_tool_call':'custom_tool_call_output'}
    output_types=set(call_types.values())
    consumed=set();result=[];i=0
    while i<len(items):
        if i in consumed:i+=1;continue
        item=items[i]
        kind=item.get('type') if isinstance(item,dict) else None
        if kind in call_types:
            # Preserve parallel calls in ONE assistant message after LiteLLM's
            # conversion, including its genuine prior reasoning. Pairwise
            # interleaving would split that message and lose reasoning on call 2.
            end=i+1
            while end<len(items) and isinstance(items[end],dict) and (items[end].get('type') in call_types or
                    items[end].get('type')=='message' and items[end].get('role')=='assistant'):end+=1
            batch=[x for x in items[i:end] if x.get('type') in call_types]
            messages=[x for x in items[i:end] if x.get('type')=='message'];outputs=[]
            for call in batch:
                match=next((j for j in range(end,len(items)) if j not in consumed and isinstance(items[j],dict)
                            and items[j].get('type')==call_types[call['type']] and items[j].get('call_id')==call.get('call_id')),None)
                if match is None:raise ValueError('missing_real_tool_output')
                outputs.append(items[match]);consumed.add(match)
            # Assistant commentary belongs to the same response as its calls.
            # Put it before the calls so the Chat converter merges one genuine
            # assistant response (reasoning + commentary + calls), rather than
            # inventing a later assistant turn without provider reasoning.
            result.extend(messages+batch+outputs);i=end;continue
        elif kind in output_types:
            raise ValueError('orphan_tool_output')
        else:result.append(item)
        i+=1
    return result


def normalize_usage(value):
    inp = value.get("input_tokens", value.get("prompt_tokens"))
    out = value.get("output_tokens", value.get("completion_tokens"))
    details = value.get("input_tokens_details") or value.get("prompt_tokens_details") or {}
    cached = value.get("prompt_cache_hit_tokens", details.get("cached_tokens", 0))
    if type(inp) is not int or type(out) is not int or inp < 0 or out < 0 or inp+out==0:
        return None
    if type(cached) is not int:cached=0
    return {"input_tokens": inp, "output_tokens": out,
            "cached_input_tokens": min(inp, max(0, cached or 0)), "raw": value}


class ExperimentService:
    def __init__(self, root, budget_cny=10., upstream="http://127.0.0.1:4000"):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.upstream = upstream.rstrip("/")
        self.pipeline = ValidationPipeline(ValidationConfig.load(), STATE_ROOT)
        self.identity = self.current_identity()
        self.lock, self.compile_lock = threading.RLock(), threading.Lock()
        self.tasks = {}
        self.ledger_path = self.root / "budget.json"
        self.ledger = json.loads(self.ledger_path.read_text(encoding="utf-8")) if self.ledger_path.exists() else {
            "limit_cny": budget_cny, "prices_cny_per_million": PRICES, "sources": PRICE_SOURCES,
            "calls": [], "basis": "Peak list prices; cache discount only with reported usage. Unknown usage uses full reservation."}
        if self.ledger["limit_cny"] != budget_cny:
            raise ValueError("Existing campaign budget differs; never silently reset spending")
        self.flush()

    def current_identity(self):
        return {"evaluation_fingerprint": evaluation_fingerprint(),
                "validation_fingerprint": self.pipeline.fingerprint(),
                "backend_fingerprint": info()["fingerprint"]}

    def flush(self):
        atomic_json(self.ledger_path, self.ledger)

    def budget(self):
        with self.lock:
            spent = sum(c.get("charged_cny", c["reserved_cny"]) for c in self.ledger["calls"])
            return {"limit_cny": self.ledger["limit_cny"], "accounted_upper_cny": round(spent, 8),
                    "remaining_cny": round(self.ledger["limit_cny"] - spent, 8),
                    "model_requests": len(self.ledger["calls"])}

    def register(self, data):
        if self.current_identity() != self.identity:
            raise ValueError("Code/test environment changed: restart service with a new frozen run")
        qid = data["question_id"]
        question = next(q for q in questions() if q["id"] == qid)
        name = data["setting"]
        if name not in {"codex-deepseek", "codex-qwen", "self-deepseek", "self-qwen", "codex-qwen-max", "self-qwen-max"}:
            raise ValueError("Unknown setting")
        evidence = Path(data["evidence"]).resolve()
        if not evidence.is_relative_to(self.root) or evidence.exists():
            raise ValueError("Evidence path must be a new directory inside the campaign")
        evidence.mkdir(parents=True)
        task_id = uuid.uuid4().hex
        task = {"task_id": task_id, "question_id": qid, "setting": name, "model": data["model"],
                "evidence": str(evidence), "deadline": time.time() + data["timeout"],
                "max_candidates": 6, "max_model_calls": 24, "max_output_tokens":MAX_OUTPUT,
                "model_options":OPTIONS[data['model']], "policy":data.get('policy',''),
                "submissions": [], "relay_errors": [], **self.identity,
                "preflight": self.pipeline.preflight(question)}
        with self.lock:
            self.tasks[task_id] = task
        atomic_json(evidence / "task.json", task)
        return task

    def check(self, task_id, raw):
        with self.compile_lock:
            task = self.tasks[task_id]
            if self.current_identity() != self.identity:
                return {"status": "environment_changed", **self.identity}
            if task["preflight"]:
                return {**task["preflight"], **self.identity}
            sha = digest(raw)
            existing = next((s for s in task["submissions"] if s["source_sha256"] == sha), None)
            if existing:
                return existing["feedback"]
            if time.time() >= task["deadline"]:
                return {"status": "task_timeout", "source_sha256": sha, **self.identity}
            if len(task["submissions"]) >= task["max_candidates"]:
                return {"status": "repair_limit", "source_sha256": sha, **self.identity}
            number = len(task["submissions"]) + 1
            directory = Path(task["evidence"]) / "submissions" / f"{number:02d}"
            directory.mkdir(parents=True)
            source = directory / "source.st"
            source.write_bytes(raw)
            started = time.monotonic()
            result = self.pipeline.evaluate(source, task["question_id"])
            result.update(**self.identity, checker_seconds=round(time.monotonic() - started, 3))
            atomic_json(directory / "result.json", result)
            feedback = evidence_brief(result)
            record = {"version": number, "source_sha256": sha, "status": result["status"],
                      "stages": {k: v.get("status") for k, v in result.get("stages", {}).items()},
                      "feedback": feedback, "result": str(directory / "result.json")}
            task["submissions"].append(record)
            atomic_json(Path(task["evidence"]) / "task.json", task)
            return feedback

    def reserve(self, task_id, payload):
        with self.lock:
            task = self.tasks[task_id]
            if time.time() >= task["deadline"]:
                raise ValueError("task_timeout")
            if payload.get("model") != task["model"]:
                raise ValueError("Model must match the frozen task setting")
            prior = [c for c in self.ledger["calls"] if c["task_id"] == task_id]
            if len(prior) >= task["max_model_calls"]:
                raise ValueError("model_call_limit")
            price = PRICES[task["model"]]
            upper = (len(json.dumps(payload, ensure_ascii=False).encode()) + 4096) * price["input"] / 1e6
            upper += MAX_OUTPUT * price["output"] / 1e6
            if upper > self.budget()["remaining_cny"]:
                raise ValueError("campaign_budget_exhausted")
            record = {"call_id": uuid.uuid4().hex, "task_id": task_id, "model": task["model"],
                      "reserved_cny": upper, "request_sha256": digest(json.dumps(payload, sort_keys=True).encode()),
                      "parameters": {k: v for k, v in payload.items() if k not in ("input", "messages", "tools", "instructions")},
                      "started_at": time.time(), "state": "reserved"}
            self.ledger["calls"].append(record)
            self.flush()
            return record

    def settle(self, record, usage, model, error=None):
        with self.lock:
            normalized = normalize_usage(usage or {})
            if normalized:
                price = PRICES[record["model"]]
                cost = ((normalized["input_tokens"] - normalized["cached_input_tokens"]) * price["input"]
                        + normalized["cached_input_tokens"] * price["cached"]
                        + normalized["output_tokens"] * price["output"]) / 1e6
            else:
                cost = record["reserved_cny"]
            record.update(state="complete" if not error else "provider_error", usage=normalized,
                          served_model=model, error=error, charged_cny=cost,
                          seconds=round(time.time() - record["started_at"], 3))
            self.flush()


def handler_for(service):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, data):
            raw = json.dumps(data, ensure_ascii=False).encode()
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if self.path == "/health":
                self.reply(200, {"status": "ok", **service.identity, "budget": service.budget()})
            elif self.path == "/budget":
                self.reply(200, service.budget())
            elif self.path == "/v1/models":
                self.reply(200, {"data": [{"id": name, "object": "model"} for name in PRICES], "object": "list"})
            else:
                self.reply(404, {"error": "unknown endpoint"})

        def do_POST(self):
            record = None
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 2_000_000:
                    raise ValueError("invalid payload size")
                raw = self.rfile.read(length)
                if self.path == "/register":
                    return self.reply(200, service.register(json.loads(raw)))
                if self.path.startswith("/check/"):
                    return self.reply(200, service.check(self.path.rsplit("/", 1)[-1], raw))
                if self.path not in ("/v1/responses", "/v1/chat/completions"):
                    return self.reply(404, {"error": "unknown endpoint"})
                task_id = self.headers.get("X-Experiment-Task", "")
                task = service.tasks[task_id]
                payload = json.loads(raw)
                model = payload["model"]
                options = OPTIONS[model]
                normalized=False
                if self.path.endswith("/responses"):
                    original=payload.get('input')
                    payload['input']=normalize_response_items(original)
                    normalized=payload['input']!=original
                    payload["max_output_tokens"] = MAX_OUTPUT
                    payload["extra_body"] = {**payload.get("extra_body", {}), **options}
                else:
                    payload.update(options, max_tokens=MAX_OUTPUT)
                    if payload.get("stream"):
                        payload["stream_options"] = {"include_usage": True}
                payload["num_retries"] = 0
                record = service.reserve(task_id, payload)
                record['history_normalized']=normalized
                request = urllib.request.Request(service.upstream + self.path,
                    data=json.dumps(payload, ensure_ascii=False).encode(),
                    headers={"Content-Type": "application/json", "Authorization": "Bearer sk-local"}, method="POST")
                usage, served = {}, model
                timeout = max(1, min(UPSTREAM_TIMEOUT, task["deadline"] - time.time()))
                with urllib.request.urlopen(request, timeout=timeout) as upstream:
                    content_type = upstream.headers.get("Content-Type", "application/json")
                    self.send_response(upstream.status)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.close_connection = True
                    disconnected = False
                    if "text/event-stream" in content_type:
                        event = []
                        while True:
                            line = upstream.readline(2_000_001)
                            if not line:
                                break
                            if time.time() > task["deadline"]:
                                raise TimeoutError("task_timeout")
                            if not disconnected:
                                try:
                                    self.wfile.write(line)
                                    self.wfile.flush()
                                except (BrokenPipeError, ConnectionResetError):
                                    disconnected = True
                            decoded = line.decode("utf-8", errors="replace").strip()
                            if decoded.startswith("data:"):
                                event.append(decoded[5:].lstrip())
                            if not decoded and event:
                                data = "\n".join(event)
                                event = []
                                if data != "[DONE]":
                                    value = json.loads(data)
                                    obj = value.get("response") or value
                                    usage = obj.get("usage") or usage
                                    served = obj.get("model") or served
                                    if value.get("type") == "response.failed" or value.get("error"):
                                        raise ValueError("upstream_response_failed")
                    else:
                        data = upstream.read(8_000_001)
                        obj = json.loads(data)
                        usage, served = obj.get("usage") or {}, obj.get("model") or model
                        try:
                            self.wfile.write(data)
                        except (BrokenPipeError, ConnectionResetError):
                            pass
                service.settle(record, usage, served)
            except urllib.error.HTTPError as exc:
                detail=re.sub(r'sk-[A-Za-z0-9_-]{6,}','[redacted]',exc.read(2000).decode('utf-8',errors='replace'))
                if record:
                    record['provider_detail']=detail
                    service.settle(record, {}, record["model"], f"upstream_http_{exc.code}")
                self.reply(exc.code, {"error": {"message": f"upstream_http_{exc.code}: {detail}", "type": "provider_error"}})
                exc.close()
            except (ValueError, KeyError, OSError, TimeoutError) as exc:
                message = str(exc) if isinstance(exc, (ValueError, KeyError)) else type(exc).__name__
                if record:
                    service.settle(record, {}, record["model"], message)
                task_id=self.headers.get('X-Experiment-Task','')
                if task_id in service.tasks:
                    service.tasks[task_id]['relay_errors'].append(message)
                self.reply(429 if "limit" in message else 402 if "budget" in message else 400,
                           {"error": {"message": message, "type": "experiment_error"}})
    return Handler


def start_service(root, budget_cny=10., port=8767):
    service = ExperimentService(root, budget_cny)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler_for(service))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return service, server
