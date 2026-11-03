"""User-facing configuration, real compiler probe and dataset SCL workflow."""
import argparse
import json
from pathlib import Path
import uuid

from . import tia, tia_workflow
from .config import ModelConfig, STATE_ROOT
from .imported_bank import ImportedBank
from .storage import atomic_json
from .plcverif_backend import configuration


def probe(config, directory, cancel_event=None):
    directory = Path(directory)
    samples = Path(__file__).resolve().parents[1]/'examples/tia'
    positive = tia.compile_scl(samples/'MotorControl.scl', config, directory=directory/'positive', cancel_event=cancel_event)
    negative = tia.compile_scl(samples/'MotorControl_bad.scl', config, directory=directory/'negative', cancel_event=cancel_event)
    result = {'status': 'probe_passed' if positive['status'] == 'compile_passed' and
              negative['status'] in ('compile_failed', 'generation_failed') else 'probe_failed',
              'positive': positive, 'negative': negative, 'behavior_tested': False}
    atomic_json(directory/'probe.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Siemens SCL generation, native behavior tests and bounded LTL verification')
    parser.add_argument('--home', type=Path, default=STATE_ROOT)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('doctor')
    configure = commands.add_parser('configure')
    configure.add_argument('--executable', required=True)
    configure.add_argument('--template-project', required=True)
    configure.add_argument('--timeout-seconds', type=int, default=300)
    configure.add_argument('--openness-directory', default='')
    configure.add_argument('--simulation-api', default='')
    configure.add_argument('--simulation-template-project', default='')
    configure.add_argument('--simulation-timeout-seconds', type=int, default=600)
    commands.add_parser('probe')
    compile_cmd = commands.add_parser('compile')
    compile_cmd.add_argument('source', type=Path)
    check = commands.add_parser('check', help='Compile, run native scenarios, then bounded LTL (no model calls)')
    check.add_argument('task_id')
    check.add_argument('source', type=Path)
    check.add_argument('--output', type=Path)
    run = commands.add_parser('run')
    run.add_argument('task_id')
    run.add_argument('--source', type=Path, help='Optional existing SCL to compile/repair first')
    run.add_argument('--output', type=Path)
    run.add_argument('--model')
    run.add_argument('--max-revisions', type=int, choices=range(6), default=5)
    run.add_argument('--compile-only', action='store_true', help='Explicitly skip behavior and formal verification')
    args = parser.parse_args(argv)
    try:
        config = tia.load_config(args.home)
        directory = args.home/'tia_runs'/uuid.uuid4().hex
        if args.action == 'doctor':
            result = tia.doctor(args.home)
        elif args.action == 'configure':
            config = {'executable': str(Path(args.executable).resolve()),
                      'template_project': str(Path(args.template_project).resolve()),
                      'timeout_seconds': args.timeout_seconds,
                      'openness_directory': args.openness_directory,
                      'simulation_api': args.simulation_api,
                      'simulation_template_project': args.simulation_template_project,
                      'simulation_timeout_seconds': args.simulation_timeout_seconds}
            tia.validate_config(config)
            atomic_json(args.home/'tia.json', config)
            result = {'status': 'configured_not_probed', 'configuration': config}
        elif args.action == 'probe':
            result = probe(config, directory)
        elif args.action == 'compile':
            result = tia.compile_scl(args.source, config, directory=directory)
        elif args.action == 'check':
            from .campaign import Trial
            import threading
            directory=args.output or directory;directory.mkdir(parents=True,exist_ok=True)
            task=ImportedBank(args.home).load(args.task_id)
            trial=Trial(directory,task,ModelConfig.load(args.home),config,threading.Event(),
                        formal_config=configuration(args.home),target='tia')
            checked=trial.check(args.source.read_text(encoding='utf-8-sig'))
            result=trial.receipt(checked['status'],{'final_evaluation':checked,
                'target_compile':checked.get('target_compile','not_executed'),
                'formal_verification':checked.get('formal_verification'),'ltl_status':checked.get('ltl_status','not_executed')})
        else:
            from dataclasses import replace
            model = ModelConfig.load(args.home)
            if args.model:
                model = replace(model, model=args.model)
            model.validate()
            directory = args.output or directory
            directory.mkdir(parents=True, exist_ok=True)
            source = directory/'candidate.scl'
            if args.source:
                source.write_bytes(args.source.read_bytes())
            task=ImportedBank(args.home).load(args.task_id)
            from .campaign import Trial, run_self
            import threading
            trial=Trial(directory,task,model,config,threading.Event(),formal_config=configuration(args.home),target='tia')
            if args.compile_only:
                result=tia_workflow.run(task,source,directory,model,vendor_config=config,max_revisions=args.max_revisions,provider=trial)
            else:result=run_self(trial,max_revisions=args.max_revisions)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['status'] in ('pass', 'finite_pass', 'compiled_without_tests', 'compile_passed', 'probe_passed', 'configured_not_probed') else 1
    except (ValueError, OSError) as exc:
        print(json.dumps({'status': 'error', 'message': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
