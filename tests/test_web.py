"""HTTP tests for the local web/API boundary, without paid model calls."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from plc_agent.config import ModelConfig
from plc_agent.web import Workbench, make_handler
from plc_agent.provider import ChatProvider
from plc_agent.dataset_workflow import usage_totals
from tests.test_agent_provider import LocalAPI

class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Workbench(Path(self.tmp.name))
        self.server = ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()
    def request(self,path,data=None,origin=None):
        headers = {'Content-Type':'application/json'}
        if origin: headers['Origin']=origin
        req=urllib.request.Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        with urllib.request.urlopen(req) as r: return r.read().decode('utf-8-sig')
    def test_config_keeps_key_server_side(self):
        with patch.dict('os.environ',{'DMXAPI_API_KEY':''}):
            result=self.request('/api/config',{'model':'exact/model-id','api_key':'test-secret','stream':False})
            self.assertNotIn('test-secret', result)
            cfg=self.app.config()
            self.assertEqual(cfg.endpoint,'https://www.dmxapi.cn/v1/chat/completions')
            self.assertFalse(cfg.stream)
            self.assertEqual(cfg.api_key,'test-secret')
            self.assertEqual(cfg.extra_body,{})
            self.assertEqual(cfg.comparison_model,'qwen3.8-flash')
            result=json.loads(self.request('/api/config',{'model':'model-a','comparison_model':'my-model-b'}))
            self.assertEqual(result['comparison_model'],'my-model-b')
            self.assertEqual(ModelConfig.load(self.app.home).comparison_model,'my-model-b')
            saved=json.loads((self.app.home/'config.json').read_text(encoding='utf-8'))
            self.assertEqual((saved['model'],saved['comparison_model']),('model-a','my-model-b'))
            with self.assertRaises(urllib.error.HTTPError):
                self.request('/api/config',{'model':'model-a','comparison_model':'undefined'})
            self.assertEqual(ModelConfig.load(self.app.home).comparison_model,'my-model-b')
    def test_no_cross_provider_key_reuse(self):
        ModelConfig(base_url='https://example.test/v1',model='old',api_key='other-secret').save(self.app.home)
        with patch.dict('os.environ',{'DMXAPI_API_KEY':''}):
            self.app.save_config({'model':'new'})
            self.assertEqual(self.app.config().api_key,'')
    def test_ui_and_bank(self):
        self.assertIn('PLC Workbench',self.request('/'))
        tasks=json.loads(self.request('/api/tasks'))['tasks']
        self.assertEqual(len(tasks),0)
        from plc_agent import dataset
        task=dataset.load('PUBLIC_01')
        result=json.loads(self.request('/api/import',{'files':[{'name':'my-tasks.json','content':json.dumps({'tasks':[task]})}]}))
        self.assertEqual(result['count'],1)
        self.assertEqual(json.loads(self.request('/api/tasks'))['tasks'],[])
        self.assertIn('requirements',self.app.bank.load(result['tasks'][0]['id']))
        detail=json.loads(self.request('/api/tasks/PUBLIC_01'))
        self.assertIn('requirements',detail)
        self.assertIn('ltl',detail)
    def test_cross_origin_and_paths_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.request('/api/config',{},'https://example.test')
        self.assertEqual(e.exception.code,403)
        with self.assertRaises(urllib.error.HTTPError): self.request('/api/runs/../../private')

    def test_campaign_preflight_checks_current_form_without_model_calls(self):
        data={'models':['deepseek-v4.1-flash-1017','qwen3.8-flash'],
              'model_settings':[{'mode':'off'},{'mode':'on','budget':1000}],
              'task_ids':['CUSTOM_09'],'concurrency':16,'codesys':True}
        with patch('plc_agent.web.preflight',return_value={'status':'ready','errors':[]}),patch.object(ChatProvider,'complete') as complete:
            result=json.loads(self.request('/api/campaign-preflight',data))
        self.assertEqual(result['total'],4);self.assertEqual(result['effective_concurrency'],4)
        self.assertEqual(result['model_calls'],0);complete.assert_not_called()
        data['model_settings'][1]={'mode':'on','budget':999999}
        with patch('plc_agent.web.preflight') as local:
            result=json.loads(self.request('/api/campaign-preflight',data))
        self.assertEqual(result['status'],'setup_required');local.assert_not_called()
        self.assertTrue(result['errors'])
    def test_first_formal_setup_does_not_require_an_existing_config(self):
        with patch('plc_agent.plcverif_backend.discover_tools',return_value={k:'' for k in ('plcverif','java','cbmc','nuxmv')}):
            state=json.loads(self.request('/api/formal/config'))
        self.assertEqual(state['status'],'not_configured');self.assertFalse(state['saved'])
        self.assertFalse((self.app.home/'formal_config.json').exists())
        paths={}
        for name in ('plcverif','java','cbmc'):
            executable=self.app.home/(name+'.exe');executable.write_bytes(b'fixture');paths[name]=str(executable)
        saved=json.loads(self.request('/api/formal/config',{'engine':'cbmc',**paths,'bound':10}))
        self.assertEqual(saved['status'],'tools_ready');self.assertTrue(saved['saved'])
        loaded=json.loads(self.request('/api/formal/config'))
        self.assertEqual(loaded['plcverif'],paths['plcverif']);self.assertEqual(loaded['bound'],10)
    def test_usage_missing_is_explicit(self):
        self.assertFalse(usage_totals([{'usage':{}}])['complete'])
        totals=usage_totals([{'usage':{'prompt_tokens':3,'completion_tokens':4,'total_tokens':7}}])
        self.assertTrue(totals['complete']); self.assertEqual(totals['total_tokens'],7)
    def test_shutdown_refuses_active_work_and_can_close_idle_service(self):
        self.app.campaigns.active['fixture']=threading.Event()
        with self.assertRaises(urllib.error.HTTPError) as rejected:self.request('/api/shutdown',{})
        self.assertEqual(rejected.exception.code,400)
        self.app.campaigns.active.clear()
        result=json.loads(self.request('/api/shutdown',{}))
        self.assertEqual(result['status'],'closing')
    def test_stream_requests_usage(self):
        payload='data: '+json.dumps({'choices':[{'delta':{'content':'OK'},'finish_reason':'stop'}]})+'\n\n'
        payload+='data: '+json.dumps({'choices':[],'usage':{'prompt_tokens':3,'completion_tokens':1,'total_tokens':4}})+'\n\n'
        payload+='data: [DONE]\n\n'
        with LocalAPI([(200,'text/event-stream',payload)]) as local:
            cfg=ModelConfig(base_url='http://127.0.0.1:'+str(local.server.server_port),model='exact-id')
            answer=ChatProvider(cfg).complete([{'role':'user','content':'hi'}])
            self.assertEqual(answer['usage']['total_tokens'],4)
            self.assertTrue(local.requests[0]['body']['stream_options']['include_usage'])

if __name__=='__main__': unittest.main()

