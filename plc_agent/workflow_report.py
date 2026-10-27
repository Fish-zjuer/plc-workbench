from collections import Counter
from decimal import Decimal
import json
from pathlib import Path

from .config import ROOT
from .storage import atomic_json
from .workflow_benchmark import R2


def main():
    data=json.loads((R2/'results.json').read_text(encoding='utf-8'))
    original=json.loads((ROOT/'experiments/deepseek_20/results.json').read_text(encoding='utf-8'))
    baseline={r['id']:r for r in original['results']}
    verified=json.loads((R2/'verification.json').read_text(encoding='utf-8'))
    unseen=json.loads((R2/'unseen_summary.json').read_text(encoding='utf-8'))
    validation=json.loads((R2/'final_validation.json').read_text(encoding='utf-8')) if (R2/'final_validation.json').exists() else None
    counts=dict(Counter(r['receipt']['status'] for r in data['results']))
    before=json.loads((R2/'preflight.json').read_text(encoding='utf-8'))['balance']
    after=json.loads((R2/'balance_after_all.json').read_text(encoding='utf-8'))
    cny=lambda value:sum(Decimal(b['total_balance']) for b in value['balance_infos'] if b['currency']=='CNY')
    cost=cny(before)-cny(after)
    repaired=[r['question_id'] for r in data['results'] if r['receipt']['status']=='verified' and baseline[r['question_id']]['final']['status'] in ('fail','compile_error')]
    added=[r['question_id'] for r in data['results'] if r['receipt']['status']=='verified' and baseline[r['question_id']]['final']['status']=='behavior_not_supported']
    nl=[]
    for name in ['natural_language_integration.json','natural_language_integration_focused.json','natural_language_integration_thinking.json']:
        p=R2/name
        if p.exists():
            r=json.loads(p.read_text(encoding='utf-8'));nl.append({'file':name,'status':r['status'],'workflow_status':r.get('last_workflow',{}).get('status'),
                                                             'requests':len(r['requests']),'configuration':r.get('configuration')})
    lines=['# PLC专用流程 R2：真实修复与回归','',
      '**原20题最终候选从10题通过有限检查，推进到16题通过；剩余4题因后端支持阻塞。** 其中4题是DeepSeek修复代码，2题是新增结构体行为覆盖；不能把这6题都算成模型修复收益。','',
      '本轮是从原始最终候选出发的继续修复，不是20次重新独立生成，也没有覆盖原始成绩。','',
      '## 实际改变','',
      '- 增加程序控制的PLC流程：收集当前源码与同版本证据→模型提案→完整性和接口检查→版本写入→立即编译/测试→按失败约束修复。',
      '- 接入TUI `/solve 05`、CLI `solve 05`，也作为通用agent的`plc_solve_bank`工具提供；计划模式只制定计划，不调用模型或执行。',
      '- 明确任务后收窄工具范围，减少无关环境/接口探测。保留既往反例，格式重试与源码修改分开计数，整个对话与内部流程共享模型请求上限。',
      '- 所有通过结论绑定源码SHA；模型说“已完成”不能盖过失败或源码变化。预算耗尽、网络错误、后端缺失均留档。','',
      '## 逐题复评','',
      '| 题 | 原始最终状态 | R2状态 | 模型提案请求数 |','|---|---|---|---|']
    for item in data['results']:
        qid=item['question_id'];receipt=item['receipt']
        lines.append(f"| [{qid}](tasks/{qid}/result.json) | {baseline[qid]['final']['status']} | {receipt['status']} | {len(item['requests'])} |")
    lines.extend(['',f'代码修复：{", ".join(repaired)}。新增行为覆盖：{", ".join(added)}。原来已通过的10题保持通过。',
      '05焊缝报警不结束初始化、10温控冷却不足、14字符串后端兼容问题已通过原判据。15选择了符合当前扫描时序契约的实现；题面允许的扫描延迟仍需明确，不能把这项差异说成已证工业故障。',
      '', '04/12仍缺少LTIME支持；08仍受开放数组构造/绑定限制；18遇到VARIANT类型支持缺失。后续R3审计另确认18旧候选正文没有访问item/buffer、容量未初始化，数据存取并未完成；不能只归因于后端，详见[后续审计](../memory_r3/report.md)。保留原题类型和方向，没有降级接口来刷通过。','',
      '## 回归与独立检查','',
      *([f'- 工具完整回归{validation["regression"]["count"]}项通过；核验16份最终源码和项目文件均匹配通过记录，代码及报告未匹配到本机已授权密钥。'] if validation and validation['status']=='pass' else []),
      f'- 16题各在两个新执行进程中重放全部现有有限检查，全部通过；每轮共{sum(r["scans_per_run"] for r in verified["results"]):,}次FB调用。原固定判据文件哈希未变。',
      '- 05/10/14另外加入未提供给修复模型的补充序列：488、640、130个扫描点，共1,258点，各重放两次，均通过。',
      '- 07/17新增固定结构体数组测试，检查优先级选择、只读配置、配方增删改查、容量、重复编号、最低空槽与状态保留；使用显式copy-in/copy-out，未验证引用别名和并发。',
      '- 对4份修订源码另做隔离上下文的对抗审查。7项提案中1项时间结构无效，6项涉及需求歧义；5项可执行提案未见断言差异，另1项出现差异但仍属待澄清时序，不增加确认缺陷数。','',
      '## 自然语言入口与推理配置','',
      '另外进行了第05题的入口试验，不能省略失败记录：','',
      '| 试验 | 流程结果 | 总模型请求 |','|---|---|---|'])
    for row in nl:
        label='低思考配置' if row['file'].endswith('_thinking.json') else '非思考/任务范围收敛后' if row['file'].endswith('_focused.json') else '非思考/范围收敛前'
        lines.append(f"| [{label}]({row['file']}) | {row['workflow_status']} | {row['requests']} |")
    lines.extend(['','同一DeepSeek模型关闭思考时，两次入口试验未完成修复；低思考配置的一次试验在一次源码修改后通过，额外未见输入也重放通过。当前TUI使用这次验证的低思考配置，仍可在模型配置中更换。这几个试验不足以估计总体可靠率，也不证明换配置后稳定成功。',
      '', '## 花费与边界','',
      f'R2预检到最终余额检查，账户人民币余额观测减少约 **¥{cost}**，包含批测修复、独立审查和入口试验。余额可能有结算延迟或其他并发使用，不是逐请求精确账单；未充值。密钥没有进入代码、报告或模型上下文。',
      '', '尚未执行CODESYS、形式化求解器或实体PLC。16/20是当前有限检查结果，不是工业正确率。剩余4题需要补齐后端能力；自然语言修复的稳定性也仍需更多独立重复试验。',
      '', '## 文件','',
      '- [R2结果矩阵](results.json)、[原始20题报告](../deepseek_20/report.md)、[源码哈希与两次回放](verification.json)。',
      '- [结构体测试范围](struct_protocol.json)、[补充测试序列](unseen_probe_protocol.json)、[补充测试摘要](unseen_summary.json)。',
      '- [独立审查及执行](independent_reviews.json)、[工具回归日志](regression_tests.log)。',
      '- [最终证据核验](final_validation.json)。模型请求数按逻辑调用计；服务的429/502/503/504错误另有每次最多3次HTTP尝试。',
      '- [架构说明](../../docs/AGENT_ARCHITECTURE.md)、[使用说明](../../AGENT_README.md)。','',
      '使用：','', '```text','/plan','/solve 05','/act','/solve 05','```','',
      '```powershell','python -B -m plc_agent solve 05 --mode plan','python -B -m plc_agent solve 05 --mode execute --max-revisions 3','```'])
    (R2/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    atomic_json(R2/'overview.json',{'counts':counts,'code_repairs':repaired,'new_behavior_coverage':added,
      'model_generation_requests':sum(len(r['requests']) for r in data['results']),
      'verified_replays':len(verified['results']),'unseen_scans_per_run':sum(r['scans_per_run'] for r in unseen.values()),
      'observed_cost_cny':str(cost),'natural_language_trials':nl,'limitation':'Finite offline checks; R2 repair/coverage experiment, not independent model accuracy or CODESYS proof.'})
    print(json.dumps({'counts':counts,'code_repairs':repaired,'added_coverage':added,'cost_cny':str(cost)},ensure_ascii=False))


if __name__=='__main__':main()
