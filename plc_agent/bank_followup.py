"""Bounded repair follow-up after harness fixes, separate from original scores."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path

from .benchmark import Budget,MeteredProvider,RUN_ROOT,verdict
from .config import ModelConfig
from .deepseek_credentials import get
from .engine import Engine
from .storage import Project,Session,atomic_json


def repair(qid,config,budget):
    original=json.loads((RUN_ROOT/'tasks'/qid/'result.json').read_text(encoding='utf-8'))
    project=Project.load(original['project_id'])
    session=Session.create(project,config.model);session.data['mode']='execute';session.save()
    folder=RUN_ROOT/'postfix_followup'/qid;folder.mkdir(parents=True,exist_ok=True)
    (folder/'before.st').write_bytes((project.workspace/'candidate.st').read_bytes())
    feedback={k:v for k,v in original['final'].items() if k not in ('cases','suites')}
    atomic_json(project.workspace/'evaluation_feedback.json',feedback)
    provider=MeteredProvider(config,budget)
    def notify(kind,payload):
        if kind=='tool' and payload['name'].startswith('plc_'):
            print(json.dumps({'followup':qid,'tool':payload['name'],'status':payload['result'].get('status')},ensure_ascii=False),flush=True)
        if kind=='tool' and payload['name']=='write_file' and payload['result'].get('status')=='written' and payload['arguments'].get('path')=='candidate.st':
            index=len(list(folder.glob('revision_*.st')))+1
            (folder/f'revision_{index:02d}.st').write_bytes((project.workspace/'candidate.st').read_bytes())
    engine=Engine(session,config,provider,notify)
    prompt=f'''继续修复公共题 {qid}。这是首次20题批测之后单独留档的有界修复回归，不覆盖原始结果。
附件中保留原始 question.md，candidate.st 是此前的实际失败版本，evaluation_feedback.json 是独立执行工具的真实反馈。
先读取题面、源码和反馈，然后在不改变要求、接口、类型的前提下修复。源码必须是完整FUNCTION_BLOCK..END_FUNCTION_BLOCK，不得删去功能或写占位分支。
用 plc_bank_test(source="candidate.st",question_id="{qid}") 实际验证。反馈里的project_evidence_path也在当前workspace内，可用read_file读取精确输入与输出。
程序已修正“同一路径源码变更后再次测试被误判重复调用”的工具问题。最多修改3次源码。对于真正不支持的语言/库保持原题接口，诚实停止。
所有修订由你完成，不提供参考实现，不允许修改监视器。修复后更新计划并简述实际结果。'''
    answer=engine.run(prompt)
    source=folder/'after.st';source.write_bytes((project.workspace/'candidate.st').read_bytes())
    result={'question_id':qid,'source_session_id':original['session_id'],'repair_session_id':session.data['id'],
            'before_status':original['final']['status'],'after':verdict(source,qid),'agent_status':session.data['status'],
            'requests':provider.metrics,'answer':answer,'scope':'Post-harness-fix bounded repair, not part of original twenty-task score'}
    atomic_json(folder/'result.json',result);session.export()
    return result


def main():
    cfg=replace(ModelConfig.load(),max_steps=8,timeout=90)
    budget=Budget(1.5)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda q:repair(q,cfg,budget),['05','10','14']))
    atomic_json(RUN_ROOT/'postfix_followup/results.json',{'results':results,'conservative_estimate_cny':budget.used,
                                                       'balance_after':get(cfg.api_key,'/user/balance')})
    print(json.dumps({'followup_results':[(r['question_id'],r['after']['status']) for r in results]},ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
