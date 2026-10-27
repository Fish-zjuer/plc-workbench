"""Live natural-language entry exercise, separated from the twenty-task matrix."""
from dataclasses import replace
import json
from .benchmark import Budget,MeteredProvider
from .config import ROOT,ModelConfig
from .engine import Engine,source_hash_for_receipt
from .r4_benchmark import OUT
from .storage import Project,Session,atomic_json


def main():
    cfg=replace(ModelConfig.load(),max_steps=12,max_output_tokens=16384,timeout=120)
    project=Project.create('R4 natural-language FIFO integration',kind='benchmark');session=Session.create(project,cfg.model)
    session.data['mode']='execute';session.save()
    source=project.workspace/'code/fifo.st';source.parent.mkdir();source.write_bytes((ROOT/'experiments/workflow_r2/tasks/18/final.st').read_bytes())
    provider=MeteredProvider(cfg,Budget(1));engine=Engine(session,cfg,provider)
    answer=engine.run('请修复第18题，源码在code/fifo.st。需要真正入队和出队元素，不能只更新计数；使用专用PLC流程并进行编译和行为测试，依据实际结果报告。')
    record={'configuration':cfg.public(),'project_id':project.data['id'],'session_id':session.data['id'],'answer':answer,
            'status':session.data['status'],'receipt':session.data.get('last_workflow'),'requests':provider.metrics,
            'verified':bool(session.data.get('last_workflow',{}).get('status')=='verified' and source_hash_for_receipt(engine.toolbox,session.data['last_workflow'])),
            'scope':'One actual natural-language entry example with a fresh original flawed FIFO candidate; not a success-rate estimate.'}
    (OUT/'natural_language_final.st').write_bytes(source.read_bytes())
    atomic_json(OUT/'natural_language_integration.json',record)
    print(json.dumps({'status':record['status'],'verified':record['verified'],'requests':len(provider.metrics)}))
    return 0 if record['verified'] else 1


if __name__=='__main__':raise SystemExit(main())
