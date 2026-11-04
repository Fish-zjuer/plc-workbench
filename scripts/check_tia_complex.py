"""Exercise representative frozen course tasks on the real TIA verification path.

Existing SCL is replayed unchanged. --generate-missing explicitly permits the
configured author model for tasks without SCL. This is coverage evidence, not a
held-out generation benchmark. No test table or shared model is modified.
"""
import argparse
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plc_agent import dataset, tia, tia_tests, tia_formal, tia_workflow
from plc_agent.campaign import Trial, run_self
from plc_agent.config import ModelConfig, STATE_ROOT
from plc_agent.plcverif_backend import configuration
from plc_agent.storage import atomic_json
from plc_probe.backend import BackendError

CASES = [
    ('CUSTOM_01', 'fixed_array_loop', 'reports/tia_final_20261104/behavior/CUSTOM_01/candidate.scl', 'Saved model-generated SCL; unchanged replay'),
    ('PUBLIC_03', 'real_hysteresis', 'reports/tia_final_20261104/behavior/PUBLIC_03/candidate.scl', 'Saved model-generated SCL; unchanged replay'),
    ('PUBLIC_05', 'native_ton', 'reports/tia_final_20261104/behavior/PUBLIC_05/candidate.scl', 'Saved model-generated SCL; unchanged replay'),
    ('PUBLIC_07', 'struct_array_inout', 'reports/tia_final_20261104/behavior/PUBLIC_07/candidate.scl', 'Saved model-generated SCL; unchanged replay'),
    ('PUBLIC_08', 'open_array_real_reference', 'reports/tia_final_20261104/pairs/08_correct/candidate.scl', 'Baseline reference port; not a model-generation result'),
    ('PUBLIC_17', 'recipe_struct_inout', 'reports/tia_final_20261104/behavior/PUBLIC_17/candidate.scl', 'Saved model-generated SCL; unchanged replay'),
    ('PUBLIC_18', 'variant_fifo_boundary', None, 'Native VARIANT capability probe only'),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def brief(value):
    keys = ('status', 'target_compile', 'behavior_tested', 'ltl_status', 'summary',
            'message', 'phase', 'failure_kind', 'timing', 'actual_scan_times_ms')
    result = {k: value[k] for k in keys if k in value}
    formal = value.get('formal_verification')
    if formal:
        result['formal'] = {k: formal[k] for k in ('status', 'bound', 'message',
            'declared_ltl_total', 'bounded_verified_property_ids', 'platform_assumptions') if k in formal}
    failed = next((c for c in value.get('cases', []) if c.get('status') == 'fail'), None)
    if failed:
        result['first_failure'] = failed.get('first_failure')
    return result


def write_summary(root, report):
    atomic_json(root/'summary.json', report)
    lines = ['# TIA complex-task coverage', '',
        'Frozen course tests; unchanged expected outputs. Native execution and source-model verification are separate.', '',
        '| Task | Feature | Origin | Compile | Behavior | Formal | Status |',
        '| --- | --- | --- | --- | --- | --- | --- |']
    for row in report['results']:
        value = row.get('evaluation', {})
        lines.append('| '+ ' | '.join(str(x).replace('|', '/') for x in (
            row['task_id'], row['feature'], row['source_origin'],
            value.get('target_compile', 'not_executed'),
            value.get('summary', {}) if value.get('behavior_tested') else 'not_executed',
            value.get('ltl_status', 'not_executed'), value.get('status', row['status'])))+' |')
    lines += ['', 'Full per-task evidence is stored beside this summary.', '',
              'Model-generated, historical model, and authored reference candidates must not be pooled as generation accuracy.']
    (root/'SUMMARY.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--home', type=Path, default=STATE_ROOT)
    parser.add_argument('--ids', default=','.join(c[0] for c in CASES))
    parser.add_argument('--generate-missing', action='store_true')
    parser.add_argument('--repair-existing', action='store_true',
                        help='Allow bounded model repair of the copied seed; preserves before.scl and all diagnostics')
    parser.add_argument('--source', action='append', default=[], metavar='TASK_ID=PATH',
                        help='Replay an explicit saved SCL candidate, including in independent formal probes')
    parser.add_argument('--max-revisions', type=int, choices=range(6), default=2)
    parser.add_argument('--max-output-tokens', type=int, default=8192)
    parser.add_argument('--thinking', choices=('default','off','on'), default='default')
    parser.add_argument('--formal-only', action='store_true', help='Independent source-model probe; never counted as full/native acceptance')
    parser.add_argument('--formal-config', type=Path, help='Explicit unchanged formal configuration for a baseline replay')
    args = parser.parse_args(argv)
    root = args.output.resolve(); root.mkdir(parents=True, exist_ok=False)
    ids = args.ids.split(',')
    if set(ids) - {c[0] for c in CASES}: raise ValueError('Unknown case ID')
    overrides = dict(item.split('=', 1) for item in args.source)
    if set(overrides) - {c[0] for c in CASES}: raise ValueError('Unknown source override task ID')
    vendor = tia.load_config(args.home)
    cfg = replace(ModelConfig.load(args.home), timeout=180, max_output_tokens=args.max_output_tokens, stream=False)
    if args.thinking != 'default':
        from plc_agent.inference import inference_config
        cfg = inference_config(cfg, cfg.model, {'mode':args.thinking})
    formal = json.loads(args.formal_config.read_text(encoding='utf-8')) if args.formal_config else configuration(args.home)
    from plc_agent.plcverif_backend import validate
    validate(formal)
    report = {'schema':'tia-complex-coverage-v1', 'started_at':datetime.now(timezone(timedelta(hours=9))).isoformat(),
              'mode':'independent_formal_probe' if args.formal_only else 'full_native',
              'model_configuration':cfg.public(), 'formal_configuration':formal,
              'scope':'Representative coverage on frozen supplied tests; not generation accuracy or cross-platform equivalence.',
              'shared_sha256':{name:sha(ROOT/'plc_agent'/name) for name in [
                  'dataset.py','behavior_plan.py','dataset_formal.py','plcverif_backend.py','plcverif_st.py','cbmc_model.py','ltl_adapter.py']},
              'results':[]}
    atomic_json(root/'vendor_config.json', vendor)
    write_summary(root, report)
    for ident, feature, existing, origin in CASES:
        if ident not in ids: continue
        if ident in overrides:
            existing = overrides[ident]
            origin = 'Explicit saved candidate replay; see source_path for generation provenance'
        if existing and args.repair_existing:
            origin += '; bounded model repair permitted after original evaluation'
        start = time.monotonic(); directory = root/ident; directory.mkdir()
        task = dataset.load(ident)
        atomic_json(directory/'task_snapshot.json', task)
        row = {'task_id':ident, 'feature':feature, 'source_origin':origin,
               'dataset_sha256':task['dataset_sha256'], 'status':'running', 'model_calls':0}
        report['results'].append(row); write_summary(root, report)
        print(ident, 'START', feature, flush=True)
        try:
            try:
                plan = tia_tests.harness(task)
                row['native_plan'] = {'rows':plan['row_count'], 'columns':len(plan['output_names']),
                                      'driver_characters':len(plan['harness_source']),
                                      'scenario_seconds':plan['simulation_timeout_seconds']}
            except (BackendError, ValueError) as exc:
                value = exc.result if isinstance(exc, BackendError) else {'status':'behavior_not_supported','message':str(exc)}
                row.update(status=value['status'], evaluation={**value, 'target_compile':'not_executed',
                    'behavior_tested':False,'ltl_status':'not_executed'}, capability_probe_only=True)
                atomic_json(directory/'capability.json', value)
                print(ident, value['status'], value.get('message',''), flush=True)
                continue
            source = directory/'candidate.scl'
            if existing:
                original = ROOT/existing
                source.write_bytes(original.read_bytes())
                row.update(source_path=str(original), original_source_sha256=sha(original))
            elif not args.generate_missing:
                row.update(status='missing_candidate', evaluation={'status':'missing_candidate'})
                continue
            if args.formal_only:
                if not source.exists():
                    row.update(status='missing_candidate', evaluation={'status':'missing_candidate'}); continue
                value = tia_formal.verify(task, source, directory/'formal', config=formal)
                atomic_json(directory/'formal_probe.json', value)
                row.update(status=value['status'], evaluation=brief({'status':value['status'], 'target_compile':'not_executed',
                    'behavior_tested':False, 'ltl_status':value['status'], 'formal_verification':value}))
            else:
                trial = Trial(directory, task, cfg, vendor, threading.Event(), formal_config=formal, target='tia')
                if source.exists() and not args.repair_existing:
                    checked = trial.check(source.read_text(encoding='utf-8-sig'))
                    receipt = trial.receipt(checked['status'], {'final_evaluation':checked,
                        'target_compile':checked.get('target_compile','not_executed'),
                        'behavior_tested':checked.get('behavior_tested',False),
                        'formal_verification':checked.get('formal_verification'),
                        'ltl_status':checked.get('ltl_status','not_executed')})
                else:
                    receipt = run_self(trial, max_revisions=args.max_revisions)
                value = receipt.get('final_evaluation') or {'status':receipt['status']}
                row.update(status=receipt['status'], model_calls=receipt['model_calls'],
                           token_usage=receipt['token_usage'], evaluation=brief(value))
                row['submissions'] = [brief(v) for v in receipt.get('submissions', [])]
            if source.exists(): row['source_sha256'] = sha(source)
            view = row.get('evaluation', {})
            print(ident, row['status'], json.dumps({k:view[k] for k in
                ('target_compile','behavior_tested','ltl_status','summary','phase','failure_kind') if k in view}, ensure_ascii=True), flush=True)
        except Exception as exc:
            value = getattr(exc,'result',{'status':'test_error','message':str(exc).replace(cfg.api_key,'[redacted]') if cfg.api_key else str(exc)})
            row.update(status=value['status'], evaluation=brief(value))
            atomic_json(directory/'runner_error.json',value)
            print(ident, row['status'], flush=True)
        finally:
            row['seconds'] = round(time.monotonic()-start, 3)
            write_summary(root, report)
    report['completed_at'] = datetime.now(timezone(timedelta(hours=9))).isoformat()
    report['shared_files_unchanged'] = all(sha(ROOT/'plc_agent'/name)==value for name,value in report['shared_sha256'].items())
    report['model_calls'] = sum(r.get('model_calls',0) for r in report['results'])
    write_summary(root, report)
    return 0 if all(r['status'] in ('pass','finite_pass','bounded_pass') for r in report['results']) else 1


if __name__ == '__main__': raise SystemExit(main())
