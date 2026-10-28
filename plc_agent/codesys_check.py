"""Check the real CODESYS compiler without a model or controller connection."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

from .config import ROOT
from .storage import atomic_json, now


def check(executable: Path, profile: str, output: Path, timeout=120):
    executable = executable.resolve()
    output = output.resolve()
    template = executable.parent.parent / 'Templates' / 'Standard.project'
    if not executable.is_file() or not template.is_file():
        raise ValueError('CODESYS.exe and Templates/Standard.project are required')
    # CODESYS parses the raw Windows command line; quoting each entire argv
    # element hides --profile from its parser. Quote option values explicitly.
    if any(char in profile for char in ('"', '\n', '\r')):
        raise ValueError('Invalid CODESYS profile')
    output.mkdir(parents=True, exist_ok=True)
    work = output / ('run-' + uuid.uuid4().hex[:12])
    work.mkdir()
    project = work / 'compiler-check.project'
    shutil.copy2(template, project)
    result_path = work / 'result.json'
    job = {
        'project': str(project), 'output': str(result_path),
        'negative_control': True,
        'declaration': 'FUNCTION_BLOCK ProbeFB\nVAR_INPUT\n Start : BOOL;\n Stop : BOOL;\nEND_VAR\nVAR_OUTPUT\n Motor : BOOL;\nEND_VAR',
        'implementation': 'IF Stop THEN Motor := FALSE; ELSIF Start THEN Motor := TRUE; END_IF;',
    }
    job_path = work / 'job.json'
    atomic_json(job_path, job)
    command = f'"{executable}" --noUI --profile="{profile}" --runscript="{ROOT / "scripts/codesys_smoke.py"}"'
    started = time.monotonic()
    timed_out = False
    try:
        run = subprocess.run(command, env={**os.environ, 'PLC_CODESYS_JOB': str(job_path)},
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=timeout)
        console = run.stdout
        returncode = run.returncode
    except subprocess.TimeoutExpired as exc:
        console = exc.stdout or b''
        returncode = None
        timed_out = True
    (work / 'console.log').write_bytes(console)
    result = json.loads(result_path.read_text(encoding='utf-8')) if result_path.exists() else {}
    passed = (not timed_out and returncode == 0 and result.get('status') == 'pass'
              and result.get('stage') == 'compiled'
              and result.get('negative_control', {}).get('rejected') is True)
    receipt = {
        'checked_at': now(), 'status': 'pass' if passed else 'setup_incomplete',
        'executable': str(executable), 'profile': profile,
        'returncode': returncode, 'timed_out': timed_out,
        'seconds': round(time.monotonic() - started, 3),
        'result': result, 'evidence_directory': str(work), 'model_calls': 0,
        'scope': 'Actual CODESYS code generation and invalid-code rejection. No controller connection or behavioral execution.',
    }
    atomic_json(output / 'receipt.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--profile', default='CODESYS V3.5 SP22 Patch 4')
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/local_setup/codesys')
    args = parser.parse_args()
    result = check(args.executable, args.profile, args.output)
    print(json.dumps({k: v for k, v in result.items() if k != 'result'}, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
