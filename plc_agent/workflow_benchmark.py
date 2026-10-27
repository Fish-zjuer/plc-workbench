"""R2: improve original final candidates using the host-owned PLC workflow."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from dataclasses import replace
import hashlib
import json

from .benchmark import Budget,MeteredProvider,RUN_ROOT
from .config import ModelConfig,ROOT
from .deepseek_credentials import get
from .storage import Project,Session,atomic_json
from .workflow import PLCWorkflow

R2=ROOT/'experiments/workflow_r2'


def run_question(qid,cfg,budget):
    directory=R2/'tasks'/qid;directory.mkdir(parents=True,exist_ok=True)
    result_path=directory/'result.json'
    if result_path.exists():return json.loads(result_path.read_text(encoding='utf-8'))
    reference=RUN_ROOT/'tasks'/qid/'final.st'
    project=Project.create(f'PLC workflow R2 · {qid}',kind='benchmark');session=Session.create(project,cfg.model)
    session.data['mode']='execute';session.save()
    (project.workspace/'candidate.st').write_bytes(reference.read_bytes())
    provider=MeteredProvider(cfg,budget)
    def notify(kind,payload):
        if kind=='notice':print(json.dumps({'question':qid,'notice':payload['text']},ensure_ascii=False),flush=True)
        elif kind=='tool':print(json.dumps({'question':qid,'tool_status':payload['result'].get('status')},ensure_ascii=False),flush=True)
    workflow=PLCWorkflow(session,cfg,provider,notify)
    with session.lease():
        receipt=workflow.run(qid,max_revisions=3,already_leased=True)
    (directory/'final.st').write_bytes((project.workspace/'candidate.st').read_bytes())
    result={'question_id':qid,'project_id':project.data['id'],'session_id':session.data['id'],
            'baseline_sha256':hashlib.sha256(reference.read_bytes()).hexdigest(),'receipt':receipt,'requests':provider.metrics,
            'receipt_path':str(project.workspace/receipt['run_path']/'receipt.json')}
    atomic_json(result_path,result)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--ids',default=','.join(f'{i:02d}' for i in range(1,21)))
    args=parser.parse_args();ids=args.ids.split(',')
    cfg=replace(ModelConfig.load(),max_output_tokens=8192,timeout=90)
    cfg.validate();R2.mkdir(exist_ok=True)
    if not (R2/'preflight.json').exists():
        atomic_json(R2/'preflight.json',{'balance':get(cfg.api_key,'/user/balance'),'models':get(cfg.api_key,'/models'),'configuration':cfg.public(),
                                       'scope':'R2 repair starts from original DeepSeek20 final sources; not new independent generations'})
    frozen=json.loads((RUN_ROOT/'test_protocol.json').read_text(encoding='utf-8'))
    for name,digest in frozen['implementation_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Frozen original evaluation changed')
    budget=Budget(4);results=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(run_question,q,cfg,budget):q for q in ids}
        for future in as_completed(futures):
            qid=futures[future]
            try:
                result=future.result();results.append(result)
                print(json.dumps({'question':qid,'workflow_result':result['receipt']['status'],'model_requests':len(result['requests'])},ensure_ascii=False),flush=True)
            except Exception as exc:
                text=str(exc).replace(cfg.api_key,'[redacted]')
                atomic_json(R2/'tasks'/qid/'error.json',{'message':text})
                print(json.dumps({'question':qid,'error':text},ensure_ascii=False),flush=True)
    all_results=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((R2/'tasks').glob('*/result.json'))]
    atomic_json(R2/'results.json',{'results':all_results,'balance_after':get(cfg.api_key,'/user/balance'),
                                 'model_requests_this_process':budget.calls,'estimated_cost_cny_this_process':budget.used,
                                 'limitation':'Repair experiment from original final candidates; unchanged finite predicates. Not CODESYS or proof.'})


if __name__=='__main__':main()
