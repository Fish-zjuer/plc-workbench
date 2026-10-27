"""Frozen PLC task data and bounded, declarative test contracts."""
from __future__ import annotations
import copy
import hashlib
import json
import math
import re

SCHEMA="plc-task-v1"
TARGETS=("offline","codesys","portable")
RANGES={"SINT":(-128,127),"USINT":(0,255),"BYTE":(0,255),"INT":(-32768,32767),
        "UINT":(0,65535),"WORD":(0,65535),"DINT":(-2147483648,2147483647),
        "UDINT":(0,4294967295),"DWORD":(0,4294967295),"TIME":(0,4294967295),
        "LTIME":(0,9000000000000)}
SCALARS={*RANGES,"BOOL","REAL","LREAL"}
OPS={"eq","ne","lt","le","gt","ge"}
RESERVED=set('VAR VAR_INPUT VAR_OUTPUT VAR_IN_OUT END_VAR FUNCTION FUNCTION_BLOCK END_FUNCTION END_FUNCTION_BLOCK PROGRAM END_PROGRAM TYPE END_TYPE STRUCT END_STRUCT IF THEN ELSE ELSIF END_IF FOR TO BY DO END_FOR WHILE END_WHILE REPEAT UNTIL END_REPEAT CASE OF END_CASE RETURN EXIT TRUE FALSE AND OR NOT XOR MOD'.split()) | SCALARS
SAMPLING=("Fresh FB per scenario; all inputs assigned each scan; outputs observed after invocation. "
          "Times and TIME/LTIME interface values are milliseconds. First eligible TON invocation "
          "has elapsed=0. No real-time/hardware claim.")

def digest(value):
    data=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()

def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,63}",value):
        raise ValueError("Names must be ASCII identifiers of 1..64 characters")
    if value.upper() in RESERVED:raise ValueError('Identifier is an ST keyword: '+value)
    return value

def fields(value,required,optional=()):
    if not isinstance(value,dict):raise ValueError('Expected an object with fields: '+', '.join(required))
    missing=set(required)-value.keys();unknown=value.keys()-set(required)-set(optional)
    if missing or unknown:
        raise ValueError('Invalid object fields: '+json.dumps({'missing':sorted(missing),'unknown':sorted(unknown),
            'required':list(required),'optional':list(optional)}))

def text(value,maximum=10000):
    if not isinstance(value,str) or not value.strip() or len(value)>maximum:
        raise ValueError(f"Expected nonempty text <= {maximum} characters")
    return value

def number(value,dtype):
    if dtype=="BOOL":
        if type(value) is not bool:raise ValueError("BOOL must be JSON true/false")
    elif dtype in RANGES:
        lo,hi=RANGES[dtype]
        if type(value) is not int or not lo<=value<=hi:raise ValueError(f"{dtype} outside [{lo},{hi}]")
    elif dtype in ("REAL","LREAL"):
        if type(value) not in (int,float) or not math.isfinite(value) or (dtype=="REAL" and abs(value)>3.4028234e38):
            raise ValueError("Need finite floating-point data in type range")
    elif value is None or not isinstance(value,(str,int,float,bool,list,dict)):
        raise ValueError("Unsupported-interface values must remain JSON data")
    return value

def ports(spec):
    return {n:t for section in ("inputs","outputs","inouts") for n,t in spec.get(section,{}).items()}

def reference_type(ref,spec):
    if ref=="time_ms":return "LTIME"
    if not isinstance(ref,str):raise ValueError("Invalid property reference")
    parts=ref.split(".")
    if parts[0]=="previous":parts=parts[1:]
    if len(parts)!=2 or parts[0] not in ("inputs","outputs") or parts[1] not in spec[parts[0]]:
        raise ValueError("Properties reference declared inputs/outputs, previous scan, or time_ms only")
    return spec[parts[0]][parts[1]]

def comparison(value,dtype):
    if isinstance(value,dict):
        fields(value,("op","value"))
        if value["op"] not in OPS or (dtype=="BOOL" and value["op"] not in ("eq","ne")):
            raise ValueError("Invalid comparison operator")
        number(value["value"],dtype)
    else:number(value,dtype)

def validate_case(case,spec):
    fields(case,("name","covers","trace"),("basis","scope"))
    text(case["name"],100)
    ids={r["id"] for r in spec["requirements"]}
    if not isinstance(case["covers"],list) or not case["covers"] or any(x not in ids for x in case["covers"]):
        raise ValueError("Scenario must cite declared requirement IDs")
    if "scope" in case and case["scope"] not in ("specified","ambiguous"):raise ValueError("Invalid review scope")
    if "basis" in case:text(case["basis"],2000)
    if not isinstance(case["trace"],list) or not 1<=len(case["trace"])<=2000:raise ValueError("Need 1..2000 scans per scenario")
    last=-1
    for row in case["trace"]:
        fields(row,("time_ms","inputs"),("expect",))
        t=row["time_ms"]
        if type(t) is not int or not last<t<=1000000000:raise ValueError("Scan times strictly increase in 0..1e9 ms")
        last=t
        if not isinstance(row["inputs"],dict) or set(row["inputs"])!=set(spec["inputs"]):
            raise ValueError("Every scan explicitly provides all inputs")
        for name,value in row["inputs"].items():number(value,spec["inputs"][name])
        if "expect" in row:
            if not isinstance(row["expect"],dict) or row["expect"].keys()-spec["outputs"].keys():
                raise ValueError("Checks must name declared outputs")
            for name,value in row["expect"].items():comparison(value,spec["outputs"][name])

def validate_spec(raw):
    spec=copy.deepcopy(raw)
    fields(spec,("schema","title","block","target","requirements","inputs","outputs","scenarios"),
           ("inouts","properties","assumptions","questions","tolerance","executor"))
    if spec["schema"]!=SCHEMA or spec["target"] not in TARGETS:raise ValueError("Unknown schema or target")
    text(spec["title"],200);identifier(spec["block"])
    spec.setdefault('executor','offline');identifier(spec['executor'])
    for key,default in (("inouts",{}),("properties",[]),("assumptions",[]),("questions",[]),("tolerance",0.000001)):
        spec.setdefault(key,default)
    tol=spec["tolerance"]
    if type(tol) not in (int,float) or not math.isfinite(tol) or not 0<=tol<=0.01:raise ValueError("Tolerance must be in [0,0.01]")
    names=[]
    for section in ("inputs","outputs","inouts"):
        mapping=spec[section]
        if not isinstance(mapping,dict) or len(mapping)>32:raise ValueError("Each port direction allows <=32 ports")
        for name,dtype in mapping.items():
            identifier(name);text(dtype,100)
            if not re.fullmatch(r"[A-Za-z_0-9\[\].,* ]+",dtype):raise ValueError("Invalid interface type")
            mapping[name]=re.sub(r"\s+","",dtype).upper();names.append(name.upper())
    if not spec["outputs"] or len(set(names))!=len(names):raise ValueError("Need outputs and unique case-insensitive port names")
    if not isinstance(spec["requirements"],list) or not 1<=len(spec["requirements"])<=40:raise ValueError("Need 1..40 requirements")
    ids=set()
    for req in spec["requirements"]:
        fields(req,("id","text"));identifier(req["id"]);text(req["text"])
        if req["id"] in ids:raise ValueError("Duplicate requirement ID")
        ids.add(req["id"])
    for key in ("assumptions","questions"):
        if not isinstance(spec[key],list) or len(spec[key])>20:raise ValueError("Too many assumptions/questions")
        for item in spec[key]:text(item,2000)
    if not isinstance(spec["properties"],list) or len(spec["properties"])>40:raise ValueError("Too many properties")
    prop_ids=set()
    for prop in spec["properties"]:
        fields(prop,("id","requirement","when","then"));identifier(prop["id"])
        if prop["id"] in prop_ids or prop["requirement"] not in ids:raise ValueError("Invalid property identity/basis")
        prop_ids.add(prop["id"])
        if not isinstance(prop["when"],dict) or not isinstance(prop["then"],dict) or not prop["then"]:
            raise ValueError("Property when/then must be maps; then cannot be empty")
        if len(prop["when"])+len(prop["then"])>32:raise ValueError("Property too large")
        for side in ("when","then"):
            for ref,expected in prop[side].items():comparison(expected,reference_type(ref,spec))
    cases=spec["scenarios"]
    if not isinstance(cases,list) or not 1<=len(cases)<=64:raise ValueError("Need 1..64 scenarios")
    covered=set();case_names=set();scans=0
    for case in cases:
        validate_case(case,spec)
        if case["name"] in case_names:raise ValueError("Duplicate scenario name")
        case_names.add(case["name"]);covered.update(case["covers"]);scans+=len(case["trace"])
        if not any(row.get("expect") for row in case["trace"]):raise ValueError("Every baseline scenario needs an explicit check")
    if ids-covered:raise ValueError("Requirements without declared scenarios: "+", ".join(sorted(ids-covered)))
    if scans>10000:raise ValueError("Task exceeds 10000 scans")
    if len(json.dumps(spec,ensure_ascii=False,allow_nan=False).encode())>800000:raise ValueError("Contract exceeds 800 KB")
    return spec

def clean_st(code):
    return re.sub(r"'(?:[^']|'')*'|\(\*.*?\*\)|//[^\n]*"," ",code,flags=re.S)

def validate_source(code,spec):
    if not isinstance(code,str) or not 20<=len(code)<=150000:raise ValueError("Need complete ST, 20..150000 characters")
    clean=clean_st(code)
    mains=list(re.finditer(r"\bFUNCTION_BLOCK\s+"+re.escape(spec["block"])+r"\b(.*?)\bEND_FUNCTION_BLOCK\b",clean,re.I|re.S))
    if len(mains)!=1:raise ValueError("Need exactly one complete FUNCTION_BLOCK "+spec["block"])
    declared={}
    for kind,body in re.findall(r"\b(VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT)\b(.*?)\bEND_VAR\b",mains[0][1],re.I|re.S):
        direction={"VAR_INPUT":"inputs","VAR_OUTPUT":"outputs","VAR_IN_OUT":"inouts"}[kind.upper()]
        for names,dtype in re.findall(r"\b([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*:\s*([^;:=]+)(?::=[^;]*)?;",body):
            for name in names.split(","):
                key=(direction,name.strip().upper())
                if key in declared:raise ValueError("Duplicate interface port")
                declared[key]=re.sub(r"\s+","",dtype).upper()
    expected={(s,n.upper()):t for s in ("inputs","outputs","inouts") for n,t in spec[s].items()}
    if declared!=expected:raise ValueError("Candidate changed the frozen task interface")

def capability_report(spec,code=""):
    from .backend_r4 import info
    active=info();blockers=[]
    if spec["inouts"]:
        blockers.append({"feature":"reference_bridge","message":"General scan bridge does not bind VAR_IN_OUT; no value-copy substitution.",
                         "actions":["Use a separately validated reference bridge","Add a typed adapter and test aliasing"]})
    missing=sorted(set(ports(spec).values())-SCALARS)
    if missing:
        blockers.append({"feature":"interface_bridge","types":missing,"message":"No general scan bridge for these declared types.",
                         "actions":["Keep the original contract; select/implement a matching adapter",
                                    "Create a separately named typed alternative, without counting it as original completion"]})
    if "LTIME" in ports(spec).values() and not active:
        blockers.append({"feature":"ltime_backend","message":"Local LTIME execution needs R4.","actions":["Build/select the pinned R4 backend"]})
    if spec["target"]!="offline":
        calls=sorted(set(re.findall(r"\b(PV_COUNT|PV_COMPATIBLE|PV_READ|PV_WRITE)\s*\(",clean_st(code),re.I)))
        if calls or "VARIANT" in ports(spec).values():
            blockers.append({"feature":"local_pv1_dependency","message":"Local PV1 support cannot establish vendor compatibility.",
                             "symbols":calls,"actions":["Keep the original interface unresolved",
                             "Develop a separately named platform adapter or an explicit typed alternative"]})
    return {"status":"blocked" if blockers else "ready_for_offline_checks","target":spec["target"],
            "executor":active["label"] if active else "STruC++ 0.7.0 + g++",
            "backend_fingerprint":active["fingerprint"] if active else None,
            "target_compile":"not_executed","blockers":blockers,"sampling":SAMPLING,
            "scope":"Local finite checks only; target-platform compile/execution is a separate evidence stage."}

def render_plan(spec):
    lines=[f"# {spec['title']}","",f"目标：{spec['target']} / 功能块：{spec['block']}","",
           "流程：完整 ST → 固定扫描检查 → 独立反例审查 → 带验证记录的交付包。","","## 接口",""]
    for section in ("inputs","outputs","inouts"):
        lines.extend(f"- {section}: {name}: {dtype}" for name,dtype in spec[section].items())
    lines+=["","## 需求及检查",""]
    for req in spec["requirements"]:
        cases=[c["name"] for c in spec["scenarios"] if req["id"] in c["covers"]]
        lines.append(f"- {req['id']}: {req['text']}；场景：{', '.join(cases)}")
    lines+=["","## 扫描约定","",SAMPLING,"","## 假设",""]+["- "+x for x in spec["assumptions"]]
    lines+=["","## 待回答问题",""]+["- "+x for x in spec["questions"]]
    lines+=["","## 预期检查（完整数据见 contract.json）",""]
    for case in spec["scenarios"]:
        lines.append(f"- {case['name']}: {len(case['trace'])} 扫描")
        for row in case["trace"]:
            if row.get("expect"):
                lines.append(f"  - {row['time_ms']} ms，输入 {json.dumps(row['inputs'],ensure_ascii=False)} → {json.dumps(row['expect'],ensure_ascii=False)}")
    return "\n".join(lines)+"\n"
