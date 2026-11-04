"""Siemens native behavior tests; scenario predicates are shared with CODESYS."""
import hashlib
import json
import math
from pathlib import Path
import re
import time

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


def _native_rows(response, plan):
    raw = response['actual_rows']; names = plan['output_names']; types = plan['output_types']
    if len(raw) != plan['row_count']:
        raise BackendError({'status': 'protocol_error', 'message': 'Wrong Siemens simulation row count'})
    for row in raw:
        if not isinstance(row, dict) or set(row) != set(names):
            raise BackendError({'status': 'protocol_error', 'message': 'Wrong Siemens simulation output columns'})
        for name, dtype in zip(names, types):
            value = row[name]
            if dtype == 'BOOL':
                if type(value) is not bool:
                    raise BackendError({'status': 'protocol_error', 'message': 'Expected native BOOL'})
            elif type(value) not in (int, float) or not math.isfinite(value):
                raise BackendError({'status': 'protocol_error', 'message': 'Expected finite native number'})
    measured = response['actual_scan_times_ms']
    if len(measured) != len(raw) or any(type(t) is not int or t < 0 for t in measured):
        raise BackendError({'status': 'protocol_error', 'message': 'Missing Siemens scan timestamps'})
    return raw


def _simulate(source, task, plan, config, directory, cancel_event):
    # Open-array scenarios have different caller-owned shapes and independent
    # FB instances. Build one complete scenario per card instead of unrolling
    # every shape into a single oversized CPU1511 program. Never split a trace.
    if task['adapter_format'] != 'analog_reference_rows' or len(task['scenarios']) < 2:
        return tia.simulate_scl(source, plan, config, directory=directory, cancel_event=cancel_event)
    directory.mkdir(parents=True, exist_ok=True)
    original = source.read_bytes()
    deadline = time.monotonic()+config.get('simulation_timeout_seconds', 600)
    manifest = {'schema': 'tia-scenario-batches-v1', 'source_sha256': hashlib.sha256(original).hexdigest(),
                'dataset_sha256': task.get('dataset_sha256'), 'row_count': plan['row_count'],
                'scenario_count': len(task['scenarios']), 'batches': [], 'status': 'running'}
    rows = []; measured = []; identity = None; cpu = None
    for index, case in enumerate(task['scenarios']):
        if source.read_bytes() != original:
            raise BackendError({'status': 'stale_evidence', 'message': 'SCL changed between Siemens scenario batches'})
        remaining = int(deadline-time.monotonic())
        batch_task = {**task, 'scenarios': [case]}
        batch_plan = harness(batch_task)
        entry = {'index': index, 'name': case['name'], 'row_offset': len(rows),
                 'row_count': batch_plan['row_count'], 'output_names': batch_plan['output_names'],
                 'scenario_sha256': hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest(),
                 'evidence_path': str(directory/f'scenario_{index+1:02d}')}
        manifest['batches'].append(entry)
        atomic_json(directory/'batch_manifest.json', manifest)
        if remaining < batch_plan['simulation_timeout_seconds']+240:
            response = {'status': 'timeout', 'phase': 'scenario_batch',
                        'message': 'Shared Siemens simulation budget exhausted before next complete scenario'}
        else:
            response = tia.simulate_scl(source, batch_plan, {**config, 'simulation_timeout_seconds': remaining},
                                       directory=Path(entry['evidence_path']), cancel_event=cancel_event, deadline=deadline)
        entry['status'] = response['status']
        if response['status'] != 'simulation_completed':
            manifest['status'] = response['status']
            atomic_json(directory/'batch_manifest.json', manifest)
            result = {**response, 'scenario_batch_index': index, 'batch_manifest': str(directory/'batch_manifest.json')}
            atomic_json(directory/'result.json', result)
            return result
        try:
            raw = _native_rows(response, batch_plan)
            if response.get('source_sha256') != manifest['source_sha256']:
                raise BackendError({'status': 'stale_evidence', 'message': 'Siemens scenario batch used a different candidate source'})
            if identity is not None and (response['execution_fingerprint'] != identity or response.get('cpu_order_number') != cpu):
                raise BackendError({'status': 'stale_evidence', 'message': 'Siemens runtime identity changed between scenario batches'})
        except BackendError as exc:
            entry['status'] = manifest['status'] = exc.result['status']
            atomic_json(directory/'batch_manifest.json', manifest)
            atomic_json(directory/'result.json', exc.result)
            raise
        identity = response['execution_fingerprint']; cpu = response.get('cpu_order_number')
        # Rectangular transport padding only; padding is discarded before the
        # original full-task predicate sees any value. Validate each native row
        # against its actual shape before adding transport-only zeros.
        rows.extend({name: row.get(name, False if dtype == 'BOOL' else 0)
                     for name, dtype in zip(plan['output_names'], plan['output_types'])} for row in raw)
        measured.extend(response['actual_scan_times_ms'])
        atomic_json(directory/'batch_manifest.json', manifest)
    manifest['status'] = 'simulation_completed'
    atomic_json(directory/'batch_manifest.json', manifest)
    fingerprint = {**identity, 'scenario_batches_sha256': tia.sha256(directory/'batch_manifest.json')}
    result = {'status': 'simulation_completed', 'simulation': True,
              'actual_rows': rows, 'actual_scan_times_ms': measured, 'execution_fingerprint': fingerprint,
              'cpu_order_number': cpu, 'source_sha256': manifest['source_sha256'],
              'test_backend': 'tia', 'batch_manifest': str(directory/'batch_manifest.json')}
    atomic_json(directory/'result.json', result)
    return result


def evaluate(source, task, config, cancel_event=None, *, directory=None):
    source = Path(source); data = source.read_bytes()
    if re.search(r'\b(?:WB_TestHarness(?:_DB)?|ORGANIZATION_BLOCK|PROGRAM)\b', mask_noncode(data.decode('utf-8-sig').replace('"', ' ')), re.I):
        raise BackendError({'status': 'behavior_not_supported', 'message': 'WB_TestHarness and test OB/DBs are reserved for the Siemens harness', 'test_backend': 'tia'})
    if re.search(r'\bDATA_BLOCK\b', mask_noncode(data.decode('utf-8-sig')), re.I):
        # Independent scenario UUTs must not acquire hidden shared mutable DB
        # state. Admit only the closed, immutable DB subset checked by the TIA
        # adapter; execute the original source unchanged in native simulation.
        from .tia_formal import adapt
        from .ltl_adapter import Unsupported
        try: adapt(data.decode('utf-8-sig'), block=task['block'])
        except (Unsupported, ValueError) as exc:
            raise BackendError({'status':'behavior_not_supported','test_backend':'tia',
                                'message':'External DB dependency: '+str(exc)}) from exc
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
    response = _simulate(source, task, plan, config, directory, cancel_event)
    if response['status'] != 'simulation_completed':
        raise BackendError(response)
    if source.read_bytes() != data:
        raise BackendError({'status': 'stale_evidence', 'message': 'SCL changed during simulation'})
    raw = _native_rows(response, plan); names = plan['output_names']; types = plan['output_types']
    lines = []
    for row in raw:
        values = []
        for name, dtype in zip(names, types):
            value = row[name]
            if dtype == 'BOOL':
                value = int(value)
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
