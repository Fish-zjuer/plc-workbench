"""TIA Openness compilation and native simulation, each on a fresh project copy."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import threading
from functools import wraps

from .config import STATE_ROOT
from .provider import Cancelled
from .storage import atomic_json, read_json
from .tia_runtime import vendor_lease, VendorBusy, infrastructure_details

PREFIX = 'WB_RESULT_JSON='
SCOPE = 'Vendor compilation only; no simulation, behavior test or PLC download'
_vendor_slot=threading.Semaphore(1)


def _serialized(operation):
    """Batch model requests may overlap; local TIA sessions are serialized."""
    @wraps(operation)
    def invoke(*args,**kwargs):
        config=kwargs.get('config') or (args[2] if operation.__name__=='simulate_scl' and len(args)>2 else args[1] if len(args)>1 else None) or load_config()
        absolute_deadline=kwargs.get('deadline')
        def queue_budget():
            limit=config.get('timeout_seconds',300)
            return min(limit,max(0,absolute_deadline-time.monotonic())) if absolute_deadline is not None else limit
        cancel=kwargs.get('cancel_event')
        owned=_vendor_slot.acquire(blocking=False)
        if not owned:
            started=time.monotonic();cancel=kwargs.get('cancel_event')
            config=kwargs.get('config') or (args[2] if operation.__name__=='simulate_scl' and len(args)>2 else args[1] if len(args)>1 else None) or load_config()
            while not owned:
                if cancel and cancel.is_set():raise Cancelled('TIA queue cancelled')
                if time.monotonic()-started>config.get('timeout_seconds',300) or queue_budget()<=0:
                    return {'status':'backend_busy','target_compile':'not_executed','behavior_tested':False,
                            'message':'Local TIA session queue timed out; reduce vendor concurrency.'}
                owned=_vendor_slot.acquire(timeout=.1)
        try:
            try:
                with vendor_lease(queue_budget(),cancel):
                    return operation(*args,**kwargs)
            except VendorBusy as exc:
                return {'status':'backend_busy','target_compile':'not_executed','behavior_tested':False,
                        'phase':'vendor_queue','failure_kind':'vendor_busy','message':str(exc)}
        finally:_vendor_slot.release()
    return invoke


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_config(home=STATE_ROOT):
    path = Path(home)/'tia.json'
    return read_json(path) if path.exists() else {}


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError('TIA configuration must be an object')
    for key, suffix in (('executable', '.exe'), ('template_project', '.ap21')):
        value = config.get(key)
        if not isinstance(value, str) or not Path(value).is_file() or Path(value).suffix.lower() != suffix:
            raise ValueError('Configure an existing TIA '+key+' ('+suffix+')')
    timeout = config.get('timeout_seconds', 300)
    if type(timeout) is not int or not 5 <= timeout <= 900:
        raise ValueError('TIA timeout_seconds must be 5..900')
    for key in ('simulation_api', 'simulation_template_project', 'openness_directory'):
        if key in config and not isinstance(config[key], str): raise ValueError(key+' must be a path string')
    if config.get('openness_directory') and not (Path(config['openness_directory'])/'Siemens.Engineering.Base.dll').is_file():
        raise ValueError('openness_directory must contain Siemens.Engineering.Base.dll')
    if 'simulation_timeout_seconds' in config and (type(config['simulation_timeout_seconds']) is not int or not 150 <= config['simulation_timeout_seconds'] <= 7200):
        raise ValueError('simulation_timeout_seconds must be 150..7200')
    return config


def doctor(home=STATE_ROOT):
    config = load_config(home)
    try:
        validate_config(config)
        return {'status': 'configured_not_probed', 'configuration': config, 'scope': SCOPE,
                'simulation': simulation_environment(config)}
    except (ValueError, OSError) as exc:
        return {'status': 'setup_required', 'configuration': config, 'message': str(exc), 'scope': SCOPE}


def parse_result(stdout, returncode):
    lines = [line.lstrip('\ufeff')[len(PREFIX):] for line in stdout.splitlines()
             if line.lstrip('\ufeff').startswith(PREFIX)]
    try:
        if len(lines) != 1:
            raise ValueError('Expected exactly one WB_RESULT_JSON receipt')
        result = json.loads(lines[0])
        allowed = {'compile_passed': 0, 'compile_failed': 1, 'generation_failed': 1, 'bridge_error': 2}
        if not isinstance(result, dict) or result.get('status') not in allowed:
            raise ValueError('Unknown bridge status')
        if returncode != allowed[result['status']]:
            raise ValueError('Bridge exit code contradicts receipt')
        if result['status'] == 'compile_passed' and (type(result.get('errors')) is not int or result['errors'] != 0):
            raise ValueError('Success receipt must contain zero compiler errors')
        return {**result, 'returncode': returncode}
    except (ValueError, TypeError) as exc:
        return {'status': 'bridge_protocol_error', 'message': str(exc), 'returncode': returncode}


def _stop(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
    else:
        process.kill()
    process.wait(timeout=20)


def _bridge_environment(config):
    if not config.get('openness_directory'): return {}
    return {'env': {**os.environ, 'TIA_OPENNESS_DIR': str(Path(config['openness_directory']).resolve())}}


@_serialized
def compile_scl(source, config=None, *, directory=None, cancel_event=None):
    """Return structured diagnostics and durable stdout/stderr for real TiaBridge."""
    config = validate_config(config if config is not None else load_config())
    source = Path(source).resolve()
    if not source.is_file() or source.suffix.lower() != '.scl':
        raise ValueError('Need an existing .scl source')
    if cancel_event and cancel_event.is_set():
        raise Cancelled('TIA compilation cancelled')
    if directory is None:
        root = STATE_ROOT/'tia_runs'
        root.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix='compile_', dir=root))
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    template = Path(config['template_project']).resolve()
    if directory.is_relative_to(template.parent):
        raise ValueError('Compile evidence must be outside the template project directory')
    data = source.read_bytes()
    source_hash = hashlib.sha256(data).hexdigest()
    identity = {'bridge_sha256': sha256(config['executable']), 'template_sha256': sha256(template),
                'adapter_sha256': sha256(__file__)}
    # TIA projects include System/ and other sidecars, not just the .ap21 file.
    # Ignore only transient locks; preserve all project content in the copy.
    project_dir = directory/'project'
    shutil.copytree(template.parent, project_dir, ignore=shutil.ignore_patterns('*.lck', '*.lock'))
    staged = directory/'input.scl'
    staged.write_bytes(data)
    command = [str(Path(config['executable']).resolve()), str(project_dir/template.name), str(staged)]
    atomic_json(directory/'request.json', {'command': command, 'source_sha256': source_hash,
                'template_project': str(template), **identity})
    started = time.monotonic()
    with (directory/'stdout.txt').open('wb') as out, (directory/'stderr.txt').open('wb') as err:
        process = subprocess.Popen(command, stdout=out, stderr=err, shell=False, **_bridge_environment(config))
        try:
            while process.poll() is None:
                if cancel_event and cancel_event.wait(.2):
                    raise Cancelled('TIA compilation cancelled')
                if not cancel_event:
                    time.sleep(.2)
                if time.monotonic()-started > config.get('timeout_seconds', 300):
                    _stop(process)
                    result = {'status': 'timeout', 'message': 'TIA bridge exceeded compile timeout'}
                    break
            else:
                result = None
        except BaseException:
            _stop(process)
            atomic_json(directory/'result.json', {'status': 'interrupted', 'source_sha256': source_hash,
                        'behavior_tested': False, 'target_compile': 'not_executed'})
            raise
    if result is None:
        result = parse_result((directory/'stdout.txt').read_text(encoding='utf-8-sig', errors='replace'), process.returncode)
    if source.read_bytes() != data or sha256(template) != identity['template_sha256'] or sha256(config['executable']) != identity['bridge_sha256']:
        result = {'status': 'stale_evidence', 'message': 'Source, template or bridge changed during compilation'}
    result = infrastructure_details(result, directory)
    result = {**result, 'source_sha256': source_hash, 'execution_fingerprint': identity,
              'target_compile': 'passed' if result['status'] == 'compile_passed' else
                                'failed' if result['status'] in ('compile_failed', 'generation_failed') else 'not_executed',
              'behavior_tested': False, 'scope': SCOPE, 'evidence_path': str(directory),
              'seconds': round(time.monotonic()-started, 3)}
    atomic_json(directory/'result.json', result)
    return result


def simulation_environment(config):
    try:
        validate_simulation_config(config)
        return {'status': 'configured_not_probed', 'message': 'PLCSIM API and template found; native execution has not been probed.'}
    except (ValueError, OSError) as exc:
        return {'status': 'behavior_not_configured', 'message': str(exc)}


def discover_simulation_api():
    roots = [Path(os.environ.get('ProgramFiles', 'C:/Program Files'))/'Siemens/Automation',
             Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)'))/'Siemens/Automation',
             Path(os.environ.get('CommonProgramFiles', 'C:/Program Files/Common Files'))/'Siemens',
             Path(os.environ.get('CommonProgramFiles(x86)', 'C:/Program Files (x86)/Common Files'))/'Siemens']
    return next((str(p) for root in roots for p in sorted(root.glob('PLCSIMADV*/API/**/Siemens.Simatic.Simulation.Runtime.Api.x64.dll'))), '')


def validate_simulation_config(config):
    validate_config(config)
    api = config.get('simulation_api') or discover_simulation_api()
    if not api or not Path(api).is_file() or Path(api).name.lower() != 'siemens.simatic.simulation.runtime.api.x64.dll':
        raise ValueError('Configure the installed PLCSIM Advanced x64 API DLL (simulation_api); standard PLCSIM has no equivalent co-simulation API.')
    template = config.get('simulation_template_project') or config['template_project']
    if not Path(template).is_file() or Path(template).suffix.lower() != '.ap21':
        raise ValueError('Configure a dedicated V21 S7-1500 simulation project (simulation_template_project)')
    seconds = config.get('simulation_timeout_seconds', 600)
    if type(seconds) is not int or not 150 <= seconds <= 7200:
        raise ValueError('simulation_timeout_seconds must be 150..7200')
    runtime_host = Path(config['executable']).resolve().with_name('TiaRuntime.exe')
    if not runtime_host.is_file():
        raise ValueError('Rebuild TiaBridge with its separate TiaRuntime.exe simulation host')
    return {**config, 'simulation_api': str(Path(api).resolve()), 'simulation_template_project': str(Path(template).resolve()),
            'simulation_runtime_host': str(runtime_host)}


def _stop_simulation(process, directory, config):
    # Give native code a chance to PowerOff/Unregister in finally. If a blocking
    # Siemens call prevents that, a separate API-only helper cleans our instance.
    (directory/'cancel.signal').write_text('cancel', encoding='ascii')
    try: process.wait(timeout=10)
    except subprocess.TimeoutExpired: _stop(process)
    manifest = directory/'simulator.json'
    if manifest.is_file() and not (directory/'simulator_closed.json').is_file():
        with (directory/'cleanup.txt').open('ab') as log:
            try:
                completed = subprocess.run([config['simulation_runtime_host'], '--cleanup-simulator', str(manifest)],
                    stdout=log, stderr=log, shell=False, timeout=60, **_bridge_environment(config))
                atomic_json(directory/'cleanup.json', {'returncode': completed.returncode, 'attempted': True})
            except (OSError, subprocess.SubprocessError) as exc:
                atomic_json(directory/'cleanup.json', {'attempted': True, 'message': str(exc)})


def _simulation_process(command, directory, config, deadline, cancel_event, *, prepare=False):
    prefix='prepare-' if prepare else ''
    stdout_path=directory/(prefix+'stdout.txt')
    with stdout_path.open('wb') as out, (directory/(prefix+'stderr.txt')).open('wb') as err:
        if cancel_event and cancel_event.is_set(): raise Cancelled('TIA simulation cancelled')
        if time.monotonic()>=deadline:
            return {'status':'timeout','phase':'prepare_card' if prepare else 'starting_runtime_host',
                    'message':'Siemens simulation budget exhausted before starting next process'}
        process=subprocess.Popen(command,stdout=out,stderr=err,shell=False,**_bridge_environment(config))
        try:
            while process.poll() is None:
                if cancel_event and cancel_event.wait(.2): raise Cancelled('TIA simulation cancelled')
                if not cancel_event: time.sleep(.2)
                if time.monotonic()>=deadline:
                    _stop_simulation(process,directory,config)
                    return {'status':'timeout','message':'Siemens simulation timeout; inspect stage and runtime evidence'}
        except BaseException:
            _stop_simulation(process,directory,config)
            atomic_json(directory/'result.json',{'status':'interrupted','behavior_tested':False})
            raise
    lines=[line.lstrip('\ufeff')[len(PREFIX):] for line in stdout_path.read_text(encoding='utf-8-sig',errors='replace').splitlines()
           if line.lstrip('\ufeff').startswith(PREFIX)]
    try:
        if len(lines)!=1: raise ValueError('Expected one simulation receipt per process; rebuild TiaBridge/TiaRuntime')
        result=json.loads(lines[0]); success='simulation_prepared' if prepare else 'simulation_completed'
        if not isinstance(result,dict) or result.get('status') not in (success,'simulation_error','behavior_not_supported','bridge_error','harness_error'):
            raise ValueError('Unknown simulation stage status')
        if process.returncode!=(0 if result['status']==success else 2): raise ValueError('Simulation exit code contradicts receipt')
        if result['status']=='simulation_completed' and (result.get('simulation') is not True or
                not isinstance(result.get('actual_rows'),list) or not isinstance(result.get('actual_scan_times_ms'),list) or not result.get('instance_name')):
            raise ValueError('Native execution evidence missing')
        return result
    except (ValueError,TypeError) as exc:
        return {'status':'bridge_protocol_error','message':str(exc)}


@_serialized
def simulate_scl(source, plan, config, *, directory, cancel_event=None, deadline=None):
    """Execute the native bridge protocol on a fresh project and owned simulator.

    The bridge exports a virtual memory card; no physical PLC endpoint is used.
    Expected outputs are never included in the simulator request.
    """
    config = validate_simulation_config(config)
    source = Path(source).resolve(); data = source.read_bytes()
    directory = Path(directory).resolve(); directory.mkdir(parents=True, exist_ok=True)
    template = Path(config['simulation_template_project'])
    if directory.is_relative_to(template.parent): raise ValueError('Simulation evidence must be outside the template project')
    identity = {'bridge_sha256': sha256(config['executable']), 'template_sha256': sha256(template),
                'runtime_host_sha256': sha256(config['simulation_runtime_host']),
                'simulation_api_sha256': sha256(config['simulation_api']), 'adapter_sha256': sha256(__file__)}
    project = directory/'project'
    shutil.copytree(template.parent, project, ignore=shutil.ignore_patterns('*.lck', '*.lock'))
    staged = directory/'input.scl'; staged.write_bytes((data.decode('utf-8-sig')+'\n'+plan['harness_source']).encode('utf-8-sig'))
    request = {'schema': 'tia-simulation-v1', 'project': str(project/template.name), 'source': str(staged),
               'source_sha256': hashlib.sha256(data).hexdigest(), 'simulation_api': config['simulation_api'],
               'output_names': plan['output_names'], 'output_types': plan['output_types'], 'row_count': plan['row_count'],
               'simulation_timeout_seconds': plan['simulation_timeout_seconds'], 'result_db': plan['result_db'],
               'evidence_directory': str(directory), 'execution_fingerprint': identity}
    atomic_json(directory/'request.json', request)
    started = time.monotonic()
    if cancel_event and cancel_event.is_set(): raise Cancelled('TIA simulation cancelled')
    deadline = min(deadline,started+config.get('simulation_timeout_seconds',600)) if deadline is not None else started+config.get('simulation_timeout_seconds',600)
    prepared = _simulation_process([str(Path(config['executable']).resolve()), '--prepare-simulation', str(directory/'request.json')],
                                   directory, config, deadline, cancel_event, prepare=True)
    atomic_json(directory/'prepare-result.json', prepared)
    result = prepared
    if prepared['status'] == 'simulation_prepared':
        # A receipt is not enough: bind the handed-off card to this exact source,
        # test driver and executables before starting any native runtime.
        try:
            card = read_json(directory/'prepared_card.json')
            valid = (card.get('schema')=='tia-prepared-card-v1' and
                     card.get('source_sha256')==request['source_sha256'] and
                     card.get('source_bundle_sha256')==sha256(staged) and
                     card.get('bridge_sha256')==identity['bridge_sha256'] and
                     card.get('runtime_host_sha256')==identity['runtime_host_sha256'])
        except (ValueError, OSError, AttributeError): valid=False
        if not valid:
            result={'status':'bridge_protocol_error','phase':'card_handoff',
                    'message':'Prepared card identity is missing or does not match the source/driver/bridge/runtime'}
        elif source.read_bytes()!=data or any(sha256(config[k])!=identity[h] for k,h in [
                ('executable','bridge_sha256'),('simulation_runtime_host','runtime_host_sha256')]):
            result={'status':'stale_evidence','phase':'card_handoff','message':'Source or executables changed before runtime startup'}
        else:
            # _simulation_process has observed the Bridge exit. The process that
            # loaded Openness is gone before Python starts the API-only worker.
            result=_simulation_process([config['simulation_runtime_host'],'--run-simulation-card',str(directory/'request.json')],
                                       directory, config, deadline, cancel_event)
    if source.read_bytes()!=data or any(sha256(config[k])!=identity[h] for k,h in [('executable','bridge_sha256'), ('simulation_runtime_host','runtime_host_sha256'), ('simulation_template_project','template_sha256'), ('simulation_api','simulation_api_sha256')]):
        result = {'status': 'stale_evidence', 'message': 'Source or simulation environment changed'}
    result = infrastructure_details(result, directory)
    result.update(source_sha256=hashlib.sha256(data).hexdigest(), execution_fingerprint=identity,
                  evidence_path=str(directory), test_backend='tia', seconds=round(time.monotonic()-started,3))
    atomic_json(directory/'result.json', result)
    return result
