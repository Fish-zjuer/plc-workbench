"""Compile arbitrary ST units; never imply unknown-interface behavior was tested."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil

from plc_probe.backend import BackendError, _command
from plc_probe.config import VERSION, cache_dir, toolchain_dir
from .storage import atomic_json


def compile_unit(source: Path) -> dict:
    if source.suffix.lower() != ".st" or source.stat().st_size > 2_000_000:
        raise ValueError("请选择 2 MB 以内的 ST 源文件")
    compiler = toolchain_dir() / ("strucpp.exe" if os.name == "nt" else "strucpp")
    cxx = os.environ.get("CXX") or shutil.which("g++")
    if not compiler.is_file() or not cxx:
        raise BackendError({"status": "missing_dependency", "message": "请先运行 plc_probe bootstrap 并准备 g++"})
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    key = hashlib.sha256(data + f"{VERSION}|{cxx}|compile-unit-v1".encode()).hexdigest()[:24]
    directory = cache_dir() / "builds" / ("unit_" + key)
    directory.mkdir(parents=True, exist_ok=True)
    metadata = directory / "unit_build.json"
    if not metadata.exists() or not (directory / "candidate.o").exists():
        (directory / "candidate.st").write_bytes(data)
        logs = [_command([str(compiler), "candidate.st", "-o", "candidate.cpp"], directory, "st_to_cpp")]
        include = os.path.relpath(toolchain_dir() / "runtime/include", directory)
        logs.append(_command([cxx, "-std=c++17", "-O1", "-I", include, "-c", "candidate.cpp", "-o", "candidate.o"], directory, "native_compile"))
        atomic_json(metadata, {"source_sha256": digest, "compiler_version": VERSION, "logs": logs})
    return {"status": "compiled_unit", "source_sha256": digest, "build_evidence": str(metadata),
            "behavior_tested": False, "codesys_compile": "not_executed",
            "message": "实际完成 ST→C++→目标文件编译；未检查功能行为，未链接外部用户库。"}
