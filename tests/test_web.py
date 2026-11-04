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
            result=self.request('/api/config',{'base_url':'https://example.test/v1','model':'exact/model-id','api_key':'test-secret','stream':False})
            self.assertNotIn('test-secret', result)
            cfg=self.app.config()
            self.assertEqual(cfg.endpoint,'https://example.test/v1/chat/completions')
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
            self.app.save_config({'base_url':'https://different.test/v1','model':'new'})
            self.assertEqual(self.app.config().api_key,'')
            self.assertEqual(self.app.config().base_url,'https://different.test/v1')
    def test_generic_provider_roundtrip_preserves_transport_and_context_settings(self):
        cfg=ModelConfig(base_url='http://localhost:9988/v1',model='local',api_key='',timeout=120,
                        context_window=64000,max_output_tokens=16000,extra_body={'temperature':.2})
        cfg.save(self.app.home)
        value=json.loads(self.request('/api/config',{'model':'renamed','stream':True}))
        self.assertFalse(value['has_api_key'])
        saved=self.app.config()
        self.assertEqual((saved.base_url,saved.timeout,saved.context_window,saved.max_output_tokens),(cfg.base_url,120,64000,16000))
        self.assertEqual(saved.extra_body,{'temperature':.2})
        self.assertTrue(saved.stream)
    def test_empty_service_and_wrong_boolean_do_not_mutate_saved_config(self):
        self.assertEqual(self.app.config().base_url,'')
        for data in ({'model':'m'},{'base_url':'https://example.test/v1','model':'m','stream':'false'}):
            with self.assertRaises(urllib.error.HTTPError):self.request('/api/config',data)
        self.assertFalse((self.app.home/'config.json').exists())
    def test_model_configuration_is_frozen_during_single_run(self):
        self.app.jobs['fixture']={'view':{'status':'running'}}
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/config',{'base_url':'https://example.test/v1','model':'m'})
        self.assertFalse((self.app.home/'config.json').exists())
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
    def test_settings_read_codesys_configuration_without_running_preflight(self):
        with patch('plc_agent.web.preflight',side_effect=AssertionError('No preflight during form load')):
            state=json.loads(self.request('/api/codesys/config'))
        self.assertEqual(state['configuration'],{});self.assertFalse(state['saved'])
        self.assertIn('codesys.json',state['config_file'])
    def test_usage_missing_is_explicit(self):
        self.assertFalse(usage_totals([{'usage':{}}])['complete'])
        totals=usage_totals([{'usage':{'prompt_tokens':3,'completion_tokens':4,'total_tokens':7}}])
        self.assertTrue(totals['complete']); self.assertEqual(totals['total_tokens'],7)
        self.assertIsNone(totals['cost']);self.assertFalse(totals['cost_complete'])
        free=usage_totals([{'usage':{'total_tokens':1,'cost':0}}])
        self.assertEqual(free['cost'],0);self.assertTrue(free['cost_complete'])
        partial=usage_totals([{'usage':{'cost':.12}},{'usage':{}}])
        self.assertIsNone(partial['cost']);self.assertEqual(partial['recorded_cost'],.12)
    def test_review_http_keeps_baseline_metrics_and_persists_independent_result(self):
        from plc_agent import dataset
        task=dataset.load('CUSTOM_09')
        ModelConfig(base_url='http://localhost:9911/v1',model='author').save(self.app.home)
        source=(Path(__file__).parent/'fixtures/dataset_r8/tasks/CUSTOM_09/final.st').read_text(encoding='utf-8')
        calls=[]
        def answer(provider,messages,*args,**kwargs):
            calls.append((provider.config.model,messages))
            provider.metrics.append({'usage':{'total_tokens':10}})
            return {'text':json.dumps({'summary':'No new justified counterexample','questions':['Unspecified failure policy'], 'scenarios':[]})}
        checked={'status':'pass','summary':{'scenarios':25,'failed':0},'target_compile':'not_executed'}
        with patch('plc_agent.local_test_support.backend'),patch('plc_agent.campaign.Trial.check',return_value=checked), \
             patch.object(ChatProvider,'complete',answer),patch('plc_agent.dataset_workflow.run',side_effect=AssertionError('Review must not run the author')):
            result=json.loads(self.request('/api/runs',{'task_id':task['id'],'action':'review',
                'code':source,'codesys':False,'review_model':'independent-reviewer'}))
            self.app.jobs[result['id']]['thread'].join(10)
        detail=json.loads(self.request('/api/runs/'+result['id']))
        self.assertEqual(detail['status'],'review_questions')
        self.assertEqual(detail['receipt']['metrics_summary']['test_cases_passed'],25)
        self.assertEqual(detail['receipt']['model_calls'],1)
        self.assertEqual(detail['receipt']['review']['status'],'review_questions')
        self.assertEqual(calls[0][0],'independent-reviewer');self.assertEqual(len(calls[0][1]),2)
        self.assertEqual(detail['code'],source)
        restarted=Workbench(self.app.home).read_job(result['id'])
        self.assertEqual(restarted['receipt']['review'],detail['receipt']['review'])
    def test_review_requires_source_and_valid_model_before_creating_job(self):
        ModelConfig(base_url='http://localhost:9911/v1',model='author').save(self.app.home)
        with patch('plc_agent.local_test_support.backend'),patch.object(ChatProvider,'complete') as complete:
            for values in ({'code':''},{'code':'x','review_model':False}):
                with self.assertRaises(urllib.error.HTTPError):
                    self.request('/api/runs',{'task_id':'CUSTOM_09','action':'review','codesys':False,**values})
        complete.assert_not_called();self.assertEqual(self.app.jobs,{})
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

