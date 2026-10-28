"""Exercise the improved workflow with scripted replies and real compilers.

These are integration fixtures, explicitly not measurements of an LLM's ability.
No API connection, credentials or external model request is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import threading
import uuid

from .config import ModelConfig, ROOT, STATE_ROOT
from .storage import Project, Session, atomic_json, now
from .validation import ValidationConfig
from .workflow import PLCWorkflow


class FixtureProvider:
    def __init__(self, codes=()):
        self.codes=iter(codes)
        self.requests=[]
        self.cancel_event=threading.Event()

    def complete(self,messages,**kwargs):
        self.requests.append(messages)
        return {'text':json.dumps({'summary':'Scripted integration-test response; not LLM output',
                                  'code':next(self.codes),'assumptions':[]}), 'usage':{}, 'calls':[]}

    def cancel(self): self.cancel_event.set()


def run(output):
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    home=STATE_ROOT/'optimization_selftest'/uuid.uuid4().hex[:12]
    config=ValidationConfig.load()
    if config.mode!='codesys':raise ValueError('Configure CODESYS validation before this self-test')
    config.save(home)
    model=ModelConfig(base_url='http://fixture.invalid/v1',model='scripted-integration-fixture')
    summary={'started_at':now(),'kind':'scripted integration fixtures with real CODESYS + real finite offline tests',
             'external_model_requests':0,'original_candidates_modified':False,'cases':[]}
    sources={qid:ROOT/'experiments/backend_r4/tasks'/qid/'final.st' for qid in ('03','18','20')}
    original_hashes={qid:hashlib.sha256(p.read_bytes()).hexdigest() for qid,p in sources.items()}

    def case(name,qid,initial,replies):
        project=Project.create('Optimization self-test '+name,home,kind='benchmark')
        session=Session.create(project,model.model);session.data['mode']='execute';session.save()
        path=project.workspace/'candidate.st';path.write_text(initial,encoding='utf-8',newline='\n')
        provider=FixtureProvider(replies)
        def notify(kind,payload):
            if kind=='notice':print(name+': '+payload['text'],flush=True)
        receipt=PLCWorkflow(session,model,provider,notify=notify).run(qid)
        directory=output/name;directory.mkdir()
        atomic_json(directory/'receipt.json',receipt)
        atomic_json(directory/'fixture_requests.json',{'requests':provider.requests,'external_model_requests':0})
        (directory/'final.st').write_bytes(path.read_bytes())
        record={'name':name,'question_id':qid,'status':receipt['status'],'fixture_proposals':len(provider.requests),
                'validation_mode':receipt.get('validation_mode'),'run_path':str(project.workspace/receipt['run_path'])}
        summary['cases'].append(record);atomic_json(output/'results.json',summary)
        return receipt,provider,session

    q20=sources['20'].read_text(encoding='utf-8')
    renamed=re.sub(r'\blint\b','clampedWeight',q20,flags=re.I)
    fixed,provider,session=case('reserved_identifier','20',q20,[renamed])
    assert fixed['status']=='verified' and len(provider.requests)==1
    packet=json.loads(provider.requests[0][1]['content'])
    assert packet['latest_evidence']['status']=='static_error'
    assert fixed['final_evaluation']['stages']['codesys']['status']=='pass'
    assert fixed['final_evaluation']['stages']['behavior']['status']=='pass'

    # Revalidate exactly the same candidate: the compiler receipt is reused,
    # while behavior checks still run against the current source.
    cached=PLCWorkflow(session,model,FixtureProvider()).run('20')
    assert cached['status']=='verified' and cached['model_calls']==0
    assert cached['final_evaluation']['stages']['codesys']['cached'] is True
    atomic_json(output/'compiler_cache_recheck.json',cached)
    summary['cache_recheck']={'status':cached['status'],'fixture_proposals':0,'cache_hit':True}

    q03=sources['03'].read_text(encoding='utf-8')
    broken=q03.replace('END_FUNCTION_BLOCK','MissingOptimizationFixtureFunction();\nEND_FUNCTION_BLOCK')
    repaired,provider,_=case('compiler_feedback','03',broken,[q03])
    assert repaired['status']=='verified' and len(provider.requests)==1
    packet=json.loads(provider.requests[0][1]['content'])
    assert packet['latest_evidence']['failure_stage']=='codesys'
    assert packet['latest_evidence']['primary_diagnostics']

    blocked,provider,_=case('platform_block','18',sources['18'].read_text(encoding='utf-8'),[])
    assert blocked['status']=='platform_blocked' and not provider.requests
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==original_hashes[qid] for qid,p in sources.items())
    summary.update(status='pass',finished_at=now(),original_source_sha256=original_hashes,
                   interpretation='Mechanism validation only. No new model capability or four-condition benchmark has been measured.')
    atomic_json(output/'results.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'reports/agent_optimization'/('selftest-'+uuid.uuid4().hex[:12]))
    args=parser.parse_args();run(args.output)


if __name__=='__main__':main()
