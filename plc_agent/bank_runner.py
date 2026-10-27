"""Native ST execution for the declared simple interfaces in the public bank."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess

from plc_probe.backend import BackendError, _command
from plc_probe.config import VERSION, cache_dir, toolchain_dir
from plc_probe.tools import probe
from .bank_contracts import KNOWN, UNSUPPORTED, block, interface, questions, scenarios
from .compile_unit import compile_unit
from .storage import atomic_json


def _access(field):
    match = re.fullmatch(r"([A-Za-z_][A-Za-z_0-9]*)(?:\[(-?\d+)\])?",field)
    if not match:
        raise ValueError("Invalid fixed interface field")
    return "uut->" + match[1].upper() + (f".at({match[2]})" if match[2] else "")


def driver(question):
    inputs, outputs = interface(question)
    if any(t.startswith(("ARRAY", "STRING")) or t not in {"BOOL","INT","USINT","UINT","DINT","UDINT","REAL","LREAL","WORD","DWORD","TIME","LTIME"} for t in [*inputs.values(),*outputs.values()]):
        raise ValueError("Unsupported generic bridge type")
    variables = "\n".join(f"{'double' if t in ('REAL','LREAL') else 'long long'} v{i};" for i,t in enumerate(inputs.values()))
    assignments = "\n".join(f"{_access(name)} = v{i}" + (" * 1000000LL;" if t in ("TIME","LTIME") else ";") for i,(name,t) in enumerate(inputs.items()))
    writes = ' << " " << '.join(f"static_cast<{'double' if t in ('REAL','LREAL','TIME','LTIME') else 'long long'}>(strucpp::iec_unwrap({_access(name)}))" + (" / 1000000.0" if t in ("TIME","LTIME") else "") for name,t in outputs.items())
    return f'''#include "candidate.hpp"
#include <iostream>
#include <iomanip>
#include <memory>
#include <string>
int main() {{
auto uut = std::make_unique<strucpp::{block(question['id']).upper()}>();
std::cout << std::setprecision(17);
std::string command;
while (std::cin >> command) {{
 if(command=="R") {{ uut=std::make_unique<strucpp::{block(question['id']).upper()}>(); strucpp::__CURRENT_TIME_NS=0; continue; }}
 if(command!="S") return 2;
 long long t;
 {variables}
 if(!(std::cin >> t >> {' >> '.join('v'+str(i) for i in range(len(inputs)))})) return 3;
 strucpp::__CURRENT_TIME_NS=t*1000000LL;
 {assignments}
 (*uut)();
 std::cout << {writes} << "\\n";
}}
}}
'''


def _compile(source, question):
    code = source.read_bytes()
    bridge = driver(question)
    cxx = os.environ.get("CXX") or shutil.which("g++")
    compiler = toolchain_dir() / ("strucpp.exe" if os.name == "nt" else "strucpp")
    if not cxx or not compiler.is_file():
        raise BackendError({"status":"missing_dependency","message":"Need STruC++ and g++"})
    key = hashlib.sha256(code+bridge.encode()+f"{VERSION}|{cxx}".encode()).hexdigest()[:24]
    directory = cache_dir()/"builds"/("bank_"+key)
    directory.mkdir(parents=True,exist_ok=True)
    exe = directory/("runner.exe" if os.name=="nt" else "runner")
    meta = directory/"build.json"
    if not exe.exists() or not meta.exists():
        (directory/"candidate.st").write_bytes(code)
        (directory/"runner.cpp").write_text(bridge,encoding="utf-8")
        logs=[_command([str(compiler),"candidate.st","-o","candidate.cpp"],directory,"st_to_cpp")]
        flags=["-std=c++17","-O1"]+(["-static"] if os.name=="nt" else [])
        include=os.path.relpath(toolchain_dir()/"runtime/include",directory)
        logs.append(_command([cxx,*flags,"-I",include,"candidate.cpp","runner.cpp","-o",exe.name],directory,"native_compile"))
        atomic_json(meta,{"source_sha256":hashlib.sha256(code).hexdigest(),"question_id":question["id"],"logs":logs})
    return exe,meta


def test_bank(source: Path, question_id: str):
    source=Path(source).resolve()
    if not source.is_file() or source.suffix.lower()!=".st" or source.stat().st_size>2_000_000:
        raise ValueError("Expected existing ST file <= 2 MB")
    question=next(q for q in questions() if q["id"]==question_id)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    if question_id in UNSUPPORTED:
        compiled=compile_unit(source)
        return {**compiled,"status":"behavior_not_supported","compile_status":"compiled_unit","question_id":question_id,
                "reason":UNSUPPORTED[question_id],"source_sha256":digest,"behavior_tested":False}
    if question_id in KNOWN:
        checks=[probe(str(source),KNOWN[question_id],suite,20261026,shrink_budget=20) for suite in ("normal","focused","random")]
        result={"status":"fail" if any(c["status"]=="fail" for c in checks) else "pass","question_id":question_id,"source_sha256":digest,
                "summary":{"scenarios":sum(c["summary"]["scenarios"] for c in checks),"scans":sum(c["summary"]["scans"] for c in checks),
                           "failed":sum(c["summary"]["failed"] for c in checks)},"suites":checks,"behavior_tested":True}
        return result
    exe,meta=_compile(source,question)
    inputs,outputs=interface(question)
    tests=scenarios(question)
    commands=[]
    for case in tests:
        commands.append("R")
        for row in case["trace"]:
            commands.append("S "+str(row["time_ms"])+" "+" ".join(str(row["inputs"][name]) for name in inputs))
    try:
        executed=subprocess.run([str(exe)],input="\n".join(commands)+"\n",capture_output=True,text=True,encoding="utf-8",timeout=15,cwd=exe.parent)
    except subprocess.TimeoutExpired:
        raise BackendError({"status":"timeout","phase":"execution","message":"Finite bank scenarios exceeded 15 seconds"}) from None
    if executed.returncode:
        raise BackendError({"status":"runtime_error","phase":"execution","returncode":executed.returncode,"stderr":executed.stderr[:2000]})
    lines=executed.stdout.splitlines()
    if len(lines)!=sum(len(c["trace"]) for c in tests):
        raise BackendError({"status":"runtime_error","message":"Output scan count mismatch"})
    offset=0;results=[]
    for case in tests:
        rows=[];violations=[]
        for scan,row in enumerate(case["trace"]):
            fields=lines[offset].split();offset+=1
            if len(fields)!=len(outputs):
                raise BackendError({"status":"runtime_error","message":"Output field count mismatch"})
            actual={name:(float(token) if kind in ("REAL","LREAL","TIME","LTIME") else int(token)) for (name,kind),token in zip(outputs.items(),fields)}
            failures=[]
            for name,expected in row["expected"].items():
                tol=1e-9 if outputs[name]=="LREAL" else 1e-5 if outputs[name]=="REAL" else 0
                if not math.isclose(actual[name],expected,rel_tol=tol,abs_tol=tol):
                    failures.append({"output":name,"expected":expected,"actual":actual[name]})
            for invariant in case["invariants"]:
                if "not_both" in invariant and all(actual[name] for name in invariant["not_both"]):
                    failures.append({"property":"mutual_exclusion","outputs":invariant["not_both"],"actual":actual})
            rows.append({**row,"actual":actual,"violations":failures})
            violations.extend({"scan":scan,"time_ms":row["time_ms"],**failure} for failure in failures)
        results.append({"name":case["name"],"status":"fail" if violations else "pass","first_failure":violations[0] if violations else None,"rows":rows})
    return {"status":"fail" if any(r["status"]=="fail" for r in results) else "pass","question_id":question_id,
            "source_sha256":digest,"behavior_tested":True,"build_evidence":str(meta),
            "summary":{"scenarios":len(results),"scans":len(lines),"failed":sum(r["status"]=="fail" for r in results)},
            "first_failure":next(({"scenario":r["name"],**r["first_failure"]} for r in results if r["first_failure"]),None),
            "cases":results,"scope":"Sparse finite question-bank checks, not full correctness or CODESYS/formal proof"}
