from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from .config import VERSION, cache_dir, toolchain_dir, save_json
from .contracts import Monitor, PROFILES, validate_trace


class BackendError(RuntimeError):
    def __init__(self, result: dict):
        self.result = result
        super().__init__(result.get("message", result["status"]))


@dataclass
class Artifact:
    profile: str
    source: str
    sha256: str
    directory: Path
    executable: Path
    evidence: dict


def _driver(profile: str) -> str:
    spec = PROFILES[profile]
    kinds = spec.input_kinds or ("int",) * len(spec.inputs)
    output_kinds = spec.output_kinds or ("int",) * len(spec.outputs)
    types = {"str": "std::string", "float": "double", "int": "long long"}
    variables = "\n".join(f"        {types[kind]} v{i};" for i, kind in enumerate(kinds))
    reads = " >> ".join(f"std::quoted(v{i})" if kind == "str" else f"v{i}" for i, kind in enumerate(kinds))
    assignments = "\n".join(f"        uut->{name.upper()} = v{i}" + (".c_str();" if kind == "str" else ";") for i, (name, kind) in enumerate(zip(spec.inputs, kinds)))
    writes = ' << " " << '.join(f"static_cast<{'double' if kind == 'float' else 'unsigned long long'}>(strucpp::iec_unwrap(uut->{name.upper()}))" for name, kind in zip(spec.outputs, output_kinds))
    return f'''#include "candidate.hpp"
#include <iostream>
#include <iomanip>
#include <memory>
#include <string>
int main() {{
    auto uut = std::make_unique<strucpp::{spec.block}>();
    std::cout << std::setprecision(17);
    std::string command;
    while (std::cin >> command) {{
        if (command == "R") {{
            uut = std::make_unique<strucpp::{spec.block}>();
            strucpp::__CURRENT_TIME_NS = 0;
            continue;
        }}
        if (command != "S") return 2;
        long long time_ms;
{variables}
        if (!(std::cin >> time_ms >> {reads})) return 3;
        strucpp::__CURRENT_TIME_NS = time_ms * 1000000LL;
{assignments}
        (*uut)();
        std::cout << {writes} << "\\n";
    }}
    return 0;
}}
'''


def _command(args: list[str], directory: Path, phase: str, timeout: int = 45) -> dict:
    # Keep rebuildable compiler temporary files inside its build directory.
    # Relative spelling also avoids MinGW locale issues with Unicode Windows paths.
    (directory / ".tmp").mkdir(exist_ok=True)
    child_env = dict(os.environ, TEMP=".tmp", TMP=".tmp", TMPDIR=".tmp")
    try:
        done = subprocess.run(args, cwd=directory, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, env=child_env)
    except subprocess.TimeoutExpired as exc:
        raise BackendError({"status": "timeout", "phase": phase, "message": f"{phase} exceeded {timeout} seconds"}) from exc
    except OSError as exc:
        raise BackendError({"status": "tool_error", "phase": phase, "message": str(exc)}) from exc
    def bounded(value: str) -> str:
        return value if len(value) <= 8000 else value[:6000] + "\n... [full log saved separately] ...\n" + value[-2000:]
    diagnostics = []
    for match in re.finditer(r"^(.+?):(\d+):(\d+):\s*(fatal error|error|warning):\s*(.+)$", done.stderr, re.MULTILINE):
        record = {"file": match[1], "line": int(match[2]), "column": int(match[3]), "severity": match[4], "message": match[5]}
        if record not in diagnostics:
            diagnostics.append(record)
    log_path = directory / (phase + ".stderr.log")
    log_path.write_text(done.stderr, encoding="utf-8")
    result = {"phase": phase, "returncode": done.returncode,
              "stdout": bounded(done.stdout), "stderr": bounded(done.stderr),
              "primary_diagnostics": diagnostics[:5], "full_stderr_path": str(log_path)}
    if done.returncode:
        raise BackendError({"status": "compile_error", **result})
    return result


def compile_source(source: str | Path, profile: str) -> Artifact:
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile {profile}")
    path = Path(source).resolve()
    if path.suffix.lower() != ".st" or not path.is_file():
        raise ValueError("source must name an existing .st file")
    source_bytes = path.read_bytes()
    if len(source_bytes) > 2_000_000:
        raise ValueError("Source exceeds 2 MB")
    compiler = toolchain_dir() / ("strucpp.exe" if os.name == "nt" else "strucpp")
    cxx = os.environ.get("CXX") or shutil.which("g++")
    if not compiler.is_file() or not cxx:
        raise BackendError({"status": "missing_dependency", "message": "Run bootstrap; a g++ toolchain is also required."})
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    driver = _driver(profile)
    flags = ["-std=c++17", "-O1"] + (["-static"] if os.name == "nt" else [])
    build_key = hashlib.sha256(source_bytes + driver.encode() + f"{VERSION}|{cxx}|{flags}".encode()).hexdigest()[:24]
    directory = cache_dir() / "builds" / build_key
    directory.mkdir(parents=True, exist_ok=True)
    exe = directory / ("scan_driver.exe" if os.name == "nt" else "scan_driver")
    metadata = directory / "build.json"
    if not exe.exists() or not metadata.exists():
        (directory / "candidate.st").write_bytes(source_bytes)
        (directory / "scan_driver.cpp").write_text(driver, encoding="utf-8")
        logs = [_command([str(compiler), "candidate.st", "-o", "candidate.cpp"], directory, "st_to_cpp")]
        include = os.path.relpath(toolchain_dir() / "runtime" / "include", directory)
        logs.append(_command([cxx, *flags, "-I", include,
                              "candidate.cpp", "scan_driver.cpp", "-o", exe.name], directory, "native_compile"))
        save_json(metadata, {"backend": f"STruC++ {VERSION} + g++", "profile": profile,
                             "source_sha256": source_sha, "logs": logs})
    evidence = json.loads(metadata.read_text(encoding="utf-8"))
    return Artifact(profile, str(path), source_sha, directory, exe, evidence)


def run_batch(artifact: Artifact, scenarios: list[dict], timeout_seconds: float = 20) -> list[dict]:
    if not 0 < timeout_seconds <= 30:
        raise ValueError("Execution timeout must be in (0, 30] seconds")
    if not scenarios or len(scenarios) > 10000:
        raise ValueError("A batch must contain 1..10000 scenarios")
    total = sum(len(s.get("trace", [])) for s in scenarios)
    if total > 250000:
        raise ValueError("A batch may contain at most 250000 scans")
    spec = PROFILES[artifact.profile]
    input_kinds = spec.input_kinds or ("int",) * len(spec.inputs)
    output_kinds = spec.output_kinds or ("int",) * len(spec.outputs)
    commands = []
    for scenario in scenarios:
        validate_trace(artifact.profile, scenario["trace"])
        commands.append("R")
        for row in scenario["trace"]:
            values = []
            for name, kind in zip(spec.inputs, input_kinds):
                value = row["inputs"][name]
                values.append(json.dumps(value) if kind == "str" else repr(float(value)) if kind == "float" else str(int(value)))
            commands.append("S " + str(row["time_ms"]) + " " + " ".join(values))
    try:
        done = subprocess.run([str(artifact.executable)], input="\n".join(commands) + "\n",
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout_seconds, cwd=artifact.directory)
    except subprocess.TimeoutExpired as exc:
        raise BackendError({"status": "timeout", "phase": "execution", "message": f"Trace execution exceeded {timeout_seconds} seconds"}) from exc
    if done.returncode:
        raise BackendError({"status": "runtime_error", "returncode": done.returncode, "stderr": done.stderr[-4000:]})
    lines = done.stdout.splitlines()
    if len(lines) != total:
        raise BackendError({"status": "protocol_error", "message": f"Expected {total} output rows, received {len(lines)}"})
    results, cursor = [], 0
    for scenario in scenarios:
        monitor = Monitor(artifact.profile)
        rows, first = [], None
        for index, row in enumerate(scenario["trace"]):
            try:
                tokens = lines[cursor].split()
                if len(tokens) != len(spec.outputs):
                    raise ValueError("Wrong output arity")
                values = [float(x) if kind == "float" else int(x) for x, kind in zip(tokens, output_kinds)]
                if len(values) != len(spec.outputs):
                    raise ValueError("Wrong output arity")
            except ValueError as exc:
                raise BackendError({"status": "protocol_error", "message": str(exc)}) from exc
            cursor += 1
            actual = dict(zip(spec.outputs, values))
            expected, violations = monitor.observe(row, actual)
            rows.append({**row, "actual": actual, "expected": expected, "violations": violations})
            if first is None and violations:
                first = {"scan": index, "time_ms": row["time_ms"], **violations[0]}
        results.append({"name": scenario["name"], "family": scenario.get("family", "custom"),
                        "status": "fail" if first else "pass", "first_failure": first, "rows": rows})
    return results
