"""Dataset tests executed by the real CODESYS simulation runtime.

One FB instance per scenario, caller-owned IN_OUT storage, one invocation per
scheduled row. Native timers use the simulation clock, never a substituted clock.
"""
import hashlib
import math
from pathlib import Path
import re
import tempfile

from plc_agent import codesys
from plc_agent import dataset
from plc_agent.st_source import split_units, mask_noncode
from plc_probe.backend import BackendError


def literal(value, dtype):
    dtype=dtype.upper()
    if dtype=='BOOL':return 'TRUE' if value else 'FALSE'
    if dtype in ('TIME','LTIME'):
        return ('T#' if dtype=='TIME' else 'LT#')+str(value)+'ms'
    if dtype.startswith('STRING'):
        return "'"+str(value).replace('$','$$').replace("'","$'").replace('\n','$N').replace('\r','$R')+"'"
    if not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError('Invalid numeric test input')
    return dtype+'#'+str(value)


RECIPE=('recipeID','ingredientType','ingredientRatio','productionTemperature')
ANALOG=('enable','hiLIM','loLIM','bipolar','measuringMode','retVal','outputValue')


def struct_field(name, kind):
    if kind=='pump':
        m=re.fullmatch(r'pump(\d+)\.(\w+)',name)
        if m:return 'pumpGroup['+m[1]+'].'+m[2]
    else:
        if name.startswith('query.'):return name.replace('query.','recipeQueryResult.',1)
        m=re.fullmatch(r'recipe(\d+)\.(\w+)',name)
        if m:return 'recipe['+m[1]+'].'+m[2]
    return name


def harness(task):
    fmt=task['adapter_format'];cases=task['scenarios']
    if fmt=='fifo_reference_rows':
        raise BackendError({'status':'behavior_not_supported','test_backend':'codesys',
            'message':'FIFO tests use the local PV1 VARIANT ABI. A native CODESYS VARIANT adapter is required; local execution is not substituted.'})
    total=sum(len(c.get('trace',c.get('rows',[]))) for c in cases)
    if not cases or not 1<=total<=20000:raise ValueError('CODESYS scan budget exceeded')
    decl=['PROGRAM PLC_PRG','VAR','WB_Done : BOOL;','WB_Case : DINT;','WB_Step : DINT;',
          'WB_Started : BOOL;','WB_Clock : TON;',f'WB_ActualMs : ARRAY[0..{total-1}] OF DINT;']
    output_types=[];outputs=[];body=['IF NOT WB_Done THEN','CASE WB_Case OF'];index=0;duration=0
    analog=fmt=='analog_reference_rows';structured=fmt=='struct_rows'
    if structured:
        kind='pump' if 'pumpGroup' in dataset.ports(task,'Input/Output') else 'recipe'
        outputs=list(task['field_order']['outputs'])
        for name in outputs:
            field=name.split('.')[-1]
            output_types.append('REAL' if field in ('ingredientRatio','productionTemperature') else 'BOOL' if field in ('selection','RunComd','recipeAdded','recipeDeleted','recipeModified','error') else 'INT' if field=='priority' else 'WORD' if field=='status' else 'DINT')
    elif analog:
        # Different scenario capacities require a rectangular transport padded to
        # the largest scenario, then trimmed before the frozen predicate runs.
        max_a=max(c['analog_length'] for c in cases);max_c=max(c['channel_length'] for c in cases)
        outputs=[f'raw{i}' for i in range(max_a)]+[f'channel{i}.{f}' for i in range(max_c) for f in ANALOG]
        output_types=['INT']*max_a+['BOOL','REAL','REAL','BOOL','INT','WORD','REAL']*max_c
    else:
        pairs=[v for n,t in dataset.ports(task,'Output').items() for v in dataset.flatten(n,t)]
        pairs += [('@input.'+n,t) for port,t in dataset.ports(task,'Input').items() for n,t in dataset.flatten(port,t) if '[' in n]
        outputs=[n for n,t in pairs];output_types=[t for n,t in pairs]
    for i,t in enumerate(output_types):
        # TIME outputs are converted explicitly to milliseconds in the harness.
        transport='LREAL' if t in ('TIME','LTIME') else t
        decl.append(f'WB_Out{i} : ARRAY[0..{total-1}] OF {transport};')
    for ci,case in enumerate(cases):
        uut=f'WB_Uut{ci}';decl.append(f'{uut} : {task["block"]};')
        bindings=[];refs={}
        for name,t in dataset.ports(task,'Input/Output').items():
            if analog:
                lo=case['analog_lower'] if name=='analogValues' else case['channel_lower']
                length=case['analog_length'] if name=='analogValues' else case['channel_length']
                t=t.replace('[*]',f'[{lo}..{lo+length-1}]')
            if '[*]' in t or t=='VARIANT':raise ValueError('Unsupported CODESYS test binding '+t)
            ref=f'WB_C{ci}_{name}';refs[name]=ref;decl.append(f'{ref} : {t};');bindings.append(name+' := '+ref)
        def expr(name):
            head=name.split('.')[0].split('[')[0]
            return (refs[head]+name[len(head):]) if head in refs else uut+'.'+name
        def typed(name,value):
            if structured:
                f=name.split('.')[-1]
                t='REAL' if f in ('ingredientRatio','productionTemperature') else 'BOOL' if f in ('mode','start','stop','selection','addRecipe','deleteRecipe','modifyRecipe','queryRecipe') else 'INT' if f in ('priority','recipeID','ingredientType') else 'DINT'
            else:
                head=name.split('[')[0];t=dataset.ports(task,'Input')[head]
                if '[' in t:t=t.split(' OF ')[-1]
            return expr(name)+' := '+literal(value,t)+';'
        rows=case.get('trace',case.get('rows',[]));times=[r.get('time_ms',0) for r in rows]
        if any(type(t) is not int or t<0 for t in times) or times!=sorted(times):raise ValueError('Test times must be monotone nonnegative integer milliseconds')
        duration+=times[-1] if times else 0
        if times and times[-1]>3600000:raise BackendError({'status':'behavior_not_supported','message':'Scenario exceeds the one-hour simulation limit','test_backend':'codesys'})
        body += [f'{ci}:', 'IF NOT WB_Started THEN', 'WB_Clock(IN := FALSE);']
        for ri,record in enumerate(case.get('initial',[]),1):
            if not structured or kind!='recipe':raise ValueError('Unsupported scenario initialization')
            for f,v in zip(RECIPE,record):body.append(typed(f'recipe[{ri}].{f}',v))
        body += ['WB_Started := TRUE;','END_IF;', 'WB_Clock(IN := TRUE, PT := T#1h);','CASE WB_Step OF']
        for si,row in enumerate(rows):
            body += [f'{si}:',f'IF WB_Clock.ET >= T#{times[si]}ms THEN']
            if structured:
                for n,v in zip(task['field_order']['inputs'],row['inputs']):body.append(typed(struct_field(n,kind),v))
            elif analog:
                body.append(uut+'.count := DINT#'+str(row['count'])+';')
                for i,v in enumerate(row['raw']):body.append(f'{refs["analogValues"]}[{case["analog_lower"]+i}] := INT#{v};')
                for i,record in enumerate(row['channels']):
                    for f,t,v in zip(ANALOG,['BOOL','REAL','REAL','BOOL','INT','WORD','REAL'],record):
                        body.append(f'{refs["channels"]}[{case["channel_lower"]+i}].{f} := {literal(v,t)};')
            else:
                for n,t in dataset.ports(task,'Input').items():
                    for field,_ in dataset.flatten(n,t):body.append(typed(field,dataset.input_value(row,field,task)))
            body.append(uut+'('+', '.join(bindings)+');')
            for oi,(n,t) in enumerate(zip(outputs,output_types)):
                if structured:value=expr(struct_field(n,kind))
                elif analog:
                    if oi<max_a:value=f'{refs["analogValues"]}[{case["analog_lower"]+oi}]' if oi<case['analog_length'] else '0'
                    else:
                        channel,field=divmod(oi-max_a,7)
                        value=f'{refs["channels"]}[{case["channel_lower"]+channel}].{ANALOG[field]}' if channel<case['channel_length'] else ('FALSE' if t=='BOOL' else '0')
                else:value=expr(n.removeprefix('@input.'))
                if t=='TIME':value='TIME_TO_LREAL('+value+')'
                if t=='LTIME':value='LINT_TO_LREAL(LTIME_TO_LINT('+value+')) / 1000000.0'
                body.append(f'WB_Out{oi}[{index}] := {value};')
            body += [f'WB_ActualMs[{index}] := TIME_TO_DINT(WB_Clock.ET);','WB_Step := WB_Step + 1;','END_IF;'];index+=1
        body += ['END_CASE;',f'IF WB_Step >= {len(rows)} THEN','WB_Step := 0;','WB_Case := WB_Case + 1;','WB_Started := FALSE;','END_IF;']
    body += ['END_CASE;',f'IF WB_Case >= {len(cases)} THEN WB_Done := TRUE; END_IF;','END_IF;']
    decl.append('END_VAR')
    return {'harness_declaration':'\n'.join(decl),'harness_body':'\n'.join(body),'output_names':outputs,
            'output_types':output_types,'row_count':total,'simulation_timeout_seconds':max(30,math.ceil(duration/1000)+total*.05+20)}


def numeric(value,dtype):
    text=str(value).strip()
    if dtype=='BOOL':return str(int(codesys.parse_value(text,'BOOL')))
    text=text.replace('_','')
    if '#' in text:text=text.split('#',1)[1]
    if dtype in ('REAL','LREAL','TIME','LTIME'):
        number=float(text)
        if not math.isfinite(number):raise ValueError('Nonfinite CODESYS output')
        return str(number)
    return str(codesys.parse_value(value,dtype))


def evaluate(source,task,config,cancel_event=None):
    source=Path(source);dataset.validate_source(source,task);data=source.read_bytes()
    plan=harness(task);cfg=dict(config)
    if plan['simulation_timeout_seconds']+40>cfg.get('timeout_seconds',120):
        raise BackendError({'status':'behavior_not_supported','test_backend':'codesys',
            'message':'Native-clock tests need %.0f seconds including IDE startup; increase the CODESYS timeout or revise the timing plan.'%(plan['simulation_timeout_seconds']+40)})
    directory=codesys.evidence_directory(source,'codesys_simulation')
    identity=codesys.fingerprint(cfg)
    try:
        response=codesys.invoke({'action':'simulate','source_sha256':hashlib.sha256(data).hexdigest(),
            'block':task['block'],'template_project':cfg['template_project'],
            'units':split_units(data.decode('utf-8-sig')),**plan,'record_scan_times':True},directory,config=cfg,cancel_event=cancel_event)
    except BackendError as exc:
        # The main chain already compiled the candidate separately. A failure
        # introduced by the test wrapper must not request a candidate rewrite.
        if exc.result.get('status')=='compile_error':
            raise BackendError({**exc.result,'status':'tool_error','phase':'codesys_test_harness',
                'message':'CODESYS rejected the test harness; inspect diagnostics before repairing the adapter.'}) from exc
        raise
    if response.get('target_compile')!='passed' or response.get('simulation') is not True:
        raise BackendError({'status':'protocol_error','message':'Missing CODESYS simulation evidence'})
    if source.read_bytes()!=data or codesys.fingerprint(cfg)!=identity:
        raise BackendError({'status':'stale_evidence','message':'Source or CODESYS environment changed'})
    raw=response.get('actual_rows',[])
    if len(raw)!=plan['row_count']:raise BackendError({'status':'protocol_error','message':'Wrong CODESYS test row count'})
    try:
        lines=[' '.join(numeric(row[n],t) for n,t in zip(plan['output_names'],plan['output_types'])) for row in raw]
        if task['adapter_format']=='analog_reference_rows':
            max_a=max(c['analog_length'] for c in task['scenarios']);cursor=0
            for case in task['scenarios']:
                for row in case['rows']:
                    values=lines[cursor].split();lines[cursor]=' '.join(values[:case['analog_length']]+values[max_a:max_a+7*case['channel_length']]);cursor+=1
    except (ValueError,KeyError,TypeError) as exc:
        raise BackendError({'status':'protocol_error','message':'Invalid CODESYS test output: '+str(exc)}) from exc
    if task['adapter_format']=='struct_rows':outputs=task['field_order']['outputs']
    else:outputs=list(zip(plan['output_names'],plan['output_types']))
    artifact={'outputs':outputs,'source_sha256':hashlib.sha256(data).hexdigest(),'execution_fingerprint':identity,
        'build_evidence':str(directory/'response.json'),'target_compile':'passed','test_backend':'codesys',
        'scope':'Actual CODESYS simulation; each supplied row invokes the FB once, native clock, actual scan timestamps recorded. No physical PLC claim.'}
    result=dataset.judge_output(source,task,artifact,lines)
    measured=response.get('actual_scan_times_ms',[])
    requested=[row.get('time_ms',0) for case in task['scenarios'] for row in case.get('trace',case.get('rows',[]))]
    if len(measured)!=len(requested) or any(type(t) is not int or t<0 for t in measured):
        raise BackendError({'status':'protocol_error','message':'Missing or invalid CODESYS scan timestamps'})
    # Native simulation can miss a millisecond boundary. Do not feed an
    # infrastructure scheduling error back to the model as a logic defect.
    timed=bool(re.search(r'\b(?:TON|TOF|TP|TON_TIME|TON_LTIME|SysTimeGet\w*)\b',mask_noncode(data.decode('utf-8-sig')),re.I))
    if timed:
        drift=max(abs(actual-target) for actual,target in zip(measured,requested))
        result['timing']={'clock':'CODESYS native','max_deviation_ms':drift,'tolerance_ms':1}
        if drift>1:
            result.update(status='behavior_not_supported',
                message='CODESYS simulation missed the requested timer sampling times; inspect actual_scan_times_ms. This is not classified as a candidate logic failure.')
    result.update(vendor='CODESYS',vendor_version=response['vendor_version'],simulation=True,
                  vendor_evidence=str(directory),actual_scan_times_ms=measured)
    return result
