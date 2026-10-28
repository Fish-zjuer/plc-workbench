"""User-only CODESYS configuration/probe commands."""
import argparse
import json
from pathlib import Path
import tempfile
from .codesys import doctor,load_config,validate_config,invoke,work_root
from .config import STATE_ROOT
from .storage import atomic_json
from plc_probe.backend import BackendError

def main(argv=None):
    parser=argparse.ArgumentParser(description='CODESYS official IDE headless integration')
    commands=parser.add_subparsers(dest='operation',required=True)
    commands.add_parser('doctor')
    config=commands.add_parser('configure')
    config.add_argument('--executable',required=True);config.add_argument('--profile',required=True)
    config.add_argument('--template-project');config.add_argument('--additional-folder')
    config.add_argument('--timeout-seconds',type=int,default=120)
    commands.add_parser('probe')
    args=parser.parse_args(argv)
    try:
        if args.operation=='doctor':result=doctor()
        elif args.operation=='configure':
            cfg={'executable':str(Path(args.executable).resolve()),'profile':args.profile,'timeout_seconds':args.timeout_seconds}
            if args.template_project:cfg['template_project']=str(Path(args.template_project).resolve())
            if args.additional_folder:cfg['additional_folder']=str(Path(args.additional_folder).resolve())
            validate_config(cfg,require_template=False)
            atomic_json(STATE_ROOT/'codesys.json',cfg)
            result={'status':'configured_not_probed','message':'Configuration saved locally. Run codesys probe before relying on it.'}
        else:
            directory=Path(tempfile.mkdtemp(prefix='probe_',dir=work_root()))
            result=invoke({'action':'probe','source_sha256':None},directory)
            atomic_json(STATE_ROOT/'codesys_probe.json',result)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (ValueError,OSError,BackendError) as exc:
        result=exc.result if isinstance(exc,BackendError) else {'status':'setup_required','message':str(exc)}
        print(json.dumps(result,ensure_ascii=False,indent=2));return 1

if __name__=='__main__':raise SystemExit(main())
