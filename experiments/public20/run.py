"""Run/restart a frozen public20 matrix with a common metered checker/relay.

Usage: python -m experiments.public20.run --ids 03,20 --run-id readiness
       python -m experiments.public20.run --ids all --run-id full --workers 2
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plc_agent.bank_contracts import block, protocol, questions
from plc_agent.storage import atomic_json
from .service import start_service, OPTIONS, PRICES, PRICE_SOURCES

SETTINGS = {name: {'framework': framework, 'model': model}
            for framework, prefix in [('codex', 'codex'), ('self', 'self')]
            for label, model in [('deepseek','deepseek-flash'),('qwen','qwen3.8-flash')]
            for name in [prefix+'-'+label]}
SETTINGS['self-qwen-max'] = {'framework': 'self', 'model': 'qwen3.8-max'}
SETTINGS['codex-qwen-max'] = {'framework': 'codex', 'model': 'qwen3.8-max'}
FORMAL_SETTINGS = ['codex-deepseek','codex-qwen-max','self-deepseek','self-qwen-max']
CODEX = ROOT / '.runtime/codex-0.80/node_modules/.bin/codex.cmd'


def safe_name(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', value):
        raise ValueError('Use a simple run/campaign name containing letters, digits, _ or -')
    return value


def code_hashes():
    paths = [*ROOT.glob('plc_agent/*.py'), *ROOT.glob('plc_probe/*.py'),
             *ROOT.glob('experiments/public20/*.py'), *ROOT.glob('scripts/codesys*.py')]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def environment():
    env = os.environ.copy()
    tools = json.loads((ROOT/'.runtime/toolchain.json').read_text(encoding='utf-8'))
    env['PATH'] = os.pathsep.join([*tools['path'],env.get('PATH','')])
    env['CXX'] = tools['cxx']
    env['PYTHONUTF8'] = '1'
    return env


def check_script(url, task_id):
    return f'''$ErrorActionPreference = 'Stop'
try {{
    $body = [IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'candidate.st'))
    $r = Invoke-RestMethod -Uri '{url}/check/{task_id}' -Method Post -Body $body -ContentType 'text/plain; charset=utf-8' -TimeoutSec 300
    $r | ConvertTo-Json -Depth 40
    if ($r.status -eq 'pass') {{ exit 0 }} else {{ exit 1 }}
}} catch {{
    'CHECKER_TRANSPORT_ERROR'
    exit 2
}}
'''


POLICY = '''Automatic tasks must preserve every required interface name, type, and direction.
Q04/Q12 use invocation-consistent time: CycleTime equals time since the previous invocation. Q04 first scan CycleTime=0; eligible debounce trigger starts elapsed=0. Runtime accumulates current CycleTime only when the current output runs, including the first running scan.
Q12 hold: a rising valid fault starts elapsed=0. Following invocations add CycleTime. With trigger at 10ms, interval 10ms, alarm remains at 500ms and may clear at 510ms. Invalid thickness clears alarm hold. Runtime accumulates CycleTime on each valid running scan.
Q20 v2 sampling: each observation pairs current inputs with post-invocation outputs. Automatic actions may respond on the triggering scan or the following scan. Motor mutual exclusion holds every scan. The question does not specify kick pulse duration/reset, so no particular duration/reset is scored.
The completion conditions are static validity, actual CODESYS target compilation, and finite offline behavior checks. Finite tests are not a formal proof or a CODESYS runtime execution.
Preserve functionality; do not use placeholders, constant fake outputs, narrowed types, altered tests, or invented unavailable helper APIs.
'''


def run_task(service, url, output, run_id, campaign_name, setting, qid, timeout):
    start = time.monotonic()
    cfg = SETTINGS[setting]
    task = service.register({'question_id':qid,'setting':setting,'model':cfg['model'],'timeout':timeout,'policy':POLICY,
                             'evidence':str(output/'evidence'/setting/qid)})
    evidence = Path(task['evidence'])
    requirement = next(q['text'] for q in questions() if q['id']==qid)
    (evidence/'requirements.md').write_text(requirement,encoding='utf-8')
    from plc_agent.validation import ValidationConfig, ValidationPipeline
    shared_policy=POLICY+'\nBackend compatibility:\n'+'\n'.join(ValidationPipeline(ValidationConfig.load(),ROOT/'agent_data').notes())
    (evidence/'policy.md').write_text(shared_policy,encoding='utf-8')
    timed_out, code, receipt, provider_events = False, None, None, []
    agent_seconds = 0.
    if not task['preflight']:
        env = environment()
        if cfg['framework']=='codex':
            workspace = Path(os.environ.get('TEMP',str(ROOT)))/'plc-baseline'/campaign_name/run_id/setting/qid
            if workspace.exists():
                raise ValueError('Refusing to overwrite existing Codex workspace: '+str(workspace))
            workspace.mkdir(parents=True)
            home=ROOT/'.runtime/public20/codex-home'/task['task_id']
            home.mkdir(parents=True)
            (home/'config.toml').write_text(f'''model = "{cfg['model']}"
model_provider = "experiment"
approval_policy = "never"
sandbox_mode = "workspace-write"
model_context_window = 128000
[model_providers.experiment]
name = "Metered local LiteLLM relay"
base_url = "{url}/v1"
env_key = "PLC_EXPERIMENT_LOCAL_KEY"
wire_api = "responses"
request_max_retries = 0
stream_max_retries = 0
http_headers = {{ "X-Experiment-Task" = "{task['task_id']}" }}
''',encoding='utf-8')
            env['CODEX_HOME']=str(home);env['PLC_EXPERIMENT_LOCAL_KEY']='sk-experiment-local'
            (workspace/'requirements.md').write_text(requirement,encoding='utf-8')
            (workspace/'policy.md').write_text(shared_policy,encoding='utf-8')
            (workspace/'check.ps1').write_text(check_script(url,task['task_id']),encoding='utf-8')
            prompt=f'''Work only inside this task directory. Do not read files outside it or search for reference solutions.
Read requirements.md and policy.md. Implement the complete FUNCTION_BLOCK {block(qid)} ... END_FUNCTION_BLOCK in candidate.st, including required TYPE definitions. Use exactly the specified interface.
Write files with PowerShell Set-Content/WriteAllText or here-strings; apply_patch in this external Windows workspace may be rejected by the CLI's separate path policy.
{shared_policy}
After each source version run: powershell -NoProfile -ExecutionPolicy Bypass -File check.ps1
Real CODESYS checking can take 120 seconds. Give the execution tool a timeout of at least 300000 ms; a short tool wait is not a candidate failure.
Use checker diagnostics to repair your own ST. Never edit requirements.md, policy.md or check.ps1.
There are at most 6 submitted source versions (initial candidate plus 5 repairs), 24 model requests and {timeout} seconds. Stop on pass, platform/environment errors, or any budget limit. Rechecking identical source does not add a version.
Finish with the status and a short explanation. Do not claim success without checker evidence.
'''
            (workspace/'prompt.txt').write_text(prompt,encoding='utf-8')
            cmd=['cmd','/c',str(CODEX),'exec','-C',str(workspace),'--skip-git-repo-check','-s','workspace-write',
                 '--json','-o',str(workspace/'final.txt'),'-']
            input_text=prompt
        else:
            home=ROOT/'.runtime/public20/self-home'/task['task_id']
            home.mkdir(parents=True)
            env['PLC_AGENT_HOME']=str(home)
            backend_profile=ROOT/'agent_data/backend.json'
            if backend_profile.exists():shutil.copy2(backend_profile,home/'backend.json')
            workspace=None
            cmd=[sys.executable,'-X','utf8','-B','-m','experiments.public20.self_worker',
                 '--task',str(evidence/'task.json'),'--url',url]
            input_text=None
        proc=subprocess.Popen(cmd,cwd=str(ROOT if workspace is None else workspace),env=env,
                              stdin=subprocess.PIPE if input_text else subprocess.DEVNULL,
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace')
        try:
            stdout,stderr=proc.communicate(input=input_text,timeout=max(1,task['deadline']-time.time()))
        except subprocess.TimeoutExpired:
            timed_out=True
            subprocess.run(['taskkill','/F','/T','/PID',str(proc.pid)],capture_output=True)
            stdout,stderr=proc.communicate(timeout=30)
        agent_seconds=round(time.monotonic()-start,3)
        (evidence/'agent.log').write_text(stdout+'\n'+stderr,encoding='utf-8')
        if cfg['framework']=='self':
            try:
                parsed=json.loads(stdout)
                receipt=parsed['receipt'];workspace=Path(parsed['workspace'])
                atomic_json(evidence/'receipt.json',receipt)
                run=workspace/receipt['run_path']
                shutil.copytree(run,evidence/'workflow_run')
            except (ValueError,KeyError):
                pass
        else:
            for line in stdout.splitlines():
                try:event=json.loads(line)
                except ValueError:continue
                if event.get('type') in ('error','turn.failed'):
                    provider_events.append(event.get('message') or event.get('error'))
        if workspace:
            candidate=workspace/'candidate.st'
            if candidate.is_file():
                code=candidate.read_bytes()
                (evidence/'candidate.st').write_bytes(code)
            for name in ('prompt.txt','check.ps1','final.txt'):
                if (workspace/name).is_file():shutil.copy2(workspace/name,evidence/name)
        exit_code=proc.returncode
    else:
        exit_code=None
    # Final assessment is included in total time. It reuses the identical source
    # record, or submits an unchecked final source under the same hard limit.
    final=task['preflight'] or (service.check(task['task_id'],code) if code else {'status':'missing_candidate'})
    submissions=task['submissions']
    calls=[c for c in service.ledger['calls'] if c['task_id']==task['task_id']]
    last=submissions[-1] if submissions else {}
    first=submissions[0] if submissions else {}
    latest_result=json.loads(Path(last['result']).read_text(encoding='utf-8')) if last else {}
    provider_error_count=sum(c['state']=='provider_error' for c in calls)
    relay_errors=task.get('relay_errors',[])
    status=(task['preflight']['status'] if task['preflight'] else 'task_timeout' if timed_out else
            'pass' if final.get('status')=='pass' else 'campaign_budget_exhausted' if 'campaign_budget_exhausted' in relay_errors else
            'provider_error' if (provider_error_count or provider_events) and not submissions else final.get('status'))
    usage=[c['usage'] for c in calls if c.get('usage')]
    row={'setting':setting,'framework':cfg['framework'],'model':cfg['model'],'question_id':qid,
         'status':status,'final_status':final.get('status'),'final':final,
         'source_versions':len(submissions),'repairs':max(0,len(submissions)-1),
         'model_requests':len(calls),'provider_errors':provider_error_count,'provider_events':provider_events,
         'relay_errors':relay_errors,'served_models':sorted(set(c.get('served_model',c['model']) for c in calls)),
         'first_compile_status':first.get('stages',{}).get('codesys','not_measured'),
         'final_compile_status':last.get('stages',{}).get('codesys','not_measured'),
         'first_behavior_status':first.get('stages',{}).get('behavior','not_measured'),
         'final_behavior_status':last.get('stages',{}).get('behavior','not_measured'),
         'behavior_summary':latest_result.get('summary'),
         'input_tokens':sum(u['input_tokens'] for u in usage) if len(usage)==len(calls) else None,
         'output_tokens':sum(u['output_tokens'] for u in usage) if len(usage)==len(calls) else None,
         'cached_input_tokens':sum(u['cached_input_tokens'] for u in usage) if len(usage)==len(calls) else None,
         'usage_complete':len(usage)==len(calls),
         'agent_source_sha256':hashlib.sha256(code).hexdigest() if code else None,
         'assessed_source_sha256':last.get('source_sha256'),
         'accounted_upper_cny':sum(c.get('charged_cny',c['reserved_cny']) for c in calls),
         'timed_out':timed_out,'agent_seconds':agent_seconds,'total_seconds':round(time.monotonic()-start,3),
         'exit_code':exit_code,'evidence':str(evidence),'task_id':task['task_id'],**service.identity}
    atomic_json(evidence/'result.json',row)
    return row


def write_summary(output, rows, manifest, service):
    groups={name:{'tasks':sum(r['setting']==name for r in rows),
                  'first_compile_pass':sum(r['setting']==name and r['first_compile_status']=='pass' for r in rows),
                  'final_compile_pass':sum(r['setting']==name and r['final_compile_status']=='pass' for r in rows),
                  'test_task_pass':sum(r['setting']==name and r['status']=='pass' for r in rows),
                  'platform_blocked':sum(r['setting']==name and r['status']=='platform_blocked' for r in rows)}
            for name in manifest['settings']}
    atomic_json(output/'summary.json',{'manifest':manifest,'groups':groups,'budget':service.budget(),'rows':rows})
    columns=['setting','question_id','status','first_compile_status','final_compile_status','final_behavior_status',
             'source_versions','repairs','model_requests','provider_errors','input_tokens','output_tokens','usage_complete',
             'accounted_upper_cny','timed_out','total_seconds']
    with (output/'results.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    lines=['# Public20四组实验', '',f"已记录 {len(rows)}/{len(manifest['ids'])*len(manifest['settings'])} 个任务运行。",
           '','CODESYS编译与有限离线行为分开统计；分母包含平台阻塞题。费用按冻结的高峰标价核算上界，不是账户账单。',
           '', '| 条件 | 已记录 | 首次编译通过 | 最后候选编译通过 | 整题测试通过 | 平台阻塞 |',
           '|---|---:|---:|---:|---:|---:|']
    for name,g in groups.items():lines.append(f"| {name} | {g['tasks']} | {g['first_compile_pass']} | {g['final_compile_pass']} | {g['test_task_pass']} | {g['platform_blocked']} |")
    lines += ['', '详细结果见results.csv、summary.json和evidence/；每版源码与实际检查保存在submissions/。',
              '', '预算状态：'+json.dumps(service.budget(),ensure_ascii=False)]
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ids',default='03,20')
    parser.add_argument('--settings',default='all')
    parser.add_argument('--campaign',default='public20_20261027')
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--budget-cny',type=float,default=10.)
    parser.add_argument('--workers',type=int,choices=(1,2),default=2)
    parser.add_argument('--timeout',type=int,default=900)
    parser.add_argument('--port',type=int,default=8767)
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    safe_name(args.campaign);safe_name(args.run_id)
    ids=[q['id'] for q in questions()] if args.ids=='all' else [x.strip().zfill(2) for x in args.ids.split(',')]
    settings=FORMAL_SETTINGS if args.settings=='all' else args.settings.split(',')
    if len(ids)!=len(set(ids)) or any(x not in {q['id'] for q in questions()} for x in ids):parser.error('invalid/duplicate ids')
    if len(settings)!=len(set(settings)) or any(x not in SETTINGS for x in settings):parser.error('invalid/duplicate settings')
    if not 0<args.budget_cny<=50:parser.error('authorized NEW campaign limit is at most CNY50')
    campaign=ROOT/'reports/experiments'/args.campaign
    output=campaign/args.run_id
    if output.exists() and not args.resume:parser.error('run exists; choose a new run id or explicitly resume')
    service,server=start_service(campaign,args.budget_cny,args.port)
    url=f'http://127.0.0.1:{args.port}'
    manifest={'schema':'public20-matrix-v3','ids':ids,'settings':settings,'timeout':args.timeout,
              'max_candidates':6,'max_repairs':5,'max_model_calls':24,
              'max_output_tokens':int(os.environ.get('PLC_EXPERIMENT_MAX_OUTPUT','16384')),
              'workers':args.workers,'code_hashes':code_hashes(),'identity':service.identity,'policy':POLICY,
              'upstream_timeout':int(os.environ.get('PLC_EXPERIMENT_UPSTREAM_TIMEOUT','180')),
              'provider_timeout':int(os.environ.get('PLC_EXPERIMENT_PROVIDER_TIMEOUT','180')),
              'thinking_note':'DeepSeek thinking low when enabled; Qwen Max thinking configured separately, equal across frameworks.',
              'model_options':OPTIONS,'prices_cny_per_million':PRICES,'price_sources':PRICE_SOURCES}
    output.mkdir(parents=True,exist_ok=True)
    if (output/'manifest.json').exists():
        if json.loads((output/'manifest.json').read_text(encoding='utf-8'))!=manifest:
            raise ValueError('Manifest mismatch: resume requires the exact frozen code/config/protocol')
    else:
        atomic_json(output/'manifest.json',manifest)
        atomic_json(output/'test_protocol.json',protocol())
        atomic_json(output/'questions.json',questions())
    rows=[json.loads(x) for x in (output/'results.jsonl').read_text(encoding='utf-8').splitlines()] if (output/'results.jsonl').exists() else []
    done={(r['setting'],r['question_id']) for r in rows}
    jobs=[(name,qid) for qid in ids for name in settings if (name,qid) not in done]
    # Incomplete pre-crash evidence is preserved. An explicit resume uses a new
    # attempt directory only for cells without a completed result row.
    for name,qid in jobs:
        existing=output/'evidence'/name/qid
        if existing.exists():
            parser.error('Incomplete evidence exists; preserve it and use a new run id for the interrupted cells')
    print(json.dumps({'output':str(output),'pending':len(jobs),'budget':service.budget()},ensure_ascii=False),flush=True)
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures={pool.submit(run_task,service,url,output,args.run_id,args.campaign,name,qid,args.timeout):(name,qid) for name,qid in jobs}
            for future in as_completed(futures):
                name,qid=futures[future]
                try:row=future.result()
                except Exception as exc:
                    raise RuntimeError(f'{name}/{qid}: {type(exc).__name__}: {exc}') from exc
                rows.append(row)
                with (output/'results.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
                write_summary(output,rows,manifest,service)
                print(json.dumps({k:row[k] for k in ['setting','question_id','status','source_versions','model_requests','total_seconds']},ensure_ascii=False),flush=True)
                print('budget',service.budget(),flush=True)
    finally:
        write_summary(output,rows,manifest,service)
        server.shutdown();server.server_close()
    return 0


if __name__=='__main__':raise SystemExit(main())
