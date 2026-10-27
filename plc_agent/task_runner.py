"""Compile and execute arbitrary scalar FB contracts, without installing global profiles."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from functools import lru_cache

from plc_probe.backend import BackendError, _command
from plc_probe.config import cache_dir, toolchain_dir
from .provider import Cancelled
from .task_spec import SCALARS, SAMPLING, digest, validate_case, validate_source
from .storage import atomic_json

@dataclass
class TaskArtifact:
    executable: Path
    directory: Path
    source_sha256: str
    execution_fingerprint: str

def execution_fingerprint():
    home=toolchain_dir()
    names=[home/("strucpp.exe" if os.name=="nt" else "strucpp"),home/"compiler.cjs"]
    names+=sorted((home/"runtime/include").rglob("*.hpp"))+sorted((home/"libs").glob("*.stlib"))
    names += [Path(__file__),*(Path(__file__).with_name(n) for n in ('task_spec.py','task_backend.py','task_workflow.py','task_store.py')),
              Path(__file__).parents[1]/'plc_probe/backend.py',Path(__file__).parents[1]/'plc_probe/config.py']
    for name in ('node-path.txt','cli-path.txt'):
        pointer=home/name
        if pointer.is_file():
            names.append(pointer)
            actual=Path(pointer.read_text(encoding='utf-8').strip())
            if actual.is_file():names.append(actual)
    cxx=os.environ.get("CXX") or shutil.which("g++")
    if cxx and Path(cxx).is_file():names.append(Path(cxx))
    signature=tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in names if p.is_file())
    return _execution_identity(signature)

@lru_cache(maxsize=8)
def _execution_identity(signature):
    return digest({name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name,_,_ in signature})

def driver(spec):
    if spec["inouts"] or any(t not in SCALARS for group in ("inputs","outputs") for t in spec[group].values()):
        raise ValueError("No scalar bridge for the unchanged declared interface")
    ins=list(spec["inputs"].items());outs=list(spec["outputs"].items())
    variables="\n".join(f"{'double' if t in ('REAL','LREAL') else 'long long'} v{i};" for i,(_,t) in enumerate(ins))
    reads=" >> ".join(["t"]+["v"+str(i) for i in range(len(ins))])
    assignments="\n".join(f"uut->{name.upper()} = v{i}"+(" * 1000000LL;" if t in ("TIME","LTIME") else ";") for i,(name,t) in enumerate(ins))
    writes=' << " " << '.join("static_cast<"+("double" if t in ("REAL","LREAL","TIME","LTIME") else "long long")+">(strucpp::iec_unwrap(uut->"+name.upper()+"))"+(" / 1000000.0" if t in ("TIME","LTIME") else "") for name,t in outs)
    return f'''#include "candidate.hpp"
#include <iostream>
#include <iomanip>
#include <memory>
#include <string>
int main(){{
  auto uut=std::make_unique<strucpp::{spec["block"].upper()}>();
  std::cout<<std::setprecision(17);
  std::string command;
  while(std::cin>>command){{
    if(command=="R"){{uut=std::make_unique<strucpp::{spec["block"].upper()}>();strucpp::__CURRENT_TIME_NS=0;continue;}}
    if(command!="S")return 2;
    long long t;
    {variables}
    if(!(std::cin >> {reads}))return 3;
    strucpp::__CURRENT_TIME_NS=t*1000000LL;
    {assignments}
    (*uut)();
    std::cout << {writes} << "\\n";
  }}
}}'''

def compile_task(source,spec):
    source=Path(source)
    data=source.read_bytes()
    validate_source(data.decode("utf-8-sig"),spec)
    bridge=driver(spec)
    cxx=os.environ.get("CXX") or shutil.which("g++")
    compiler=toolchain_dir()/("strucpp.exe" if os.name=="nt" else "strucpp")
    if not cxx or not compiler.is_file():
        raise BackendError({"status":"missing_dependency","message":"Build/select STruC++ and provide a C++17 g++ compiler."})
    fingerprint=execution_fingerprint()
    parent=cache_dir()/"task_builds";parent.mkdir(parents=True,exist_ok=True)
    # Separate directories avoid cross-project cache races and partial executable reuse.
    directory=Path(tempfile.mkdtemp(prefix="task_",dir=parent))
    exe=directory/("runner.exe" if os.name=="nt" else "runner")
    (directory/"candidate.st").write_bytes(data)
    (directory/"runner.cpp").write_text(bridge,encoding="utf-8")
    logs=[_command([str(compiler),"candidate.st","-o","candidate.cpp"],directory,"st_to_cpp")]
    flags=["-std=c++17","-O1"]+(["-static"] if os.name=="nt" else [])
    include=os.path.relpath(toolchain_dir()/"runtime/include",directory)
    logs.append(_command([cxx,*flags,"-I",include,"candidate.cpp","runner.cpp","-o",exe.name],directory,"native_compile"))
    if execution_fingerprint()!=fingerprint:
        raise BackendError({"status":"backend_changed","message":"Backend changed during compilation; result invalidated."})
    source_sha=hashlib.sha256(data).hexdigest()
    atomic_json(directory/"build.json",{"source_sha256":source_sha,"contract_sha256":digest(spec),
                "execution_fingerprint":fingerprint,"driver_sha256":hashlib.sha256(bridge.encode()).hexdigest(),"logs":logs})
    return TaskArtifact(exe,directory,source_sha,fingerprint)

def compare(actual,expected,tolerance):
    op,value=(expected["op"],expected["value"]) if isinstance(expected,dict) else ("eq",expected)
    equal=actual==value
    if type(actual) in (int,float) and type(value) in (int,float) and (isinstance(actual,float) or isinstance(value,float)):
        equal=math.isclose(actual,value,abs_tol=tolerance,rel_tol=0)
    if op=="eq":return equal
    if op=="ne":return not equal
    return {"lt":lambda:actual<value,"le":lambda:actual<=value,
            "gt":lambda:actual>value,"ge":lambda:actual>=value}[op]()

def lookup(ref,row,previous):
    if ref.startswith("previous."):
        if previous is None:return None
        return lookup(ref[len("previous."):],previous,None)
    if ref=="time_ms":return row["time_ms"]
    group,name=ref.split(".")
    return row["inputs" if group=="inputs" else "actual"][name]

def monitor(spec,cases,actual_rows,include_expect=True):
    expected_count=sum(len(c["trace"]) for c in cases)
    if len(actual_rows)!=expected_count:raise ValueError("Wrong scan count")
    cursor=0;results=[];activations={p["id"]:0 for p in spec["properties"]};assertions=0
    for case in cases:
        previous=None;rows=[];first=None
        for index,scan in enumerate(case["trace"]):
            actual=actual_rows[cursor];cursor+=1
            row={**scan,"actual":actual};violations=[]
            if include_expect:
                for name,expected in scan.get("expect",{}).items():
                    assertions+=1
                    if not compare(actual[name],expected,spec["tolerance"]):
                        violations.append({"kind":"example","output":name,"expected":expected,"actual":actual[name]})
            for prop in spec["properties"]:
                if previous is None and any(k.startswith("previous.") for side in ("when","then") for k in prop[side]):continue
                if all(compare(lookup(ref,row,previous),expected,spec["tolerance"]) for ref,expected in prop["when"].items()):
                    activations[prop["id"]]+=1
                    for ref,expected in prop["then"].items():
                        assertions+=1;value=lookup(ref,row,previous)
                        if not compare(value,expected,spec["tolerance"]):
                            violations.append({"kind":"property","property":prop["id"],"requirement":prop["requirement"],
                                               "output":ref,"expected":expected,"actual":value})
            row["violations"]=violations;rows.append(row)
            if first is None and violations:first={"scan":index,"time_ms":scan["time_ms"],**violations[0]}
            previous=row
        results.append({"name":case["name"],"covers":case["covers"],"status":"fail" if first else "pass",
                        "first_failure":first,"rows":rows})
    return {"status":"fail" if any(c["first_failure"] for c in results) else "pass",
            "cases":results,"summary":{"scenarios":len(cases),"scans":expected_count,"assertions":assertions,
            "failed":sum(c["status"]=="fail" for c in results),"property_activations":activations}}

def execute_task(artifact,spec,cases,cancel_event=None,include_expect=True,timeout=15):
    if len(cases)>128 or not 1<=sum(len(c["trace"]) for c in cases)<=20000:raise ValueError("Execution scan budget exceeded")
    commands=[]
    for case in cases:
        validate_case(case,spec);commands.append("R")
        for row in case["trace"]:
            # Contract map order, independent of JSON property order in an uploaded scan.
            values=[str(int(row["inputs"][n])) if spec["inputs"][n]=="BOOL" else repr(row["inputs"][n]) for n in spec["inputs"]]
            commands.append("S "+str(row["time_ms"])+" "+" ".join(values))
    if cancel_event and cancel_event.is_set():raise Cancelled("Task cancelled before execution")
    started=time.monotonic()
    process=subprocess.Popen([str(artifact.executable)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             cwd=artifact.directory,text=True,encoding="utf-8",errors="replace")
    payload="\n".join(commands)+"\n";first=True
    try:
        while True:
            if cancel_event and cancel_event.is_set():raise Cancelled("Task scan execution cancelled")
            if time.monotonic()-started>timeout:
                raise BackendError({"status":"timeout","phase":"execution","message":"Task exceeded bounded scan execution time"})
            try:
                out,err=process.communicate(payload if first else None,timeout=.2);break
            except subprocess.TimeoutExpired:first=False
    finally:
        if process.poll() is None:process.kill();process.communicate()
    if process.returncode:
        raise BackendError({"status":"runtime_error","returncode":process.returncode,"stderr":err[-4000:]})
    lines=out.splitlines()
    if len(lines)!=sum(len(c["trace"]) for c in cases):
        raise BackendError({"status":"protocol_error","message":"Unexpected output scan count"})
    actual=[]
    for line in lines:
        tokens=line.split()
        if len(tokens)!=len(spec["outputs"]):raise BackendError({"status":"protocol_error","message":"Unexpected output arity"})
        row={}
        for (name,dtype),value in zip(spec["outputs"].items(),tokens):
            try:
                parsed=float(value) if dtype in ("REAL","LREAL","TIME","LTIME") else int(value)
                if not math.isfinite(parsed) or (dtype=="BOOL" and parsed not in (0,1)):raise ValueError()
                row[name]=bool(parsed) if dtype=="BOOL" else parsed
            except ValueError:raise BackendError({"status":"protocol_error","message":"Invalid or nonfinite output"}) from None
        actual.append(row)
    return monitor(spec,cases,actual,include_expect)

def evaluate_task(source,spec,cancel_event=None,extra_cases=()):
    artifact=compile_task(source,spec)
    cases=spec["scenarios"]+list(extra_cases)
    result=execute_task(artifact,spec,cases,cancel_event)
    if result["status"]=="pass" and any(n==0 for n in result["summary"]["property_activations"].values()):
        result["status"]="coverage_gap"
    result.update(source_sha256=artifact.source_sha256,contract_sha256=digest(spec),
                  execution_fingerprint=artifact.execution_fingerprint,behavior_tested=True,
                  target_compile="not_executed",build_evidence=str(artifact.directory/"build.json"),sampling=SAMPLING)
    return result,artifact
