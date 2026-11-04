"""结果输出：统一目录、详细日志、指标计算和运行摘要。"""
from datetime import datetime, timezone, timedelta
import csv
import json
from pathlib import Path
import re
import threading
from plc_agent.config import ROOT, STATE_ROOT
from plc_agent.storage import atomic_json
from plc_agent.ltl_adapter import property_count

_lock=threading.RLock()
LOCAL_TIME=timezone(timedelta(hours=8))
STATUS_LABELS={'pass':'测试通过','finite_pass':'功能测试通过','compiled_without_tests':'仅编译通过，未提供测试',
 'compile_error':'编译失败','fail':'功能测试失败','runtime_error':'程序执行失败','formal_blocked':'形式化反例待复核',
 'bounded_pass':'在扫描上界内通过','bounded_inconclusive':'未得到确定结论','unsupported':'当前不支持','unsupported_model':'缺少验证模型',
 'not_executed':'未执行','not_started':'尚未开始','timeout':'超时','interrupted':'已取消','tool_error':'工具错误',
 'agent_error':'模型或流程错误','task_error':'任务错误','invalid_candidate':'源码不符合要求','missing_dependency':'缺少依赖',
 'no_progress':'修改无进展','revision_limit':'达到版本上限','model_call_limit':'达到请求上限',
 'compile_passed':'目标编译通过','compile_failed':'目标编译失败','generation_failed':'生成块失败',
 'probe_passed':'编译器正负对照通过','probe_failed':'编译器正负对照失败',
 'behavior_not_configured':'原生仿真未配置','behavior_not_supported':'当前行为模型不支持',
 'simulation_error':'仿真执行错误','harness_error':'测试驱动错误','bridge_protocol_error':'Bridge 协议错误',
 'formal_probe_passed':'形式化对照符合预期','formal_probe_failed':'形式化对照未通过'}

def status_label(value):return STATUS_LABELS.get(value,value or '未记录')

def valid_run_id(value):
    return isinstance(value,str) and bool(re.fullmatch(r'(?:[a-f0-9]{32}|\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(?:_[A-Za-z0-9_-]+)?)',value))

def reserve_run(parent,suffix='',when=None):
    parent=Path(parent);parent.mkdir(parents=True,exist_ok=True)
    base=(when or datetime.now(LOCAL_TIME)).strftime('%Y-%m-%d_%H-%M-%S')
    if suffix:base+='_'+re.sub(r'[^A-Za-z0-9_-]','_',suffix)[:60]
    for number in range(1,10000):
        name=base if number==1 else base+f'_{number:02d}'
        path=parent/name
        try:path.mkdir();return path
        except FileExistsError:continue
    raise ValueError('Too many runs with the same timestamp')

def details_path(path):
    path=Path(path)
    return path/'details' if (path/'details').is_dir() else path

def trial_path(path,record,framework,model_index,task_index):
    if record.get('layout_version')==2:
        task_id=record['task_ids'][task_index].split('__')[-1]
        name=f'{task_index+1:02d}_'+re.sub(r'[^A-Za-z0-9_-]','_',task_id)
        return Path(path)/'tasks'/name/(framework+'_'+chr(65+model_index))
    return Path(path)/framework/str(model_index)/str(task_index)

def log_path(directory):
    directory=Path(directory)
    return (directory.parent if directory.name=='details' else directory)/'run.log'

def failure_reason(receipt):
    result=receipt.get('final_evaluation') or receipt
    message=receipt.get('message') or result.get('message')
    if not message:
        diagnostics=result.get('diagnostics') or (result.get('codesys') or {}).get('diagnostics')
        if diagnostics:message=diagnostics[0]
    if not message and result.get('counterexample'):
        item=result['counterexample'];message='测试反例：'+str(item.get('name',''))+' '+str(item.get('first_failure',''))
    if not message:message=status_label(result.get('status',receipt.get('status','未记录')))
    return str(message).replace('\n',' ')[:1000]

def write_campaign_summary(path,record):
    path=Path(path)
    states={'running':'运行中','pausing':'正在暂停，等待当前任务结束','paused':'已暂停，可继续','stopping':'正在结束','interrupted':'已结束，未完成任务取消','completed':'已完成','error':'运行出错'}
    lines=['# 批量实验',f"开始时间：{record.get('started_at',record['id'])}",
           f"状态：{states.get(record['status'],record['status'])}",f"目标平台：{record.get('target','codesys')}",
           f"已结束任务：{record.get('completed',0)}/{record['total']}（包括通过、失败和取消）",
           f"模型 A：{record['models'][0]}；模型 B：{record['models'][1]}",
           f"同时运行任务数：{record.get('concurrency',1)}",'',
           '先看 results.csv 的逐题结果和失败原因；每题摘要在 tasks/题目/框架_模型/SUMMARY.md。',
           '配置、题目快照、结构化指标和工具检查放在 details/。关闭网页后记录仍保留。','',
           '| 框架 / 模型 | 已结束 | 编译通过 | 功能任务通过 | 测试场景通过 | 有界LTL性质通过 |',
           '|---|---:|---:|---:|---:|---:|']
    for row in record.get('summary',[]):
        lines.append(f"| {row['framework']} / {row['model']} | {row['completed']} | {row.get('target_compiled',row.get('codesys_compiled',0))} | {row.get('passed',0)} | {row.get('test_cases_passed',0)}/{row.get('test_cases_total',0)} | {row.get('formal_properties_verified',0)}/{row.get('formal_properties_total',0)} |")
    if record.get('message'):lines+=['',record['message']]
    lines+=['','功能测试通过与形式化通过分别统计。LTL结论仅针对记录的扫描上界和假设。']
    (path/'SUMMARY.md').write_text('\n'.join(lines),encoding='utf-8')
    # Atomic replacement lets a reader inspect the table while tasks finish.
    import io
    output=io.StringIO(newline='');writer=csv.writer(output)
    writer.writerow(['题目','框架','模型','结果','状态代码','编译','测试通过','测试总数','LTL通过','LTL总数','原因','文件夹'])
    by_key={(r['framework'],r['model'],r['task_id']):r for r in record.get('results',[])}
    for index,ident in enumerate(record['task_ids']):
        for framework in ('self','codex'):
            for model_index,model in enumerate(record['models']):
                row=by_key.get((framework,model,ident),{});m=row.get('metrics_summary') or {}
                folder=trial_path(path,record,framework,model_index,index)
                writer.writerow([ident.split('__')[-1],framework,model,status_label(row.get('status','not_started')),row.get('status','not_started'),row.get('target_compile','not_executed'),m.get('test_cases_passed',''),m.get('test_cases_total',''),m.get('formal_properties_verified',''),m.get('formal_properties_total',''),failure_reason(row) if row else '尚未开始',str(folder.relative_to(path))])
    temporary=details_path(path)/'results.csv.tmp';temporary.write_text(output.getvalue(),encoding='utf-8-sig')
    try:temporary.replace(path/'results.csv')
    except PermissionError:pass  # Excel may hold the previous table open.

def output_root(home=STATE_ROOT):
    home=Path(home).resolve()
    return ROOT/'outputs' if home==STATE_ROOT else home/'outputs'

def event(directory, stage, **data):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    record={'time':datetime.now(timezone.utc).isoformat(),'stage':stage,**data}
    with _lock:
        with (directory/'events.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(record,ensure_ascii=False,default=str)+'\n')
        with log_path(directory).open('a',encoding='utf-8') as stream:
            stream.write(f"{record['time']} [{stage}] "+json.dumps(data,ensure_ascii=False,default=str)+'\n')

def metrics(result, task=None):
    result=result or {};formal=result.get('formal_verification') or {}
    summary=result.get('summary') or {}
    cases=summary.get('scenarios')
    failed=summary.get('failed')
    if result.get('test_backend')=='tia' and result.get('behavior_tested') is False:
        cases=failed=None  # Invalid native timing/transport cannot count as test passes.
    total=len(task.get('scenarios',[])) if task is not None else cases
    return {'target_platform':result.get('target','codesys'),
            'target_compile':result.get('target_compile','not_executed'),
            'codesys_compile':result.get('target_compile','not_executed') if result.get('target')!='tia' else 'not_executed',
            'test_cases_total':total,'test_cases_executed':cases or 0,
            'test_cases_not_executed':max(0,(total or 0)-(cases or 0)),
            'test_cases_passed':cases-failed if cases is not None and failed is not None else None,
            'test_case_pass_rate':(cases-failed)/total if total and cases is not None and failed is not None else None,
            'finite_test_status':result.get('finite_test_status',result.get('status','not_executed')),
            'formal_status':formal.get('status','not_executed'),
            'formal_backend':formal.get('backend'),
            'formal_unwind':formal.get('unwind'),
            'formal_unwind_complete':formal.get('unwind_complete'),
            'formal_valid_domain_witness':formal.get('valid_domain_witness'),
            'mapped_assertions_total':formal.get('mapped_assertions_total',0),
            'mapped_assertions_proved':len(formal.get('proved_property_ids',[])),
            'declared_ltl_total':formal.get('declared_ltl_total',property_count((task or {}).get('ltl',{}))),
            'formal_full_ltl_proved':False,
            'formal_bound':formal.get('bound'),
            'formal_properties_verified':len(formal.get('bounded_verified_property_ids',[])),
            'formal_properties_total':formal.get('declared_ltl_total',property_count((task or {}).get('ltl',{}))),
            'formal_properties_executed':sum(p.get('status') in ('bounded_pass','counterexample','bounded_inconclusive') for p in formal.get('properties',[])),
            'formal_properties_unsupported':sum(p.get('status') in ('unsupported','unsupported_model') for p in formal.get('properties',[])),
            'formal_counterexamples':sum(p.get('status')=='counterexample' for p in formal.get('properties',[])),
            'formal_property_pass_rate':len(formal.get('bounded_verified_property_ids',[]))/formal['declared_ltl_total'] if formal.get('declared_ltl_total') else None,
            'formal_all_properties_verified':formal.get('bounded_all_properties_verified',False),
            'scope':'Formal pass counts apply only to the reported scan bound and assumptions; not an infinite-scan proof.'}

def finish(directory, receipt, task=None):
    directory=Path(directory)
    visible=directory.parent if directory.name=='details' else directory
    result={**(receipt.get('final_evaluation') or receipt),
            'target':receipt.get('target',(receipt.get('final_evaluation') or receipt).get('target','codesys'))}
    suffix='.scl' if result['target']=='tia' else '.st'
    receipt['metrics_summary']=metrics(result,task)
    receipt['output_path']=str(visible.resolve())
    event(directory,'finished',status=receipt.get('status'),metrics=receipt['metrics_summary'],
          model_calls=receipt.get('model_calls'),token_usage=receipt.get('token_usage'),seconds=receipt.get('seconds'))
    atomic_json(Path(directory)/'metrics.json',receipt['metrics_summary'])
    atomic_json(Path(directory)/'receipt.json',receipt)
    m=receipt['metrics_summary']
    lines=['# 运行结果',f"题目：{receipt.get('task_id','').split('__')[-1]}",f"模型：{receipt.get('model','未记录')}",
           f"状态：{status_label(receipt.get('status'))}（{receipt.get('status')}）",f"原因 / 说明：{failure_reason(receipt)}",'',
           f"编译（{'TIA Portal' if result['target']=='tia' else 'CODESYS'}）：{m['target_compile']}",f"功能测试：{m['test_cases_passed'] if m['test_cases_passed'] is not None else '未执行'} / {m['test_cases_total'] if m['test_cases_total'] is not None else '未提供'}",
           f"形式化：{status_label(m['formal_status'])}；界内通过 {m['formal_properties_verified']} / {m['formal_properties_total']}；扫描上界 {m['formal_bound'] if m['formal_bound'] is not None else '未执行'}",
           f"模型请求：{receipt.get('model_calls',0)}；耗时：{receipt.get('seconds','未记录')} 秒",'',
           f'final{suffix}：最终代码。run.log：按时间记录的生成、修改与检查过程。',
           'details/：完整JSON结论、逐次请求、各版源码及验证工具证据。' if directory.name=='details' else '完整结论见 receipt.json，指标见 metrics.json，各版代码见 submissions/。',
           '形式化结论仅针对记录的扫描上界和假设，不代表无限扫描证明。']
    (visible/'SUMMARY.md').write_text('\n'.join(lines),encoding='utf-8')
    if directory.name=='details' and (directory/('candidate'+suffix)).exists():
        (visible/('final'+suffix)).write_bytes((directory/('candidate'+suffix)).read_bytes())
    return receipt
