"""Small synchronous MCP stdio server (JSON-RPC, newline-delimited UTF-8).

No network listener, model API, credentials, global client configuration, or
physical controller access. Compiler and native runner have independent limits.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from . import __version__
from .adversarial import review
from .backend import BackendError, compile_source, run_batch
from .config import cache_dir, doctor, save_json
from .contracts import PROFILES
from .tools import EVIDENCE_SCOPE, compare, minimize_failure, probe, replay


SOURCE = {"type": "string", "description": "Absolute path to a local .st source file."}
PROFILE = {"type": "string", "enum": list(PROFILES)}
SUITE = {"type": "string", "enum": ["normal", "focused", "random"], "default": "focused"}


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": properties, "required": required, "additionalProperties": False}}


TOOLS = [
    _tool("plc_environment", "Inspect offline compiler availability. Does not install dependencies or access a PLC.", {}, []),
    _tool("plc_compile", "Compile actual ST with STruC++ and g++. This is explicitly NOT a CODESYS compile result.",
          {"source": SOURCE, "profile": PROFILE}, ["source", "profile"]),
    _tool("plc_probe", "Run finite PLC scenarios against a known contract; return a compact verdict and replayable reduced counterexample. A pass is NOT formal proof.",
          {"source": SOURCE, "profile": PROFILE, "suite": SUITE,
           "seed": {"type": "integer", "default": 20261026},
           "shrink_budget": {"type": "integer", "minimum": 0, "maximum": 200, "default": 60}}, ["source", "profile"]),
    _tool("plc_run_trace", "Execute your exact timestamped input sequence, reset the FB first, and check outputs after each scan. Times are simulated milliseconds.",
          {"source": SOURCE, "profile": PROFILE,
           "trace": {"type": "array", "minItems": 1, "maxItems": 10000,
                     "items": {"type": "object", "required": ["time_ms", "inputs"],
                               "properties": {"time_ms": {"type": "integer"}, "inputs": {"type": "object"}}}}},
          ["source", "profile", "trace"]),
    _tool("plc_replay", "Replay a saved counterexample against the supplied source. Reports both the original property and any new violations after a repair.",
          {"source": SOURCE, "counterexample_path": {"type": "string"}}, ["source", "counterexample_path"]),
    _tool("plc_compare", "Check both versions against the same contract and scenarios; report newly failing and resolved cases. The old version is not assumed correct.",
          {"before": SOURCE, "after": SOURCE, "profile": PROFILE, "suite": SUITE,
           "seed": {"type": "integer", "default": 20261026}}, ["before", "after", "profile"]),
    _tool("plc_adversarial_review", "Execute independent reviewer hypotheses twice in fresh processes. Source hashes and a separate requirement adjudication guard the verdict. No adjudication means pending, not pass.",
          {"proposals_path": {"type": "string"}, "adjudication_path": {"type": "string"},
           "output": {"type": "string"}}, ["proposals_path"]),
]


def _validate(name: str, arguments: dict) -> None:
    tool = next((t for t in TOOLS if t["name"] == name), None)
    if tool is None:
        raise ValueError(f"Unknown tool: {name}")
    schema = tool["inputSchema"]
    if not isinstance(arguments, dict) or set(arguments) - set(schema["properties"]):
        raise ValueError("Unknown arguments or arguments is not an object")
    for required in schema["required"]:
        if required not in arguments:
            raise ValueError(f"Missing required argument: {required}")
    types = {"string": str, "integer": int, "array": list}
    for key, value in arguments.items():
        rule = schema["properties"][key]
        expected_type = types.get(rule["type"])
        if expected_type and type(value) is not expected_type:
            raise ValueError(f"Invalid argument type: {key}")
        if "enum" in rule and value not in rule["enum"]:
            raise ValueError(f"Invalid {key}: {value}")
        if "minimum" in rule and value < rule["minimum"] or "maximum" in rule and value > rule["maximum"]:
            raise ValueError(f"Argument outside allowed bounds: {key}")


def _compact(result: dict) -> dict:
    """Retain full evidence on disk; do not dump hundreds of passing rows to an LLM."""
    digest = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:20]
    path = cache_dir() / "tool-results" / f"{digest}.json"
    save_json(path, result)
    result = json.loads(json.dumps(result))
    for key in ("summary", "before_summary", "after_summary"):
        if key in result:
            result[key].pop("cases", None)
    if "changes" in result:
        result["changes_total"] = len(result["changes"])
        result["changes"] = result["changes"][:12]
    for finding in result.get("findings", []):
        if "checks" in finding:
            finding["assertions_total"] = len(finding["checks"])
            finding["checks"] = finding["checks"][:8]
    if "result" in result and "rows" in result["result"] and len(result["result"]["rows"]) > 16:
        result["result"]["rows_total"] = len(result["result"]["rows"])
        failure = result["result"]["first_failure"]
        end = failure["scan"] + 1 if failure else 8
        result["result"]["rows"] = result["result"]["rows"][max(0, end - 8):end]
    result["full_evidence_path"] = str(path)
    return result


def call_tool(name: str, arguments: dict) -> dict:
    _validate(name, arguments)
    if name == "plc_environment":
        return doctor()
    if name == "plc_compile":
        artifact = compile_source(**arguments)
        return {"status": "compiled", "source_sha256": artifact.sha256,
                "build_evidence": str(artifact.directory / "build.json"), "evidence_scope": EVIDENCE_SCOPE}
    if name == "plc_probe":
        return _compact(probe(**arguments))
    if name == "plc_compare":
        return _compact(compare(**arguments))
    if name == "plc_adversarial_review":
        return _compact(review(**arguments))
    if name == "plc_replay":
        record_path = Path(arguments["counterexample_path"])
        if record_path.stat().st_size > 2_000_000:
            raise ValueError("Counterexample exceeds 2 MB")
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if "counterexample" in record:
            record = record["counterexample"]
        return _compact(replay(arguments["source"], record))
    artifact = compile_source(arguments["source"], arguments["profile"])
    result = run_batch(artifact, [{"name": "agent_supplied_trace", "trace": arguments["trace"]}])[0]
    response = {"status": result["status"], "result": result, "evidence_scope": EVIDENCE_SCOPE}
    if result["first_failure"]:
        response["counterexample"] = minimize_failure(artifact, result)
    return _compact(response)


def serve() -> None:
    for raw in sys.stdin.buffer:
        request_id = None
        try:
            if len(raw) > 2_000_000:
                raise ValueError("Request exceeds 2 MB")
            message = json.loads(raw.decode("utf-8"))
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                raise ValueError("Expected a JSON-RPC 2.0 object")
            request_id = message.get("id")
            if "id" not in message:
                continue
            method, params = message.get("method"), message.get("params", {})
            if not isinstance(params, dict):
                raise ValueError("params must be an object")
            if method == "initialize":
                requested = params.get("protocolVersion")
                supported = ("2024-11-05", "2025-03-26", "2025-06-18")
                result = {"protocolVersion": requested if requested in supported else "2025-06-18",
                          "capabilities": {"tools": {}}, "serverInfo": {"name": "plc-probe", "version": __version__},
                          "instructions": "Offline ST scenario testing only. Never report these results as CODESYS compilation or formal proof."}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                try:
                    payload = call_tool(params["name"], params.get("arguments", {}))
                    error = payload.get("status") in ("tool_error", "missing_dependency", "compile_error", "runtime_error", "timeout")
                except BackendError as exc:
                    payload, error = exc.result, True
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    payload, error = {"status": "tool_error", "message": str(exc)}, True
                result = {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}], "isError": error}
            else:
                response = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                continue
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        except json.JSONDecodeError:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        except (ValueError, TypeError, KeyError) as exc:
            response = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": str(exc)}}
        except Exception as exc:
            print(f"Internal tool error: {type(exc).__name__}: {exc}", file=sys.stderr)
            response = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": "Internal tool error"}}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()
