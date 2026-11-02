"""TIA Openness compile-only adapter. Each invocation owns a fresh project copy."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from .config import STATE_ROOT
from .provider import Cancelled
from .storage import atomic_json, read_json

PREFIX = 'WB_RESULT_JSON='
SCOPE = 'Vendor compilation only; no simulation, behavior test or PLC download'


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
    return config


def doctor(home=STATE_ROOT):
    config = load_config(home)
    try:
        validate_config(config)
        return {'status': 'configured_not_probed', 'configuration': config, 'scope': SCOPE}
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
        process = subprocess.Popen(command, stdout=out, stderr=err, shell=False)
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
    result = {**result, 'source_sha256': source_hash, 'execution_fingerprint': identity,
              'target_compile': 'passed' if result['status'] == 'compile_passed' else
                                'failed' if result['status'] in ('compile_failed', 'generation_failed') else 'not_executed',
              'behavior_tested': False, 'scope': SCOPE, 'evidence_path': str(directory),
              'seconds': round(time.monotonic()-started, 3)}
    atomic_json(directory/'result.json', result)
    return result
