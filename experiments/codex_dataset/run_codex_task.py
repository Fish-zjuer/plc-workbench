"""Run one frozen dataset task with the Codex CLI and fixed host-side tests."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from plc_agent import dataset

R8 = Path(__file__).resolve().parents[2]
MAIN = Path(r"D:\大三上\GenAI赋能工业编程\final project\plc-workbench")
CODEX = MAIN / ".runtime" / "codex-0.80" / "node_modules" / ".bin" / "codex.cmd"
PYTHON = MAIN / ".venv" / "Scripts" / "python.exe"
CHECK = R8 / "experiments" / "codex_dataset" / "check.py"
CXX = Path(r"C:\Users\Athan\.cache\plc-workbench-toolchains\mingw64\bin\g++.exe")
RUNTIME_BIN = MAIN / ".runtime" / "bin"
NODE_BIN = Path(r"C:\Users\Athan\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin")
OUT = R8 / "reports" / "codex_dataset"


def interface_markdown(task: dict) -> str:
    rows = ["| Direction | Variable/Field | Data Type |", "|---|---|---|"]
    for port in task["interface"]:
        rows.append(f"| {port['direction']} | `{port['name']}` | `{port['type']}` |")
    return "\n".join(rows)


def main() -> int:
    task_id, model = sys.argv[1], sys.argv[2]
    task = dataset.load(task_id)
    run_id = uuid.uuid4().hex[:12]
    workspace = Path(os.environ.get("TEMP", str(R8))) / "plc-dataset-codex" / run_id / f"{task_id}-{model}"
    home = workspace.parent / "codex-home"
    workspace.mkdir(parents=True)
    home.mkdir(parents=True)
    (workspace / "requirements.md").write_text(
        task["requirements"] + "\n\n## Interface Definition\n\n" + interface_markdown(task) + "\n",
        encoding="utf-8")
    (workspace / "policy.md").write_text(
        "Fixed host-side tests. Expected outputs are not provided to the author. "
        "The checker returns pass/fail and concrete diagnostics only. "
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
Read requirements.md and policy.md. Implement the complete FUNCTION_BLOCK {task['block']} ... END_FUNCTION_BLOCK in candidate.st, including necessary TYPE definitions. Use exactly the specified interface.
After each source version run: powershell -NoProfile -ExecutionPolicy Bypass -File check.ps1
Use the checker diagnostics to repair your own ST. Never edit requirements.md, policy.md or check.ps1.
There are at most 6 submitted source versions (initial candidate plus 5 repairs), 24 model requests and 1800 seconds. Stop on pass or any budget limit. Rechecking identical source does not add a version.
Finish with the status and a short explanation. Do not claim success without checker evidence.
"""
    (workspace / "prompt.txt").write_text(prompt, encoding="utf-8")
    (home / "config.toml").write_text(f'''model = "{model}"
model_provider = "litellm"
approval_policy = "never"
sandbox_mode = "workspace-write"
model_context_window = 128000
[model_providers.litellm]
name = "local LiteLLM"
base_url = "http://127.0.0.1:4000/v1"
env_key = "PLC_CODEX_KEY"
wire_api = "{'chat' if model.startswith('deepseek') else 'responses'}"
request_max_retries = 0
stream_max_retries = 0
''', encoding="utf-8")
    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    env["PLC_CODEX_KEY"] = "sk-local"
    env["PYTHONPATH"] = str(R8)
    env["PATH"] = str(NODE_BIN) + os.pathsep + str(RUNTIME_BIN) + os.pathsep + env.get("PATH", "")
    cmd = ["cmd", "/c", str(CODEX), "exec", "-C", str(workspace), "--skip-git-repo-check",
           "-s", "workspace-write", "--json", "-o", str(workspace / "final.txt"), "-"]
    started = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(cmd, cwd=workspace, env=env, input=prompt, text=True,
                              encoding="utf-8", errors="replace", capture_output=True, timeout=1800)
        stdout, stderr = proc.stdout, proc.stderr
        code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = exc.stdout or "", exc.stderr or ""
        code = None
        timed_out = True
    (workspace / "agent.log").write_text(stdout + "\n" + stderr, encoding="utf-8")
    candidate = workspace / "candidate.st"
    if candidate.is_file():
        try:
            result = dataset.evaluate(candidate, task)
        except Exception as exc:  # noqa: BLE001
            result = {"status": "invalid_candidate", "message": str(exc)}
    else:
        result = {"status": "missing_candidate"}
    OUT.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema": "codex-dataset-run-v1",
        "task_id": task_id,
        "model": model,
        "workspace": str(workspace),
        "timed_out": timed_out,
        "exit_code": code,
        "seconds": round(time.monotonic() - started, 2),
        "status": result.get("status"),
        "summary": result.get("summary"),
        "first_failure": result.get("first_failure"),
    }
    path = OUT / f"{task_id}_{model}_{run_id}.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
