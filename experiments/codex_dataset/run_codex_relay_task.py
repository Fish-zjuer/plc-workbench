"""Codex dataset task through the metered public20 relay (response normalization)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

os.environ.setdefault("PLC_EXPERIMENT_THINKING", "0")
os.environ.setdefault("PLC_EXPERIMENT_MAX_OUTPUT", "32768")
os.environ.setdefault("PLC_EXPERIMENT_UPSTREAM_TIMEOUT", "600")

from plc_agent import bank32, dataset
from plc_agent.dataset_workflow import normalize_source
from experiments.public20.service import start_service

R8 = Path(__file__).resolve().parents[2]
MAIN = Path(r"D:\大三上\GenAI赋能工业编程\final project\plc-workbench")
CODEX = MAIN / ".runtime" / "codex-0.80" / "node_modules" / ".bin" / "codex.cmd"
PYTHON = MAIN / ".venv" / "Scripts" / "python.exe"
CHECK = R8 / "experiments" / "codex_dataset" / "check.py"
CXX = Path(r"C:\Users\Athan\.cache\plc-workbench-toolchains\mingw64\bin\g++.exe")
NODE_BIN = Path(r"C:\Users\Athan\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin")
RUNTIME_BIN = MAIN / ".runtime" / "bin"
OUT = Path(os.environ.get("BANK32_OUT", str(R8 / "reports" / "codex_relay")))
RELAY_ROOT = R8 / "reports" / "codex_relay_ledger"
PORT = 8770


def interface_markdown(task: dict) -> str:
    rows = ["| Direction | Variable/Field | Data Type |", "|---|---|---|"]
    for port in task["interface"]:
        rows.append(f"| {port['direction']} | `{port['name']}` | `{port['type']}` |")
    return "\n".join(rows)


def main() -> int:
    task_id, model = sys.argv[1], sys.argv[2]
    task = dataset.load(task_id)
    service, _server = start_service(RELAY_ROOT, budget_cny=50.0, port=PORT)
    relay_task = service.register({
        "question_id": "01",
        "setting": "codex-deepseek" if model.startswith("deepseek") else "codex-qwen",
        "model": model,
        "timeout": 1800,
        "policy": "dataset codex run",
        "evidence": str(RELAY_ROOT / "evidence" / uuid.uuid4().hex),
    })
    task_key = relay_task["task_id"]
    run_id = uuid.uuid4().hex[:12]
    workspace = Path(os.environ.get("TEMP", str(R8))) / "plc-dataset-codex" / run_id / f"{task_id}-{model}"
    home = workspace.parent / "codex-home"
    workspace.mkdir(parents=True)
    home.mkdir(parents=True)
    packet = bank32.author_packet(task)
    (workspace / "requirements.md").write_text(
        packet["requirements"] + "\n\n## Interface Definition\n\n" + interface_markdown(task) +
        "\n\n## LTL Requirements\n\n" + json.dumps(packet["ltl_requirements"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    (workspace / "policy.md").write_text(
        packet["backend_notes"] + "\nFixed host-side tests; expected outputs are host-owned and not shown. "
        "At most 6 source versions, 24 model requests and 1800 seconds. "
        "Never edit requirements.md, policy.md or check.ps1.\n",
        encoding="utf-8")
    ps = f"""$ErrorActionPreference = 'Stop'
$env:CXX = '{CXX}'
$env:PATH = '{CXX.parent};{RUNTIME_BIN};' + $env:PATH
$env:PYTHONPATH = '{R8}'
& '{PYTHON}' -X utf8 '{CHECK}' '{task_id}' 'candidate.st'
exit $LASTEXITCODE
"""
    (workspace / "check.ps1").write_text(ps, encoding="utf-8")
    prompt = f"""Work only inside this task directory. Do not read files outside it or search for reference solutions.
Read requirements.md and policy.md. Implement the complete FUNCTION_BLOCK {task['block']} ... END_FUNCTION_BLOCK in candidate.st, including necessary TYPE definitions. Use exactly the specified interface: never add, remove, or change any interface variable or type.
After each source version run: powershell -NoProfile -ExecutionPolicy Bypass -File check.ps1
Use only the checker diagnostics to repair your own ST. Do not inspect generated C++ headers, compiler caches, or files outside this task directory. Do not access TON internal members such as CURRENT_TIME. Never edit requirements.md, policy.md or check.ps1.
There are at most 6 submitted source versions (initial candidate plus 5 repairs), 24 model requests and 1800 seconds. Stop on pass or any budget limit. Rechecking identical source does not add a version.
Finish with the status and a short explanation. Do not claim success without checker evidence.
Strict budget mode: use at most 24 model requests. Do NOT run any PowerShell command other than check.ps1. Do not inspect check.ps1, requirements more than once, generated C++, caches, or other files. Write candidate.st directly. Never use LEN or CHAR as variable names; use LEN() as a function. Make one focused repair per failed version; stop after 6 versions.
"""
    (workspace / "prompt.txt").write_text(prompt, encoding="utf-8")
    (home / "config.toml").write_text(f'''model = "{model}"
model_provider = "relay"
approval_policy = "never"
sandbox_mode = "workspace-write"
model_context_window = 128000
[model_providers.relay]
name = "metered local relay"
base_url = "http://127.0.0.1:{PORT}/v1"
env_key = "PLC_CODEX_KEY"
wire_api = "responses"
request_max_retries = 0
stream_max_retries = 0
http_headers = {{ "X-Experiment-Task" = "{task_key}" }}
''', encoding="utf-8")
    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    env["PLC_CODEX_KEY"] = "sk-experiment-local"
    env["PYTHONPATH"] = str(R8)
    env["PATH"] = str(NODE_BIN) + os.pathsep + str(RUNTIME_BIN) + os.pathsep + env.get("PATH", "")
    cmd = ["cmd", "/c", str(CODEX), "exec", "-C", str(workspace), "--skip-git-repo-check",
           "-s", "workspace-write", "--json", "-o", str(workspace / "final.txt"), "-"]
    started = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(cmd, cwd=workspace, env=env, input=prompt, text=True,
                              encoding="utf-8", errors="replace", capture_output=True, timeout=1800)
        stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, code, timed_out = exc.stdout or "", exc.stderr or "", None, True
    (workspace / "agent.log").write_text(stdout + "\n" + stderr, encoding="utf-8")
    candidate = workspace / "candidate.st"
    if candidate.is_file():
        text = candidate.read_text(encoding="utf-8-sig")
        normalized = normalize_source(text, task["block"])
        if normalized != text:
            candidate.write_text(normalized, encoding="utf-8")
        try:
            result = dataset.evaluate(candidate, task)
        except Exception as exc:  # noqa: BLE001
            result = {"status": "invalid_candidate", "message": str(exc)}
    else:
        result = {"status": "missing_candidate"}
    calls = [c for c in service.ledger["calls"] if c["task_id"] == task_key]
    usage = [c.get("usage") or {} for c in calls]
    OUT.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema": "codex-dataset-relay-v1",
        "task_id": task_id,
        "model": model,
        "workspace": str(workspace),
        "timed_out": timed_out,
        "exit_code": code,
        "seconds": round(time.monotonic() - started, 2),
        "status": result.get("status"),
        "summary": result.get("summary"),
        "first_failure": result.get("first_failure"),
        "model_requests": len(calls),
        "input_tokens": sum(u.get("input_tokens", 0) for u in usage),
        "output_tokens": sum(u.get("output_tokens", 0) for u in usage),
        "budget": service.budget(),
    }
    path = OUT / f"{task_id}_{model}_{run_id}.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
