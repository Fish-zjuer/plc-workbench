"""R4 backend/repair experiment: warm start, fixed predicates, no root-authored ST."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from dataclasses import replace
import hashlib
import json
from urllib.parse import urlparse

from plc_probe.backend import BackendError
from .backend_r4 import info
from .benchmark import Budget,MeteredProvider
from .config import ModelConfig,ROOT
from .deepseek_credentials import get
from .extended_eval import evaluate
from .storage import Project,Session,atomic_json
from .workflow import PLCWorkflow

OUT=ROOT/'experiments/backend_r4'


def verdict(source,qid):
    try:return evaluate(source,qid)
    except BackendError as exc:return exc.result


def solve(qid,cfg,budget):
    folder=OUT/'tasks'/qid;folder.mkdir(parents=True,exist_ok=True)
    if (folder/'result.json').exists():return json.loads((folder/'result.json').read_text(encoding='utf-8'))
    source=ROOT/'experiments/workflow_r2/tasks'/qid/'final.st'
    project=Project.create(f'PLC backend R4 {qid}',kind='benchmark');session=Session.create(project,cfg.model)
    session.data['mode']='execute';session.save();candidate=project.workspace/'candidate.st';candidate.write_bytes(source.read_bytes())
    before=verdict(candidate,qid);atomic_json(folder/'before_evaluation.json',before)
    provider=MeteredProvider(cfg,budget)
    def notify(kind,payload):
        if kind=='notice':print(json.dumps({'id':qid,'notice':payload['text']},ensure_ascii=False),flush=True)
        if kind=='tool':print(json.dumps({'id':qid,'test':payload['result'].get('status')},ensure_ascii=False),flush=True)
    receipt=PLCWorkflow(session,cfg,provider,notify).run(qid,max_revisions=5)
    (folder/'final.st').write_bytes(candidate.read_bytes())
    result={'question_id':qid,'project_id':project.data['id'],'session_id':session.data['id'],
            'baseline_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'before_status':before['status'],
            'receipt':receipt,'requests':provider.metrics,'receipt_path':str(project.workspace/receipt['run_path']/'receipt.json')}
    atomic_json(folder/'result.json',result);return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--ids',default='04,08,12,18');args=parser.parse_args()
    if not info():raise ValueError('Select the independently built R4 backend first')
    cfg=replace(ModelConfig.load(),max_steps=12,max_output_tokens=16384,timeout=120)
    if urlparse(cfg.base_url).hostname!='api.deepseek.com':raise ValueError('This measured experiment is restricted to authorized DeepSeek credentials')
    cfg.validate();OUT.mkdir(exist_ok=True)
    protocol=json.loads((ROOT/'experiments/deepseek_20/test_protocol.json').read_text(encoding='utf-8'))
    for name,digest in protocol['implementation_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('Original predicates changed')
    if not (OUT/'preflight.json').exists():
        atomic_json(OUT/'preflight.json',{'configuration':cfg.public(),'balance':get(cfg.api_key,'/user/balance'),'backend':info(),
                                        'scope':'R4 repairs from original R2 candidates; changed backend, separate new reference tests; not independent generation accuracy'})
    budget=Budget(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(solve,qid,cfg,budget):qid for qid in args.ids.split(',')}
        for future in as_completed(futures):
            qid=futures[future]
            try:
                result=future.result();print(json.dumps({'id':qid,'status':result['receipt']['status'],'requests':len(result['requests'])}),flush=True)
            except Exception as exc:
                message=str(exc).replace(cfg.api_key,'[redacted]')
                atomic_json(OUT/'tasks'/qid/'error.json',{'message':message});print(json.dumps({'id':qid,'error':message}),flush=True)
    results=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((OUT/'tasks').glob('*/result.json'))]
    atomic_json(OUT/'results.json',{'results':results,'balance_after':get(cfg.api_key,'/user/balance'),'model_calls_this_process':budget.calls})


if __name__=='__main__':main()
