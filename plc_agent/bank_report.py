from __future__ import annotations

from collections import Counter
from decimal import Decimal
import html
import json
from pathlib import Path

from .benchmark import RUN_ROOT
from .config import ROOT
from .storage import atomic_json


LABELS={'pass':'有限检查通过','fail':'测试失败','compile_error':'离线编译失败','behavior_not_supported':'仅编译，行为未测'}
CHINESE={
 '01':'灌装线','02':'DWORD边沿检测','03':'滞环报警','04':'果酱泵运行维护','05':'焊缝报警',
 '06':'曝气风机','07':'多泵切换','08':'模拟量批处理','09':'移动平均','10':'温度控制',
 '11':'三工位生产线','12':'板厚报警历史','13':'办公HVAC','14':'IPv4解析','15':'物料配比',
 '16':'柔性加工路线','17':'配方管理','18':'VARIANT FIFO','19':'机械臂','20':'五工位生产控制'}


def main():
    data=json.loads((RUN_ROOT/'results.json').read_text(encoding='utf-8'))
    verification=json.loads((RUN_ROOT/'verification.json').read_text(encoding='utf-8'))
    reviews=json.loads((RUN_ROOT/'adversarial_reviews.json').read_text(encoding='utf-8'))
    followup_path=RUN_ROOT/'postfix_followup/results.json'
    followup=json.loads(followup_path.read_text(encoding='utf-8')) if followup_path.exists() else None
    followups={r['question_id']:r for r in followup['results']} if followup else {}
    before=json.loads((RUN_ROOT/'preflight.json').read_text(encoding='utf-8'))['balance']
    after=followup['balance_after'] if followup else json.loads((RUN_ROOT/'balance_after_review.json').read_text())
    cny=lambda obj:sum(Decimal(r['total_balance']) for r in obj['balance_infos'] if r['currency']=='CNY')
    cost=cny(before)-cny(after)
    requests=sum(len(r['requests']) for r in data['results'])
    scan_count=sum(r['final'].get('summary',{}).get('scans',0) for r in data['results'])
    lines=['# DeepSeek 公共题库20题真实实测','',
      '状态：本轮完成，待审核。结果不支持把当前版本称为成熟工业 agent。','',
      '**原始20题批测：10题通过当前有限检查，3题测试失败，5题未通过离线编译，2题仅编译而未执行行为验证。** 首稿通过有限检查的有4题，修订后增加至10题。共15题完成离线编译，13题实际执行了行为检查。','',
      '这不是“模型正确率50%”：测试覆盖有限，编译失败包含后端兼容问题，没有CODESYS、形式化验证或实体PLC结果。','',
      '## 实验怎么跑的','',
      '- 按原始ZIP中的顺序，完整使用6道easy、8道medium、6道hard，没有另挑容易的20道。',
      '- 直接调用用户授权的真实DeepSeek官方服务，接口查询返回模型`deepseek-flash` / `DeepSeek-V4.1-Flash`。本次显式关闭思考模式。',
      '- 使用实际`Engine`、文件导入和工具闭环；每题独立项目及会话。模型先读题、生成ST，再收到真实编译/行为反馈自行修订；主控没有改写任何被测ST。',
      '- 每题最多14个模型步骤、两题并行。提示中要求最多三次修订，但这不是工具层硬上限；个别题超过该修订次数，代码和记录如实保留。',
      '- 判据在生成前固定；16题有预定义有限行为检查，4题的结构体引用/开放数组/VARIANT桥接未适配，明确标注。题面未定义的部分尽量不打分。',
      f'- 主流程实际发出{requests}个模型请求，输入{data["usage"]["prompt_tokens"]:,} tokens，输出{data["usage"]["completion_tokens"]:,} tokens；输入包含重复上下文和缓存命中。',
      f'- 最终可执行候选的一轮检查共{scan_count:,}次功能块调用；13题另外各在两个新进程中重放，结果全部一致。','',
      '## 逐题结果','',
      '| 题号 / 内容 | 难度 | 首稿 | 批测最终 | ST版本数 | 模型请求数 |',
      '|---|---|---|---|---|---|']
    for r in data['results']:
        lines.append(f"| [{r['id']} {CHINESE[r['id']]}](tasks/{r['id']}/result.json) | {r['difficulty']} | {LABELS.get(r['first']['status'],r['first']['status'])} | {LABELS.get(r['final']['status'],r['final']['status'])} | {r['versions']} | {len(r['requests'])} |")
    lines.extend(['','## 三个测试失败如何解释','',
      '1. **05 焊缝报警：明确逻辑缺陷。** 最终候选从未把`bInitDone`置TRUE，也没有正常监控/防抖报警分支。时间到5101 ms时仍处于初始化，报警为FALSE。完整轨迹和两次重放保留，不能因“能编译”算完成。',
      '2. **10 温控：明确冷却时间问题。** 在5001 ms首次输出过热保护，7999 ms已重新开启加热，仅间隔2998 ms，未等满3秒。候选在更新状态之前计算边沿，保护开始时间取成了前次调用时刻。',
      '3. **15 物料配比：扫描时序契约不一致。** 当前判据要求关B后下一次调用已开C，但候选多经过一个内部过渡状态，此时C仍关闭。这是实测差异；题面没有量化允许几轮扫描的延迟，需澄清，不能与前两条同样宣布为无条件工业缺陷。','',
      '## 五个离线编译失败与两个未验证项','',
      '| 题 | 阻塞点 | 可得出的结论 |','|---|---|---|',
      '| 04、12 | STruC++报告未定义`LTIME` | 原题固定接口使用该类型，不能靠降级接口冒充通过 |',
      '| 08 | 开放数组生成的`ArrayView1D`缺少可用默认构造 | ST前端后生成C++失败，须检查后端/目标平台兼容 |',
      '| 14 | 字符串下标生成`.at()`，运行时没有该成员 | 与此前Luna实验遇到的后端问题同类 |',
      '| 18 | VARIANT及CODESYS专有辅助接口的解析/类型支持失败 | 当前离线结果不能判断真实CODESYS下是否正确 |',
      '| 07、17 | 目标文件编译成功，但未适配调用者持有的结构体/数组引用 | 没有行为结果，不能计作通过 |','',
      '## 独立对抗审查','',
      f'另以新上下文对20份最终源码全部审查，不提供作者历史或已有测试结果。审查者提出{reviews["counts"]["hypotheses"]}条假设，**这不是51个确认漏洞**。',
      '主控抽查并留档16条裁决。焊缝初始化问题与已有失败一致；窗口3输入1..7的实际重放反驳了“移动平均必然覆盖错位置”的指控。另有把合法循环误读为倒序、把调用方禁止的输入当反例、审查文字自行承认正确但标题仍说错等情况。其余假设未逐条完成裁决，不计入缺陷数。',
      '这轮证明审查者也会产生错误主张，因此审查必须接执行与需求裁决，不能将“另一个模型说有bug”当作证据。','',
      '## 本轮对agent的修正','',
      '- 修正重复工具调用保护：同一路径的文件内容变化后视为新调用，允许继续编译/测试；原20题运行时仍使用旧版本，原始分数不重写。',
      '- 提示要求写出完整功能块，保留全部功能，不能为了编译成功删成占位程序；这项提示修改不等于已证明模型以后不会犯错。',
      '- 模型配置支持服务扩展参数，兼容DeepSeek的thinking开关；保留需要回传的reasoning_content，不展示成答案。',
      '- 增加题库编译/测试工具、可恢复的批测脚本、请求用量与预算保护。应用本身仍以base_url/api_key/model配置，不绑定某个厂商。','',
      '## 修正工具后的单独回归',''])
    if followup:
        lines.extend(['这些是后续修复，**不并入上面的20题原始统计**。仍由DeepSeek写ST，主控只提供真实反馈；每题使用新修复会话，最多8个模型步骤。','',
                      '| 题 | 原始最终结果 | 后续结果 | 请求数 |','|---|---|---|---|'])
        for r in followup['results']:
            lines.append(f"| [{r['question_id']}](postfix_followup/{r['question_id']}/result.json) | {LABELS[r['before_status']]} | {LABELS.get(r['after']['status'],r['after']['status'])} | {len(r['requests'])} |")
    else:
        lines.append('有界回归正在运行，完成后另行记录。')
    lines.extend(['','## 花费与复现','',
      f'从最初余额检查到当前最后一次检查，账户人民币余额减少 **¥{cost}**。这是账户余额观测差，包含连接检查、批测、审查及已完成后续回归；若有其他并发使用或余额延迟，不等于精确逐请求账单。未充值。密钥未写入源码、报告或聊天。','',
      '- [原始题面](questions.json)、[固定判据与哈希](test_protocol.json)、[实际请求/结果矩阵](results.json)。',
      '- [新进程复核与部分审查裁决](verification.json)、[独立审查原文](adversarial_reviews.json)。',
      '- 每题`tasks/题号/`中有首稿、逐次修订、最终ST、编译诊断、逐扫描结果；实际agent会话保存在本机`agent_data/projects/`。',
      '- [运行时源码快照](agent_runtime_snapshot/manifest.json)保留原始批测版本；工具修正后的代码与原分数分开。',
      '- [工具回归测试日志](regression_tests.log)。','',
      '```powershell',
      'python -B -m plc_agent.benchmark --credential-folder "C:\\Users\\29927\\Desktop\\API keys" --workers 2 --budget-cny 8',
      'python -B -m plc_agent.bank_verification',
      '```','',
      '批测脚本会跳过已完成题目、恢复未完成题目；固定判据改变时拒绝悄悄沿用旧实验。已有结果目录用于本轮续跑，不代表启动全新独立重复实验。','',
      'API行为核对：[模型列表](https://api-docs.deepseek.com/api/list-models/)、[工具调用](https://api-docs.deepseek.com/guides/tool_calls/)、[思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)、[余额接口](https://api-docs.deepseek.com/api/get-user-balance/)。','',
      '下一步最有价值的工作是接入CODESYS并完善结构体、开放数组和VARIANT调用桥接，随后扩充独立状态/时序判据；不是继续堆通用聊天功能。'])
    (RUN_ROOT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    rows=[]
    for r in data['results']:
        ident=r['id'];status=r['final']['status'];label=LABELS.get(status,status)
        rows.append(f'<tr data-status="{status}"><td>{ident}</td><td>{html.escape(CHINESE[ident])}</td><td>{r["difficulty"]}</td><td>{html.escape(LABELS.get(r["first"]["status"],r["first"]["status"]))}</td><td class="{status}">{label}</td><td>{r["versions"]}</td><td><a href="tasks/{ident}/final.st">ST</a> · <a href="tasks/{ident}/result.json">证据</a></td></tr>')
    document='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DeepSeek · PLC 20题实测</title>
<style>body{font:16px/1.6 system-ui;margin:40px auto;padding:0 24px;max-width:1100px;background:#0d1728;color:#dce8f5}h1{font-size:30px}a{color:#75dacf}.cards{display:flex;gap:16px;flex-wrap:wrap}.card{padding:18px;background:#17283d;border-radius:12px;flex:1;min-width:150px}.num{font-size:32px;font-weight:700}.muted{color:#9dafc3}table{width:100%;border-collapse:collapse;margin-top:20px}th,td{text-align:left;padding:12px;border-bottom:1px solid #294059}.pass{color:#7ce5b8}.fail{color:#ffb488}.compile_error{color:#edce7e}.behavior_not_supported{color:#aabbd1}input,select{font:inherit;padding:9px;background:#17283d;border:1px solid #38546f;color:inherit;border-radius:7px;margin:18px 12px 0 0}</style>
<h1>DeepSeek · PLC公共题库20题实测</h1><p class="muted">真实API + 本地agent闭环；固定判据，首稿与修订均保留。不是CODESYS或形式化证明。</p>
<div class="cards"><div class="card"><div class="num">20</div>题目全部尝试</div><div class="card"><div class="num">4 → 10</div>首稿到最终有限检查通过</div><div class="card"><div class="num">13</div>实际执行行为测试</div><div class="card"><div class="num">¥COST</div>账户余额观测减少</div></div>
<p>最终：10题有限检查通过 · 3题测试失败（含1题扫描时序约定）· 5题离线编译失败 · 2题行为未测。<br>独立审查51条假设，不能算成51个确认漏洞。<a href="report.md">完整报告与后续回归</a></p>
<input id="query" placeholder="搜索题号/名称"><select id="status"><option value="">全部结果</option><option value="pass">有限检查通过</option><option value="fail">测试失败</option><option value="compile_error">离线编译失败</option><option value="behavior_not_supported">仅编译</option></select>
<table><thead><tr><th>题</th><th>内容</th><th>难度</th><th>首稿</th><th>最终</th><th>版本</th><th>留档</th></tr></thead><tbody>ROWS</tbody></table>
<script>const q=document.getElementById('query'),s=document.getElementById('status');function filter(){document.querySelectorAll('tbody tr').forEach(r=>r.hidden=(!r.textContent.toLowerCase().includes(q.value.toLowerCase()))||(s.value&&r.dataset.status!==s.value))}q.oninput=s.onchange=filter;</script></html>'''
    (RUN_ROOT/'report.html').write_text(document.replace('COST',str(cost)).replace('ROWS',''.join(rows)),encoding='utf-8')
    atomic_json(RUN_ROOT/'overview.json',{'counts':data['counts'],'requests_main':requests,'scans_final_once':scan_count,
                                        'replays_match':verification['all_replays_match'],'review_hypotheses':reviews['counts']['hypotheses'],
                                        'observed_cost_cny':str(cost),'followups':{qid:r['after']['status'] for qid,r in followups.items()}})
    print(json.dumps({'report':str(RUN_ROOT/'report.md'),'cost_cny':str(cost),'followups':{qid:r['after']['status'] for qid,r in followups.items()}},ensure_ascii=False))


if __name__=='__main__':
    main()
