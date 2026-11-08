"""Replay baseline source-model regressions as ST/SCL pairs, without a model call.

Both sides use the unchanged baseline PLCverif/CBMC modules. PV1 examples
exercise the shared local storage contract only, never a vendor VARIANT ABI.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from plc_agent import dataset, plcverif_backend, tia, tia_formal
from plc_agent.st_source import mask_noncode, split_units
from plc_agent.storage import atomic_json

BASELINE = 'ea42b6ebcd41228d7c3e41ee526a9aafa9550751'
CORE = ('plcverif_backend.py', 'plcverif_st.py', 'cbmc_model.py', 'ltl_adapter.py',
        'plcverif_references.py', 'reference_observers.py', 'dataset.py')


def baseline_file(path):
    return subprocess.run(['git','show',BASELINE+':'+path], cwd=ROOT,
                          stdout=subprocess.PIPE, check=True).stdout.decode('utf-8')


def digest(text):
    return hashlib.sha256(text.replace('\r\n','\n').encode('utf-8')).hexdigest()


def to_scl(source):
    """Port packaging/spelling only; retain each declaration and expression."""
    parts = []
    for unit in split_units(source):
        declaration = unit['declaration']
        if unit['kind'] == 'TYPE':
            declaration = re.sub(r'\bTYPE\s+'+re.escape(unit['name'])+r'\s*:',
                                 'TYPE "'+unit['name']+'"\nVERSION : 0.1',declaration,count=1,flags=re.I)
            parts.append(declaration); continue
        if unit['kind'] != 'FUNCTION_BLOCK':
            raise ValueError('Baseline port admits FB/TYPE units only')
        declaration = re.sub(r'\bFUNCTION_BLOCK\s+'+re.escape(unit['name'])+r'\b',
            'FUNCTION_BLOCK "'+unit['name']+'"\n{ S7_Optimized_Access := \'TRUE\' }\nVERSION : 0.1',
            declaration,count=1,flags=re.I)
        declaration = re.sub(r':\s*TON\s*;', ': TON_TIME;', declaration, flags=re.I)
        names = {m.lower() for m in re.findall(r'\b(\w+)\s*:',mask_noncode(unit['declaration']))}
        body=unit['implementation']; masked=mask_noncode(body); edits=[]
        for match in re.finditer(r'\b[A-Za-z_]\w*\b',masked):
            prefix=masked[:match.start()].rstrip()
            if match[0].lower() in names and not prefix.endswith(('.', '#')):
                edits.append((match.start(),match.start(),'#'))
        for start,end,value in reversed(edits):body=body[:start]+value+body[end:]
        body=re.sub(r'\b(LOWER_BOUND|UPPER_BOUND)\((#\w+),\s*1\)',
                    r'\1(ARR := \2, DIM := UDINT#1)',body,flags=re.I)
        body=re.sub(r'(#\w+)\(IN\s*:=',r'\1.TON(IN :=',body,flags=re.I)
        body=re.sub(r'\bSHL\(DWORD#1,\s*(#\w+)\)',r'SHL(IN := DWORD#1, N := \1)',body,flags=re.I)
        visible=mask_noncode(body);ends=[]
        for match in re.finditer(r'\bEND_(?:IF|FOR|WHILE|CASE|REPEAT)\b',visible,re.I):
            if not visible[match.end():].lstrip().startswith(';'):ends.append(match.end())
        for pos in reversed(ends):body=body[:pos]+';'+body[pos:]
        parts.append(declaration+'\nBEGIN\n'+body+'\nEND_FUNCTION_BLOCK')
    return '\n\n'.join(parts)+'\n'


def reference_cases():
    task={'id':'REFERENCE_DEMO','block':'Demo','interface':[
        {'direction':'Input','name':'x','type':'DINT'},
        {'direction':'Output','name':'y','type':'DINT'},
        {'direction':'Input/Output','name':'a','type':'ARRAY[*] OF DINT'},
        {'direction':'Input/Output','name':'b','type':'DINT'}],
        'ltl':{'properties':[{'id':'P1','formula':'G(y = x)'}], 'execution':{
            'reference_model':{'version':1,'objects':[{'name':'PVL_Store_Data','type':'ARRAY[-3..1] OF DINT'}],
                               'bindings':{'a':'PVL_Store_Data','b':'PVL_Store_Data[-3]'}}}}}
    rows=[('alias',False,'a[LOWER_BOUND(a, 1)] := x; y := b;','bounded_pass'),
          ('alias_mutant',False,'a[LOWER_BOUND(a, 1)] := x; y := 0;','counterexample'),
          ('return',False,'y := x; IF x = 0 THEN RETURN; END_IF; a[-3] := x;','bounded_pass'),
          ('pv1',True,'idx := 1; copyDone := PV_WRITE(a, idx, b); idx := 0; copyDone := PV_READ(a, idx, b); idx := 1; copyDone := PV_READ(a, idx, b);','bounded_pass'),
          ('pv1_mutant',True,'idx := 1; copyDone := TRUE; idx := 0; copyDone := PV_READ(a, idx, b); idx := 1; copyDone := PV_READ(a, idx, b);','counterexample'),
          ('pv1_bounds',True,'idx := -1; copyDone := PV_READ(a, idx, b); y := 0; IF copyDone THEN y := 1; END_IF;','bounded_pass')]
    for name,variant,body,expected in rows:
        spec=deepcopy(task)
        if variant:
            for p in spec['interface']:
                if p['direction']=='Input/Output':p['type']='VARIANT'
            execution=spec['ltl']['execution'];model=execution['reference_model']
            model['objects'].append({'name':'PVL_Store_Item','type':'DINT'})
            model['bindings']['b']='PVL_Store_Item'
            execution['entry']=['PVL_Store_Item := x;']
            execution['declarations']=['PVL_Destination : DINT;']
            execution['before']=['PVL_Destination := PVL_Store_Data[1];']
            spec['ltl']['properties'][0]['formula']='G((PVL_Store_Item = x) & (PVL_Destination = x))' if name!='pv1_bounds' else 'G((PVL_Store_Item = x) & (y = 0))'
        inouts='a : VARIANT; b : VARIANT;' if variant else 'a : ARRAY[*] OF DINT; b : DINT;'
        source=('FUNCTION_BLOCK Demo\nVAR_INPUT x : DINT; END_VAR\n'
                'VAR_OUTPUT y : DINT; END_VAR\nVAR_IN_OUT '+inouts+' END_VAR\n'
                'VAR copyDone : BOOL; idx : DINT; END_VAR\n'+body+'\nEND_FUNCTION_BLOCK')
        yield {'name':name,'task':spec,'source':source,'expected':expected,'origin':'scripts/check_plcverif_references.py',
               'settings':{'bound':3,'timeout_seconds':45,'unwind':8},'native_compilable':not variant}


def cases():
    yield from reference_cases()
    q08=baseline_file('examples/formal/Q08.st');q18=baseline_file('examples/formal/Q18.st')
    raw='aLower := LOWER_BOUND(analogValues, 1);';cfg='cLower := LOWER_BOUND(channels, 1);'
    rows=[('08_correct','PUBLIC_08',q08,'bounded_pass'),
          ('08_raw_write','PUBLIC_08',q08.replace(raw,raw+'\nanalogValues[aLower] := INT#0;'),'counterexample'),
          ('08_config_write','PUBLIC_08',q08.replace(cfg,cfg+'\nchannels[cLower].hiLIM := 0.0;'),'counterexample'),
          ('18_correct','PUBLIC_18',q18,'bounded_pass'),
          ('18_count_only','PUBLIC_18',q18.replace('PV_WRITE(buffer, diTail, item)','TRUE'),'counterexample'),
          ('18_missing_read','PUBLIC_18',q18.replace('PV_READ(buffer, diHead, item)','TRUE'),'counterexample'),
          ('18_wrong_empty_status','PUBLIC_18',q18.replace('status := 16#8001;','status := 16#8002;'),'counterexample')]
    for name,ident,source,expected in rows:
        yield {'name':name,'task':dataset.load(ident),'source':source,'expected':expected,'origin':'scripts/check_course_references.py',
               'settings':{'bound':3 if ident=='PUBLIC_08' else 4,'unwind':16,'timeout_seconds':180,'reference_numeric_domain':'boundary'},
               'native_compilable':ident=='PUBLIC_08'}
    # Additional pairs exercise the exact supported TON/SHL patterns from the
    # baseline's tests, rather than expanding the shared model's support set.
    for preset in (30,5,0):
        for mutant in (False,True):
            source=f'''FUNCTION_BLOCK Delay
VAR_INPUT enable : BOOL; END_VAR
VAR_OUTPUT ready : BOOL; END_VAR
VAR timer : TON; END_VAR
timer(IN := enable, PT := T#{preset}ms);
ready := {'NOT ' if mutant else ''}timer.Q;
END_FUNCTION_BLOCK'''
            task={'id':'TON_PATTERN','block':'Delay','interface':[
                {'direction':'Input','name':'enable','type':'BOOL'}, {'direction':'Output','name':'ready','type':'BOOL'}],
                'ltl':{'properties':[{'id':'elapsed','formula':'G(ready = refReady)'}], 'execution':{
                    'declarations':['PVL_RefNow : DINT := 0;','PVL_RefStart : DINT := 0;','PVL_RefPrevious : BOOL := FALSE;'],
                    'before':['IF NOT enable OR NOT PVL_RefPrevious THEN PVL_RefStart := PVL_RefNow; END_IF;'],
                    'after':['PVL_RefPrevious := enable;','PVL_RefNow := PVL_RefNow + 10;'],
                    'bindings':{'refReady':f'enable & ((PVL_RefNow - PVL_RefStart) >= {preset})'}}}}
            yield {'name':f'ton_{preset}ms'+('_mutant' if mutant else ''),'task':task,'source':source,
                   'expected':'counterexample' if mutant else 'bounded_pass','origin':'tests/test_plcverif_st.py supported timer patterns; added absolute-time observer',
                   'settings':{'bound':8,'scan_period_ms':10,'unwind':256,'timeout_seconds':120},'native_compilable':True}
    for mutant in (False,True):
        source='''FUNCTION_BLOCK Edge
VAR_OUTPUT checksum : DWORD; END_VAR
VAR mask : DWORD; bitIndex : INT; END_VAR
checksum := DWORD#0;
FOR bitIndex := 0 TO 31 DO
    mask := SHL(DWORD#1, bitIndex);
    checksum := checksum OR MASK_VALUE;
END_FOR;
END_FUNCTION_BLOCK'''.replace('MASK_VALUE','DWORD#0' if mutant else 'mask')
        task={'id':'SHL_PATTERN','block':'Edge','interface':[{'direction':'Output','name':'checksum','type':'DWORD'}],
              'ltl':{'properties':[{'id':'all_bits','formula':'G(allBits)'}],
                     'execution':{'declarations':['PVL_AllBits : DWORD := DWORD#16#FFFFFFFF;'],
                                  'bindings':{'allBits':'checksum = PVL_AllBits'}}}}
        yield {'name':'shift'+('_mutant' if mutant else ''),'task':task,'source':source,
               'expected':'counterexample' if mutant else 'bounded_pass','origin':'tests/test_plcverif_st.py bounded DWORD#1 / 0..31 pattern; added checksum',
               'settings':{'bound':3,'unwind':256,'timeout_seconds':120},'native_compilable':True}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--ids',help='Comma-separated case names; default all')
    parser.add_argument('--include-probes',action='store_true',help='Also run timer probes not qualified as baseline real-tool successes')
    parser.add_argument('--compile-only',type=Path,help='Compile the saved native-compilable SCL from an earlier paired run')
    args=parser.parse_args(argv)
    registry=list(cases())
    ids=set(args.ids.split(',')) if args.ids else None
    if ids and ids-{case['name'] for case in registry}:parser.error('Unknown baseline case ID')
    selected=[case for case in registry if (case['name'] in ids if ids else args.include_probes or not case['name'].startswith('ton_'))
              and (not args.compile_only or case['native_compilable'])]
    if not selected:parser.error('No eligible baseline cases selected')
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    identities={name:digest(baseline_file('plc_agent/'+name)) for name in CORE}
    assert all(digest((ROOT/'plc_agent'/name).read_text(encoding='utf-8'))==value for name,value in identities.items()), 'Shared baseline core changed'
    report={'baseline':BASELINE,'process_id':os.getpid(),'mode':'native_compile' if args.compile_only else 'paired_formal',
            'shared_core_sha256':identities,'model_calls':0,'results':[],
            'scope':'Paired source-model checks; PV1 is model-only. Native compilation is recorded independently.'}
    config=plcverif_backend.configuration()
    for case in selected:
        folder=root/case['name'];folder.mkdir()
        task=case['task'];source=folder/'baseline.st';scl=folder/'candidate.scl'
        source.write_text(case['source'],encoding='utf-8');scl.write_text(to_scl(case['source']),encoding='utf-8')
        atomic_json(folder/'task_snapshot.json',task)
        cfg={**config,**case['settings']};atomic_json(folder/'formal_config.json',cfg)
        row={'case':case['name'],'expected':case['expected'],'origin':case['origin'],'settings':case['settings'],
             'native_compilable':case['native_compilable'],'baseline_source_sha256':tia.sha256(source),'scl_sha256':tia.sha256(scl)}
        report['results'].append(row);atomic_json(root/'summary.json',report)
        print(case['name'],'START',flush=True);start=time.monotonic()
        if args.compile_only:
            saved=args.compile_only/case['name']/'candidate.scl'
            assert saved.read_bytes()==scl.read_bytes(),'Saved port differs'
            result=tia.compile_scl(scl,tia.load_config(),directory=folder/'compile')
            row.update(actual=result['status'],errors=result.get('errors'),warnings=result.get('warnings'),ok=result['status']=='compile_passed')
        else:
            baseline=plcverif_backend.verify(task,source,folder/'baseline',config=cfg)
            port=tia_formal.verify(task,scl,folder/'tia',config=cfg)
            base_props={p['id']:p['status'] for p in baseline['properties']}
            tia_props={p['id']:p['status'] for p in port['properties']}
            row.update(baseline_actual=baseline['status'],tia_actual=port['status'],
                       baseline_properties=base_props,tia_properties=tia_props,
                       baseline_ok=baseline['status']==case['expected'],
                       ok=baseline['status']==case['expected'] and port['status']==case['expected'] and base_props==tia_props,
                       baseline_message=baseline.get('message'),tia_message=port.get('message'))
        row['seconds']=round(time.monotonic()-start,3)
        print(json.dumps({key:row[key] for key in ('case','expected','baseline_actual','tia_actual','actual','ok','seconds') if key in row},ensure_ascii=True),flush=True)
        atomic_json(root/'summary.json',report)
    report['completed']=True
    report['all_pairs_match']=all(r['ok'] for r in report['results'])
    report['shared_core_unchanged']=all(digest((ROOT/'plc_agent'/name).read_text(encoding='utf-8'))==value for name,value in identities.items())
    atomic_json(root/'summary.json',report)
    return 0 if report['all_pairs_match'] else 1


if __name__=='__main__':raise SystemExit(main())
