"""Replay packaged candidate ST without configuring or calling any model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from plc_probe.backend import BackendError
from .config import ROOT
from .extended_eval import evaluate,evaluation_fingerprint
from .storage import atomic_json


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description='Check saved public-bank candidates; no model or API key required')
    parser.add_argument('--ids',default=','.join(f'{i:02d}' for i in range(1,21)))
    parser.add_argument('--directory',type=Path,default=ROOT/'experiments/backend_r4/tasks')
    parser.add_argument('--output',type=Path,default=ROOT/'reports/team_bank_check.json')
    args=parser.parse_args();ids=[q.strip().zfill(2) for q in args.ids.split(',')]
    if any(q not in {f'{i:02d}' for i in range(1,21)} for q in ids):parser.error('--ids must contain question numbers 01..20')
    results=[]
    for qid in ids:
        source=args.directory/qid/'final.st'
        try:result=evaluate(source,qid)
        except BackendError as exc:result=exc.result
        except (ValueError,OSError) as exc:result={'status':'tool_error','message':str(exc)}
        results.append({'question_id':qid,'source':str(source),'result':result})
        print(json.dumps({'question_id':qid,'status':result['status'],'first_failure':result.get('first_failure'),
                          'message':result.get('message')},ensure_ascii=False),flush=True)
    atomic_json(args.output,{'model_calls':0,'evaluation_fingerprint':evaluation_fingerprint(),'results':results,
                             'scope':'Finite offline replay only. Backend must be installed; not CODESYS or formal proof.'})
    return 0 if all(row['result']['status']=='pass' for row in results) else 1


if __name__=='__main__':raise SystemExit(main())
