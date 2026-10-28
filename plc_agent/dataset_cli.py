"""User-owned dataset plan/execute surface, shared with the TUI."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path
import sys
import uuid
from . import dataset
from .config import ROOT,STATE_ROOT,ModelConfig
from .storage import atomic_json

def perform(session,config,action,task_id=None,provider=None,notify=print):
    if action=='list':return {'status':'dataset_catalog','tasks':dataset.catalog()['tasks']}
    task=dataset.load(task_id)
    if action=='show':return {'status':'dataset_plan','task_id':task_id,'title':task['title'],'requirements':task['requirements'],'interface':task['interface'],
        'scenarios':len(task['scenarios']),'dataset_sha256':task['dataset_sha256'],'ltl_status':'requirements_only_not_executed'}
    if action!='run':raise ValueError('Use /dataset list | show/run PUBLIC_01 or CUSTOM_01')
    if session.data['mode']!='execute':return {'status':'planned','task_id':task_id,'execution_started':False,'message':'Switch /act to execute the frozen supplied dataset'}
    from .dataset_workflow import run
    source=session.project.workspace/'code'/f'{task_id}.st'
    directory=session.project.path/'dataset_runs'/task_id/uuid.uuid4().hex[:12]
    seed=ROOT/'experiments/backend_r4/tasks'/task_id[-2:]/'final.st' if task_id.startswith('PUBLIC') else None
    result=run(task_id,source,directory,config,seed=seed,provider=provider,notify=notify)
    session.data['last_dataset']=result;session.save();return result

def main(argv=None):
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description='Fixed 32-task dataset: inspect, native check, bounded weak-model run')
    parser.add_argument('action',choices=('list','show','check','run'));parser.add_argument('--ids',default='all')
    parser.add_argument('--mode',choices=('plan','execute'),default='plan');parser.add_argument('--workers',type=int,choices=(1,2),default=1)
    parser.add_argument('--output',type=Path);parser.add_argument('--max-revisions',type=int,choices=(1,2,3),default=3)
    parser.add_argument('--no-review',action='store_true');args=parser.parse_args(argv)
    ids=[t['id'] for t in dataset.catalog()['tasks']] if args.ids=='all' else args.ids.split(',')
    tasks=[dataset.load(i) for i in ids]
    if args.action=='list':print(json.dumps(dataset.catalog(),ensure_ascii=False,indent=2));return 0
    if args.action=='show' or args.mode!='execute':
        print(json.dumps({'status':'planned','execution_started':False,'tasks':[{'id':t['id'],'title':t['title'],'interface':t['interface'],'scenarios':len(t['scenarios'])} for t in tasks]},ensure_ascii=False,indent=2));return 0
    out=(args.output or STATE_ROOT/'dataset_benchmarks'/uuid.uuid4().hex[:12]).resolve();out.mkdir(parents=True,exist_ok=False)
    config=ModelConfig.load();results=[]
    def one(task):
        ident=task['id'];directory=out/ident;source=directory/'candidate.st';seed=ROOT/'experiments/backend_r4/tasks'/ident[-2:]/'final.st' if ident.startswith('PUBLIC') else None
        if args.action=='check':
            directory.mkdir();source=seed or ROOT/'experiments/dataset_r8/tasks'/ident/'final.st'
            try:r=dataset.evaluate(source,task)
            except Exception as exc:r=exc.result if hasattr(exc,'result') else {'status':'not_measured','message':str(exc)}
            atomic_json(directory/'evaluation.json',r)
            print(ident+' '+r['status'],flush=True)
            return {'task_id':ident,'status':r['status'],'final_evaluation':{k:v for k,v in r.items() if k!='cases'},'model_calls':0}
        from .dataset_workflow import run
        return run(ident,source,directory,config,seed=seed,max_revisions=args.max_revisions,review=not args.no_review,notify=lambda text:print(text,flush=True))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(one,t) for t in tasks]):
            results.append(future.result());results.sort(key=lambda r:r['task_id'])
            atomic_json(out/'results.json',{'schema':'plc-dataset-benchmark-v1','scope':'Supplied finite tests; adaptive model repair. LTL requirements are not all executed/proved.','results':results})
    print(json.dumps({'output':str(out),'tasks':len(results),'status_counts':{s:sum(r['status']==s for r in results) for s in sorted({r['status'] for r in results})}},ensure_ascii=False))
    return 0

if __name__=='__main__':raise SystemExit(main())
