"""Recompile R8's saved weak-model candidates with current fixed tests; no API calls."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone,timedelta
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from plc_agent import dataset
from plc_agent.storage import atomic_json
from plc_probe.backend import BackendError

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ids',default='all');parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    ids=[t['id'] for t in dataset.catalog()['tasks']] if args.ids=='all' else args.ids.split(',')
    for ident in ids:dataset.load(ident)
    output=args.output or ROOT/'outputs'/'saved_replay'/datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d_%H-%M-%S')
    output.mkdir(parents=True,exist_ok=False);rows=[]
    def one(ident):
        task=dataset.load(ident);source=ROOT/'tests/fixtures/dataset_r8/tasks'/ident/'final.st'
        try:
            first=dataset.evaluate(source,task);second=dataset.evaluate(source,task)
            atomic_json(output/ident/'evaluation.json',first)
            return {'task_id':ident,'status':first['status'] if first==second else 'non_deterministic',
                    'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'dataset_sha256':task['dataset_sha256'],
                    'summary':first.get('summary'),'replay_identical':first==second}
        except (BackendError,ValueError,OSError) as exc:
            failure=exc.result if isinstance(exc,BackendError) else {'status':'tool_error','message':str(exc)}
            atomic_json(output/ident/'evaluation.json',failure);return {'task_id':ident,**failure}
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(one,i) for i in ids]):
            row=future.result();rows.append(row);rows.sort(key=lambda x:x['task_id']);print(row['task_id']+' '+row['status'],flush=True)
            atomic_json(output/'results.json',{'schema':'plc-saved-replay-v1','model_calls':0,'replays_per_task':2,
                'target_compile':'not_executed','formal_status':'not_executed','source_revision':'7885ef3',
                'scope':'Saved weak-model candidates on current supplied finite tests. Not new generation, vendor validation, independent model accuracy or full LTL proof.',
                'results':rows})
    return 0 if all(r['status']=='pass' for r in rows) else 1

if __name__=='__main__':raise SystemExit(main())
