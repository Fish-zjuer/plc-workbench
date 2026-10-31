"""Frozen external datasets, actual scan bridges, and finite supplied-test judgment.

Requirements are prompt data; expected tables stay in the host-side checker.
No arbitrary expressions from the supplied LTL are evaluated.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from .config import ROOT
from .storage import atomic_json
from .task_spec import digest,SCALARS
from .task_runner import execution_fingerprint
from plc_probe.config import cache_dir,toolchain_dir
from plc_probe.backend import BackendError,_command

DATA=ROOT/'datasets/standalone32'

def fingerprint():return digest({'native':execution_fingerprint(),'adapter':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})

def catalog():
    manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
    if manifest['schema']!='plc-dataset-v1':raise ValueError('Unknown dataset manifest')
    return manifest

def load(ident):
    if not re.fullmatch(r'(PUBLIC|CUSTOM)_\d\d',ident):raise ValueError('Use PUBLIC_01..20 or CUSTOM_01..12')
    entry=next((t for t in catalog()['tasks'] if t['id']==ident),None)
    if entry is None:raise ValueError('Unknown dataset task')
    path=(DATA/entry['file']).resolve()
    if not path.is_relative_to(DATA.resolve()):raise ValueError('Invalid dataset member')
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Dataset changed since manifest was frozen')
    task=json.loads(data);task['dataset_sha256']=entry['sha256']
    return task

def ports(task,direction):return {p['name']:p['type'].upper() for p in task['interface'] if p['direction']==direction}

def flatten(name,dtype):
    match=re.fullmatch(r'ARRAY\[(-?\d+)\.\.(-?\d+)\] OF (\w+)',dtype)
    if match:
        lo,hi,t=match.groups();lo=int(lo);hi=int(hi)
        if not 0<hi-lo+1<=128 or t not in SCALARS:raise ValueError('Unsupported fixed array interface')
        return [(f'{name}[{i}]',t) for i in range(lo,hi+1)]
    if dtype not in SCALARS and not re.fullmatch(r'STRING(?:\(\d+\))?',dtype):raise ValueError('Unsupported scalar interface '+dtype)
    return [(name,dtype)]

def access(name):
    m=re.fullmatch(r'([A-Za-z_]\w*)(?:\[(-?\d+)\])?',name)
    if not m:raise ValueError('Invalid driver field')
    return 'uut->'+m[1].upper()+(f'.at({m[2]})' if m[2] is not None else '')

def trace_driver(task):
    ins=[v for n,t in ports(task,'Input').items() for v in flatten(n,t)]
    outs=[v for n,t in ports(task,'Output').items() for v in flatten(n,t)]
    readonly=[('@input.'+n,t) for n,t in ins if '[' in n]
    variables=[];reads=['t'];assign=[]
    for i,(name,dtype) in enumerate(ins):
        string=dtype.startswith('STRING');kind='std::string' if string else 'double' if dtype in ('REAL','LREAL') else 'long long'
        variables.append(f'{kind} v{i};');reads.append(f'std::quoted(v{i})' if string else f'v{i}')
        assign.append(access(name)+f' = v{i}'+('.c_str();' if string else ' * 1000000LL;' if dtype in ('TIME','LTIME') else ';'))
    def output(name,dtype):
        expr=access(name.removeprefix('@input.'));real=dtype in ('REAL','LREAL','TIME','LTIME')
        return f'static_cast<{"double" if real else "long long"}>(strucpp::iec_unwrap({expr}))'+(' / 1000000.0' if dtype in ('TIME','LTIME') else '')
    writes=' << " " << '.join(output(n,t) for n,t in outs+readonly)
    bridge='''#include "candidate.hpp"
#include <iostream>
#include <iomanip>
#include <memory>
#include <string>
int main(){auto uut=std::make_unique<strucpp::BLOCK>();std::cout<<std::setprecision(17);std::string command;
while(std::cin>>command){if(command=="R"){uut=std::make_unique<strucpp::BLOCK>();strucpp::__CURRENT_TIME_NS=0;continue;}
if(command!="S")return 2;long long t; VARIABLES
if(!(std::cin >> READS))return 3;strucpp::__CURRENT_TIME_NS=t*1000000LL;
ASSIGN
(*uut)();std::cout << WRITES << "\\n";}}
'''
    for key,value in [('BLOCK',task['block'].upper()),('VARIABLES','\n'.join(variables)),('READS',' >> '.join(reads)),('ASSIGN','\n'.join(assign)),('WRITES',writes)]:bridge=bridge.replace(key,value)
    return bridge,ins,outs+readonly

def validate_source(source,task):
    from .st_source import split_units,mask_noncode
    code=Path(source).read_text(encoding='utf-8-sig')
    units=split_units(code);main=[u for u in units if u['kind']=='FUNCTION_BLOCK' and u['name'].upper()==task['block'].upper()]
    if len(main)!=1:raise ValueError('Expected exactly one complete '+task['block'])
    declared={}
    for direction,body in re.findall(r'\b(VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT)\b(.*?)\bEND_VAR\b',mask_noncode(main[0]['declaration']),re.I|re.S):
        for names,dtype in re.findall(r'\b([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*:\s*([^;:=]+)(?::=[^;]*)?;',body):
            for name in names.split(','):declared[(direction.upper(),name.strip().upper())]=re.sub(r'\s+','',dtype).upper()
    directions={'Input':'VAR_INPUT','Output':'VAR_OUTPUT','Input/Output':'VAR_IN_OUT'}
    expected={(directions[p['direction']],p['name'].upper()):re.sub(r'\s+','',p['type']).upper() for p in task['interface']}
    if declared!=expected:raise ValueError('Candidate changed the frozen dataset interface')

def compile_task(source,task):
    source=Path(source);validate_source(source,task)
    fmt=task['adapter_format'];qid=task['id'][-2:]
    if fmt=='struct_rows':
        from .struct_checks import driver
        bridge=driver(qid);ins=[];outs=task['field_order']['outputs']
    elif fmt in ('analog_reference_rows','fifo_reference_rows'):
        from .reference_checks import ANALOG_DRIVER,FIFO_DRIVER
        bridge=ANALOG_DRIVER if fmt=='analog_reference_rows' else FIFO_DRIVER;ins=[];outs=[]
    else:bridge,ins,outs=trace_driver(task)
    identity=fingerprint()
    data=source.read_bytes();key=hashlib.sha256(data+bridge.encode()+identity.encode()).hexdigest()[:24]
    directory=cache_dir()/'dataset_builds'/key;directory.mkdir(parents=True,exist_ok=True)
    exe=directory/('runner.exe' if os.name=='nt' else 'runner');meta=directory/'build.json'
    if not exe.is_file() or not meta.is_file():
        compiler=toolchain_dir()/('strucpp.exe' if os.name=='nt' else 'strucpp');cxx=os.environ.get('CXX') or shutil.which('g++')
        if not compiler.is_file() or not cxx:raise BackendError({'status':'missing_dependency','message':'Need selected STruC++ and g++'})
        (directory/'candidate.st').write_bytes(data);(directory/'driver.cpp').write_text(bridge,encoding='utf-8')
        logs=[_command([str(compiler),'candidate.st','-o','candidate.cpp'],directory,'st_to_cpp')]
        include=os.path.relpath(toolchain_dir()/'runtime/include',directory);flags=['-std=c++17','-O1']+(['-static'] if os.name=='nt' else [])
        logs.append(_command([cxx,*flags,'-I',include,'candidate.cpp','driver.cpp','-o',exe.name],directory,'native_compile'))
        atomic_json(meta,{'source_sha256':hashlib.sha256(data).hexdigest(),'execution_fingerprint':identity,'logs':logs})
    return {'executable':exe,'directory':directory,'source_sha256':hashlib.sha256(data).hexdigest(),'execution_fingerprint':identity,'inputs':ins,'outputs':outs,'build_evidence':str(meta)}

def input_value(row,name,task):
    if name in row['inputs']:return row['inputs'][name]
    m=re.fullmatch(r'(.+)\[(-?\d+)\]',name)
    dtype=ports(task,'Input')[m[1]];lo=int(re.search(r'\[(-?\d+)',dtype)[1])
    return row['inputs'][m[1]][int(m[2])-lo]

def token(value):
    if type(value) is bool:return str(int(value))
    if isinstance(value,str):return json.dumps(value)
    if isinstance(value,list):return ' '.join(token(v) for v in value)
    if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('Input must be a finite scalar')
    return str(value)

def commands(task,artifact):
    lines=[];fmt=task['adapter_format']
    for case in task['scenarios']:
        if fmt=='analog_reference_rows':lines.append('R '+' '.join(str(case[k]) for k in ('analog_length','analog_lower','channel_length','channel_lower')))
        elif fmt=='fifo_reference_rows':lines.append(f"R {case['kind']} {case['capacity']}")
        else:lines.append('R')
        if fmt=='struct_rows' and 'initial' in case:lines.append('D '+token([v for record in case['initial'] for v in record]))
        for row in case.get('trace',case.get('rows',[])):
            if fmt=='analog_reference_rows':values=[row['count'],*row['raw'],*[v for record in row['channels'] for v in record]]
            elif fmt=='fifo_reference_rows':values=[row['enqueue'],row['dequeue'],row['reset'],row['item']]
            elif fmt=='struct_rows':values=row['inputs']
            else:values=[row['time_ms'],*[input_value(row,n,task) for n,_ in artifact['inputs']]]
            lines.append('S '+' '.join(token(v) for v in values))
    return '\n'.join(lines)+'\n'

def equal(actual,expected,task,name=''):
    if isinstance(expected,list):return isinstance(actual,list) and len(actual)==len(expected) and all(equal(a,b,task,name) for a,b in zip(actual,expected))
    dtype=ports(task,'Output').get(name,'')
    if type(expected) is bool or (type(expected) is int and dtype not in ('REAL','LREAL')):return actual==expected
    if type(expected) in (int,float):
        if not math.isfinite(actual):return False
        tolerances=task.get('tolerance',{});default=1e-9 if dtype=='LREAL' else 1e-5
        absolute=tolerances.get(name,tolerances.get('default_absolute',default));relative=0 if task.get('original_id',task['id']).split('__')[-1].startswith('CUSTOM') else default
        if task['adapter_format']=='analog_reference_rows':absolute=relative=1e-6
        if task['adapter_format']=='fifo_reference_rows':absolute=relative=1e-6 if task.get('reference_kind')=='real' else 1e-12
        # Exact integer expectations are above; REAL transports round to IEEE binary32.
        return math.isclose(actual,expected,abs_tol=absolute,rel_tol=relative)
    return actual==expected

def evaluate(source,task):
    artifact=compile_task(source,task)
    try:run=subprocess.run([str(artifact['executable'])],input=commands(task,artifact),capture_output=True,text=True,encoding='utf-8',timeout=25,cwd=artifact['directory'])
    except subprocess.TimeoutExpired:raise BackendError({'status':'timeout','phase':'execution','message':'Dataset execution exceeded 25 seconds'}) from None
    if run.returncode:raise BackendError({'status':'runtime_error','phase':'execution','message':run.stderr[-2000:]})
    output=run.stdout.splitlines();total=sum(len(c.get('trace',c.get('rows',[]))) for c in task['scenarios'])
    if len(output)!=total:raise BackendError({'status':'protocol_error','message':'Dataset output row count mismatch'})
    results=[];cursor=assertions=0;fmt=task['adapter_format']
    for case in task['scenarios']:
        rows=[];first=None;previous_buffer=None
        check_task={**task,'reference_kind':case.get('kind')}
        for index,row in enumerate(case.get('trace',case.get('rows',[]))):
            values=[float(v) for v in output[cursor].split()];cursor+=1
            if not all(math.isfinite(v) for v in values):raise BackendError({'status':'runtime_error','message':'Nonfinite native output'})
            extra={}
            if fmt=='analog_reference_rows':
                a=case['analog_length'];c=case['channel_length']
                if len(values)!=a+7*c:raise ValueError('Analog output arity mismatch')
                actual={'raw':values[:a],'channels':[values[a+7*i:a+7*(i+1)] for i in range(c)]};expected={'raw':row['raw'],'channels':row['expected']}
            elif fmt=='fifo_reference_rows':
                width=2 if case['kind']=='record' else 1;cap=case['capacity']
                if len(values)!=2+width*(cap+1):raise ValueError('FIFO output arity mismatch')
                payload=[values[2+i*width:2+(i+1)*width] if width==2 else values[2+i] for i in range(cap+1)]
                actual={'elementCount':values[0],'status':values[1],'item':payload[0],'buffer':payload[1:]};expected=dict(row['expected'])
                if previous_buffer is not None and not row['enqueue'] and not row['dequeue'] and not row['reset']:expected['buffer']=previous_buffer
                previous_buffer=actual['buffer']
            else:
                fields=artifact['outputs'] if fmt=='struct_rows' else [n for n,_ in artifact['outputs']]
                if len(fields)!=len(values):raise ValueError('Dataset output arity mismatch')
                actual=dict(zip(fields,values));expected=dict(row.get('expected',{}))
                for name,_ in artifact['outputs'] if fmt!='struct_rows' else []:
                    if name.startswith('@input.'):expected[name]=input_value(row,name[7:],task)
            violations=[]
            for name,value in expected.items():
                assertions+=1
                if name not in actual or not equal(actual[name],value,check_task,name):violations.append({'output':name,'expected':value,'actual':actual.get(name)})
            for invariant in case.get('invariants',[]):
                if isinstance(invariant,dict) and 'not_both' in invariant:
                    assertions+=1
                    if all(actual[n] for n in invariant['not_both']):violations.append({'invariant':'not_both','outputs':invariant['not_both']})
                else:raise ValueError('Unknown supplied invariant; refusing to silently skip it')
            rows.append({**row,'actual':actual,'violations':violations})
            if violations and first is None:first={'scan':index,**violations[0]}
        for window in case.get('response_windows',[]):
            lo=window['start_scan'];hi=window['end_scan'];want=window['expected'];assertions+=1
            if not 0<=lo<=hi<len(rows):raise ValueError('Invalid response window')
            if not any(all(equal(r['actual'][n],v,task,n) for n,v in want.items()) for r in rows[lo:hi+1]):
                violation={'window':[lo,hi],'expected':want,'actual':[r['actual'] for r in rows[lo:hi+1]]}
                if first is None:first={'scan':hi,**violation}
                rows[hi]['violations'].append(violation)
        results.append({'name':case['name'],'status':'fail' if first else 'pass','first_failure':first,'rows':rows})
    result={'status':'fail' if any(c['status']=='fail' for c in results) else 'pass','task_id':task['id'],
        'source_sha256':artifact['source_sha256'],'dataset_sha256':task['dataset_sha256'],'execution_fingerprint':artifact['execution_fingerprint'],
        'cases':results,'summary':{'scenarios':len(results),'scans':total,'assertions':assertions,'failed':sum(c['status']=='fail' for c in results)},
        'target_compile':'not_executed','ltl_status':'requirements_only_not_executed','build_evidence':artifact['build_evidence'],
        'scope':'Supplied finite tests on actual local ST execution; struct07/17 copy-in/out and local VARIANT ABI limits remain. Not full LTL or vendor runtime verification.'}
    if hashlib.sha256(Path(source).read_bytes()).hexdigest()!=artifact['source_sha256']:result['status']='stale_source'
    return result
