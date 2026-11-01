"""统一任务控制：管理预算、模型请求、代码提交及两个框架的对照实验。"""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime

from plc_agent import bank32
from plc_agent import codesys
from plc_agent import dataset_workflow
from plc_agent.bank32_v6 import normalize_v6
from plc_agent.codesys_dataset import evaluate_candidate
from plc_agent.config import ROOT, STATE_ROOT, ModelConfig
from plc_agent.imported_bank import ImportedBank
from plc_agent.provider import ChatProvider, ProviderError, Cancelled
from plc_agent.inference import inference_config
from plc_agent.storage import atomic_json, read_json
from plc_agent.run_output import output_root, event, finish, metrics, reserve_run, valid_run_id, details_path, trial_path, write_campaign_summary, LOCAL_TIME
from plc_agent import plcverif_backend
from plc_agent.ltl_adapter import property_count

LIMITS={'source_versions':6,'model_requests':24,'seconds':1800}


def codex_path():
    supplied=os.environ.get('PLC_CODEX_CLI')
    candidates=[Path(supplied)] if supplied else [ROOT/'.runtime/codex-0.80/node_modules/.bin/codex.cmd',
        ROOT.parent/'plc-workbench/.runtime/codex-0.80/node_modules/.bin/codex.cmd']
    return next((p.resolve() for p in candidates if p.is_file()),None)


def cli_command(path):
    path=Path(path)
    if path.suffix.lower()=='.cmd':
        # npm's cmd shim needs node on PATH and is fragile with spaced paths.
        # Prefer the exact packaged binary from the same pinned installation.
        binary=path.parent.parent/'@openai/codex/vendor/x86_64-pc-windows-msvc/codex/codex.exe'
        if binary.is_file():return [str(binary)]
        js=path.parent.parent/'@openai/codex/bin/codex.js'
        node=shutil.which('node')
        if js.is_file() and node:return [node,str(js)]
        raise ValueError('Codex package binary or Node.js is missing; repair the selected CLI installation')
    return [str(path)]


def local_proxy_bypass(environment):
    """Keep external proxy settings; send only loopback relay traffic direct."""
    result=dict(environment);hosts=[]
    for key in ('NO_PROXY','no_proxy'):
        for host in result.get(key,'').split(','):
            host=host.strip()
            if host and host.lower() not in {h.lower() for h in hosts}:hosts.append(host)
    for host in ('127.0.0.1','localhost','::1'):
        if host not in hosts:hosts.append(host)
    result['NO_PROXY']=result['no_proxy']=','.join(hosts)
    return result


def preflight(home=STATE_ROOT, require_vendor=True):
    from plc_agent.runtime_env import configure_tools
    tools=configure_tools()
    cfg=ModelConfig.load(Path(home))
    errors=[]
    try: cfg.validate()
    except ValueError as exc: errors.append(str(exc))
    if not cfg.api_key: errors.append('请先配置 DMXAPI Key')
    cli=codex_path(); version=None
    if cli:
        try: version=subprocess.check_output(cli_command(cli)+['--version'],text=True,timeout=10).strip()
        except (OSError,ValueError,subprocess.SubprocessError) as exc: errors.append('Codex CLI version check failed: '+str(exc))
    else: errors.append('未找到实验用 Codex CLI；设置 PLC_CODEX_CLI 为支持 Chat Completions 的 Codex 0.80.0 路径')
    if version and version!='codex-cli 0.80.0': errors.append('此 DMXAPI Chat 适配固定 Codex 0.80.0；当前为 '+version)
    vendor=codesys.load_config(Path(home))
    if require_vendor:
        try: codesys.validate_config(vendor)
        except ValueError as exc: errors.append(str(exc))
    from plc_probe.config import toolchain_dir
    backend=None
    if not require_vendor:
        from plc_agent.local_test_support import backend as optional_backend
        try:optional_backend()
        except Exception as exc:errors.append(str(exc))
        if not (toolchain_dir()/('strucpp.exe' if os.name=='nt' else 'strucpp')).is_file(): errors.append('本地备用 ST 编译器未配置')
        if not (os.environ.get('CXX') or shutil.which('g++')): errors.append('本地备用测试需要 g++（CXX 或 PATH）')
        try:
            from optional_local_tests.backend_r4 import info
            backend=info()
            if backend is None:errors.append('本地备用测试需要 R4 后端；先 build 再 activate')
        except (ValueError,OSError,ModuleNotFoundError) as exc:errors.append('本地备用后端校验失败: '+str(exc))
    return {'local_backend':{'home':None if require_vendor else str(toolchain_dir()),'extension':backend.get('extension') if backend else None,'fingerprint':backend.get('fingerprint') if backend else None},'status':'ready' if not errors else 'setup_required','errors':errors,
        'codex_path':str(cli) if cli else None,'codex_version':version,
        'vendor_required':require_vendor,'test_backend':'codesys' if require_vendor else 'optional_local','codesys':vendor,'limits':LIMITS,'tools':tools,'formal':plcverif_backend.environment(home)}


class Trial:
    def __init__(self,path,task,cfg,vendor,stop,formal_config=None,save_snapshots=True):
        self.path=Path(path); self.path.mkdir(parents=True,exist_ok=True)
        self.task=task;self.cfg=cfg;self.vendor=vendor;self.stop=stop
        self.formal_config=dict(formal_config) if formal_config is not None else plcverif_backend.configuration()
        self.provider=ChatProvider(replace(cfg,transport_retries=0)); self.metrics=[]
        self.calls=0;self.started=time.monotonic();self.submissions={};self.lock=threading.RLock()
        if self.path.name=='details':
            (self.path.parent/'SUMMARY.md').write_text('# 运行结果\n\n题目：'+task.get('original_id',task['id']).split('__')[-1]+'\n\n状态：运行中。过程见 run.log，完成后本页自动更新。\n',encoding='utf-8')
        if save_snapshots:
            atomic_json(self.path/'task_snapshot.json',task)
            atomic_json(self.path/'formal_config.json',self.formal_config)
        event(self.path,'started',task_id=task['id'],model=cfg.model,formal_policy='automatic',requirements=task['requirements'],interface=task['interface'],ltl=task.get('ltl'))
    def complete(self,messages,tools=None,on_delta=None,**kwargs):
        # Shared policy for self and Codex: at most three transport attempts.
        # Every actual request consumes the same per-task budget.
        for attempt in range(3):
            with self.lock:
                if self.stop.is_set():
                    self.provider.cancel();raise Cancelled('Task stopped')
                if time.monotonic()-self.started>LIMITS['seconds']:
                    self.provider.cancel();raise ProviderError('task_time_limit')
                if self.calls>=LIMITS['model_requests']: raise ProviderError('model_call_limit')
                self.calls+=1
                self.provider.config=replace(self.provider.config, timeout=max(5,min(self.cfg.timeout,int(LIMITS['seconds']-(time.monotonic()-self.started)))))
            before=len(self.provider.metrics)
            event(self.path,'model_request',request=self.calls,messages=messages)
            request_dir=self.path/'requests'/f'{self.calls:02d}'
            request_dir.mkdir(parents=True,exist_ok=True)
            atomic_json(request_dir/'input.json',{'messages':messages,'model':self.cfg.model})
            try:
                answer=self.provider.complete(messages,tools,on_delta,**kwargs)
                self.metrics.append(self.provider.metrics[-1])
                visible={k:v for k,v in answer.items() if k!='reasoning_content'}
                atomic_json(request_dir/'output.json',visible)
                event(self.path,'model_response',request=self.calls,response=visible)
                return answer
            except Exception as exc:
                # A rejected/truncated response can still contain billable usage.
                metric=dict(self.provider.metrics[-1]) if len(self.provider.metrics)>before else {'usage':{}}
                message=str(exc).replace(self.cfg.api_key,'[redacted]') if self.cfg.api_key else str(exc)
                metric.update(status='request_error',error=message)
                self.metrics.append(metric)
                atomic_json(request_dir/'output.json',{'status':'request_error','error':message,'usage':metric.get('usage',{})})
                event(self.path,'model_error',request=self.calls,error=message,usage=metric.get('usage',{}))
                transient=isinstance(exc,ProviderError) and any(token in message for token in (
                    '模型连接失败','HTTP 429','HTTP 502','HTTP 503','HTTP 504','timed out','UNEXPECTED_EOF','模型流提前中断'))
                if not transient or attempt==2:raise
                if self.stop.wait(2**attempt):raise ProviderError('Campaign stopped')
    @property
    def cancel_event(self):return self.stop
    def cancel(self):
        self.stop.set();self.provider.cancel()
    def check(self,text):
        with self.lock:
            if self.stop.is_set(): return {'status':'interrupted'}
            if time.monotonic()-self.started>LIMITS['seconds']:return {'status':'timeout'}
            if not isinstance(text,str) or len(text)>200000:raise ValueError('ST source must be <=200 KB')
            text=normalize_v6(text,self.task['block'])
            sha=hashlib.sha256(text.encode()).hexdigest()
            if sha in self.submissions:return self.submissions[sha]
            if len(self.submissions)>=LIMITS['source_versions']:return {'status':'revision_limit'}
            folder=self.path/'submissions'/str(len(self.submissions)+1)
            folder.mkdir(parents=True)
            source=folder/'candidate.st';source.write_text(text,encoding='utf-8')
            result=evaluate_candidate(source,self.task,self.vendor,self.stop,
                formal_directory=folder/'formal',
                formal_timeout=max(0,LIMITS['seconds']-(time.monotonic()-self.started)),formal_config=self.formal_config)
            if self.stop.is_set():result={**result,'status':'interrupted'}
            elif time.monotonic()-self.started>LIMITS['seconds']:result={**result,'status':'timeout','message':'Whole-task time limit reached'}
            event(self.path,'evaluation',version=len(self.submissions)+1,source_sha256=sha,result=result)
            atomic_json(folder/'evaluation.json',result)
            result=dataset_workflow.compact(result)
            self.submissions[sha]=result
            result['metrics_summary']=metrics(result,self.task)
            (self.path/'candidate.st').write_text(text,encoding='utf-8')
            return result
    def receipt(self,status,extra=None):
        value={'task_id':self.task['id'],'dataset_sha256':self.task['dataset_sha256'],
            'model':self.cfg.model,'inference_parameters':self.cfg.extra_body,'status':status,'model_calls':self.calls,
            'token_usage':dataset_workflow.usage_totals(self.metrics),'metrics':self.metrics,
            'seconds':round(time.monotonic()-self.started,3),'evidence_path':str(self.path),'submissions':list(self.submissions.values()),
            'limits':LIMITS,'formal_policy':'automatic', **(extra or {})}
        candidate=self.path/'candidate.st'
        value['source_sha256']=hashlib.sha256(candidate.read_bytes()).hexdigest() if candidate.exists() else None
        return finish(self.path,value,self.task)


def run_self(trial):
    dataset_workflow.normalize_source=normalize_v6
    source=trial.path/'candidate.st'
    def check(path,task):return trial.check(Path(path).read_text(encoding='utf-8'))
    result=dataset_workflow.run(trial.task['id'],source,trial.path,trial.cfg,
        task_override=trial.task,provider=trial,max_revisions=LIMITS['source_versions'],review=False,
        evaluator=check,notify=lambda text:event(trial.path,'progress',message=text))
    return trial.receipt(result['status'],{'final_evaluation':result.get('final_evaluation'),
            'target_compile':result.get('target_compile','not_executed'),
            'formal_verification':result.get('formal_verification'),
            'ltl_status':result.get('ltl_status','not_executed')})


class Relay:
    """The CLI sees a local temporary token; the real DMXAPI key stays in the host."""
    def __init__(self,trial):
        self.trial=trial; token=uuid.uuid4().hex;self.token=token
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def send(self,value,status=200):
                raw=json.dumps(value,ensure_ascii=False).encode()
                self.send_response(status);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def do_POST(self):
                if self.headers.get('Authorization')!='Bearer '+token:return self.send({'error':'Unauthorized'},401)
                try:
                    length=int(self.headers.get('Content-Length',0))
                    if not 0<length<=2000000:raise ValueError('Request too large')
                    p=json.loads(self.rfile.read(length))
                    if self.path=='/check':return self.send(trial.check(p['code']))
                    if self.path!='/v1/chat/completions':return self.send({'error':'Unsupported endpoint'},404)
                    if p.get('model')!=trial.cfg.model:raise ValueError('Frozen model mismatch')
                    answer=trial.complete(p['messages'],tools=p.get('tools'))
                    calls=[{'id':c['id'],'type':'function','function':{'name':c['name'],'arguments':json.dumps(c['arguments'],ensure_ascii=False)}} for c in answer.get('calls',[])]
                    message={'role':'assistant','content':answer.get('text') or None}
                    if calls:message['tool_calls']=calls
                    if answer.get('reasoning_content'):message['reasoning_content']=answer['reasoning_content']
                    usage=answer.get('usage',{})
                    finish='tool_calls' if calls else 'stop'
                    if not p.get('stream'):return self.send({'id':'chatcmpl-'+uuid.uuid4().hex,'object':'chat.completion','model':trial.cfg.model,'choices':[{'index':0,'message':message,'finish_reason':finish}],'usage':usage})
                    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Connection','close');self.end_headers();self.close_connection=True
                    if calls:
                        message['tool_calls']=[{**c,'index':i} for i,c in enumerate(calls)]
                    chunk={'id':'chatcmpl-'+uuid.uuid4().hex,'object':'chat.completion.chunk','model':trial.cfg.model,'choices':[{'index':0,'delta':message,'finish_reason':finish}],'usage':usage}
                    self.wfile.write(('data: '+json.dumps(chunk,ensure_ascii=False)+'\n\ndata: [DONE]\n\n').encode());self.wfile.flush()
                except Exception as exc:
                    self.send({'error':{'message':str(exc).replace(trial.cfg.api_key,'[redacted]') if trial.cfg.api_key else str(exc)}},400)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
    def __enter__(self):self.thread.start();return self
    def __exit__(self,*_):self.server.shutdown();self.server.server_close();self.thread.join()


def run_codex(trial,cli):
    workspace=trial.path/'workspace';workspace.mkdir()
    home=trial.path/'cli_home';home.mkdir()
    packet=bank32.author_packet(trial.task,backend='codesys' if trial.vendor is not None else 'optional_local')
    # Only the author packet enters the CLI workspace; expected tables stay host-side.
    (workspace/'requirements.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2),encoding='utf-8')
    with Relay(trial) as relay:
        port=relay.server.server_port
        (home/'config.toml').write_text('model = '+json.dumps(trial.cfg.model)+'\nmodel_provider = "experiment"\napproval_policy = "never"\nsandbox_mode = "workspace-write"\n[model_providers.experiment]\nname = "DMXAPI metered Chat relay"\nbase_url = "http://127.0.0.1:'+str(port)+'/v1"\nenv_key = "PLC_BENCHMARK_TOKEN"\nwire_api = "chat"\nrequest_max_retries = 0\nstream_max_retries = 0\n',encoding='utf-8')
        checker="""import json, pathlib, urllib.request
p=pathlib.Path('candidate.st')
req=urllib.request.Request(URL,data=json.dumps({'code':p.read_text(encoding='utf-8-sig')}).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+TOKEN},method='POST')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(req,timeout=600) as r: print(r.read().decode())
""".replace('URL',repr('http://127.0.0.1:'+str(port)+'/check')).replace('TOKEN',repr(relay.token))
        (workspace/'check.py').write_text(checker,encoding='utf-8')
        prompt='Read requirements.json. Write complete candidate.st with the exact interface. In PowerShell run: & '+json.dumps(sys.executable)+' check.py after each version. Repair using diagnostics. Repair compile_error, fail, invalid_candidate, runtime_error and formal_counterexample using the actual diagnostics. Stop when status is pass or compiled_without_tests; also stop and report formal_incomplete, formal_blocked, timeout, missing_dependency, tool_error, protocol_error, stale_source, stale_evidence, behavior_not_supported, capability_blocked, backend_busy, revision_limit, interrupted or no_progress instead of guessing a code fix. At most 6 distinct source versions, 24 model requests, 1800 seconds. Work only in this directory; never edit requirements.json or check.py, read parent directories, hidden tests, compiler caches or reference solutions. Finish with status.'
        env={k:v for k,v in os.environ.items() if not any(word in k.upper() for word in ('API_KEY','TOKEN','SECRET','PASSWORD','CODEX_HOME','OPENAI_'))}
        env=local_proxy_bypass(env)
        env.update(CODEX_HOME=str(home),PLC_BENCHMARK_TOKEN=relay.token)
        log=trial.path/'agent.log'
        with log.open('w',encoding='utf-8') as output:
            process=subprocess.Popen(cli_command(cli)+['exec','-C',str(workspace),'--skip-git-repo-check','-s','workspace-write','--json','-'],
                cwd=workspace,env=env,stdin=subprocess.PIPE,stdout=output,stderr=subprocess.STDOUT,text=True,encoding='utf-8')
            process.stdin.write(prompt);process.stdin.close()
            while process.poll() is None:
                if trial.stop.wait(.25) or time.monotonic()-trial.started>LIMITS['seconds']:
                    trial.provider.cancel()
                    if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                    else:process.kill()
                    break
            process.wait()
        candidate=workspace/'candidate.st'
        result={'status':'missing_candidate','target_compile':'not_executed'}
        if candidate.exists():result=trial.check(candidate.read_text(encoding='utf-8-sig'))
        status='finite_pass' if result['status']=='pass' else result['status']
        return trial.receipt(status,{'final_evaluation':result,'target_compile':result.get('target_compile','not_executed'),
            'formal_verification':result.get('formal_verification'),'ltl_status':result.get('ltl_status','not_executed'),
            'cli_exit_code':process.returncode,'framework_version':'codex-cli 0.80.0','wire_api':'chat'})


def summarize(rows,expected,tasks=None):
    table=[]
    for framework,model in expected:
        group=[r for r in rows if r['framework']==framework and r['model']==model]
        passed=sum(r['status']=='finite_pass' for r in group)
        compiled=sum(r.get('target_compile')=='passed' for r in group)
        first_vendor=sum(bool(r.get('submissions')) and r['submissions'][0].get('target_compile')=='passed' for r in group)
        first_pass=sum(bool(r.get('submissions')) and r['submissions'][0].get('status')=='pass' for r in group)
        totals=dataset_workflow.usage_totals([m for r in group for m in r.get('metrics',[])])
        summaries=[(r.get('final_evaluation') or {}).get('summary') or {} for r in group]
        scenarios=sum(s.get('scenarios',0) for s in summaries)
        failed=sum(s.get('failed',0) for s in summaries)
        reports=[(r.get('final_evaluation') or {}).get('formal_verification') or {} for r in group]
        from collections import Counter
        formal_statuses=dict(Counter(f.get('status','not_executed') for f in reports))
        assertions=sum(f.get('mapped_assertions_total',0) for f in reports)
        proved=sum(len(f.get('proved_property_ids',[])) for f in reports)
        verified=sum(len(f.get('bounded_verified_property_ids',[])) for f in reports)
        formal_total=sum(property_count(t.get('ltl',{})) for t in tasks) if tasks is not None else sum(f.get('declared_ltl_total',0) for f in reports)
        denominator=len(tasks) if tasks is not None else len(group)
        declared_tests=sum(len(t.get('scenarios',[])) for t in tasks) if tasks is not None else scenarios
        table.append({'framework':framework,'model':model,'completed':len(group),'passed':passed,
            'task_count':denominator,'codesys_compile_rate':compiled/denominator if denominator else None,
            'codesys_first_compile_rate':first_vendor/denominator if denominator else None,
            'task_pass_rate':passed/denominator if denominator else None,
            'test_cases_passed':scenarios-failed,'test_cases_total':declared_tests,
            'test_cases_executed':scenarios,'test_cases_not_executed':max(0,declared_tests-scenarios),
            'test_case_pass_rate':(scenarios-failed)/declared_tests if declared_tests else None,
            'mapped_assertions_proved':proved,'mapped_assertions_total':assertions,
            'mapped_assertion_pass_rate':proved/assertions if assertions else None,
            'formal_statuses':formal_statuses,'formal_proved_tasks':sum(f.get('status')=='proved' for f in reports),
            'formal_properties_verified':verified,'formal_properties_total':formal_total,
            'formal_property_pass_rate':verified/formal_total if formal_total else None,
            'formal_verified_tasks':sum(f.get('bounded_all_properties_verified',False) for f in reports),
            'formal_bounds':sorted({f['bound'] for f in reports if f.get('bound') is not None}),
            'declared_ltl_total':formal_total,
            'failed_tasks':sum(r['status'] not in ('finite_pass','compiled_without_tests','interrupted') for r in group),
            'codesys_compiled':compiled,'codesys_first_compile_passed':first_vendor,'pass_at_1':first_pass,'scenario_count':scenarios,'failed_scenarios':failed,
            'model_calls':sum(r.get('model_calls',0) for r in group),'token_usage':totals,
            'seconds':round(sum(r.get('seconds',0) for r in group),3)})
    return table


def campaign_inputs(data,cfg):
    models=data.get('models',[])
    if not isinstance(models,list) or len(models)!=2 or any(not isinstance(m,str) or not m.strip() for m in models):raise ValueError('请填写两个不同的准确模型 ID')
    models=[m.strip() for m in models]
    if models[0]==models[1]:raise ValueError('请填写两个不同的准确模型 ID')
    ids=data.get('task_ids',[])
    if not isinstance(ids,list) or not ids or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids):raise ValueError('请导入并选择至少一道不重复题目')
    vendor_required=data.get('codesys',True)
    if type(vendor_required) is not bool:raise ValueError('codesys must be boolean')
    for model in models:
        if len(model)>200 or any(ord(c)<32 for c in model):raise ValueError('Invalid model ID')
    concurrency=data.get('concurrency',16)
    if type(concurrency) is not int or concurrency<1:raise ValueError('并发数必须为正整数')
    settings=data.get('model_settings',[{},{}])
    if not isinstance(settings,list) or len(settings)!=2:raise ValueError('需要模型 A、B 的两份推理设置')
    model_configs={m:inference_config(cfg,m,s) for m,s in zip(models,settings)}
    return models,ids,vendor_required,concurrency,settings,model_configs


class Campaigns:
    def __init__(self,home=STATE_ROOT):
        self.home=Path(home);self.root=output_root(home)/'campaigns';self.active={};self.pauses={};self.threads={};self.lock=threading.RLock()
    def read(self,ident):
        if not valid_run_id(ident):raise ValueError('Invalid campaign ID')
        result=read_json(details_path(self.root/ident)/'campaign.json')
        if result['status'] in ('running','pausing','paused','stopping') and ident not in self.active:
            result['status']='interrupted';result['message']='服务已退出；记录保留，本轮未完成。'
        result['can_resume']=ident in self.active and ident in self.pauses and self.pauses[ident].is_set()
        return result
    def list(self):
        if not self.root.exists():return []
        paths=sorted((p for p in self.root.iterdir() if p.is_dir() and valid_run_id(p.name)),key=lambda p:p.stat().st_mtime,reverse=True)
        return [self.read(p.name) for p in paths if (details_path(p)/'campaign.json').exists() and not (p/'hidden.json').exists()][:100]
    def persist(self,path,record):
        directory=details_path(path)
        atomic_json(directory/'campaign.json',record)
        atomic_json(directory/'metrics.json',record['summary'])
        write_campaign_summary(path,record)
    def start(self,data):
        cfg=ModelConfig.load(self.home)
        models,ids,vendor_required,concurrency,settings,model_configs=campaign_inputs(data,cfg)
        ready=preflight(self.home,vendor_required)
        formal_config=plcverif_backend.configuration(self.home)
        if ready['errors']:raise ValueError('\n'.join(ready['errors']))
        bank=ImportedBank(self.home);tasks=[bank.load(ident) for ident in ids]
        cfg=ModelConfig.load(self.home)
        if cfg.base_url.rstrip('/')!='https://www.dmxapi.cn/v1':raise ValueError('批量实验需要配置 DMXAPI 接口地址')
        with self.lock:
            if self.active:raise ValueError('已有批量实验在运行或暂停')
            path=reserve_run(self.root);ident=path.name
            directory=path/'details';directory.mkdir()
            stop=threading.Event();pause=threading.Event();self.active[ident]=stop;self.pauses[ident]=pause
        expected=[(f,m) for f in ('self','codex') for m in models]
        # Freeze code, dataset, model settings and vendor configuration for this campaign.
        code_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in [*sorted((ROOT/'plc_agent').glob('*.py'))]}
        record={'id':ident,'layout_version':2,'started_at':datetime.now(LOCAL_TIME).isoformat(),'status':'running','models':models,'task_ids':ids,'total':4*len(tasks),
            'completed':0,'results':[],'summary':summarize([],expected,tasks),'limits':LIMITS,
            'model_configuration':cfg.public(),'model_settings':settings,'formal_configuration':formal_config,
            'model_configurations':{m:c.public() for m,c in model_configs.items()},'code_hashes':code_hashes,'preflight':ready,
            'task_count':len(tasks),'concurrency':concurrency,'formal_policy':'automatic','output_path':str(path.resolve()),
            'scope':'CODESYS compilation + local finite tests' if vendor_required else 'Local-only pilot; not assignment vendor evidence'}
        atomic_json(directory/'tasks.json',tasks);self.persist(path,record)
        def worker():
            try:
                # Validate IDE positive/negative controls once before paid generation.
                if vendor_required:
                    validate_vendor_environment(ready['codesys'],directory/'vendor_preflight',stop)
                jobs=iter((framework,model,index,task) for index,task in enumerate(tasks) for framework,model in expected)
                def execute(job):
                    framework,model,index,task=job
                    trial=Trial(trial_path(path,record,framework,models.index(model),index)/'details',task,model_configs[model],ready['codesys'] if vendor_required else None,stop,formal_config=formal_config,save_snapshots=False)
                    try:
                        value=run_self(trial) if framework=='self' else run_codex(trial,Path(ready['codex_path']))
                    except Exception as exc:
                        message=str(exc).replace(cfg.api_key,'[redacted]') if cfg.api_key else str(exc)
                        value=trial.receipt('interrupted' if stop.is_set() else 'task_error',{'message':message,'target_compile':'not_executed'})
                    value['framework']=framework
                    return value
                last_state=None
                with ThreadPoolExecutor(max_workers=min(concurrency,record['total']),thread_name_prefix='campaign') as pool:
                    pending={}
                    exhausted=False
                    try:
                        while pending or not exhausted:
                            while not stop.is_set() and not pause.is_set() and not exhausted and len(pending)<concurrency:
                                if any(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()!=sha for f,sha in code_hashes.items()):
                                    raise ValueError('Code changed during frozen campaign')
                                job=next(jobs,None)
                                if job is None:exhausted=True;break
                                pending[pool.submit(execute,job)]=job
                            record['current']=[{'framework':f,'model':m,'task_id':t['id']} for f,m,i,t in pending.values()]
                            record['status']='stopping' if stop.is_set() else ('pausing' if pending else 'paused') if pause.is_set() else 'running'
                            state=(record['status'],record['completed'],len(pending))
                            if state!=last_state:self.persist(path,record);last_state=state
                            if not pending:
                                if pause.is_set() and not stop.is_set() and record['completed']<record['total']:
                                    stop.wait(.15);continue
                                break
                            done,_=wait(pending,timeout=.25,return_when=FIRST_COMPLETED)
                            for future in done:
                                pending.pop(future)
                                record['results'].append(future.result());record['completed']+=1
                            if done:
                                record['summary']=summarize(record['results'],expected,tasks)
                            if stop.is_set():exhausted=True
                    except Exception:
                        stop.set()
                        raise
                record['status']='interrupted' if stop.is_set() else 'completed'
            except Cancelled:
                record['status']='interrupted'
            except Exception as exc:
                record['status']='error';record['message']=str(exc).replace(cfg.api_key,'[redacted]') if cfg.api_key else str(exc)
            finally:
                record.pop('current',None)
                self.persist(path,record)
                event(directory,'campaign_finished',status=record['status'],summary=record['summary'])
                with self.lock:self.active.pop(ident,None);self.pauses.pop(ident,None);self.threads.pop(ident,None)
        thread=threading.Thread(target=worker,daemon=True)
        with self.lock:self.threads[ident]=thread
        thread.start()
        return {'id':ident,'total':record['total']}
    def stop(self,ident):
        self.read(ident)
        with self.lock:
            if ident in self.active:self.active[ident].set()
        return {'status':'stop_requested'}
    def pause(self,ident):
        self.read(ident)
        with self.lock:
            if ident not in self.active or self.active[ident].is_set():raise ValueError('该实验已结束，不能暂停')
            self.pauses[ident].set()
        return {'status':'pause_requested'}
    def resume(self,ident):
        self.read(ident)
        with self.lock:
            if ident not in self.active or self.active[ident].is_set():raise ValueError('服务已关闭或实验已结束；此记录不能原地继续')
            self.pauses[ident].clear()
        return {'status':'resume_requested'}


def dataset_catalog():
    from plc_agent.dataset import catalog
    return catalog()['tasks']


def validate_vendor_environment(config,directory,stop):
    """Both controls go through the same compiler path as measured candidates."""
    directory=Path(directory);directory.mkdir(parents=True)
    from plc_agent.codesys_dataset import compile_dataset
    task={'id':'CONTROL','block':'WB_Control','interface':[], 'dataset_sha256':'control'}
    good=directory/'good.st';bad=directory/'bad.st'
    good.write_text('FUNCTION_BLOCK WB_Control\nVAR X : BOOL; END_VAR\nX := TRUE;\nEND_FUNCTION_BLOCK',encoding='utf-8')
    bad.write_text('FUNCTION_BLOCK WB_Control\nVAR X : BOOL; END_VAR\nX := UndefinedVariable;\nEND_FUNCTION_BLOCK',encoding='utf-8')
    ok=compile_dataset(good,task,config,stop)
    from plc_probe.backend import BackendError
    try: compile_dataset(bad,task,config,stop)
    except BackendError as exc:
        if exc.result['status']!='compile_error':raise
        atomic_json(directory/'environment.json',{'positive':ok,'negative':exc.result,'negative_control_rejected':True})
        return
    raise ValueError('CODESYS failed to reject the negative control')
