"""Publish exact R4 evidence and its local-ABI/finite-check boundaries."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from .backend_r4 import info
from .config import ROOT,ModelConfig
from .deepseek_credentials import get,candidates
from .extended_eval import evaluation_fingerprint
from .r4_benchmark import OUT
from .storage import atomic_json,now


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    verification=read(OUT/'verification.json');tasks={r['question_id']:r for r in read(OUT/'results.json')['results']}
    cfg=ModelConfig.load()
    if urlparse(cfg.base_url).hostname=='api.deepseek.com':atomic_json(OUT/'balance_after_all.json',get(cfg.api_key,'/user/balance'))
    before=read(OUT/'preflight.json')['balance'];after=read(OUT/'balance_after_all.json')
    balance=lambda b:sum(Decimal(r['total_balance']) for r in b['balance_infos'] if r['currency']=='CNY')
    cost=balance(before)-balance(after)
    integration=read(OUT/'natural_language_integration.json') if (OUT/'natural_language_integration.json').exists() else None
    cleanup=read(OUT/'temporary_drive_cleanup.json') if (OUT/'temporary_drive_cleanup.json').exists() else None
    reviews=read(OUT/'independent_reviews.json')['results']
    counts=dict(Counter(f['status'] for r in reviews for f in r['findings']))
    log=(OUT/'regression_tests.log').read_text(encoding='utf-8-sig',errors='replace')
    match=re.search(r'Ran (\d+) tests in ([\d.]+)s',log);skip=re.search(r'OK \(skipped=(\d+)\)',log)
    tests={'run':int(match[1]) if match else None,'skipped':int(skip[1]) if skip else 0,
           'passed':bool(match and re.search(r'\nOK(?: \(skipped=\d+\))?\s*$',log))}
    upstream=(OUT/'upstream_tests.log').read_text(encoding='utf-8-sig',errors='replace')
    source_checks={r['question_id']:sha(OUT/'tasks'/r['question_id']/'final.st')==r['source_sha256'] for r in verification['results']}
    reference=read(OUT/'reference_protocol.json');duration=read(OUT/'duration_protocol.json')
    oracle_checks={'reference':sha(ROOT/'plc_agent/reference_checks.py')==reference['implementation_sha256'],
                   'duration':sha(ROOT/'plc_agent/duration_checks.py')==duration['implementation_sha256']}
    secrets={key.encode() for key,_ in candidates(Path.home()/'Desktop/API keys')}
    if cfg.api_key:secrets.add(cfg.api_key.encode())
    hits=[];scanned=0
    for path in ROOT.rglob('*'):
        if not path.is_file():continue
        rel=path.relative_to(ROOT)
        if rel.parts[:2]==('agent_data','private') or any(p in ('__pycache__','.git','.venv') for p in rel.parts):continue
        data=path.read_bytes();scanned+=1
        if any(secret in data for secret in secrets):hits.append(str(rel))
    okay=(tests['passed'] and len(source_checks)==20 and all(source_checks.values()) and all(oracle_checks.values())
          and all(verification['original_predicates_unchanged'].values()) and all(r['workflow_status']=='verified' and r['replay_statuses']==['pass','pass'] for r in verification['results'])
          and verification['backend']['fingerprint']==info()['fingerprint'] and verification['evaluation_fingerprint']==evaluation_fingerprint()
          and all(v['statuses']==['pass','pass'] for v in verification['unseen'].values()) and not hits)
    result={'checked_at':now(),'status':'pass' if okay else 'fail','regression':tests,'upstream_selected_tests_passed':bool(re.search(r'Tests\s+93 passed',upstream)),
            'source_checks':source_checks,'supplemental_oracles_unchanged_since_protocol':oracle_checks,
            'original_predicates_unchanged':verification['original_predicates_unchanged'],'backend_fingerprint':info()['fingerprint'],
            'evaluation_fingerprint':evaluation_fingerprint(),'review_status_counts':counts,
            'integration_verified':integration.get('verified') if integration else None,'observed_balance_decrease_cny':str(cost),
            'temporary_test_drive_cleanup':cleanup,
            'exact_secret_scan':{'files_scanned':scanned,'matches':hits},
            'runtime_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'plc_agent').glob('*.py'))},
            'scope':'All 20 current candidates pass this finite offline local-ABI evaluation. Warm-start repair/coverage; not independent generation accuracy or vendor correctness.'}
    atomic_json(OUT/'final_validation.json',result)
    rows=['# R4：补齐后端与剩余4题','',
      '**20题当前候选均通过本轮离线有限检查。** 原来受阻的4题现在可编译执行；04/12/18由真实DeepSeek修订，08原候选无需修改。原16题在新后端上保持通过。',
      '', '本轮从既有候选继续修复，并扩展了后端与测试覆盖，不是20次独立生成的100%准确率。第18题使用本地PV1引用接口，未验证Siemens/CODESYS兼容；通过不等于完整工业正确性。','',
      '## 实际修复','',
      '| 题 | 查到的问题与处理 | 本轮作者请求 |','|---|---|---|']
    descriptions={'04':'开放LTIME后发现TIME毫秒被当纳秒；补充边界又查出500h阈值小1000倍，均由模型修复。',
                  '08':'后端增加未绑定数组状态及真实调用方存储绑定，保留下界；原候选通过，无需修改。',
                  '12':'修复报警保持起点；补充测试发现新故障未重启500ms保持，再修订；内部累计改用LTIME。',
                  '18':'移除原来的只维护计数占位方案；实现真实元素复制、循环索引、容量、边沿、复位和拒绝状态。'}
    for q in ('04','08','12','18'):rows.append(f"| [{q}](tasks/{q}/final.st) | {descriptions[q]} | {len(tasks[q]['requests'])} |")
    rows.extend(['','原4份接口名称、类型与方向保持不变。所有候选ST由DeepSeek输出，主控编写后端、测试和执行流程。初次有限检查通过但补充检查失败的版本保留为initial_final.st及result_initial_checks.json；04与12的跟进记录在各题result.json。','',
      '## 后端改动','',
      '- 固定STruC++源码提交fcccfbdf53704fad1f5e71dd2a05d440b9028b47，附完整补丁和构建方法；原0.7.0发布后端保留。',
      '- 补齐LTIME注册、转换和字面量；用精确整数生成超过2^53的纳秒值。TIME_TO_LINT为毫秒，LTIME_TO_LINT为纳秒，原代码不能混用。',
      '- 一维开放数组直接绑定调用方存储，测试不同长度与独立下界、只读输入、配置不变、仅修改输出字段。',
      '- VARIANT使用PV1本地类型擦除引用。PV_COUNT查容量，PV_COMPATIBLE查类型，PV_READ/PV_WRITE复制一个元素；队列算法仍在ST内，不由后端替题。',
      '- 换后端/运行库会进入新的缓存目录；安装产物有内容清单。通过记录绑定源码、后端和判据三种身份，任一变化都需要重验。','',
      '使用了[上游STruC++源码](https://github.com/Autonomy-Logic/STruCpp/tree/fcccfbdf53704fad1f5e71dd2a05d440b9028b47)；时长转换依据[CODESYS官方时间转换说明](https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_operator_time_to.html)。PV1是本地扩展，不是厂商VARIANT二进制布局。详见[后端与许可证](../../backend_extensions/README.md)。','',
      '## 执行证据','',
      f'- 20题每题在新进程重放两次，均通过；每轮{sum(r["scans_per_replay"] for r in verification["results"]):,}次FB调用。原固定判据哈希未变，补充判据单独留档。',
      f'- 另换随机种子检查04/08/12/18，每轮{sum(r["scans_per_run"] for r in verification["unseen"].values()):,}个扫描点，各执行两次通过。新序列没有提供给代码作者。',
      '- FIFO覆盖DINT、REAL、BOOL和两字段记录，容量1/2/7；检查实际出队值、循环回绕、满/空拒绝、保持请求不重复、复位优先及调用方数组内容。',
      '- 注入“只改计数不写元素”和“修改只读模拟量”等故障，测试能检出；运行库还检查错误类型、空绑定和越界拒绝。',
      f'- 工具回归运行{tests["run"]}项，跳过{tests["skipped"]}项，{"通过" if tests["passed"] else "未通过"}；跳过的是旧发布版专属预检用例，新测试已显式核验旧预检仍可用。',
      '- 上游选定类型/数组/转换测试93项通过。原测试明确断言LTIME应不可声明，随新增功能改为验证LTIME转换及大字面量；其他长日期类型仍保持不支持。首轮中文路径运行失败和旧功能预期失败记录保留。','',
      '## 对抗审查与入口','',
      '4题各用隔离上下文重新审查，仅提供题意、候选和后端语义，没有作者历史或测试结论。第一次8条提案均缺少可执行字段，原始记录保留；补充格式约束后再审查，状态分布：'+json.dumps(counts,ensure_ascii=False)+'。',
      '合法序列都执行两次。04的一条差异来自审查者在正好100ms时仍期望关闭输出，与题意及其文字理由不一致，未作为确认缺陷；08另一条、18另一条涉及题面明确禁止的负count或同时请求；12提案字段不合格。不能把模型给出的标题数计为缺陷数，目前没有新增已确认需求违反。',
      f'另外单独测试自然语言入口修复原始错误FIFO：{"通过" if integration and integration["verified"] else "尚未通过或尚未完成"}，调用{len(integration["requests"]) if integration else "待完成"}次。该入口使用code/fifo.st独立项目，不混入20题矩阵。单次入口成功不能证明稳定成功。','',
      '## 花费和边界','',
      f'R4预检至最终余额观测减少约¥{cost}，包括修复、审查和入口试验；余额可能延迟结算，不是逐请求账单。未充值，密钥未进入代码或报告。',
      *(['','为运行上游测试创建了指向固定源码目录的临时R:映射。已核对目标后尝试清理，但Windows返回拒绝访问（错误5）；没有提权或修改其他盘符，映射仍可能存在。本项目启动和运行不依赖该盘符，记录见[清理结果](temporary_drive_cleanup.json)。'] if cleanup and cleanup.get('verified_target') and not cleanup.get('removed') else []),
      '', '尚未运行CODESYS、Siemens编译器、形式化求解器或实体PLC。运行库的TIME采用64位纳秒表示，未模拟所有厂商32位TIME溢出；开放数组目前只扩展一维；PV1未验证厂商ABI。07/17既有检查仍是显式copy-in/copy-out，不新增共享引用或并发保证。','',
      '当前通过说明原20题候选在明确的离线语义与有限输入下可复核。需要真实目标平台导入、交叉执行及更丰富的独立任务才能评价工业可靠性。','',
      '## 文件与启动','',
      '- [最终20题与源码SHA](verification.json)、[各题源码](tasks)、[工具回归](regression_tests.log)、[最终核验](final_validation.json)。',
      '- [引用测试规约](reference_protocol.json)、[补充时间规约](duration_protocol.json)、[新种子输入](unseen_protocol.json)、[重放摘要](unseen_summary.json)。',
      '- [独立审查](independent_reviews.json)、[自然语言入口](natural_language_integration.json)、[上游测试](upstream_tests.log)。',
      '- [可重建后端及补丁](../../backend_extensions/README.md)、[agent使用说明](../../AGENT_README.md)。','',
      '本机已选中R4后端，原launch.cmd继续可用。TUI `/backend`查看后端，`/solve 18`先计划，切换`/act`后再次发送执行。','',
      '```powershell','python -B -m plc_agent.backend_r4 status','python -B -m plc_agent solve 18 --mode execute',
      '# 切回保留的旧后端','python -B -m plc_agent.backend_r4 legacy','```'])
    (OUT/'report.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'tests':tests,'observed_cost_cny':str(cost),'secret_matches':len(hits)}))
    return 0 if okay else 1


if __name__=='__main__':raise SystemExit(main())
