from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest

from plc_agent.config import ModelConfig
from plc_agent.engine import Engine,reconcile_tools
from plc_agent.provider import ChatProvider,ProviderError
from plc_agent.provider import Cancelled
from plc_agent.storage import Project,Session,atomic_json
from plc_agent.workflow import PLCWorkflow
from plc_probe.config import cache_dir
from test_agent_core import ScriptedProvider,call
from test_agent_provider import LocalAPI,event


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=cache_dir());self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name);self.project=Project.create('恢复项目',self.home);self.session=Session.create(self.project)
        self.config=ModelConfig(base_url='http://localhost:1/v1',model='fixture')

    def test_constructor_never_overwrites_an_active_sessions_status_or_context(self):
        atomic_json(self.session.path/'context.json',{'messages':[{'role':'assistant','content':None,'tool_calls':[
            {'id':'unfinished','type':'function','function':{'name':'write_file','arguments':'{}'}}]}]})
        self.session.data['status']='running';self.session.save()
        context=(self.session.path/'context.json').read_bytes();state=(self.session.path/'session.json').read_bytes()
        with self.session.lease():
            other=Session.load(self.project,self.session.data['id'])
            engine=Engine(other,self.config,ScriptedProvider([]))
            self.assertIn('interrupted',engine.messages[1]['content'])
            self.assertEqual(context,(self.session.path/'context.json').read_bytes())
            self.assertEqual(state,(self.session.path/'session.json').read_bytes())

    def test_second_open_engine_reloads_new_history_after_project_lease(self):
        one=Engine(self.session,self.config,ScriptedProvider([{'text':'第一轮已记录'}]))
        second_provider=ScriptedProvider([{'text':'第二轮已记录'}])
        two=Engine(Session.load(self.project,self.session.data['id']),self.config,second_provider)
        one.run('用户先前的要求：停止优先')
        two.run('现在继续')
        request=second_provider.requests[0][0]
        self.assertIn('用户先前的要求：停止优先',[m.get('content') for m in request])
        self.assertEqual(len([m for m in two.messages if m['role']=='user']),2)

    def test_restoring_older_project_and_session_persists_selection(self):
        older=self.session;new=Session.create(self.project)
        another=Project.create('另一个较新项目',self.home);Session.create(another)
        older.activate()
        self.assertEqual(Project.load(self.project.data['id'],self.home).data['last_session'],older.data['id'])
        self.assertEqual(Project.list(self.home)[0]['id'],self.project.data['id'])

    def test_tool_ids_reused_later_do_not_hide_an_unanswered_old_call(self):
        request={'role':'assistant','content':None,'tool_calls':[{'id':'same','function':{'name':'read_file','arguments':'{}'}}]}
        recovered=reconcile_tools([copy.deepcopy(request),{'role':'user','content':'new'},copy.deepcopy(request),{'role':'tool','tool_call_id':'same','content':'new result'}])
        self.assertEqual(recovered[1]['role'],'tool');self.assertIn('interrupted',recovered[1]['content'])
        self.assertEqual(recovered[-1]['content'],'new result')

    def test_stop_during_tool_start_does_not_write(self):
        self.session.data['mode']='execute'
        engine=Engine(self.session,self.config,ScriptedProvider([call('write_file',{'path':'never.st','content':'x'})]))
        engine.notify=lambda kind,payload:engine.cancel() if kind=='tool_start' else None
        engine.run('写入文件')
        self.assertFalse((self.project.workspace/'never.st').exists())
        self.assertEqual(self.session.data['status'],'interrupted')

    def test_invalid_configuration_types_fail_with_useful_validation_errors(self):
        for config in (ModelConfig(context_window='large'),ModelConfig(max_steps=True),ModelConfig(extra_body={'p':float('nan')}),ModelConfig(compact_target_ratio=float('nan'))):
            with self.subTest(config=config):
                with self.assertRaises(ValueError):config.validate(require_ready=False)
        atomic_json(self.home/'config.json',[])
        with self.assertRaisesRegex(ValueError,'JSON对象'):ModelConfig.load(self.home)

    def test_event_log_after_partial_crash_keeps_next_valid_message(self):
        self.session.event('user',text='先前完整记录')
        with (self.session.path/'events.jsonl').open('ab') as stream:stream.write(b'{"partial":')
        self.session.event('assistant',text='重启后新记录')
        self.assertEqual([e['text'] for e in self.session.events()],['先前完整记录','重启后新记录'])
        broken=self.home/'projects'/'123456abcdef';broken.mkdir()
        atomic_json(broken/'project.json',[])
        self.assertEqual([p['id'] for p in Project.list(self.home)],[self.project.data['id']])

    def test_per_request_summary_output_limit_reaches_actual_http(self):
        response=json.dumps({'choices':[{'message':{'content':'ok'},'finish_reason':'stop'}]})
        with LocalAPI([(200,'application/json',response)]) as api:
            api.provider(stream=False).complete([],max_output_tokens=512)
            self.assertEqual(api.requests[0]['body']['max_tokens'],512)

    def test_switching_native_history_to_json_does_not_send_native_tool_roles(self):
        messages=[{'role':'assistant','content':None,'reasoning_content':'private vendor protocol',
                   'tool_calls':[{'id':'old','type':'function','function':{'name':'list_files','arguments':'{}'}}]},
                  {'role':'tool','tool_call_id':'old','content':'{"status":"ok"}'}]
        response=json.dumps({'choices':[{'message':{'content':'ok'},'finish_reason':'stop'}]})
        with LocalAPI([(200,'application/json',response)]) as api:
            api.provider(tool_mode='json',stream=False).complete(messages)
            wire=api.requests[0]['body']['messages']
            self.assertEqual([m['role'] for m in wire],['assistant','user'])
            self.assertNotIn('reasoning_content',wire[0]);self.assertNotIn('tool_calls',wire[0])
        self.assertIn('tool_calls',messages[0])

    def test_duplicate_tool_ids_and_done_without_finish_are_rejected(self):
        provider=ChatProvider(self.config)
        repeated={'id':'same','function':{'name':'list_files','arguments':'{}'}}
        with self.assertRaisesRegex(ProviderError,'重复'):
            provider._normalize({'tool_calls':[repeated,repeated]}, {},'tool_calls')
        stream=event({'choices':[{'delta':{'content':'unfinished'}}]})+'data: [DONE]\n\n'
        with LocalAPI([(200,'text/event-stream',stream)]) as api:
            with self.assertRaisesRegex(ProviderError,'提前中断'):api.provider().complete([])

    def test_delayed_cancel_close_cannot_close_a_later_request(self):
        gate=threading.Event();closed=threading.Event()
        class Old:
            def close(self):gate.wait(2);closed.set()
        class New:
            def __init__(self):self.closed=False
            def close(self):self.closed=True
        provider=ChatProvider(self.config);provider._response=Old();provider.cancel()
        self.assertTrue(provider.cancel_event.is_set())
        provider.cancel_event.clear();new=New();provider._response=new;gate.set()
        self.assertTrue(closed.wait(2));self.assertFalse(new.closed)
        self.assertFalse(provider.cancel_event.is_set())

    def test_planned_workflow_preserves_custom_source_for_later_execution(self):
        result=PLCWorkflow(self.session,ModelConfig()).run('05',source='code/seam.st')
        self.assertEqual(result['status'],'planned')
        self.assertEqual(self.session.data['planned_task']['source'],'code/seam.st')
        continued=PLCWorkflow(self.session,ModelConfig()).run('05')
        self.assertEqual(self.session.data['planned_task']['source'],'code/seam.st')

    def test_known_backend_gap_stops_before_generating_an_unverifiable_stub(self):
        from plc_agent.backend_capabilities import preflight
        from plc_agent.bank_contracts import questions
        question=next(q for q in questions() if q['id']=='18')
        if preflight(question) is None:self.skipTest('Pinned backend fingerprint differs')
        self.session.data['mode']='execute';provider=ScriptedProvider([])
        result=PLCWorkflow(self.session,self.config,provider).run('18')
        self.assertEqual(result['status'],'backend_variant_unavailable')
        self.assertEqual(provider.requests,[])
        self.assertFalse((self.project.workspace/'candidate.st').exists())
        self.assertEqual(result['backend_preflight']['candidate_correctness'],'not_established')

    def test_fifo_missing_data_access_is_exposed_separately_from_backend_gap(self):
        from plc_agent.backend_capabilities import candidate_warnings
        from plc_agent.config import ROOT
        code=(ROOT/'experiments/workflow_r2/tasks/18/final.st').read_text(encoding='utf-8')
        warning=candidate_warnings(code,'18')
        self.assertEqual(warning[0]['fields'],['item','buffer'])

    def test_workflow_cancel_saves_receipt_without_writing_model_source(self):
        self.session.data['mode']='execute'
        from plc_agent.bank_contracts import block,questions
        from plc_agent.workflow import interface_contract
        question=next(q for q in questions() if q['id']=='03')
        provider=ScriptedProvider([Cancelled('stopped')])
        with self.assertRaises(Cancelled):PLCWorkflow(self.session,self.config,provider).run('03')
        receipt=self.session.data['last_workflow']
        self.assertEqual(receipt['status'],'interrupted')
        self.assertTrue((self.project.workspace/receipt['run_path']/'receipt.json').is_file())
        self.assertFalse((self.project.workspace/'candidate.st').exists())


if __name__=='__main__':unittest.main()
