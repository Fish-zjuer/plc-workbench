"""Continue saved R4 candidates against explicitly expanded checks; retain first pass."""
from dataclasses import replace
import hashlib
import json
from .benchmark import Budget,MeteredProvider
from .config import ROOT,ModelConfig
from .r4_benchmark import OUT,verdict
from .storage import Project,Session,atomic_json
from .workflow import PLCWorkflow


def main():
    cfg=replace(ModelConfig.load(),max_steps=8,max_output_tokens=16384,timeout=120)
    budget=Budget(1)
    for qid in ('04','12'):
        folder=OUT/'tasks'/qid;result_path=folder/'result.json'
        record=json.loads(result_path.read_text(encoding='utf-8'))
        initial=folder/'result_initial_checks.json'
        if not initial.exists():initial.write_bytes(result_path.read_bytes());(folder/'initial_final.st').write_bytes((folder/'final.st').read_bytes())
        project=Project.load(record['project_id']);session=Session.load(project,record['session_id'])
        source=project.workspace/'candidate.st'
        before=verdict(source,qid);atomic_json(folder/'expanded_before_followup.json',before)
        provider=MeteredProvider(cfg,budget)
        def notify(kind,payload):
            if kind=='notice':print(json.dumps({'id':qid,'notice':payload['text']},ensure_ascii=False),flush=True)
        receipt=PLCWorkflow(session,cfg,provider,notify).run(qid,max_revisions=3)
        (folder/'final.st').write_bytes(source.read_bytes())
        record.setdefault('followup_stages',[]).append({'trigger':'Expanded duration/hold checks','previous_status':before['status'],
                'previous_first_failure':before.get('first_failure'),'requests':provider.metrics,'receipt':receipt})
        record['requests'].extend(provider.metrics);record['receipt']=receipt
        record['receipt_path']=str(project.workspace/receipt['run_path']/'receipt.json')
        atomic_json(result_path,record)
        print(json.dumps({'id':qid,'status':receipt['status'],'extra_requests':len(provider.metrics)}),flush=True)
    current=json.loads((OUT/'results.json').read_text(encoding='utf-8'))
    current['results']=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((OUT/'tasks').glob('*/result.json'))]
    current['note']='Warm-start repair, expanded duration checks after initial candidate inspection; original checks unchanged.'
    atomic_json(OUT/'results.json',current)


if __name__=='__main__':main()
