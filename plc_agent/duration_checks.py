"""Additional duration/data-history checks; original sparse predicates stay frozen."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import random
import subprocess

from plc_probe.backend import BackendError
from .bank_contracts import questions,interface
from .bank_runner import _compile


def cases(qid):
    result=[]
    if qid=='04':
        rows=[]
        for t,cycle in [(0,1),(1,1),(1799999999,1799999998),(1800000000,1),(1800000001,1)]:
            rows.append({'time_ms':t,'inputs':{'VISCOSITY_OK':1,'PASTE_E_STOP_NC':1,'DebounceTime':1,'CycleTime':cycle},
                         'expected':{'VFD_RUN':int(t>0),'PUMP_RUNTIME_ACC':t,'PUMP_MAINT_DUE':int(t>=1800000000)}})
        result.append({'name':'maintenance_just_below_at_above_500_hours','trace':rows})
        rng=random.Random(20261029);rows=[];start=None;total=0;t=0
        for i in range(320):
            step=rng.choice([1,3,11,29,80]);t+=step
            viscosity=int(i%19 not in (0,1,2));permit=int(i%43 not in (0,1,2,3));pt=37
            if not viscosity or not permit:start=None
            elif start is None:start=t
            run=int(start is not None and t-start>=pt)
            if run:total+=step
            rows.append({'time_ms':t,'inputs':{'VISCOSITY_OK':viscosity,'PASTE_E_STOP_NC':permit,'DebounceTime':pt,'CycleTime':step},
                         'expected':{'VFD_RUN':run,'PUMP_RUNTIME_ACC':total,'PUMP_MAINT_DUE':0}})
        result.append({'name':'irregular_cycles_stop_clears_debounce_and_preserves_total','trace':rows})
        return result
    if qid!='12':raise ValueError('Duration supplement supports 04 and 12')
    rows=[];runtime=0
    # Total beyond 32-bit milliseconds, using individually valid TIME intervals.
    for i in range(8):
        cycle=1000000000;runtime+=cycle
        rows.append({'time_ms':i*1000000000,'inputs':{'THICKNESS_FAULT':0,'THICKNESS_SIGNAL_VALID':1,'CUTTING_RUN':1,'FaultTimestamp':i,'CycleTime':cycle},
                     'expected':{'THICKNESS_ALARM':0,'Slab_Fault_Counter':0,'Slab_Runtime_Accumulator':runtime}})
    result.append({'name':'long_runtime_more_than_32bit_milliseconds','trace':rows})
    rows=[]
    for t,fault,alarm,count in [(0,0,0,0),(10,1,1,1),(400,0,1,1),(450,1,1,2),(460,0,1,2),(700,0,1,2),(949,0,1,2),(950,0,None,2)]:
        expected={'Slab_Fault_Counter':count}
        if alarm is not None:expected['THICKNESS_ALARM']=alarm
        rows.append({'time_ms':t,'inputs':{'THICKNESS_FAULT':fault,'THICKNESS_SIGNAL_VALID':1,'CUTTING_RUN':0,'FaultTimestamp':t,'CycleTime':1},'expected':expected})
    result.append({'name':'each_new_fault_restarts_its_minimum_hold','trace':rows})
    rng=random.Random(20261029);rows=[];history=[0]*5;count=0;runtime=0;t=0;old=0;trigger=None
    for i in range(320):
        step=rng.choice([1,17,70,160,501]);t+=step
        valid=int(i%47 not in (0,1,2));fault=int(i%23 in (4,5,6));run=int(i%7!=0);active=valid and fault
        if active and not old:count+=1;history=[t,*history[:4]];trigger=t
        if not valid:trigger=None
        old=active
        if run and valid and not fault:runtime+=step
        expected={'Slab_Fault_Counter':count,'Slab_Runtime_Accumulator':runtime,
                  **{f'Slab_Fault_History[{j}]':v for j,v in enumerate(history)}}
        if not valid:expected['THICKNESS_ALARM']=0
        elif fault or trigger is not None and t-trigger<500:expected['THICKNESS_ALARM']=1
        # Do not turn the minimum-hold requirement into an unstated maximum.
        rows.append({'time_ms':t,'inputs':{'THICKNESS_FAULT':fault,'THICKNESS_SIGNAL_VALID':valid,'CUTTING_RUN':run,'FaultTimestamp':t,'CycleTime':step},'expected':expected})
    result.append({'name':'validity_edges_history_rotation_runtime_and_minimum_hold','trace':rows})
    return result


def test_durations(source,qid):
    source=Path(source).resolve();question=next(q for q in questions() if q['id']==qid)
    exe,meta=_compile(source,question);inputs,outputs=interface(question);tests=cases(qid);commands=[]
    for case in tests:
        commands.append('R')
        for row in case['trace']:commands.append('S '+str(row['time_ms'])+' '+' '.join(str(row['inputs'][name]) for name in inputs))
    try:run=subprocess.run([str(exe)],input='\n'.join(commands)+'\n',capture_output=True,text=True,encoding='utf-8',timeout=15,cwd=exe.parent)
    except subprocess.TimeoutExpired:raise BackendError({'status':'timeout','message':'Duration supplement exceeded 15 seconds'}) from None
    if run.returncode:raise BackendError({'status':'runtime_error','stderr':run.stderr[:1500]})
    lines=run.stdout.splitlines()
    if len(lines)!=sum(len(c['trace']) for c in tests):raise BackendError({'status':'runtime_error','message':'Duration output scan count mismatch'})
    offset=0;results=[]
    for case in tests:
        rows=[];first=None
        for index,row in enumerate(case['trace']):
            tokens=lines[offset].split();offset+=1
            if len(tokens)!=len(outputs):raise BackendError({'status':'runtime_error','message':'Duration output field count mismatch'})
            actual={name:float(token) for name,token in zip(outputs,tokens)}
            failures=[{'output':name,'expected':value,'actual':actual[name]} for name,value in row['expected'].items() if not math.isfinite(actual[name]) or actual[name]!=value]
            rows.append({**row,'actual':actual,'violations':failures})
            if failures and first is None:first={'scan':index,'time_ms':row['time_ms'],**failures[0]}
        results.append({'name':case['name'],'status':'fail' if first else 'pass','first_failure':first,'rows':rows})
    return {'status':'fail' if any(c['first_failure'] for c in results) else 'pass','question_id':qid,
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'behavior_tested':True,'cases':results,
            'first_failure':next(({'scenario':c['name'],**c['first_failure']} for c in results if c['first_failure']),None),
            'summary':{'scenarios':len(tests),'scans':len(lines),'failed':sum(c['status']=='fail' for c in results)},
            'scope':'Additional finite duration/history checks; Q12 alarm only asserts minimum hold outside original fixed examples.',
            'build_evidence':str(meta)}
