"""Opt-in real PLCverif/CBMC positive and negative reference checks.

Run from project root: python -m scripts.check_plcverif_references --temp-root <ASCII writable directory>
"""
import argparse
import json
from pathlib import Path
import tempfile

from plc_agent.plcverif_backend import DEFAULTS, discover_tools, verify


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--temp-root',required=True)
    parser.add_argument('--output',default='outputs/reference-extension-check')
    args=parser.parse_args()
    temporary=Path(args.temp_root).resolve()
    if not str(temporary).isascii() or not temporary.is_dir():
        parser.error('--temp-root must be an existing writable ASCII directory')
    tempfile.tempdir=str(temporary)
    root=Path(args.output);root.mkdir(parents=True,exist_ok=True)
    base={'id':'REFERENCE_DEMO','block':'Demo','interface':[
        {'direction':'Input','name':'x','type':'DINT'},
        {'direction':'Output','name':'y','type':'DINT'},
        {'direction':'Input/Output','name':'a','type':'ARRAY[*] OF DINT'},
        {'direction':'Input/Output','name':'b','type':'DINT'}],
        'ltl':{'properties':[{'id':'P1','formula':'G(y = x)'}], 'execution':{
            'reference_model':{'version':1,'objects':[{'name':'PVL_Store_Data','type':'ARRAY[-3..1] OF DINT'}],
                               'bindings':{'a':'PVL_Store_Data','b':'PVL_Store_Data[-3]'}}}}}
    cases=[('alias',False,'a[LOWER_BOUND(a, 1)] := x; y := b;','bounded_pass'),
           ('alias_mutant',False,'a[LOWER_BOUND(a, 1)] := x; y := 0;','counterexample'),
           ('return',False,'y := x; IF x = 0 THEN RETURN; END_IF; a[-3] := x;','bounded_pass'),
           ('pv1',True,'idx := 1; copyDone := PV_WRITE(a, idx, b); idx := 0; copyDone := PV_READ(a, idx, b); idx := 1; copyDone := PV_READ(a, idx, b);','bounded_pass'),
           ('pv1_mutant',True,'idx := 1; copyDone := TRUE; idx := 0; copyDone := PV_READ(a, idx, b); idx := 1; copyDone := PV_READ(a, idx, b);','counterexample'),
           ('pv1_bounds',True,'idx := -1; copyDone := PV_READ(a, idx, b); y := 0; IF copyDone THEN y := 1; END_IF;','bounded_pass')]
    summary=[]
    for name,variant,body,expected in cases:
        task=json.loads(json.dumps(base))
        if variant:
            for p in task['interface']:
                if p['direction']=='Input/Output':p['type']='VARIANT'
            execution=task['ltl']['execution'];model=execution['reference_model']
            model['objects'].append({'name':'PVL_Store_Item','type':'DINT'})
            model['bindings']['b']='PVL_Store_Item'
            execution['entry']=['PVL_Store_Item := x;']
            # Check physical destination as well as read-back: a broken cast
            # mapping every index to zero must not pass a round-trip test.
            execution['declarations']=['PVL_Destination : DINT;']
            execution['before']=['PVL_Destination := PVL_Store_Data[1];']
            task['ltl']['properties'][0]['formula']='G((PVL_Store_Item = x) & (PVL_Destination = x))' if name!='pv1_bounds' else 'G((PVL_Store_Item = x) & (y = 0))'
        inouts='a : VARIANT; b : VARIANT;' if variant else 'a : ARRAY[*] OF DINT; b : DINT;'
        source=('FUNCTION_BLOCK Demo\nVAR_INPUT x : DINT; END_VAR\n'
                'VAR_OUTPUT y : DINT; END_VAR\nVAR_IN_OUT '+inouts+' END_VAR\n'
                'VAR copyDone : BOOL; idx : DINT; END_VAR\n'+body+'\nEND_FUNCTION_BLOCK')
        p=root/(name+'.st');p.write_text(source,encoding='utf-8')
        result=verify(task,p,root/name,config={**DEFAULTS,**discover_tools(),'bound':3,'timeout_seconds':45,'unwind':8})
        row={'case':name,'expected':expected,'actual':result['status'],'ok':result['status']==expected}
        summary.append(row);print(json.dumps(row),flush=True)
    (root/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return 0 if all(row['ok'] for row in summary) else 1


if __name__=='__main__':raise SystemExit(main())
