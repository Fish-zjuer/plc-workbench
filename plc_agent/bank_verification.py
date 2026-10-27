"""Post-run replay and explicitly limited human adjudication of review claims."""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path

from plc_probe.backend import compile_source,run_batch
from .bank_contracts import questions
from .bank_runner import test_bank
from .benchmark import RUN_ROOT
from .storage import atomic_json


def main():
    data=json.loads((RUN_ROOT/"results.json").read_text(encoding="utf-8"))
    frozen=json.loads((RUN_ROOT/"test_protocol.json").read_text(encoding="utf-8"))
    root=RUN_ROOT.parents[1]
    hashes={name:hashlib.sha256((root/name).read_bytes()).hexdigest()==digest for name,digest in frozen['implementation_sha256'].items()}
    if not all(hashes.values()):
        raise RuntimeError("Evaluation code changed")
    replays=[]
    for task in data['results']:
        if task['final'].get('behavior_tested'):
            source=RUN_ROOT/'tasks'/task['id']/'final.st'
            runs=[test_bank(source,task['id']) for _ in range(2)]
            path=RUN_ROOT/'tasks'/task['id']/'fresh_replays.json'
            atomic_json(path,{'source_sha256':task['final_source_sha256'],'runs':runs,
                              'note':'Exact frozen finite tests, separate fresh execution processes per run; no sparse-assertion minimization'})
            replays.append({'id':task['id'],'statuses':[r['status'] for r in runs],
                            'first_failures':[r.get('first_failure') for r in runs],
                            'matches_recorded':all(r['status']==task['final']['status'] for r in runs),'evidence':str(path)})
    # An independently specified rolling-window trace refutes the reviewer's
    # claim that replacing the oldest slot is inherently incorrect.
    average=RUN_ROOT/'tasks/09/final.st'
    trace=[{'time_ms':i,'inputs':{'cyclicExecution':1,'trigger':0,'value':v,'windowSize':3,'reset':0}} for i,v in enumerate([1,2,3,4,5,6,7])]
    actual=run_batch(compile_source(average,'moving_average'),[{'name':'independent_review_ring_replay','trace':trace}])[0]
    ring={'scenario':{'trace':trace},'expected_averages':[1,1.5,2,3,4,5,6],
          'actual_averages':[r['actual']['average'] for r in actual['rows']],'result':actual}
    atomic_json(RUN_ROOT/'review_ring_replay.json',ring)
    adjudications=[
      ('01','REV-001','needs_requirement_clarification','题面未规定所有按钮的上升沿策略或确认按钮预先保持时的处理。评论本身承认 CASE 不会重入，不能据此确认同扫描级联。'),
      ('02','REV-001','rejected_self_refuting_claim','审查正文已自行推导首扫输出为零且符合注释，题面也未规定首扫历史。标题不能当成缺陷。'),
      ('03','REV-001','needs_requirement_clarification','负滞环宽度的允许域和处理未明确；当前有限判据未补充该需求，不能直接确认额外错误检查是缺陷。'),
      ('05','REV-001','confirmed_existing_failure','冻结测试及两次新进程复核均显示，5秒后仍停留初始化且报警不启动。此条与主测试发现的是同一个缺陷。'),
      ('05','REV-002','duplicate_of_confirmed_failure','正常监控缺失与永不结束初始化属于同一最终候选的既有失败，不增加题目失败数量。'),
      ('07','REV-001','rejected_by_code_inspection','每次调用对5个泵计算严格全序：更大优先级在前，同优先级按索引。k+1覆盖1..5全部唯一位置，rankIdx无需先清零；未宣称完成本题行为桥接。'),
      ('08','REV-001','rejected_requirement_misread','题面第7条对hiLIM<=loLIM的8002规则没有仅限线性模式的例外，不能按审查者新增的例外判错。'),
      ('08','REV-003','outside_caller_contract','题面明确caller supplies count from zero through smaller array length，负count不属于允许输入。'),
      ('09','REV-001','refuted_by_executed_probe','窗口3的1..7序列实际输出1,1.5,2,3,4,5,6，与独立重算一致，替换最老样本的笼统指控未复现。完整轨迹另存。'),
      ('09','REV-003','needs_requirement_clarification','非法窗口与reset同周期的优先级没有明确；既有契约排除了此同时事件，不直接计缺陷。'),
      ('12','REV-003','outside_caller_contract','external callers must not modify history是调用方约束。按题面将历史定义为VAR_OUTPUT不能据此认定违反要求，且本题LTIME尚未在后端执行。'),
      ('13','REV-001','needs_requirement_clarification','初始化变量与首次调用后输出的区别需明确，原题同时要求正常计算按当前输入更新。有限检查没有补定首扫adjust。'),
      ('14','REV-001','rejected_language_semantics','默认正步长FOR从0到-1执行零次，并非自动倒序循环；这项标题/推断不成立。源程序其他部分仍受离线字符串后端阻塞。'),
      ('14','REV-003','rejected_self_refuting_claim','审查者正文已自行推导段数不符时ipValue=0符合要求，没有提出反例。'),
      ('15','REV-001','rejected_language_semantics','FB输出在未赋新值时保留旧值是ST状态语义，不是随机的后端差异；本题主测试失败另为阀C启动的扫描延迟，需明确时序契约。'),
      ('16','REV-001','outside_caller_contract','原题规定非末尾活动项只能是2..4，末项是5；首目标1不属于题目承诺的输入。'),
    ]
    triage=[dict(question_id=qid,finding_id=ident,status=status,reason=reason) for qid,ident,status,reason in adjudications]
    reviews=json.loads((RUN_ROOT/'adversarial_reviews.json').read_text(encoding='utf-8'))
    before=json.loads((RUN_ROOT/'preflight.json').read_text(encoding='utf-8'))['balance']
    after=json.loads((RUN_ROOT/'balance_after_review.json').read_text(encoding='utf-8'))
    cny=lambda obj:sum(Decimal(b['total_balance']) for b in obj['balance_infos'] if b['currency']=='CNY')
    costs={'balance_before_cny':str(cny(before)),'balance_after_cny':str(cny(after)),
           'observed_account_decrease_cny':str(cny(before)-cny(after)),
           'note':'Observed account balance difference across preflight, 20-task agent run and review run; possible concurrent account activity and balance reporting delay mean this is not exact per-request billing.'}
    first=[r for r in data['results'] if r['first']['status']=='pass']
    final=[r for r in data['results'] if r['final']['status']=='pass']
    value={'frozen_evaluation_hashes_match':hashes,'fresh_replays':replays,
           'all_replays_match':all(r['matches_recorded'] for r in replays),
           'ring_probe_refuted':ring['actual_averages']==ring['expected_averages'],
           'adversarial_findings_total':reviews['counts']['hypotheses'],'selected_adjudications':triage,
           'remaining_not_individually_adjudicated':reviews['counts']['hypotheses']-len(triage),
           'known_clear_behavior_failures':['05','10'],
           'timing_contract_failure_requiring_clarification':['15'],
           'initial_pass_ids':[r['id'] for r in first],'final_pass_ids':[r['id'] for r in final],
           'final_compiled_count':sum(r['final']['status'] in ('pass','fail','behavior_not_supported') for r in data['results']),
           'final_behavior_executed_count':len(replays),'costs':costs}
    atomic_json(RUN_ROOT/'verification.json',value)
    print(json.dumps({'replayed':len(replays),'all_match':value['all_replays_match'],'review_hypotheses':reviews['counts']['hypotheses'],'costs':costs},ensure_ascii=False))


if __name__=='__main__':
    main()
