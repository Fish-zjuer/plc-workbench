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


from plc_agent.behavior_plan import literal, struct_field, harness, RECIPE, ANALOG


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
