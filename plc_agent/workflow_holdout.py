"""Additional unseen finite probes, not silently merged into original scores."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
import subprocess

from plc_probe.backend import compile_source,run_batch
from .bank_contracts import questions,interface
from .bank_runner import _compile
from .storage import atomic_json
from .workflow_benchmark import R2


def probes():
    rng=random.Random(7271026);all_cases={}
    cases=[]
    for debounce in [1,10,100,350]:
        rows=[{'time_ms':0,'inputs':{'Gap_Exceeded':0,'Weld_E_Stop_NC':1,'DebounceTime':debounce},'expected':{'Operator_Alert':0}},
              {'time_ms':5000,'inputs':{'Gap_Exceeded':0,'Weld_E_Stop_NC':1,'DebounceTime':debounce},'expected':{'Operator_Alert':0}}]
        time=6000;since=None
        for _ in range(120):
            gap=int(rng.random()<.75);permit=int(rng.random()<.85)
            if not gap or not permit:since=None
            elif since is None:since=time
            alarm=int(since is not None and time-since>=debounce)
            rows.append({'time_ms':time,'inputs':{'Gap_Exceeded':gap,'Weld_E_Stop_NC':permit,'DebounceTime':debounce},
                         'expected':{'Operator_Alert':alarm,'Weld_Soft_Start_Active':0}})
            time+=rng.choice([1,7,debounce-1 if debounce>1 else 1,debounce,debounce+1,700])
        cases.append({'name':f'unseen_debounce_{debounce}','trace':rows})
    all_cases['05']=cases
    cases=[]
    for n in range(8):
        rows=[];time=0;heating_since=None;cooling_since=None
        for _ in range(80):
            if cooling_since is not None and time-cooling_since>=3000:
                cooling_since=None;heating_since=None
            if cooling_since is None:
                if heating_since is None:heating_since=time
                elapsed=time-heating_since
                if elapsed==5000:time+=1;elapsed+=1  # Do not settle the exact > versus >= wording.
                if elapsed>5000:cooling_since=time;heating_since=None
            heater=int(cooling_since is None)
            rows.append({'time_ms':time,'inputs':{'TemperatureSensorInput':10+n,'SetTemperature':30},
                         'expected':{'HeaterOutput':heater,'HeaterStatus':heater,'OverheatProtection':1-heater}})
            time+=rng.choice([17,53,499,999,1501,2507])
        cases.append({'name':f'unseen_heating_cooldown_{n}','trace':rows})
    all_cases['10']=cases
    return all_cases


def execute(source,qid,cases):
    question=next(q for q in questions() if q['id']==qid)
    exe,meta=_compile(source,question);inputs,outputs=interface(question)
    commands=[]
    for case in cases:
        commands.append('R')
        for row in case['trace']:
            commands.append('S '+str(row['time_ms'])+' '+' '.join(str(row['inputs'][k]) for k in inputs))
    run=subprocess.run([str(exe)],input='\n'.join(commands)+'\n',capture_output=True,text=True,encoding='utf-8',timeout=15,cwd=exe.parent)
    if run.returncode:raise RuntimeError(run.stderr)
    lines=run.stdout.splitlines();cursor=0;results=[]
    if len(lines)!=sum(len(c['trace']) for c in cases):raise RuntimeError('Holdout output scan count mismatch')
    for case in cases:
        rows=[];first=None
        for index,row in enumerate(case['trace']):
            actual={k:float(v) for k,v in zip(outputs,lines[cursor].split())};cursor+=1
            failed=[{'output':k,'expected':v,'actual':actual[k]} for k,v in row['expected'].items() if actual[k]!=v]
            if failed and first is None:first={'scan':index,'time_ms':row['time_ms'],**failed[0]}
            rows.append({**row,'actual':actual,'violations':failed})
        results.append({'name':case['name'],'status':'fail' if first else 'pass','first_failure':first,'rows':rows})
    return {'status':'fail' if any(r['first_failure'] for r in results) else 'pass','cases':results,'build_evidence':str(meta),
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'scans':len(lines)}


def main():
    tests=probes();atomic_json(R2/'unseen_probe_protocol.json',{'source':'Independent monitors from task timing requirements; not provided to repair model',
      'scope':'Finite supplemental tests; no exact 5s threshold comparison, no new decisions about startup/estop precedence','probes':tests})
    results={}
    for qid,cases in tests.items():
        source=R2/'tasks'/qid/'final.st'
        runs=[execute(source,qid,cases) for _ in range(2)]
        atomic_json(R2/('unseen_'+qid+'.json'),{'runs':runs})
        results[qid]={'statuses':[r['status'] for r in runs],'scans_per_run':runs[0]['scans'],
                      'first_failures':[c['first_failure'] for c in runs[0]['cases'] if c['first_failure']]}
    rng=random.Random(276);texts=['.'.join(str(rng.randrange(256)) for _ in range(4)) for _ in range(120)]
    texts+=['','1.2.3','256.0.0.1','-1.2.3.4','1..2.3','1.2.3.4.5','1.2.3.4 ',' 1.2.3.4','a.b.c.d','1.2.3.9999999999999999999999999999999']
    scenario={'name':'unseen_ipv4','trace':[{'time_ms':i,'inputs':{'ipText':text}} for i,text in enumerate(texts)]}
    runs=[run_batch(compile_source(R2/'tasks/14/final.st','ipv4'),[scenario])[0] for _ in range(2)]
    atomic_json(R2/'unseen_14.json',{'scenario':scenario,'runs':runs})
    results['14']={'statuses':[r['status'] for r in runs],'scans_per_run':len(texts),'first_failures':[r['first_failure'] for r in runs if r['first_failure']]}
    atomic_json(R2/'unseen_summary.json',results)
    print(json.dumps(results,ensure_ascii=False))


if __name__=='__main__':main()
