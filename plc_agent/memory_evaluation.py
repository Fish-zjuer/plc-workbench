"""Small live-service memory recall check; kept separate from offline regressions."""
from __future__ import annotations

from dataclasses import replace
import json
from urllib.parse import urlparse

from .benchmark import Budget,MeteredProvider
from .config import ROOT,ModelConfig
from .deepseek_credentials import get
from .engine import Engine
from .provider import json_value
from .storage import Project,Session,atomic_json


def main():
    folder=ROOT/'experiments/memory_r3';folder.mkdir(parents=True,exist_ok=True)
    cfg=replace(ModelConfig.load(),context_window=16000,max_output_tokens=2048,max_steps=6,
                compact_summary_tokens=2048,timeout=120)
    if urlparse(cfg.base_url).hostname!='api.deepseek.com':
        raise ValueError('本实测脚本含DeepSeek余额检查，只能使用已授权的api.deepseek.com配置；不会将其他服务密钥发送给DeepSeek。')
    cfg.validate();budget=Budget(1);provider=MeteredProvider(cfg,budget)
    project=Project.create('Memory R3 live recall',kind='benchmark');session=Session.create(project,cfg.model)
    engine=Engine(session,cfg,provider)
    old_sha='a1'*32;new_sha='b2'*32
    fixtures=[
      ('user','我们负责PLC agent。必须用base_url、api_key、model接任意兼容服务，不能绑定某厂商。不要Electron，做TUI，必须上传文件、计划模式、上下文压缩。停止优先于启动。候选路径code/seam.st。冷却先按2秒。'+('旧讨论：仍在比较工具选择，尚无部署结论。'*120)),
      ('assistant',f'旧版本SHA={old_sha}曾完成离线编译，行为测试尚未完成，CODESYS没运行。'+('编译通过不能说明实际行为正确。'*70)),
      ('user',f'更正：冷却是3秒，撤销先前2秒。最新文件SHA={new_sha}，不能沿用旧版结果。'+('任务讨论记录：需求的更正高于旧约定。'*110)),
      ('assistant','发现缺陷：初始化从未结束。先前仅修复语法，行为修复仍待回归；对抗审查有歧义，不能都算故障。'+('分析记录：需要保留证据和未完成事项。'*120)),
      ('user','还有操作记录：文件上传后只复制到项目；需要读取时才给模型正文。'+('流程讨论：记录计划，检查输出，保存结果。'*95)),
      ('assistant','当前还不能说程序已被形式化证明；没有跑求解器或实体PLC。'),
      ('user','近期讨论：界面保持简单。'),('assistant','采用终端界面。'),
      ('user','保留失败实验，不要只展示成功。'),('assistant','已记录这个要求。')]
    engine.messages=[]
    for role,text in fixtures:
        engine.messages.append({'role':role,'content':text});session.event(role,text=text)
    initial=engine.context_stats();atomic_json(folder/'fixture.json',{'messages':engine.messages,'configuration':cfg.public()})
    before=get(cfg.api_key,'/user/balance')
    record={'project_id':project.data['id'],'session_id':session.data['id'],'configuration':cfg.public(),'before_context':initial}
    try:
        record['compressed']=engine.compact();record['after_context']=engine.context_stats()
        record['memory']=session.data.get('working_memory')
        prompt='只据已有历史回答，缺失就填null。只输出JSON：vendor_neutral(布尔)、interface("TUI"等)、upload_required(布尔)、cooldown_seconds(数字)、priority("stop"或"start")、source_path(字符串)、latest_sha(字符串)、latest_behavior_verified(布尔)、codesys_verified(布尔)、formal_verified(布尔)、pending_defect(字符串)。不要推断已经修复。'
        answer=engine.run(prompt);record['answer']=answer;record['session_status']=session.data['status']
        value=json_value(answer)
        expected={'vendor_neutral':True,'interface':'TUI','upload_required':True,'cooldown_seconds':3,'priority':'stop',
                  'source_path':'code/seam.st','latest_sha':new_sha,'latest_behavior_verified':False,'codesys_verified':False,'formal_verified':False}
        record['checks']={name:value.get(name)==expected_value for name,expected_value in expected.items()}
        record['checks']['pending_defect']=isinstance(value.get('pending_defect'),str) and '初始化' in value['pending_defect']
        record['all_passed']=all(record['checks'].values())
    except Exception as exc:
        record.update(all_passed=False,error=str(exc).replace(cfg.api_key,'[redacted]'))
    finally:
        record['metrics']=provider.metrics;record['logical_calls']=budget.calls
        record['after_balance']=get(cfg.api_key,'/user/balance');record['before_balance']=before
        record['limitation']='One constructed long-history recall sample using a real service; not a general memory reliability estimate.'
        atomic_json(folder/'live_recall.json',record)
    print(json.dumps({k:record.get(k) for k in ('compressed','all_passed','checks','error','logical_calls')},ensure_ascii=False))
    return 0 if record['all_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
