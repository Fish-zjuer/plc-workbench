"""Refresh evidence on current code, reusing explicitly labeled historical review proposals."""
import copy
import json
import shutil
import sys
import threading
from plc_agent.config import ROOT,STATE_ROOT,ModelConfig
from plc_agent.storage import Project,Session,atomic_json
from plc_agent.task_store import TaskStore
from plc_agent.task_workflow import TaskWorkflow
from plc_probe.config import base_cache_dir

class RecordedReview:
    def __init__(self,review):self.review=review;self.cancel_event=threading.Event();self.calls=0
    def complete(self,messages,**kwargs):
        if self.calls:raise RuntimeError('Unexpected second model request; recheck must not author new code')
        self.calls+=1
        return {'text':json.dumps({'summary':self.review['summary'],'questions':self.review['questions'],'scenarios':self.review['proposals']})}

def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    out=ROOT/'experiments/formal_r7/final_recheck';out.mkdir(exist_ok=True);matrix=[]
    for category in ('real_model','fault_injection'):
        results=json.loads((out.parent/category/'results.json').read_text(encoding='utf-8'))['results']
        for item in results:
            project=Project.load(item['private_project_id']);session=Session.load(project,project.data['last_session'])
            store=TaskStore(session);previous=json.loads((store.directory(item['task_id'])/'latest.json').read_text(encoding='utf-8'))
            provider=RecordedReview(previous['reviews'][-1]);cfg=ModelConfig(base_url='http://localhost:1/v1',model='historical-proposal-replay')
            result=TaskWorkflow(session,cfg,provider,notify=lambda _,p:print(p.get('text',''),flush=True)).run(item['task_id'])
            if result['attempts']:raise ValueError('Source changed in recheck')
            if store.latest(item['task_id'])['status']!=result['status']:raise ValueError('Fresh evidence is stale')
            run=store.directory(item['task_id'])/'runs'/result['run_id'];dest=out/(category+'_'+item['name']);dest.mkdir(exist_ok=True)
            def clean(v):
                if isinstance(v,str):
                    for old,new in ((str(project.path),'<local_project>'),(str(STATE_ROOT),'<private_state>'),(str(base_cache_dir()),'<compiler_cache>')):
                        v=v.replace(old,new).replace(old.replace('\\','/'),new)
                    return v
                if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
                if isinstance(v,list):return [clean(x) for x in v]
                return v
            for path in run.rglob('*'):
                if not path.is_file() or path.suffix not in ('.json','.st','.smt2'):continue
                target=dest/path.relative_to(run);target.parent.mkdir(parents=True,exist_ok=True)
                if path.suffix=='.json':atomic_json(target,clean(json.loads(path.read_text(encoding='utf-8'))))
                else:shutil.copyfile(path,target)
            matrix.append({'case':category+'_'+item['name'],'status':result['status'],'source_sha256':result['source_sha256'],
                'new_model_calls':0,'recorded_review_requests':provider.calls,'source_revisions':len(result['attempts']),
                'formal_status':result['formal_verification']['status'],'proved_property_ids':result['formal_verification']['proved_property_ids'],
                'regression_scenarios':result['regression_scenarios'],'execution_fingerprint':result['execution_fingerprint'],
                'baseline':result['final_evaluation']['summary'],'target_compile':result['target_compile']})
            atomic_json(out/'results.json',{'scope':'Recompile/solve/replay saved actual weak-model code with current implementation; historical model review proposals replayed, no new model review or generation.','results':matrix})

if __name__=='__main__':main()
