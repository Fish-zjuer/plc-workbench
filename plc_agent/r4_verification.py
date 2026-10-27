"""Final all-task replay and independent random-seed probes with zero generation."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import random
import threading
from unittest.mock import patch

from .backend_r4 import info
from .config import ModelConfig,ROOT
from .extended_eval import evaluate,evaluation_fingerprint
from .r4_benchmark import OUT
from .storage import Project,Session,atomic_json
from .workflow import PLCWorkflow


class NoModel:
    def __init__(self):self.cancel_event=threading.Event();self.calls=0
    def complete(self,*args,**kwargs):self.calls+=1;raise AssertionError('Verification cannot author ST')
    def cancel(self):self.cancel_event.set()


def task(qid,cfg):
    folder=OUT/'tasks'/qid;folder.mkdir(parents=True,exist_ok=True)
    source=folder/'final.st'
    if not source.exists():source.write_bytes((ROOT/'experiments/workflow_r2/tasks'/qid/'final.st').read_bytes())
    project=Project.create(f'R4 final replay {qid}',kind='benchmark');session=Session.create(project,cfg.model)
    session.data['mode']='execute';session.save();candidate=project.workspace/'candidate.st';candidate.write_bytes(source.read_bytes())
    no_model=NoModel();receipt=PLCWorkflow(session,cfg,no_model).run(qid)
    runs=[evaluate(candidate,qid) for _ in range(2)]
    atomic_json(folder/'final_replay.json',{'receipt':receipt,'runs':runs,'project_id':project.data['id'],'session_id':session.data['id']})
    same=hashlib.sha256(source.read_bytes()).hexdigest()==hashlib.sha256(candidate.read_bytes()).hexdigest()==receipt.get('source_sha256')
    return {'question_id':qid,'workflow_status':receipt['status'],'replay_statuses':[r['status'] for r in runs],
            'source_sha256':receipt.get('source_sha256'),'source_unchanged':same,'model_calls':no_model.calls,
            'scans_per_replay':runs[0]['summary']['scans']+runs[0].get('original_finite_scans',0),
            'backend_fingerprint':receipt.get('backend_fingerprint'),'evaluation_fingerprint':receipt.get('evaluation_fingerprint'),
            'receipt_path':str(project.workspace/receipt['run_path']/'receipt.json')}


def unseen():
    # Different seeds after repairs; these exact sequences are never sent to the author.
    from . import reference_checks as ref
    from . import duration_checks as duration
    cases={}
    for qid in ('04','12'):
        generator=random.Random(394105+int(qid))
        with patch.object(duration.random,'Random',return_value=generator):cases[qid]=duration.cases(qid)
    generator=random.Random(394113)
    with patch.object(ref.random,'Random',return_value=generator):cases['08']=ref.analog_cases()
    generator=random.Random(394123)
    with patch.object(ref.random,'Random',return_value=generator):cases['18']=ref.fifo_cases()
    atomic_json(OUT/'unseen_protocol.json',{'scope':'New deterministic seeds after repair; never supplied to author; same independently written requirement monitors','cases':cases})
    results={}
    for qid in ('04','08','12','18'):
        source=OUT/'tasks'/qid/'final.st'
        if qid in ('04','12'):
            with patch.object(duration,'cases',return_value=cases[qid]):runs=[duration.test_durations(source,qid) for _ in range(2)]
        else:
            with patch.object(ref,'analog_cases' if qid=='08' else 'fifo_cases',return_value=cases[qid]):runs=[ref.test_references(source,qid) for _ in range(2)]
        atomic_json(OUT/('unseen_'+qid+'.json'),{'runs':runs})
        results[qid]={'statuses':[r['status'] for r in runs],'scans_per_run':runs[0]['summary']['scans'],
                      'first_failures':[r.get('first_failure') for r in runs]}
    atomic_json(OUT/'unseen_summary.json',results)
    return results


def main():
    if not info():raise ValueError('R4 backend must be selected')
    cfg=replace(ModelConfig.load(),max_steps=1)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda q:task(q,cfg),[f'{n:02d}' for n in range(1,21)]))
    holdout=unseen()
    frozen=json.loads((ROOT/'experiments/deepseek_20/test_protocol.json').read_text(encoding='utf-8'))['implementation_sha256']
    hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in frozen.items()}
    result={'results':results,'backend':info(),'evaluation_fingerprint':evaluation_fingerprint(),'original_predicates_unchanged':hashes,
            'unseen':holdout,'scope':'All-task warm-start repair/coverage replay using a source-extended offline backend. Not independent model accuracy, vendor ABI equivalence, formal proof or hardware validation.'}
    atomic_json(OUT/'verification.json',result)
    okay=all(r['workflow_status']=='verified' and r['replay_statuses']==['pass','pass'] and r['source_unchanged'] and r['model_calls']==0 for r in results)
    okay=okay and all(hashes.values()) and all(r['statuses']==['pass','pass'] for r in holdout.values())
    print(json.dumps({'all_passed':okay,'questions':len(results),'scans_per_round':sum(r['scans_per_replay'] for r in results),
                      'unseen_scans_per_round':sum(r['scans_per_run'] for r in holdout.values())}))
    return 0 if okay else 1


if __name__=='__main__':raise SystemExit(main())
