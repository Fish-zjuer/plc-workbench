"""Measure saved public-bank candidates with the actual CODESYS compiler."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid

from .bank_contracts import block, questions
from .config import ROOT
from .storage import atomic_json, now
from .st_source import mask_noncode, split_units, caller


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_receipt(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(value, dict): raise ValueError('Receipt must be a JSON object')
        return value
    except (OSError, ValueError) as exc:
        return {'status': 'invalid_receipt', 'message': str(exc)}


def summarize(results, environment):
    counts = Counter(row['status'] for row in results)
    ready = (environment.get('status') == 'pass'
             and environment.get('negative_control', {}).get('rejected') is True)
    return {'tasks': len(results), 'compiled': counts['pass'],
            'compile_errors': counts['compile_error'],
            'not_measured': len(results) - counts['pass'] - counts['compile_error'],
            'environment_validated': ready,
            'compilation_pass_rate': counts['pass'] / len(results) if ready and results else None,
            'status_counts': dict(counts)}


def run_bank(executable, profile, ids, sources, output, timeout=600):
    executable = executable.resolve()
    output = output.resolve()
    template = executable.parent.parent / 'Templates/Standard.project'
    if not executable.is_file() or not template.is_file(): raise ValueError('CODESYS installation not found')
    if any(c in profile for c in ('"', '\n', '\r')): raise ValueError('Invalid CODESYS profile')
    output.mkdir(parents=True, exist_ok=False)
    run_id = uuid.uuid4().hex
    scratch = ROOT / '.runtime/codesys-bank' / run_id
    scratch.mkdir(parents=True)
    shutil.copy2(template, scratch / 'base.project')
    tasks = []
    from .workflow import validate_candidate
    catalog = {q['id']: q for q in questions()}
    for qid in ids:
        source = sources / qid / 'final.st'
        directory = output / 'tasks' / qid
        directory.mkdir(parents=True)
        data = source.read_bytes()
        snapshot = directory / 'source.st'
        snapshot.write_bytes(data)
        code = data.decode('utf-8-sig')
        task = {'question_id': qid, 'run_id': run_id, 'source_path': str(source.resolve()),
                'source_sha256': hashlib.sha256(data).hexdigest(),
                'title': catalog[qid]['text'].splitlines()[0].lstrip('# '),
                'difficulty': catalog[qid]['difficulty'],
                'result_path': str(directory / 'result.json'),
                'project_path': str(scratch / (qid + '.project'))}
        try:
            validate_candidate(code, catalog[qid])
            task.update(units=split_units(code), caller=caller(catalog[qid]))
            atomic_json(directory / 'import.json', {'units': task['units'], 'caller': task['caller']})
        except ValueError as exc:
            task['import_error'] = str(exc)
        tasks.append(task)
    job = {'run_id': run_id, 'tasks': tasks, 'base_project': str(scratch / 'base.project'),
           'environment_path': str(output / 'environment.json'),
           'device': {'type': 4096, 'id': '0000 0004', 'version': '3.5.22.40'}}
    job_path = output / 'job.json'
    atomic_json(job_path, job)
    started = time.monotonic()
    command = f'"{executable}" --noUI --profile="{profile}" --runscript="{ROOT / "scripts/codesys_batch.py"}"'
    returncode = None
    timed_out = False
    try:
        with (output / 'console.log').open('wb') as console:
            completed = subprocess.run(command, env={**os.environ, 'PLC_CODESYS_BANK_JOB': str(job_path)},
                                       stdin=subprocess.DEVNULL, stdout=console, stderr=subprocess.STDOUT, timeout=timeout)
            returncode = completed.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
    env_path = Path(job['environment_path'])
    environment = read_receipt(env_path)
    results = []
    for task in tasks:
        path = Path(task['result_path'])
        result = read_receipt(path) if path.exists() else {
            'question_id': task['question_id'], 'status': 'not_measured', 'message': 'No completed compiler receipt'}
        if (result.get('run_id') != run_id or result.get('source_sha256') != task['source_sha256']
                or result.get('stage') != 'compiled'):
            if result.get('status') in ('pass', 'compile_error'):
                result.update(status='invalid_receipt', message='Unbound or incomplete compiler evidence')
        if digest(task['source_path']) != task['source_sha256']:
            result['source_changed_since_snapshot'] = True
        result.update(title=task['title'], difficulty=task['difficulty'], source_path=task['source_path'],
                      measured_source_sha256=task['source_sha256'])
        results.append(result)
    # An invalid environment makes candidate verdicts unusable as measurements.
    if environment.get('status') != 'pass' or not environment.get('negative_control', {}).get('rejected'):
        for result in results:
            if result['status'] in ('pass', 'compile_error'): result['status'] = 'environment_error'
    report = {'checked_at': now(), 'run_id': run_id, 'profile': profile, 'executable': str(executable),
              'executable_sha256': digest(executable), 'returncode': returncode, 'timed_out': timed_out,
              'seconds': round(time.monotonic() - started, 3), 'environment': environment,
              'summary': summarize(results, environment), 'results': results, 'model_calls': 0,
              'scope': 'Unmodified supplied ST candidates; actual CODESYS target code generation. No behavioral execution or new model generation.'}
    atomic_json(output / 'results.json', report)
    write_report(output, report)
    return report


def write_report(output, report):
    s = report['summary']
    rate = '未测得' if s['compilation_pass_rate'] is None else f"{s['compilation_pass_rate']:.1%}"
    local_time = datetime.fromisoformat(report['checked_at']).astimezone(timezone(timedelta(hours=8)))
    lines = ['# 公共20题 CODESYS 编译测量', '',
             f"时间：{local_time.strftime('%Y-%m-%d %H:%M:%S')}（北京时间）。平台：{report['profile']} / Control Win V3 x64 3.5.22.40。", '',
             f"通过 {s['compiled']}/{s['tasks']}，编译失败 {s['compile_errors']}，未完成测量 {s['not_measured']}；通过率 **{rate}**。", '',
             '本轮冻结并原样导入提供的 ST 候选。仅拆分 CODESYS 编辑器要求的 DUT/POU 声明及实现，调用驱动提供 IN_OUT 存储；未修复候选、增加 PV1 替身或改写接口。通过要求真实目标代码生成无错误。', '',
             '每题独立工程；编译环境先通过正确程序及故意错误程序的正反对照。功能正确性、PLC运行与新的模型生成表现不在本轮测量范围内。', '',
             '| 题号 | 题目 | 结果 | 错误数 | 警告数 | 首条诊断 |',
             '|---|---|---|---:|---:|---|']
    for r in report['results']:
        errors = r.get('errors', [])
        message = errors[0]['text'] if errors else r.get('message', '')
        message = message.replace('|', '/').replace('\n', ' ')[:180]
        lines.append(f"| {r['question_id']} | {r['title']} | {r['status']} | {len(errors)} | {len(r.get('warnings', []))} | {message} |")
    lines += ['', '完整诊断、运行标识和 SHA256 见 results.json；逐题原样源码及导入信息在 tasks/<题号>/。CODESYS 原始输出见 console.log。历史离线20/20结果与本轮平台编译指标分别报告。', '']
    with (output / 'report.md').open('w', encoding='utf-8', newline='\n') as stream:
        stream.write('\n'.join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', required=True, type=Path)
    parser.add_argument('--profile', default='CODESYS V3.5 SP22 Patch 4')
    parser.add_argument('--ids', default=','.join(f'{i:02d}' for i in range(1, 21)))
    parser.add_argument('--sources', type=Path, default=ROOT / 'experiments/backend_r4/tasks')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    ids = [s.strip().zfill(2) for s in args.ids.split(',')]
    if not ids or len(ids) != len(set(ids)) or any(i not in {q['id'] for q in questions()} for i in ids):
        parser.error('--ids requires distinct public question numbers 01..20')
    output = args.output or ROOT / 'reports/codesys_public20' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    report = run_bank(args.executable, args.profile, ids, args.sources, output)
    print(json.dumps({'summary': report['summary'], 'output': str(output)}, ensure_ascii=False, indent=2))
    return 0 if report['summary']['not_measured'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
