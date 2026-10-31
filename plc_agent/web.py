"""Loopback-only web workbench over the existing frozen bank workflow."""
from __future__ import annotations
import argparse
from dataclasses import replace
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import socket
import uuid

from . import dataset, dataset_workflow
from .bank32_v6 import normalize_v6
from .config import ModelConfig, STATE_ROOT, ROOT
from .provider import ChatProvider
from .imported_bank import ImportedBank
from .campaign import Campaigns, preflight
from . import codesys
from .codesys_dataset import compile_dataset
from .storage import atomic_json, read_json

STATIC = Path(__file__).with_name('web_static')

class Workbench:
    def __init__(self, home=STATE_ROOT):
        self.home = Path(home)
        self.bank = ImportedBank(self.home)
        self.campaigns = Campaigns(self.home)
        self.root = self.home / 'web_runs'
        self.jobs = {}
        self.lock = threading.Lock()

    def config(self):
        cfg = ModelConfig.load(self.home)
        return cfg if cfg.base_url else ModelConfig.dmxapi()

    def public_config(self):
        cfg = self.config()
        return {**cfg.public(), 'has_api_key': bool(cfg.api_key)}

    def save_config(self, data):
        old = self.config()
        # Keys remain on the server and are never returned by this API.
        cfg = ModelConfig.dmxapi(model=data.get('model', '').strip(),
                                api_key=data.get('api_key') or (old.api_key if old.base_url.rstrip('/') == 'https://www.dmxapi.cn/v1' else ''),
                                stream=bool(data.get('stream', False)),
                                timeout=180, context_window=128000, max_output_tokens=16384)
        cfg.validate()
        cfg.save(self.home)
        return self.public_config()

    def read_job(self, ident):
        if not isinstance(ident, str) or len(ident) != 32 or any(c not in '0123456789abcdef' for c in ident):
            raise ValueError('Invalid run ID')
        path = self.root / ident
        job = self.jobs.get(ident)
        saved = read_json(path/'run.json') if (path/'run.json').exists() else None
        if not job and not saved:
            raise ValueError('Unknown run')
        value = dict(job['view']) if job else {**saved, 'status': 'interrupted'}
        if (path/'receipt.json').exists():
            value['receipt'] = read_json(path/'receipt.json')
            if not job: value['status'] = value['receipt']['status']
        if (path/'candidate.st').exists(): value['code'] = (path/'candidate.st').read_text(encoding='utf-8')
        value['versions'] = [{'name': f.name, 'code': f.read_text(encoding='utf-8')}
                             for f in sorted(path.glob('proposal_*.st'))]
        return value

    def start(self, data):
        task = self.bank.load(data['task_id'])
        action = data.get('action', 'generate')
        if action not in ('generate', 'check', 'codesys'): raise ValueError('Unknown action')
        code = data.get('code', '')
        if not isinstance(code, str) or len(code) > 200000: raise ValueError('ST source too large')
        cfg = self.config()
        if data.get('model'): cfg = replace(cfg, model=data['model'])
        if action == 'generate': cfg.validate()
        with self.lock:
            if self.campaigns.active: raise ValueError('批量实验运行中，请等待结束')
            if any(j['view']['status'] in ('queued', 'running') for j in self.jobs.values()):
                raise ValueError('A task is already running; stop it or wait')
            ident = uuid.uuid4().hex
            path = self.root/ident
            path.mkdir(parents=True)
            source = path/'candidate.st'
            if code.strip(): source.write_text(code, encoding='utf-8')
            provider = ChatProvider(cfg)
            view = {'id': ident, 'task_id': task['id'], 'model': cfg.model, 'status': 'queued', 'logs': []}
            atomic_json(path/'run.json', view)
            atomic_json(path/'task_snapshot.json', task)
            job = {'view': view, 'provider': provider}
            self.jobs[ident] = job
        def worker():
            view['status'] = 'running'
            try:
                if action == 'generate':
                    dataset_workflow.normalize_source = normalize_v6
                    result = dataset_workflow.run(task['id'], source, path, cfg, provider=provider,
                                                  max_revisions=5, review=False, task_override=task,
                                                  notify=lambda message: view['logs'].append(str(message)))
                elif action == 'codesys':
                    result=compile_dataset(source, task, codesys.load_config(self.home), provider.cancel_event)
                    atomic_json(path/'receipt.json',result)
                else:
                    if task.get('scenarios'):
                        result = dataset_workflow.compact(dataset.evaluate(source, task))
                    else:
                        dataset.compile_task(source,task)
                        result = {'status':'compiled_without_tests','message':'No functional tests supplied'}
                    result = {'task_id': task['id'], 'status': result['status'],
                              'final_evaluation': result, 'target_compile': 'not_executed',
                              'ltl_status': 'requirements_only_not_executed'}
                    atomic_json(path/'receipt.json', result)
                view['status'] = result['status']
            except Exception as exc:
                result = getattr(exc, 'result', {'status': 'error', 'message': str(exc).replace(cfg.api_key, '[redacted]') if cfg.api_key else str(exc)})
                atomic_json(path/'receipt.json', result)
                view['status'] = result.get('status', 'error')
            atomic_json(path/'run.json', view)
        threading.Thread(target=worker, daemon=True).start()
        return {'id': ident}

    def runs(self):
        if not self.root.exists(): return []
        return [self.read_job(p.name) for p in sorted(self.root.iterdir(), key=lambda p:p.stat().st_mtime, reverse=True)
                if p.is_dir() and (p/'run.json').exists() and not (p/'hidden.json').exists()][:100]

    def clear_records(self):
        # Hide completed history; retain all source, receipts and evidence on disk.
        with self.lock, self.campaigns.lock:
            if self.campaigns.active or any(j['view']['status'] in ('queued','running') for j in self.jobs.values()):
                raise ValueError('请先停止或等待运行中的任务结束，再清空记录')
            count=0
            for root,name in ((self.root,'run.json'),(self.campaigns.root,'campaign.json')):
                for record in root.glob('*/'+name):
                    marker=record.parent/'hidden.json'
                    if not marker.exists():
                        atomic_json(marker,{'hidden':True});count+=1
            return {'cleared':count,'evidence_retained':True}


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
                if self.path == '/api/tasks': return self.send_json({'schema':'plc-workbench-catalog-v1','tasks':[]})
                if self.path.startswith('/api/tasks/'):
                    return self.send_json(app.bank.load(self.path.rsplit('/',1)[1]))
                if self.path == '/api/runs': return self.send_json(app.runs())
                if self.path.startswith('/api/runs/'):
                    return self.send_json(app.read_job(self.path.rsplit('/',1)[1]))
                if self.path == '/api/environment':
                    from plc_probe.config import toolchain_dir
                    return self.send_json({'codesys':codesys.load_config(app.home), 'preflight':preflight(app.home), 'local_backend':str(toolchain_dir()),
                                           'formal_status':'not_executed'})
                if self.path == '/api/campaigns': return self.send_json(app.campaigns.list())
                if self.path.startswith('/api/campaigns/'):
                    return self.send_json(app.campaigns.read(self.path.rsplit('/',1)[1]))
                if self.path == '/api/preflight': return self.send_json(preflight(app.home))
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
                if self.path == '/api/config':
                    if app.campaigns.active: raise ValueError('冻结实验运行期间不能修改配置')
                    result = app.save_config(data)
                elif self.path == '/api/codesys/config':
                    if app.campaigns.active:raise ValueError('冻结实验运行期间不能修改 CODESYS 配置')
                    codesys.validate_config(data)
                    atomic_json(app.home/'codesys.json',data)
                    result={'status':'configured_not_probed','configuration':data}
                elif self.path == '/api/codesys/probe':
                    if app.campaigns.active:raise ValueError('批量实验期间不能重复验证编译器')
                    from .campaign import validate_vendor_environment
                    directory=app.home/'vendor_checks'/uuid.uuid4().hex
                    validate_vendor_environment(codesys.load_config(app.home),directory,threading.Event())
                    result=json.loads((directory/'environment.json').read_text(encoding='utf-8'))
                elif self.path == '/api/campaigns':
                    if any(j['view']['status'] in ('queued','running') for j in app.jobs.values()):raise ValueError('单题任务运行中')
                    result=app.campaigns.start(data)
                elif self.path == '/api/records/clear': result=app.clear_records()
                elif self.path == '/api/campaigns/stop': result=app.campaigns.stop(data['id'])
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
    from .runtime_env import configure_tools
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
            with urllib.request.urlopen(url + '/api/tasks', timeout=2) as response:
                existing = json.load(response)
            if existing.get('schema') in ('plc-dataset-v1','plc-workbench-catalog-v1'):
                webbrowser.open(url)
                print('Opened existing PLC Workbench: ' + url)
                return
        except (OSError, ValueError):
            pass
    class LocalServer(ThreadingHTTPServer):
        allow_reuse_address = False
        def server_bind(self):
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()
    server = LocalServer(('127.0.0.1',args.port),make_handler(Workbench()))
    print(f'PLC Workbench: {url}',flush=True)
    if args.open_browser:
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__ == '__main__': main()
