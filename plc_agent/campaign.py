"""Frozen 2x2 campaigns: shared checker, budgets, snapshots, and real Codex CLI."""
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

from . import bank32, codesys, dataset_workflow
from .bank32_v6 import normalize_v6
from .codesys_dataset import evaluate_candidate
from .config import ROOT, STATE_ROOT, ModelConfig
from .imported_bank import ImportedBank
from .provider import ChatProvider, ProviderError
from .inference import inference_config
from .storage import atomic_json, read_json

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


def preflight(home=STATE_ROOT, require_vendor=True):
    from .runtime_env import configure_tools
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
    if not (toolchain_dir()/('strucpp.exe' if os.name=='nt' else 'strucpp')).is_file(): errors.append('本地 ST 编译器未配置')
    if not (os.environ.get('CXX') or shutil.which('g++')): errors.append('g++ 未配置（CXX 或 PATH）')
    from .backend_r4 import info
    backend=None
    try:
        backend=info()
        if backend is None:errors.append('当前本地后端为原版，缺少工作台声明的 LTIME/开放数组支持；请运行 python -m plc_agent.backend_r4 activate')
    except (ValueError,OSError) as exc:errors.append('本地扩展后端校验失败: '+str(exc))
    return {'local_backend':{'home':str(toolchain_dir()),'extension':backend.get('extension') if backend else None,'fingerprint':backend.get('fingerprint') if backend else None},'status':'ready' if not errors else 'setup_required','errors':errors,
        'codex_path':str(cli) if cli else None,'codex_version':version,
        'vendor_required':require_vendor,'codesys':vendor,'limits':LIMITS,'tools':tools}


class Trial:
    def __init__(self,path,task,cfg,vendor,stop):
        self.path=Path(path); self.path.mkdir(parents=True,exist_ok=True)
        self.task=task;self.cfg=cfg;self.vendor=vendor;self.stop=stop
        self.provider=ChatProvider(replace(cfg,transport_retries=0)); self.metrics=[]
        self.calls=0;self.started=time.monotonic();self.submissions={};self.lock=threading.RLock()
        atomic_json(self.path/'task_snapshot.json',task)
    def complete(self,messages,tools=None,on_delta=None,**kwargs):
        # Shared policy for self and Codex: at most three transport attempts.
        # Every actual request consumes the same per-task budget.
        for attempt in range(3):
            with self.lock:
                if self.stop.is_set() or time.monotonic()-self.started>LIMITS['seconds']:
                    self.provider.cancel(); raise ProviderError('Campaign stopped or task timed out')
                if self.calls>=LIMITS['model_requests']: raise ProviderError('model_call_limit')
                self.calls+=1
                self.provider.config=replace(self.provider.config, timeout=max(5,min(self.cfg.timeout,int(LIMITS['seconds']-(time.monotonic()-self.started)))))
            before=len(self.provider.metrics)
            try:
                answer=self.provider.complete(messages,tools,on_delta,**kwargs)
                self.metrics.append(self.provider.metrics[-1]); return answer
            except Exception as exc:
                # A rejected/truncated response can still contain billable usage.
                metric=dict(self.provider.metrics[-1]) if len(self.provider.metrics)>before else {'usage':{}}
                message=str(exc).replace(self.cfg.api_key,'[redacted]') if self.cfg.api_key else str(exc)
                metric.update(status='request_error',error=message)
                self.metrics.append(metric)
                transient=isinstance(exc,ProviderError) and any(token in message for token in (
                    '模型连接失败','HTTP 429','HTTP 502','HTTP 503','HTTP 504','timed out','UNEXPECTED_EOF','模型流提前中断'))
                if not transient or attempt==2:raise
                if self.stop.wait(2**attempt):raise ProviderError('Campaign stopped')
    @property
    def cancel_event(self):return self.stop
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
            result=evaluate_candidate(source,self.task,self.vendor,self.stop)
            atomic_json(folder/'evaluation.json',result)
            result=dataset_workflow.compact(result)
            self.submissions[sha]=result
            (self.path/'candidate.st').write_text(text,encoding='utf-8')
            return result
    def receipt(self,status,extra=None):
        value={'task_id':self.task['id'],'dataset_sha256':self.task['dataset_sha256'],
            'model':self.cfg.model,'inference_parameters':self.cfg.extra_body,'status':status,'model_calls':self.calls,
            'token_usage':dataset_workflow.usage_totals(self.metrics),'metrics':self.metrics,
            'seconds':round(time.monotonic()-self.started,3),'evidence_path':str(self.path),'submissions':list(self.submissions.values()),
            'limits':LIMITS, **(extra or {})}
        candidate=self.path/'candidate.st'
        value['source_sha256']=hashlib.sha256(candidate.read_bytes()).hexdigest() if candidate.exists() else None
        atomic_json(self.path/'receipt.json',value)
        return value


def run_self(trial):
    dataset_workflow.normalize_source=normalize_v6
    source=trial.path/'candidate.st'
    def check(path,task):return trial.check(Path(path).read_text(encoding='utf-8'))
    result=dataset_workflow.run(trial.task['id'],source,trial.path,trial.cfg,
        task_override=trial.task,provider=trial,max_revisions=LIMITS['source_versions'],review=False,
        evaluator=check,notify=lambda _:None)
    return trial.receipt(result['status'],{'final_evaluation':result.get('final_evaluation'),
        'target_compile':result.get('target_compile','not_executed')})


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
    packet=bank32.author_packet(trial.task)
    # Only the author packet enters the CLI workspace; expected tables stay host-side.
    (workspace/'requirements.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2),encoding='utf-8')
    with Relay(trial) as relay:
        port=relay.server.server_port
        (home/'config.toml').write_text('model = '+json.dumps(trial.cfg.model)+'\nmodel_provider = "experiment"\napproval_policy = "never"\nsandbox_mode = "workspace-write"\n[model_providers.experiment]\nname = "DMXAPI metered Chat relay"\nbase_url = "http://127.0.0.1:'+str(port)+'/v1"\nenv_key = "PLC_BENCHMARK_TOKEN"\nwire_api = "chat"\nrequest_max_retries = 0\nstream_max_retries = 0\n',encoding='utf-8')
        checker="""import json, pathlib, urllib.request
p=pathlib.Path('candidate.st')
req=urllib.request.Request(URL,data=json.dumps({'code':p.read_text(encoding='utf-8-sig')}).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+TOKEN},method='POST')
with urllib.request.urlopen(req,timeout=600) as r: print(r.read().decode())
""".replace('URL',repr('http://127.0.0.1:'+str(port)+'/check')).replace('TOKEN',repr(relay.token))
        (workspace/'check.py').write_text(checker,encoding='utf-8')
        prompt='Read requirements.json. Write complete candidate.st with the exact interface. In PowerShell run: & '+json.dumps(sys.executable)+' check.py after each version. Repair using diagnostics. Stop when status is pass or compiled_without_tests. At most 6 distinct source versions, 24 model requests, 1800 seconds. Work only in this directory; never edit requirements.json or check.py, read parent directories, hidden tests, compiler caches or reference solutions. Finish with status.'
        env={k:v for k,v in os.environ.items() if not any(word in k.upper() for word in ('API_KEY','TOKEN','SECRET','PASSWORD','CODEX_HOME','OPENAI_'))}
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
            'cli_exit_code':process.returncode,'framework_version':'codex-cli 0.80.0','wire_api':'chat'})


def summarize(rows,expected):
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
        table.append({'framework':framework,'model':model,'completed':len(group),'passed':passed,
            'failed_tasks':sum(r['status'] not in ('finite_pass','compiled_without_tests','interrupted') for r in group),
            'codesys_compiled':compiled,'codesys_first_compile_passed':first_vendor,'pass_at_1':first_pass,'scenario_count':scenarios,'failed_scenarios':failed,
            'model_calls':sum(r.get('model_calls',0) for r in group),'token_usage':totals,
            'seconds':round(sum(r.get('seconds',0) for r in group),3)})
    return table


class Campaigns:
    def __init__(self,home=STATE_ROOT):
        self.home=Path(home);self.root=self.home/'campaigns';self.active={};self.lock=threading.Lock()
    def read(self,ident):
        if not isinstance(ident,str) or len(ident)!=32 or any(c not in '0123456789abcdef' for c in ident):raise ValueError('Invalid campaign ID')
        result=read_json(self.root/ident/'campaign.json')
        if result['status']=='running' and ident not in self.active:result['status']='interrupted'
        return result
    def list(self):
        return [self.read(p.parent.name) for p in sorted(self.root.glob('*/campaign.json'),key=lambda p:p.stat().st_mtime,reverse=True) if not (p.parent/'hidden.json').exists()][:30]
    def start(self,data):
        models=data.get('models',[])
        if len(models)!=2 or any(not isinstance(m,str) or not m.strip() for m in models) or models[0]==models[1]:raise ValueError('请填写两个不同的准确模型 ID')
        ids=data.get('task_ids',[])
        if not isinstance(ids,list) or not ids or len(set(ids))!=len(ids):raise ValueError('请导入并选择至少一道不重复题目')
        vendor_required=data.get('codesys',True)
        if type(vendor_required) is not bool:raise ValueError('codesys must be boolean')
        for model in models:
            if len(model)>200 or any(ord(c)<32 for c in model):raise ValueError('Invalid model ID')
        concurrency=data.get('concurrency',16)
        if type(concurrency) is not int or concurrency<1:raise ValueError('并发数必须为正整数')
        settings=data.get('model_settings',[{},{}])
        if not isinstance(settings,list) or len(settings)!=2:raise ValueError('需要模型 A、B 的两份推理设置')
        cfg=ModelConfig.load(self.home)
        model_configs={m:inference_config(cfg,m,s) for m,s in zip(models,settings)}
        ready=preflight(self.home,vendor_required)
        if ready['errors']:raise ValueError('\n'.join(ready['errors']))
        bank=ImportedBank(self.home);tasks=[bank.load(ident) for ident in ids]
        cfg=ModelConfig.load(self.home)
        if cfg.base_url.rstrip('/')!='https://www.dmxapi.cn/v1':raise ValueError('本批次需要老师指定 DMXAPI endpoint')
        ident=uuid.uuid4().hex;path=self.root/ident
        with self.lock:
            if self.active:raise ValueError('已有批量实验在运行')
            path.mkdir(parents=True)
            stop=threading.Event();self.active[ident]=stop
        expected=[(f,m) for f in ('self','codex') for m in models]
        # Freeze code, dataset, model settings and vendor configuration for this campaign.
        code_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in [*sorted((ROOT/'plc_agent').glob('*.py'))]}
        record={'id':ident,'status':'running','models':models,'task_ids':ids,'total':4*len(tasks),
            'completed':0,'results':[],'summary':summarize([],expected),'limits':LIMITS,
            'model_configuration':cfg.public(),'model_settings':settings,
            'model_configurations':{m:c.public() for m,c in model_configs.items()},'code_hashes':code_hashes,'preflight':ready,
            'task_count':len(tasks),'concurrency':concurrency,
            'scope':'CODESYS compilation + local finite tests' if vendor_required else 'Local-only pilot; not assignment vendor evidence'}
        atomic_json(path/'tasks.json',tasks);atomic_json(path/'campaign.json',record)
        def worker():
            try:
                # Validate IDE positive/negative controls once before paid generation.
                if vendor_required:
                    validate_vendor_environment(ready['codesys'],path/'vendor_preflight',stop)
                jobs=iter((framework,model,index,task) for index,task in enumerate(tasks) for framework,model in expected)
                def execute(job):
                    framework,model,index,task=job
                    trial=Trial(path/framework/str(models.index(model))/str(index),task,model_configs[model],ready['codesys'] if vendor_required else None,stop)
                    try:
                        value=run_self(trial) if framework=='self' else run_codex(trial,Path(ready['codex_path']))
                    except Exception as exc:
                        message=str(exc).replace(cfg.api_key,'[redacted]') if cfg.api_key else str(exc)
                        value=trial.receipt('interrupted' if stop.is_set() else 'task_error',{'message':message,'target_compile':'not_executed'})
                    value['framework']=framework
                    return value
                with ThreadPoolExecutor(max_workers=min(concurrency,record['total']),thread_name_prefix='campaign') as pool:
                    pending={}
                    exhausted=False
                    try:
                        while pending or not exhausted:
                            while not stop.is_set() and not exhausted and len(pending)<concurrency:
                                if any(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()!=sha for f,sha in code_hashes.items()):
                                    raise ValueError('Code changed during frozen campaign')
                                job=next(jobs,None)
                                if job is None:exhausted=True;break
                                pending[pool.submit(execute,job)]=job
                            record['current']=[{'framework':f,'model':m,'task_id':t['id']} for f,m,i,t in pending.values()]
                            atomic_json(path/'campaign.json',record)
                            if not pending:break
                            done,_=wait(pending,timeout=.25,return_when=FIRST_COMPLETED)
                            for future in done:
                                pending.pop(future)
                                record['results'].append(future.result());record['completed']+=1
                            if done:
                                record['summary']=summarize(record['results'],expected)
                            if stop.is_set():exhausted=True
                    except Exception:
                        stop.set()
                        raise
                record['status']='interrupted' if stop.is_set() else 'completed'
            except Exception as exc:
                record['status']='error';record['message']=str(exc).replace(cfg.api_key,'[redacted]') if cfg.api_key else str(exc)
            finally:
                record.pop('current',None)
                atomic_json(path/'campaign.json',record)
                with self.lock:self.active.pop(ident,None)
        threading.Thread(target=worker,daemon=True).start()
        return {'id':ident,'total':record['total']}
    def stop(self,ident):
        self.active[ident].set();return {'status':'stop_requested'}


def dataset_catalog():
    from .dataset import catalog
    return catalog()['tasks']


def validate_vendor_environment(config,directory,stop):
    """Both controls go through the same compiler path as measured candidates."""
    directory=Path(directory);directory.mkdir(parents=True)
    from .codesys_dataset import compile_dataset
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
