"""One isolated self-developed Agent task using the common checker/relay."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plc_agent.config import ModelConfig
from plc_agent.provider import ChatProvider
from plc_agent.storage import Project, Session
from plc_agent.validation import ValidationConfig, ValidationPipeline
from plc_agent.workflow import PLCWorkflow


class RemoteValidation:
    def __init__(self, url, task):
        self.url, self.task = url, task
        self.config = ValidationConfig.load(ROOT / 'agent_data')

    def fingerprint(self):
        return self.task['validation_fingerprint']

    def notes(self):
        notes = ValidationPipeline(self.config, ROOT / 'agent_data').notes()
        notes.append(self.task.get('policy',''))
        if self.task.get('question_id') == '12':
            notes.append('Q12 hold contract: trigger at scan t; set hold elapsed to 0 at the trigger scan, then add CycleTime on every following scan. Release at the first scan where elapsed >= 500ms. Example with CycleTime=10ms and trigger at 10ms: 500ms scan has elapsed 490ms (alarm=1), 510ms scan has elapsed 500ms (alarm=0). Accumulate runtime on the first valid scan.')
        notes.append('Q20 v2: automatic actions may respond on the triggering scan or the next scan; mutual exclusion holds every scan. Kick duration/reset is unspecified and not scored.')
        return notes

    def preflight(self, _):
        return self.task.get('preflight')

    def evaluate(self, source, qid):
        request = urllib.request.Request(self.url+'/check/'+self.task['task_id'], data=source.read_bytes(),
                                         headers={'Content-Type':'text/plain; charset=utf-8'},method='POST')
        with urllib.request.urlopen(request,timeout=300) as response:
            return json.loads(response.read())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--task',type=Path,required=True)
    parser.add_argument('--url',required=True)
    args=parser.parse_args()
    task=json.loads(args.task.read_text(encoding='utf-8'))
    config=ModelConfig(base_url=args.url+'/v1',model=task['model'],api_key='sk-experiment-local',
                       extra_body=task['model_options'],
                       max_output_tokens=task['max_output_tokens'],context_window=128000,max_steps=24,
                       timeout=int(os.environ.get('PLC_EXPERIMENT_PROVIDER_TIMEOUT','180')))
    provider=ChatProvider(config,extra_headers={'X-Experiment-Task':task['task_id']})
    project=Project.create(task['setting']+'-'+task['question_id'],kind='benchmark')
    session=Session.create(project,config.model)
    session.data['mode']='execute';session.save()
    validator=RemoteValidation(args.url,task)
    def notice(kind,payload):
        if kind in ('notice','error'):print(payload.get('text',''),file=sys.stderr,flush=True)
    receipt=PLCWorkflow(session,config,provider,notice,evaluator=validator.evaluate,validation=validator,
                        candidate_limit=6,time_limit=max(1,task['deadline']-__import__('time').time())).run(task['question_id'])
    print(json.dumps({'receipt':receipt,'workspace':str(project.workspace)},ensure_ascii=False),flush=True)
    return 0 if receipt['status']=='verified' else 1


if __name__=='__main__':raise SystemExit(main())
