"""网页服务入口：接收任务、读取配置、调用统一流程并展示运行结果。"""
from __future__ import annotations
import argparse
from dataclasses import replace
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import socket
import uuid

from plc_agent import dataset
from plc_agent import dataset_workflow
from plc_agent.bank32_v6 import normalize_v6
from plc_agent.config import ModelConfig, STATE_ROOT, ROOT
from plc_agent.provider import ChatProvider, Cancelled
from plc_agent.imported_bank import ImportedBank
from plc_agent.campaign import Campaigns, Trial, preflight, campaign_inputs
from plc_agent import codesys
from plc_agent import tia, tia_workflow
from plc_agent.codesys_dataset import compile_dataset
from plc_agent.storage import atomic_json, read_json
from plc_agent.run_output import output_root, finish, event, reserve_run, valid_run_id, details_path, trial_path, log_path

STATIC = Path(__file__).with_name('web_static')

class Workbench:
    def __init__(self, home=STATE_ROOT):
        self.home = Path(home)
        self.bank = ImportedBank(self.home)
        self.campaigns = Campaigns(self.home)
        self.root = output_root(home) / 'single'
        self.jobs = {}
        self.lock = threading.Lock()

    def config(self):
        return ModelConfig.load(self.home)

    def public_config(self):
        cfg = self.config()
        return {**cfg.public(), 'has_api_key': bool(cfg.api_key)}

    def save_config(self, data):
        if not isinstance(data,dict):raise ValueError('Model configuration must be an object')
        old = self.config()
        # Keys remain on the server and are never returned by this API.
        for key in ('base_url','model','comparison_model','api_key'):
            if key in data and not isinstance(data[key],str):raise ValueError(key+' must be text')
        for key in ('stream','clear_api_key'):
            if key in data and type(data[key]) is not bool:raise ValueError(key+' must be boolean')
        base=data.get('base_url',old.base_url).strip()
        same_endpoint=base.rstrip('/')==old.base_url.rstrip('/')
        key='' if data.get('clear_api_key') else data.get('api_key') or (old.api_key if same_endpoint else '')
        cfg=replace(old,base_url=base,model=data.get('model',old.model).strip(),
                    comparison_model=data.get('comparison_model',old.comparison_model).strip(),
                    api_key=key,key_env=old.key_env if same_endpoint else 'PLC_AGENT_API_KEY',
                    stream=data.get('stream',old.stream))
        cfg.validate()
        cfg.save(self.home)
        return self.public_config()

    def campaign_preflight(self,data):
        """Check this form's inputs and local tools without model requests."""
        cfg=self.config()
        try:
            models,ids,vendor,concurrency,settings,configs=campaign_inputs(data,cfg)
            for ident in ids:self.bank.load(ident)
        except (ValueError,KeyError,OSError) as exc:
            return {'status':'setup_required','errors':[str(exc)],'model_calls':0}
        target=data.get('target','codesys')
        ready=preflight(self.home,vendor,**({'target':target} if target!='codesys' else {}))
        return {**ready,'models':models,'model_settings':settings,
                'task_count':len(ids),'total':4*len(ids),'concurrency':concurrency,
                'effective_concurrency':min(concurrency,4*len(ids)),
                'model_calls':0,'scope':'Local configuration checks only; API connectivity and vendor execution are not tested.'}

    def read_job(self, ident, detail=True):
        if not valid_run_id(ident):
            raise ValueError('Invalid run ID')
        path = self.root / ident
        directory=details_path(path)
        job = self.jobs.get(ident)
        saved = read_json(directory/'run.json') if (directory/'run.json').exists() else None
        if not job and not saved:
            raise ValueError('Unknown run')
        value = dict(job['view']) if job else {**saved, 'status': 'interrupted'}
        if detail and (path/'run.log').exists():
            with (path/'run.log').open(encoding='utf-8') as stream:
                from collections import deque
                value['logs']=[line[:8000] for line in deque(stream,maxlen=150)]
        value['output_path']=str(path.resolve())
        if (directory/'receipt.json').exists():
            value['receipt'] = read_json(directory/'receipt.json')
            if not job: value['status'] = value['receipt']['status']
        if not detail:return value
        extension = '.scl' if value.get('target') == 'tia' else '.st'
        source = directory/('candidate'+extension)
        if source.exists(): value['code'] = source.read_text(encoding='utf-8-sig')
        if extension == '.scl':
            versions = sorted((directory/'submissions').glob('*/candidate.scl'),key=lambda p:int(p.parent.name)) or sorted(directory.glob('proposal_*.scl'))
            value['versions'] = [{'name': ('提交 '+f.parent.name) if f.name=='candidate.scl' else f.name, 'code': f.read_text(encoding='utf-8-sig')} for f in versions]
        else:
            value['versions'] = [{'name': '提交 '+f.parent.name, 'code': f.read_text(encoding='utf-8-sig')}
                                 for f in sorted((directory/'submissions').glob('*/candidate.st'),key=lambda p:int(p.parent.name))]
        return value

    def read_trial(self,data):
        record=self.campaigns.read(data['campaign_id'])
        framework=data['framework'];model=data['model_index'];index=data['task_index']
        if framework not in ('self','codex') or type(model) is not int or type(index) is not int:
            raise ValueError('Invalid trial address')
        if not 0<=model<len(record['models']) or not 0<=index<len(record['task_ids']):raise ValueError('Invalid trial index')
        path=trial_path(self.campaigns.root/record['id'],record,framework,model,index)
        directory=details_path(path)
        receipt=read_json(directory/'receipt.json')
        suffix='.scl' if receipt.get('target')=='tia' else '.st'
        log=(path/'run.log').read_text(encoding='utf-8') if (path/'run.log').exists() else ''
        return {'status':receipt['status'],'receipt':receipt,'output_path':str(path.resolve()),
                'task_id':receipt['task_id'],'model':receipt['model'],
                'task':read_json(directory/'task_snapshot.json') if (directory/'task_snapshot.json').exists() else read_json(details_path(self.campaigns.root/record['id'])/'tasks.json')[index],
                'target':receipt.get('target','codesys'),
                'code':(directory/('candidate'+suffix)).read_text(encoding='utf-8-sig') if (directory/('candidate'+suffix)).exists() else '',
                'versions':[{'name':'提交 '+p.parent.name,'code':p.read_text(encoding='utf-8-sig')} for p in sorted((directory/'submissions').glob('*/candidate'+suffix),key=lambda p:int(p.parent.name))],
                'logs':[line[:8000] for line in log.splitlines()[-150:]],'full_log':log if data.get('include_log') else None}

    def start(self, data):
        task = self.bank.load(data['task_id'])
        action = data.get('action', 'generate')
        if action not in ('generate', 'check', 'codesys', 'tia_generate', 'tia', 'tia_check'): raise ValueError('Unknown action')
        target = 'tia' if action in ('tia_generate', 'tia', 'tia_check') else data.get('target', 'codesys')
        if target not in ('tia', 'codesys'): raise ValueError('Unknown platform')
        if target == 'tia' and action == 'check': action = 'tia_check'
        if target == 'tia' and action == 'generate': action = 'tia_generate'
        if target == 'tia' and action == 'codesys': action = 'tia'
        use_vendor=data.get('codesys',True)
        if type(use_vendor) is not bool:raise ValueError('codesys must be boolean')
        vendor_config = dict(tia.load_config(self.home)) if target == 'tia' else None
        if vendor_config is not None: tia.validate_config(vendor_config)
        vendor=codesys.load_config(self.home) if target != 'tia' and (use_vendor or action=='codesys') else None
        if vendor is not None:codesys.validate_config(vendor)
        elif target != 'tia':
            from plc_agent.local_test_support import backend as local_backend
            local_backend()
        code = data.get('code', '')
        if not isinstance(code, str) or len(code) > 200000: raise ValueError('ST source too large')
        cfg = self.config()
        if data.get('model'): cfg = replace(cfg, model=data['model'])
        if 'model_settings' in data:
            from plc_agent.inference import inference_config
            cfg = inference_config(cfg, cfg.model, data['model_settings'])
        if action in ('generate', 'tia_generate'): cfg.validate()
        with self.lock:
            if self.campaigns.active: raise ValueError('批量实验运行中，请等待结束')
            if any(j['view']['status'] in ('queued', 'running') for j in self.jobs.values()):
                raise ValueError('A task is already running; stop it or wait')
            path=reserve_run(self.root,task.get('original_id',task['id']).split('__')[-1]);ident=path.name
            directory=path/'details';directory.mkdir()
            source = directory/('candidate.scl' if target == 'tia' else 'candidate.st')
            if code.strip(): source.write_text(code, encoding='utf-8-sig' if target == 'tia' else 'utf-8')
            from plc_agent.plcverif_backend import configuration
            trial=Trial(directory,task,cfg,vendor_config if target=='tia' else vendor,threading.Event(),
                        formal_config=configuration(self.home),target=target)
            provider = trial
            view = {'id': ident, 'task_id': task['id'], 'model': cfg.model, 'target': target, 'status': 'queued', 'logs': []}
            atomic_json(directory/'run.json', view)
            atomic_json(directory/'task_snapshot.json', task)
            job = {'view': view, 'provider': provider}
            self.jobs[ident] = job
        def worker():
            view['status'] = 'running'
            try:
                if action == 'tia_generate':
                    from plc_agent.campaign import run_self
                    result=run_self(trial)
                elif action == 'tia_check':
                    checked=trial.check(source.read_text(encoding='utf-8-sig'))
                    result=trial.receipt(checked['status'],{'final_evaluation':checked,
                        'target_compile':checked.get('target_compile','not_executed'),
                        'behavior_tested':checked.get('behavior_tested',False),
                        'formal_verification':checked.get('formal_verification'),'ltl_status':checked.get('ltl_status','not_executed')})
                elif action == 'tia':
                    compiled = tia_workflow.compile_candidate(source, task, vendor_config, provider.cancel_event, directory/'compile')
                    result = {**compiled, 'task_id': task['id'], 'model': cfg.model, 'target': 'tia',
                              'dialect': 'siemens_scl', 'final_evaluation': compiled, 'behavior_tested': False,
                              'model_calls': 0, 'ltl_status': 'not_executed'}
                elif action == 'generate':
                    dataset_workflow.normalize_source = normalize_v6
                    result = dataset_workflow.run(task['id'], source, directory, cfg, provider=provider,
                                                  max_revisions=6, review=False, task_override=task,
                                                  evaluator=lambda candidate,t:trial.check(Path(candidate).read_text(encoding='utf-8')),
                                                  notify=lambda message:event(directory,'progress',message=message))
                    result=trial.receipt(result['status'],{'final_evaluation':result.get('final_evaluation'),
                        'target_compile':result.get('target_compile','not_executed'),
                        'formal_verification':result.get('formal_verification'),'ltl_status':result.get('ltl_status','not_executed')})
                elif action == 'codesys':
                    compiled=compile_dataset(source, task, codesys.load_config(self.home), provider.cancel_event)
                    result=trial.receipt(compiled['status'],{'final_evaluation':compiled,
                        'target_compile':compiled.get('target_compile','not_executed'),'ltl_status':'not_executed'})
                else:
                    checked=trial.check(source.read_text(encoding='utf-8'))
                    result=trial.receipt(checked['status'],{'final_evaluation':checked,
                        'target_compile':checked.get('target_compile','not_executed'),
                        'formal_verification':checked.get('formal_verification'),'ltl_status':checked.get('ltl_status','not_executed')})
            except Exception as exc:
                failure = getattr(exc, 'result', {'status': 'interrupted' if isinstance(exc, Cancelled) or provider.cancel_event.is_set() else 'error', 'message': str(exc).replace(cfg.api_key, '[redacted]') if cfg.api_key else str(exc)})
                if trial is not None:
                    result=trial.receipt(failure['status'],{'final_evaluation':failure,'message':failure.get('message','')})
                else:
                    result={**failure, 'task_id': task['id'], 'model': cfg.model, 'target': 'tia',
                            'behavior_tested': False, 'final_evaluation': failure}
            finish(directory,result,task)
            view['status'] = result.get('status', 'error')
            atomic_json(directory/'run.json', view)
        thread=threading.Thread(target=worker,daemon=True);job['thread']=thread;thread.start()
        return {'id':ident}

    def runs(self):
        if not self.root.exists(): return []
        return [self.read_job(p.name,detail=False) for p in sorted(self.root.iterdir(), key=lambda p:p.stat().st_mtime, reverse=True)
                if p.is_dir() and (details_path(p)/'run.json').exists() and not (p/'hidden.json').exists()][:100]

    def start_tia_probe(self):
        from plc_agent.tia_cli import probe
        config = dict(tia.load_config(self.home))
        tia.validate_config(config)
        with self.lock:
            if self.busy(): raise ValueError('请等待当前任务结束再验证 TIA 编译器')
            path = reserve_run(self.root, 'TIA_PROBE'); ident = path.name
            directory = path/'details'; directory.mkdir()
            provider = ChatProvider(self.config())
            view = {'id': ident, 'task_id': 'TIA_PROBE', 'model': '', 'target': 'tia', 'status': 'queued', 'logs': []}
            job = {'view': view, 'provider': provider}; self.jobs[ident] = job
            atomic_json(directory/'run.json', view)
        def worker():
            view['status'] = 'running'
            event(directory, 'progress', message='TIA 正负对照编译中；每次使用独立工程副本')
            try:
                result = probe(config, directory, provider.cancel_event)
            except Exception as exc:
                result = {'status': 'interrupted' if isinstance(exc, Cancelled) else 'error', 'message': str(exc)}
            result.update(task_id='TIA_PROBE', model='', target='tia', behavior_tested=False)
            finish(directory, result)
            view['status'] = result['status']
            atomic_json(directory/'run.json', view)
        thread = threading.Thread(target=worker, daemon=True); job['thread'] = thread; thread.start()
        return {'id': ident}

    def clear_records(self):
        # Hide completed history; retain all source, receipts and evidence on disk.
        with self.lock, self.campaigns.lock:
            if self.campaigns.active or any(j['view']['status'] in ('queued','running') for j in self.jobs.values()):
                raise ValueError('请先停止或等待运行中的任务结束，再清空记录')
            count=0
            for root,name in ((self.root,'run.json'),(self.campaigns.root,'campaign.json')):
                for folder in root.iterdir() if root.exists() else []:
                    record=details_path(folder)/name
                    if not record.is_file():continue
                    marker=folder/'hidden.json'
                    if not marker.exists():
                        atomic_json(marker,{'hidden':True});count+=1
            return {'cleared':count,'evidence_retained':True}


    def busy(self):
        return bool(self.campaigns.active) or any(j['view']['status'] in ('queued','running') for j in self.jobs.values())

    def cancel_and_wait(self,seconds=30):
        import time
        for job in list(self.jobs.values()):job['provider'].cancel()
        for stop in list(self.campaigns.active.values()):stop.set()
        deadline=time.monotonic()+seconds
        threads=[j.get('thread') for j in self.jobs.values()]+list(self.campaigns.threads.values())
        for thread in threads:
            if thread and thread.is_alive():thread.join(max(0,deadline-time.monotonic()))


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def send_json(self, value, status=200):
            data = json.dumps(value, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers(); self.wfile.write(data)
        def allowed(self):
            host = self.headers.get('Host', '')
            expected = '127.0.0.1:' + str(self.server.server_port)
            if host not in (expected, 'localhost:' + str(self.server.server_port)): return False
            origin = self.headers.get('Origin')
            return not origin or origin in ('http://' + expected, 'http://localhost:' + str(self.server.server_port))
        def do_GET(self):
            if not self.allowed(): return self.send_json({'error':'Invalid origin'},403)
            try:
                if self.path == '/api/config': return self.send_json(app.public_config())
                if self.path == '/api/formal/config':
                    from plc_agent.plcverif_backend import environment
                    return self.send_json(environment(app.home))
                if self.path == '/api/codesys/config':
                    cfg=codesys.load_config(app.home)
                    return self.send_json({'configuration':cfg,'saved':(app.home/'codesys.json').is_file(),
                                           'config_file':'agent_data/codesys.json'})
                if self.path == '/api/tia/config':
                    return self.send_json({**tia.doctor(app.home), 'saved':(app.home/'tia.json').is_file(),
                                           'config_file':'agent_data/tia.json'})
                if self.path == '/api/tasks': return self.send_json({'schema':'plc-workbench-catalog-v1','tasks':[]})
                if self.path.startswith('/api/tasks/'):
                    return self.send_json(app.bank.load(self.path.rsplit('/',1)[1]))
                if self.path == '/api/runs': return self.send_json(app.runs())
                if self.path.startswith('/api/run-log/'):
                    ident=self.path.rsplit('/',1)[1]
                    app.read_job(ident)
                    return self.send_json({'text':(app.root/ident/'run.log').read_text(encoding='utf-8')})
                if self.path.startswith('/api/runs/'):
                    return self.send_json(app.read_job(self.path.rsplit('/',1)[1]))
                if self.path == '/api/environment':
                    from plc_probe.config import toolchain_dir
                    from plc_agent.plcverif_backend import environment
                    return self.send_json({'tia':tia.doctor(app.home), 'codesys':codesys.load_config(app.home), 'preflight':preflight(app.home), 'local_backend':str(toolchain_dir()),
                                            'formal':environment(app.home),'formal_status':environment(app.home)['status']})
                if self.path == '/api/campaigns': return self.send_json(app.campaigns.list())
                if self.path.startswith('/api/campaigns/'):
                    return self.send_json(app.campaigns.read(self.path.rsplit('/',1)[1]))
                if self.path.split('?')[0] == '/api/preflight':
                    from urllib.parse import parse_qs, urlsplit
                    required=parse_qs(urlsplit(self.path).query).get('codesys',['true'])[0]!='false'
                    return self.send_json(preflight(app.home,required))
                name = {'/':'index.html','/app.js':'app.js','/style.css':'style.css'}.get(self.path)
                if not name: return self.send_json({'error':'Not found'},404)
                data = (STATIC/name).read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', {'index.html':'text/html; charset=utf-8','app.js':'text/javascript; charset=utf-8','style.css':'text/css; charset=utf-8'}[name])
                self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.end_headers(); self.wfile.write(data)
            except (ValueError,KeyError,OSError) as exc: self.send_json({'error':str(exc)},400)
        def do_POST(self):
            if not self.allowed(): return self.send_json({'error':'Invalid origin'},403)
            try:
                if 'application/json' not in self.headers.get('Content-Type',''): raise ValueError('JSON required')
                size = int(self.headers.get('Content-Length','0'))
                if not 0 < size <= 140000000: raise ValueError('Invalid request size')
                data = json.loads(self.rfile.read(size))
                if self.path == '/api/trial':return self.send_json(app.read_trial(data))
                if self.path == '/api/campaign-preflight':return self.send_json(app.campaign_preflight(data))
                if self.path == '/api/config':
                    if app.campaigns.active or any(j['view']['status'] in ('queued','running') for j in app.jobs.values()):
                        raise ValueError('任务运行期间不能修改模型配置')
                    result = app.save_config(data)
                elif self.path == '/api/tia/config':
                    if app.busy(): raise ValueError('任务运行期间不能修改 TIA 配置')
                    tia.validate_config(data)
                    atomic_json(app.home/'tia.json', data)
                    result = tia.doctor(app.home)
                elif self.path == '/api/tia/probe': result = app.start_tia_probe()
                elif self.path == '/api/codesys/config':
                    if app.campaigns.active:raise ValueError('冻结实验运行期间不能修改 CODESYS 配置')
                    codesys.validate_config(data)
                    atomic_json(app.home/'codesys.json',data)
                    result={'status':'configured_not_probed','configuration':data}
                elif self.path == '/api/formal/config':
                    if app.campaigns.active or any(j['view']['status'] in ('queued','running') for j in app.jobs.values()):
                        raise ValueError('任务运行期间不能修改形式化配置')
                    from plc_agent.plcverif_backend import save_configuration
                    result=save_configuration(data,app.home)
                elif self.path == '/api/codesys/probe':
                    if app.campaigns.active:raise ValueError('批量实验期间不能重复验证编译器')
                    from plc_agent.campaign import validate_vendor_environment
                    directory=app.home/'vendor_checks'/uuid.uuid4().hex
                    validate_vendor_environment(codesys.load_config(app.home),directory,threading.Event())
                    result=json.loads((directory/'environment.json').read_text(encoding='utf-8'))
                elif self.path == '/api/campaigns':
                    if any(j['view']['status'] in ('queued','running') for j in app.jobs.values()):raise ValueError('单题任务运行中')
                    result=app.campaigns.start(data)
                elif self.path == '/api/records/clear': result=app.clear_records()
                elif self.path == '/api/campaigns/stop': result=app.campaigns.stop(data['id'])
                elif self.path == '/api/campaigns/pause':result=app.campaigns.pause(data['id'])
                elif self.path == '/api/campaigns/resume':result=app.campaigns.resume(data['id'])
                elif self.path == '/api/shutdown':
                    if app.busy():raise ValueError('请先结束或完成当前任务；暂停中的实验也需要先结束，关闭服务后不能原地继续。')
                    self.send_json({'status':'closing','message':'记录已保留，下次运行 start.cmd 可查看历史。'})
                    threading.Thread(target=self.server.shutdown,daemon=True).start()
                    return
                elif self.path == '/api/import': result = app.bank.import_files(data['files'],data.get('target'))
                elif self.path == '/api/test':
                    answer = ChatProvider(app.config()).complete([{'role':'user','content':'Reply OK.'}], max_output_tokens=128)
                    result = {'text':answer.get('text'), 'usage':answer.get('usage')}
                elif self.path == '/api/runs': result = app.start(data)
                elif self.path == '/api/stop':
                    job = app.jobs[data['id']]
                    job['provider'].cancel()
                    result = {'status':'stop_requested'}
                else: return self.send_json({'error':'Not found'},404)
                self.send_json(result)
            except Exception as exc:
                key = app.config().api_key
                message = str(exc).replace(key,'[redacted]') if key else str(exc)
                self.send_json({'error':message},400)
    return Handler


def main(argv=None):
    from plc_agent.runtime_env import configure_tools
    configure_tools()
    parser = argparse.ArgumentParser(description='PLC browser workbench (localhost only)')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--open-browser', action='store_true')
    args = parser.parse_args(argv)
    url = f'http://127.0.0.1:{args.port}'
    if args.open_browser:
        import urllib.request
        import webbrowser
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url+'/api/tasks',timeout=2) as response:
                existing = json.load(response)
            if existing.get('schema') in ('plc-dataset-v1','plc-workbench-catalog-v1'):
                webbrowser.open(url)
                print('Opened existing PLC Workbench: '+url+'\nThis terminal does not own the existing server. Close it using the webpage Close service button when idle.')
                return
        except (OSError, ValueError):
            pass
    class LocalServer(ThreadingHTTPServer):
        allow_reuse_address = False
        def server_bind(self):
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()
    app=Workbench()
    server=LocalServer(('127.0.0.1',args.port),make_handler(app))
    print(f'PLC Workbench: {url}\nPress Ctrl+C to stop tasks and close the server. Records stay on disk.',flush=True)
    if args.open_browser:
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
    try: server.serve_forever()
    except KeyboardInterrupt:
        print('Stopping tasks and saving results...',flush=True)
    finally:
        app.cancel_and_wait();server.server_close()

if __name__ == '__main__': main()
