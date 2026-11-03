"""Siemens native behavior tests; scenario predicates are shared with CODESYS."""
import hashlib
import math
from pathlib import Path
import re

from . import dataset, tia
from .behavior_plan import harness as scenario_plan
from .st_source import mask_noncode
from .storage import atomic_json
from plc_probe.backend import BackendError


def _locals(text):
    masked = mask_noncode(text)
    parts=[];cursor=0
    for match in re.finditer(r'\bWB_\w+\b', masked):
        parts.extend((text[cursor:match.start()], '#', text[match.start():match.end()]))
        cursor=match.end()
    return ''.join(parts)+text[cursor:]


def harness(task):
    plan = scenario_plan(task, backend='tia')
    decl = plan.pop('harness_declaration')
    decl = decl.replace('PROGRAM PLC_PRG', 'FUNCTION_BLOCK "WB_TestHarness"\n{ S7_Optimized_Access := \'TRUE\' }\nVERSION : 0.1')
    decl = re.sub(r':\s*TON\s*;', ': TON_TIME;', decl, flags=re.I)
    decl = re.sub(r'STRING\((\d+)\)', r'STRING[\1]', decl, flags=re.I)
    body = _locals(plan.pop('harness_body'))
    body = re.sub(r'#WB_Clock\s*\(', '#WB_Clock.TON(', body)
    body = body.replace('#WB_Clock.TON(IN := FALSE);', '#WB_Clock.TON(IN := FALSE, PT := T#1h);')
    body = re.sub(r'TIME_TO_LREAL\(([^()]+)\)', r'DINT_TO_LREAL(TIME_TO_DINT(\1))', body)
    scl = decl+'\nBEGIN\n'+body+'\nEND_FUNCTION_BLOCK\n'+'''
DATA_BLOCK "WB_TestHarness_DB"
{ S7_Optimized_Access := 'TRUE' }
VERSION : 0.1
"WB_TestHarness"
BEGIN
END_DATA_BLOCK

ORGANIZATION_BLOCK "Main"
{ S7_Optimized_Access := 'TRUE' }
VERSION : 0.1
VAR_INPUT
    Initial_Call : BOOL;
    Remanence : BOOL;
END_VAR
BEGIN
    "WB_TestHarness_DB"();
END_ORGANIZATION_BLOCK
'''
    return {**plan, 'harness_source': scl, 'result_db': 'WB_TestHarness_DB',
            'clock': 'PLCSIM Advanced native', 'semantics': 'One FB call per supplied row; isolated instance per scenario'}


def evaluate(source, task, config, cancel_event=None, *, directory=None):
    source = Path(source); data = source.read_bytes()
    if re.search(r'\b(?:WB_TestHarness(?:_DB)?|ORGANIZATION_BLOCK|DATA_BLOCK|PROGRAM)\b', mask_noncode(data.decode('utf-8-sig').replace('"', ' ')), re.I):
        raise BackendError({'status': 'behavior_not_supported', 'message': 'WB_TestHarness and test OB/DBs are reserved for the Siemens harness', 'test_backend': 'tia'})
    try: plan = harness(task)
    except ValueError as exc:
        raise BackendError({'status': 'behavior_not_supported', 'test_backend': 'tia', 'message': str(exc)}) from exc
    try: tia.validate_simulation_config(config)
    except ValueError as exc:
        raise BackendError({'status': 'behavior_not_configured', 'test_backend': 'tia', 'message': str(exc)}) from exc
    # Reserve the bridge's 180-second startup window plus project setup time;
    # an outer timeout must not kill PLCSIM while PowerOn is still pending.
    if plan['simulation_timeout_seconds']+240 > config.get('simulation_timeout_seconds', 600):
        raise BackendError({'status': 'behavior_not_supported', 'test_backend': 'tia',
                            'message': 'Increase the Siemens simulation timeout for this native-clock scenario.'})
    directory = Path(directory or source.parent/'tia_simulation')
    response = tia.simulate_scl(source, plan, config, directory=directory, cancel_event=cancel_event)
    if response['status'] != 'simulation_completed':
        raise BackendError(response)
    if source.read_bytes() != data:
        raise BackendError({'status': 'stale_evidence', 'message': 'SCL changed during simulation'})
    raw = response['actual_rows']; names = plan['output_names']; types = plan['output_types']
    if len(raw) != plan['row_count']:
        raise BackendError({'status': 'protocol_error', 'message': 'Wrong Siemens simulation row count'})
    lines = []
    for row in raw:
        if not isinstance(row, dict) or set(row) != set(names):
            raise BackendError({'status': 'protocol_error', 'message': 'Wrong Siemens simulation output columns'})
        values = []
        for name, dtype in zip(names, types):
            value = row[name]
            if dtype == 'BOOL':
                if type(value) is not bool: raise BackendError({'status': 'protocol_error', 'message': 'Expected native BOOL'})
                value = int(value)
            elif type(value) not in (int, float) or not math.isfinite(value):
                raise BackendError({'status': 'protocol_error', 'message': 'Expected finite native number'})
            values.append(str(value))
        lines.append(' '.join(values))
    if task['adapter_format'] == 'analog_reference_rows':
        max_a = max(c['analog_length'] for c in task['scenarios']); cursor = 0
        for case in task['scenarios']:
            for _ in case['rows']:
                values = lines[cursor].split()
                lines[cursor] = ' '.join(values[:case['analog_length']]+values[max_a:max_a+7*case['channel_length']]); cursor += 1
    measured = response['actual_scan_times_ms']
    requested = [r.get('time_ms', 0) for c in task['scenarios'] for r in c.get('trace', c.get('rows', []))]
    if len(measured) != len(requested) or any(type(t) is not int or t < 0 for t in measured):
        raise BackendError({'status': 'protocol_error', 'message': 'Missing Siemens scan timestamps'})
    outputs = task['field_order']['outputs'] if task['adapter_format'] == 'struct_rows' else list(zip(names, types))
    result = dataset.judge_output(source, task, {'outputs': outputs, 'source_sha256': hashlib.sha256(data).hexdigest(),
        'execution_fingerprint': response['execution_fingerprint'], 'target_compile': 'passed', 'test_backend': 'tia',
        'build_evidence': str(directory/'result.json'), 'scope': 'Native PLCSIM Advanced finite scenarios, no physical PLC claim'}, lines)
    result.update(target='tia', vendor='Siemens', simulation=True, behavior_tested=True,
                  vendor_evidence=str(directory), actual_scan_times_ms=measured, simulation_cpu=response.get('cpu_order_number'))
    if re.search(r'\b(?:TON|TOF|TP|TON_TIME|TOF_TIME|TP_TIME|TON_LTIME|RD_SYS_T|RD_LOC_T)\b', mask_noncode(data.decode('utf-8-sig')), re.I):
        drift = max((abs(a-b) for a, b in zip(measured, requested)), default=0)
        result['timing'] = {'clock': 'Siemens native', 'max_deviation_ms': drift, 'tolerance_ms': 1}
        if drift > 1:
            result.update(status='behavior_not_supported', behavior_tested=False,
                          message='Native simulation missed requested timer sampling times; not a candidate logic failure.')
    atomic_json(directory/'judgement.json', result)
    return result
