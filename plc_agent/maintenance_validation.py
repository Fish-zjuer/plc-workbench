"""R3 regression evidence: unchanged candidates, zero model generation, live-memory receipts."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import threading

from .config import ROOT,ModelConfig
from .deepseek_credentials import candidates
from .storage import Project,Session,atomic_json,now
from .workflow import PLCWorkflow


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))


class NoModel:
    def __init__(self):self.cancel_event=threading.Event();self.calls=0
    def complete(self,*args,**kwargs):
        self.calls+=1;raise AssertionError('Regression replay must never generate or repair ST')
    def cancel(self):self.cancel_event.set()


def main():
    folder=ROOT/'experiments/memory_r3';folder.mkdir(parents=True,exist_ok=True)
    cfg=replace(ModelConfig.load(),max_steps=1)
    results=[]
    for number in range(1,21):
        qid=f'{number:02d}';reference=ROOT/'experiments/workflow_r2/tasks'/qid/'final.st'
        project=Project.create(f'R3 regression {qid}',kind='benchmark');session=Session.create(project,cfg.model)
        session.data['mode']='execute';session.save()
        source=project.workspace/'candidate.st';source.write_bytes(reference.read_bytes());provider=NoModel()
        result=PLCWorkflow(session,cfg,provider).run(qid)
        record={'question_id':qid,'receipt':result,'source_unchanged':sha(source)==sha(reference),
                'model_calls':provider.calls,'project_id':project.data['id']}
        results.append(record)
        print(json.dumps({'question_id':qid,'status':result['status'],'source_unchanged':record['source_unchanged'],
                          'candidate_warnings':len(result.get('candidate_warnings',[]))}),flush=True)
    atomic_json(folder/'bank_replay.json',{'results':results,'regeneration':False})
    counts=dict(Counter(r['receipt']['status'] for r in results))
    fixed=read(ROOT/'experiments/deepseek_20/test_protocol.json')['implementation_sha256']
    frozen={p:sha(ROOT/p)==digest for p,digest in fixed.items()}
    log=(folder/'regression_tests.log').read_text(encoding='utf-8-sig',errors='replace')
    match=re.search(r'Ran (\d+) tests in ([\d.]+)s',log)
    tests={'count':int(match[1]) if match else None,'passed':bool(match and re.search(r'\nOK\s*$',log))}
    trials=[read(folder/name) for name in ['live_recall_thinking_length_failure.json','live_recall_before_reference_ledger.json','live_recall.json']]
    cny=lambda balance:sum(Decimal(b['total_balance']) for b in balance['balance_infos'] if b['currency']=='CNY')
    cost=cny(trials[0]['before_balance'])-cny(trials[-1]['after_balance'])
    secrets={key.encode() for key,_ in candidates(Path.home()/'Desktop/API keys')}
    if cfg.api_key:secrets.add(cfg.api_key.encode())
    hits=[];files=0
    for path in ROOT.rglob('*'):
        if not path.is_file():continue
        rel=path.relative_to(ROOT)
        if rel.parts[:2]==('agent_data','private') or any(part in ('__pycache__','.git','.venv') for part in rel.parts):continue
        data=path.read_bytes();files+=1
        if any(secret in data for secret in secrets):hits.append(str(rel))
    okay=(tests['passed'] and all(frozen.values()) and counts.get('verified')==16
          and all(r['source_unchanged'] and r['model_calls']==0 for r in results)
          and bool(results[-3]['receipt'].get('candidate_warnings')) and trials[-1].get('all_passed') and not hits)
    summary={'checked_at':now(),'status':'pass' if okay else 'fail','regression':tests,
             'bank_counts':counts,'unchanged_bank_sources':all(r['source_unchanged'] for r in results),
             'bank_model_calls':sum(r['model_calls'] for r in results),'frozen_predicates_unchanged':frozen,
             'live_recall_trials':[{'compressed':r.get('compressed'),'all_passed':r['all_passed'],'checks':r.get('checks'),
                                    'error':r.get('error'),'logical_calls':r['logical_calls']} for r in trials],
             'observed_balance_change_cny':str(cost),'exact_secret_scan':{'files_scanned':files,'matches':hits},
             'runtime_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'plc_agent').glob('*.py'))},
             'unresolved':['04/12: LTIME backend support','08: open-array construction/binding',
                           '18: VARIANT platform/backend support AND incomplete old candidate data access'],
             'limits':'Finite offline regression plus one constructed memory recall case. No CODESYS, formal solver, hardware PLC or guarantee that all bugs are fixed.'}
    atomic_json(folder/'final_validation.json',summary)
    print(json.dumps({'status':summary['status'],'tests':tests,'bank_counts':counts,'secret_matches':len(hits),'observed_cost_cny':str(cost)}))
    return 0 if okay else 1


if __name__=='__main__':raise SystemExit(main())
