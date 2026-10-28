"""Real weak-model author/reviewer with source-derived Z3; no hand-authored candidate."""
from dataclasses import replace
import argparse
import json
from pathlib import Path
import shutil
import sys
from plc_agent.config import ModelConfig,ROOT,STATE_ROOT
from plc_agent.storage import Project,Session,atomic_json
from plc_agent.provider import ChatProvider
from plc_agent.task_store import TaskStore
from plc_agent.task_workflow import TaskWorkflow
from plc_probe.config import base_cache_dir

def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('--fault-injection',action='store_true');args=parser.parse_args()
    cfg=replace(ModelConfig.load(),max_steps=10,timeout=120);cfg.validate()
    out=ROOT/'experiments/formal_r7'/('fault_injection' if args.fault_injection else 'real_model');out.mkdir(parents=True,exist_ok=True)
    matrix=[]
    for name in (('interlocked_start',) if args.fault_injection else ('interlocked_start','acknowledge_latch')):
        print('BEGIN '+name,flush=True)
        spec=json.loads((ROOT/'examples/tasks'/f'{name}.json').read_text(encoding='utf-8'))
        spec['formal']={'mode':'required','bound':20,'timeout_seconds':20}
        if name=='interlocked_start':
            spec['properties'] += [
                {'id':'P_HOLD','requirement':'R1','when':{'previous.outputs.running':True,'inputs.stop':False,'inputs.permit':True},'then':{'outputs.running':True}},
                {'id':'P_HELD_START','requirement':'R3','when':{'previous.outputs.running':False,'previous.inputs.start':True,'inputs.start':True},'then':{'outputs.running':False}},
                {'id':'P_EDGE','requirement':'R1','when':{'previous.inputs.start':False,'inputs.start':True,'inputs.stop':False,'inputs.permit':True},'then':{'outputs.running':True}}]
        if args.fault_injection:spec['formal']['bound']=32
        project=Project.create('R7 formal real trial '+name,STATE_ROOT,kind='benchmark')
        session=Session.create(project,cfg.model);store=TaskStore(session);task_id=store.create(spec)['task_id']
        if args.fault_injection:
            from plc_agent.codesys import split_source
            seed=(ROOT/'experiments/formal_r7/real_model'/name/'candidate_final.st').read_text(encoding='utf-8')
            declaration,body=split_source(seed,spec['block'])
            mutated=declaration+'\nVAR WB_FaultScan : USINT; END_VAR\n'+body+'\nWB_FaultScan := WB_FaultScan + 1;\nIF WB_FaultScan = 24 THEN running := TRUE; END_IF;\nEND_FUNCTION_BLOCK\n'
            path=project.workspace/'code'/f'{task_id}.st';path.parent.mkdir(exist_ok=True);path.write_text(mutated,encoding='utf-8')
        # Developer-reviewed fixture; the model never approves or changes this contract.
        store.accept(task_id);session.data['mode']='execute';session.save()
        provider=ChatProvider(cfg)
        result=TaskWorkflow(session,cfg,provider,notify=lambda _,p:print(p.get('text',''),flush=True)).run(task_id,max_revisions=3)
        run=store.directory(task_id)/'runs'/result['run_id'];dest=out/name;dest.mkdir(exist_ok=True)
        def clean(v):
            if isinstance(v,str):
                for old,new in ((str(project.path),'<local_project>'),(str(STATE_ROOT),'<private_state>'),(str(base_cache_dir()),'<compiler_cache>')):
                    v=v.replace(old,new).replace(old.replace('\\','/'),new)
                return v.replace(cfg.api_key,'[redacted]') if cfg.api_key else v
            if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
            if isinstance(v,list):return [clean(x) for x in v]
            return v
        for path in run.rglob('*'):
            if not path.is_file() or path.suffix not in ('.json','.st','.smt2'):continue
            target=dest/path.relative_to(run);target.parent.mkdir(parents=True,exist_ok=True)
            if path.suffix=='.json':atomic_json(target,clean(json.loads(path.read_text(encoding='utf-8'))))
            else:shutil.copyfile(path,target)
        matrix.append({'name':name,'model':cfg.model,'source_origin':'synthetic delayed fault injected into saved weak-model source; actual weak-model repair' if args.fault_injection else 'configured weak model, empty source',
            'status':result['status'],'source_sha256':result['source_sha256'],
            'formal_status':result['formal_verification']['status'] if isinstance(result['formal_verification'],dict) else result['formal_verification'],
            'proved_property_ids':result['formal_verification'].get('proved_property_ids',[]) if isinstance(result['formal_verification'],dict) else [],
            'model_calls':len(provider.metrics),'revisions':len(result['attempts']),'reviews':len(result['reviews']),
            'target_compile':result['target_compile'],'private_project_id':project.data['id'],'task_id':task_id,
            'metrics':[{k:m[k] for k in ('status','duration_seconds','usage','http_status') if k in m} for m in provider.metrics]})
        atomic_json(out/'results.json',{'scope':'Synthetic delayed-fault detection and real weak-model repair, one run; not an estimate of natural model defects.' if args.fault_injection else 'Two frozen developer-reviewed tasks, one run each. Z3 proofs are for named properties of the strict source model; not vendor or physical PLC correctness.','results':matrix})
        print('END '+name+' '+result['status'],flush=True)

if __name__=='__main__':main()
