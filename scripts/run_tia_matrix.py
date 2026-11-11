"""Single-model TIA matrix: two frameworks times independent repeats, frozen tasks."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from plc_agent import dataset, tia
from plc_agent.campaign import LIMITS, Trial, preflight, run_codex, run_self
from plc_agent.config import ModelConfig, STATE_ROOT
from plc_agent.inference import inference_config
from plc_agent.plcverif_backend import configuration
from plc_agent.public_output import export
from plc_agent.run_output import LOCAL_TIME, reserve_run
from plc_agent.storage import atomic_json
from plc_agent.tia_cli import probe


def task_matrix(ids, repeats=2):
    return [{'task_id': ident, 'framework': framework, 'repeat': repeat, 'status': 'not_started',
             'group': framework + '_r' + str(repeat)}
            for ident in ids for framework in ('self', 'codex') for repeat in range(1, repeats+1)]


def configure_temporary(path):
    # Keep an explicitly supplied drive alias: resolve() expands it back to the
    # original Unicode path and would defeat the shared verifier's ASCII rule.
    temporary = Path(path).expanduser().absolute()
    if not str(temporary).isascii():
        raise ValueError('PLCverif needs an ASCII temporary path; set --temp-root or use run-tia-matrix.ps1')
    temporary.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(temporary)
    os.environ['TEMP'] = os.environ['TMP'] = str(temporary)


def prepare(ids, model, repeats, home):
    cfg = inference_config(ModelConfig.load(home), model, {'mode': 'low'})
    tasks = [dataset.load(ident) for ident in ids]
    ready = preflight(home, True, target='tia')
    formal = configuration(home)
    errors = list(ready['errors'])
    try:
        tia.validate_simulation_config(tia.load_config(home))
    except (ValueError, OSError) as exc:
        errors.append(str(exc))
    for tool in ('plcverif', 'java', 'cbmc'):
        if not formal.get(tool) or not Path(formal[tool]).is_file():
            errors.append('Formal tool missing: ' + tool)
    return cfg, tasks, {'status': 'setup_required' if errors else 'ready', 'errors': list(dict.fromkeys(errors)),
                        'runtime': ready, 'formal': formal}, task_matrix(ids, repeats)


def write_summary(path, record):
    atomic_json(path/'matrix.json', record)
    with (path/'results.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['task_id', 'framework', 'repeat', 'group', 'status',
                                                    'target_compile', 'finite_test_status', 'formal_status', 'model_calls'])
        writer.writeheader()
        for row in record['jobs']:
            writer.writerow({k: row.get(k, '') for k in writer.fieldnames})
    lines = ['# TIA 单模型重复实验', '', '状态：' + record['status'],
             '模型：' + record['model'], '计划任务：' + str(record['total']),
             '已结束：' + str(record['completed']), '模型请求：' + str(record['model_calls']), '',
             '四组为 self_r1 / self_r2 / codex_r1 / codex_r2；同一模型、同一推理设置、独立从空源码开始。',
             '这是框架与重复实验，不是两个不同模型的对照。', '']
    lines += ['- ' + message for message in record['preflight']['errors']]
    (path/'SUMMARY.md').write_text('\n'.join(lines), encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=STATE_ROOT)
    parser.add_argument('--model', default='deepseek-flash')
    parser.add_argument('--ids', default='all')
    parser.add_argument('--repeats', type=int, choices=range(1, 5), default=2)
    parser.add_argument('--concurrency', type=int, choices=range(1, 5), default=2)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--temp-root', type=Path, default=Path.home()/'.cache/plc-workbench/tmp')
    args = parser.parse_args(argv)
    ids = [t['id'] for t in dataset.catalog()['tasks']] if args.ids == 'all' else args.ids.split(',')
    if not ids or len(set(ids)) != len(ids):
        parser.error('Task IDs must be nonempty and unique')
    cfg, tasks, readiness, jobs = prepare(ids, args.model, args.repeats, args.home)
    cfg.validate()
    path = reserve_run(ROOT/'outputs/tia_matrix', 'deepseek_flash')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    code_hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for folder in ('plc_agent', 'integrations', 'scripts') for p in (ROOT/folder).rglob('*')
                   if p.is_file() and p.suffix in ('.py', '.ps1', '.cs', '.csproj') and not {'bin', 'obj'}.intersection(p.parts)}
    record = {'schema': 'plc-tia-repeat-matrix-v1', 'id': path.name, 'target': 'tia', 'model': cfg.model,
              'source_revision': revision,
              'source_worktree_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
              'code_hashes': code_hashes, 'model_configuration': cfg.public(),
              'inference_parameters': cfg.extra_body, 'limits': LIMITS, 'repeats': args.repeats,
              'concurrency': args.concurrency, 'total': len(jobs), 'completed': 0, 'model_calls': 0,
              'status': 'prepared' if readiness['status'] == 'ready' else 'setup_required',
              'preflight': readiness, 'jobs': jobs, 'started_at': datetime.now(LOCAL_TIME).isoformat(),
              'scope': 'Same model, independent repetitions in self/Codex; original TIA functional and shared bounded formal checks. No hardware or infinite-scan proof.'}
    atomic_json(path/'tasks.json', tasks); write_summary(path, record)
    stop = threading.Event()
    try:
        if not args.prepare_only and readiness['status'] == 'ready':
            configure_temporary(args.temp_root)
            controls = probe(readiness['runtime']['vendor_config'], path/'vendor_preflight', stop)
            if controls['status'] != 'probe_passed':
                record['status'] = 'vendor_probe_failed'
            else:
                record['status'] = 'running'; write_summary(path, record)
                by_id = {t['id']: t for t in tasks}
                def execute(row):
                    if any(hashlib.sha256((ROOT/p).read_bytes()).hexdigest() != sha for p, sha in code_hashes.items()):
                        raise ValueError('Source changed during frozen matrix')
                    directory = path/'tasks'/row['task_id']/row['group']/'details'
                    trial = Trial(directory, by_id[row['task_id']], cfg,
                                  readiness['runtime']['vendor_config'], stop,
                                  formal_config=readiness['formal'], target='tia')
                    try:
                        receipt = run_self(trial) if row['framework'] == 'self' else run_codex(trial, Path(readiness['runtime']['codex_path']))
                    except Exception as exc:
                        receipt = trial.receipt('interrupted' if stop.is_set() else 'task_error',
                                                {'message': str(exc).replace(cfg.api_key, '[redacted]') if cfg.api_key else str(exc)})
                    receipt.update(framework=row['framework'], repeat=row['repeat'], group=row['group'])
                    atomic_json(directory/'receipt.json', receipt)
                    m = receipt['metrics_summary']
                    return {**row, 'status': receipt['status'], 'target_compile': receipt.get('target_compile', 'not_executed'),
                            'finite_test_status': m.get('finite_test_status'), 'formal_status': m.get('formal_status'),
                            'model_calls': receipt['model_calls']}
                with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                    futures = {pool.submit(execute, row): index for index, row in enumerate(jobs)}
                    try:
                        for future in as_completed(futures):
                            row = future.result(); record['jobs'][futures[future]] = row
                            record['completed'] += 1; record['model_calls'] += row['model_calls']
                            write_summary(path, record); print(json.dumps(row), flush=True)
                    except BaseException:
                        stop.set()
                        for future in futures:
                            future.cancel()
                        raise
                record['status'] = 'completed'
    except KeyboardInterrupt:
        stop.set(); record['status'] = 'interrupted'
    except Exception as exc:
        stop.set(); record.update(status='error', message=str(exc).replace(cfg.api_key, '[redacted]') if cfg.api_key else str(exc))
    finally:
        # Receipts remain authoritative after interruption while workers save.
        for row in record['jobs']:
            saved = path/'tasks'/row['task_id']/row['group']/'details/receipt.json'
            if saved.is_file():
                receipt = json.loads(saved.read_text(encoding='utf-8'))
                m = receipt.get('metrics_summary', {})
                row.update(status=receipt['status'], model_calls=receipt.get('model_calls', 0),
                           target_compile=receipt.get('target_compile', 'not_executed'),
                           finite_test_status=m.get('finite_test_status'), formal_status=m.get('formal_status'))
        record['completed'] = sum(row['status'] != 'not_started' for row in record['jobs'])
        record['model_calls'] = sum(row.get('model_calls', 0) for row in record['jobs'])
        write_summary(path, record)
        public = ROOT/'outputs/published'/path.name
        export(path, public, secrets=(cfg.api_key,), path_replacements={str(ROOT): '<PROJECT>', str(Path.home()): '<USER_HOME>'})
    print(json.dumps({'status': record['status'], 'planned': record['total'], 'completed': record['completed'],
                      'model_calls': record['model_calls'], 'public_output': str(public)}, ensure_ascii=True))
    return 0 if record['status'] in ('prepared', 'completed') else 2


if __name__ == '__main__':
    raise SystemExit(main())
