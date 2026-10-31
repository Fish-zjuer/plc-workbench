"""Fresh self validation; preserves all outcomes, no selective replacement."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
import argparse, json, threading, hashlib
from plc_agent.campaign import Trial, run_self, validate_vendor_environment, summarize
from plc_agent.config import ModelConfig, STATE_ROOT, ROOT
from plc_agent.runtime_env import configure_tools
from plc_agent.storage import atomic_json, read_json
from plc_agent import codesys

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--ids',default='all')
    parser.add_argument('--tasks-file',required=True,type=Path,help='Frozen tasks.json snapshot exported from a campaign')
    parser.add_argument('--models',nargs='+',default=['deepseek-v4.1-flash-1017','qwen3.8-flash'])
    parser.add_argument('--resume-all-completed',action='store_true')
    parser.add_argument('--deepseek-nonthinking',action='store_true')
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--timeout',type=int,default=600)
    parser.add_argument('--qwen-thinking',action='store_true',help='Default uses explicit enable_thinking=false for Qwen')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=args.resume_all_completed)
    configure_tools()
    tasks=read_json(args.tasks_file)
    if not isinstance(tasks,list) or not tasks:raise ValueError('tasks-file must contain a nonempty task list')
    if args.ids!='all':tasks=[t for t in tasks if t['id'].split('__')[-1] in args.ids.split(',')]
    cfg=replace(ModelConfig.load(),stream=True,timeout=args.timeout,max_output_tokens=32768)
    cfg.validate();vendor=codesys.load_config();stop=threading.Event()
    from plc_agent.backend_r4 import info
    from plc_agent.dataset import fingerprint
    backend=info()
    if backend is None:raise RuntimeError('Validated R4 local backend required')
    backend_fingerprint=fingerprint()
    models=args.models
    atomic_json(args.output/('continuation_snapshot.json' if args.resume_all_completed else 'snapshot.json'),{'tasks':tasks,'config':cfg.public(),'vendor':vendor,'local_backend':backend,'local_execution_fingerprint':backend_fingerprint,
      'model_overrides':{'qwen3.8-flash':{} if args.qwen_thinking else {'enable_thinking':False},'deepseek-v4.1-flash-1017':{'thinking':{'type':'disabled'}} if args.deepseek_nonthinking else {}},
      'code_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'plc_agent').glob('*.py')}})
    validate_vendor_environment(vendor,args.output/('continuation_vendor_preflight' if args.resume_all_completed else 'vendor_preflight'),stop)
    frozen={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'plc_agent').glob('*.py')}
    results=[]
    def job(index,task,model):
        if fingerprint()!=backend_fingerprint or any(hashlib.sha256(p.read_bytes()).hexdigest()!=sha for p,sha in frozen.items()):
            stop.set();raise RuntimeError('Frozen code changed; validation stopped')
        existing=args.output/model/str(index)/'receipt.json'
        if args.resume_all_completed and existing.exists():
            r=read_json(existing);r['framework']='self';return r
        if args.resume_all_completed and existing.parent.exists():
            raise RuntimeError('Incomplete trial exists; use a fresh output directory instead of resetting its budget')
        print('START',model,task['id'].split('__')[-1],flush=True)
        model_cfg=replace(cfg,model=model)
        if model=='qwen3.8-flash' and not args.qwen_thinking:
            model_cfg=replace(model_cfg,extra_body={**cfg.extra_body,'enable_thinking':False})
        if model=='deepseek-v4.1-flash-1017' and args.deepseek_nonthinking:
            model_cfg=replace(model_cfg,extra_body={**cfg.extra_body,'thinking':{'type':'disabled'}})
        trial=Trial(args.output/model/str(index),task,model_cfg,vendor,stop)
        try:r=run_self(trial)
        except Exception as exc:r=trial.receipt('task_error',{'final_evaluation':{'message':str(exc).replace(cfg.api_key,'[redacted]')}})
        r['framework']='self';return r
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending=[pool.submit(job,i,t,m) for i,t in enumerate(tasks) for m in models]
        for f in as_completed(pending):
            r=f.result();results.append(r)
            atomic_json(args.output/('continuation_results.json' if args.resume_all_completed else 'results.json'),{'results':results,'summary':summarize(results,[('self',m) for m in models])})
            print(r['model'],r['task_id'].split('__')[-1],r['status'],r['model_calls'],flush=True)
    print('DONE',flush=True)

if __name__=='__main__':main()
