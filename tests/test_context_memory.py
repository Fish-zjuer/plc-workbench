from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest

from plc_agent.call_budget import CallBudget
from plc_agent.config import ModelConfig
from plc_agent.context_memory import estimate, user_turn
from plc_agent.engine import Engine
from plc_agent.provider import Cancelled, ProviderError
from plc_agent.storage import Project, Session
from plc_agent.toolbox import Toolbox
from plc_probe.config import cache_dir
from test_agent_core import ScriptedProvider,call


MEMORY={'objective':'实现PLC且保留用户约束','constraints':['停止优先'], 'decisions':[],
        'progress':['已发现失败，未确认修复'],'pending':['回归'],'evidence':['code/a.st SHA-EXAMPLE']}


class Reducer(ScriptedProvider):
    def __init__(self,config,fail_at=None,cancel=None):
        super().__init__([]);self.config=config;self.options=[];self.fail_at=fail_at;self.cancel_on_return=cancel

    def complete(self,messages,tools=None,on_delta=None,**kwargs):
        self.requests.append(copy.deepcopy((messages,tools)));self.options.append(kwargs)
        if estimate(messages)+kwargs['max_output_tokens']>self.config.context_window:
            raise AssertionError('Summary request itself overflowed')
        if self.fail_at==len(self.requests):raise ProviderError('injected transient failure')
        if self.cancel_on_return:self.cancel_on_return()
        return {'text':json.dumps(MEMORY,ensure_ascii=False),'usage':{},'calls':[]}


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=cache_dir());self.addCleanup(self.temp.cleanup)
        self.project=Project.create('记忆回归',Path(self.temp.name));self.session=Session.create(self.project)
        self.config=ModelConfig(base_url='http://localhost:1/v1',model='fixture',context_window=32000,max_output_tokens=2048)

    def engine(self):
        provider=Reducer(self.config)
        return Engine(self.session,self.config,provider),provider

    def history(self,size=12000,turns=6):
        messages=[{'role':'user','content':'旧要求 停止优先 '+('x'*size)},{'role':'assistant','content':'失败待修复'}]
        for i in range(1,turns):messages.extend([{'role':'user','content':f'原文第{i}轮'}, {'role':'assistant','content':f'答复{i}'}])
        return messages

    def test_budget_can_keep_more_than_two_recent_turns(self):
        engine,provider=self.engine();engine.messages=self.history()
        self.assertTrue(engine.compact())
        self.assertEqual(sum(user_turn(m) for m in engine.messages),5)
        self.assertIn('原文第5轮',engine.messages[-2]['content'])
        self.assertIn('read_history',engine.messages[0]['content'])
        self.assertEqual(len(provider.requests),1)

    def test_summary_batches_fit_and_carry_memory_forward(self):
        self.config.context_window=8000;self.config.max_output_tokens=1024
        engine,provider=self.engine();engine.messages=self.history(size=43000,turns=3)
        self.assertTrue(engine.compact())
        self.assertGreater(len(provider.requests),2)
        second=json.loads(provider.requests[1][0][-1]['content'])
        self.assertEqual(second['previous_memory'],MEMORY)
        self.assertLessEqual(max(o['max_output_tokens'] for o in provider.options),2000)
        self.assertEqual(engine.messages[-2]['content'],'原文第2轮')

    def test_single_long_tool_turn_compacts_without_dropping_user_or_breaking_calls(self):
        self.config.context_window=8000;self.config.max_output_tokens=1024
        engine,provider=self.engine()
        def request(ident):return {'role':'assistant','content':None,'tool_calls':[{'id':ident,'type':'function','function':{'name':'read_file','arguments':'{"path":"a.st"}'}}]}
        engine.messages=[{'role':'user','content':'请按本题接口修复，停止优先'},request('old'),
                         {'role':'tool','tool_call_id':'old','content':'old evidence '+('x'*25000)},request('last'),
                         {'role':'tool','tool_call_id':'last','content':'latest failure'}]
        self.assertTrue(engine.compact())
        self.assertEqual(engine.messages[1]['content'],'请按本题接口修复，停止优先')
        self.assertEqual(engine.messages[-2]['tool_calls'][0]['id'],'last')
        self.assertEqual(engine.messages[-1]['tool_call_id'],'last')
        self.assertEqual(self.session.data['working_memory']['strategy'],'tool_transactions')

    def test_cancelled_summary_keeps_original_and_failed_attempt_archive(self):
        engine,provider=self.engine();engine.messages=self.history();original=copy.deepcopy(engine.messages)
        provider.cancel_on_return=engine.cancel
        with self.assertRaises(Cancelled):engine.compact()
        self.assertEqual(engine.messages,original)
        self.assertEqual(self.session.data['compactions'],0)
        self.assertEqual(self.session.data['status'],'interrupted')
        self.assertTrue(list((self.session.path/'compaction_jobs').glob('*.json')))

    def test_interrupted_multibatch_summary_resumes_without_replaying_first_batch(self):
        self.config.context_window=8000;self.config.max_output_tokens=1024
        engine,first=self.engine();engine.messages=self.history(size=43000,turns=3);first.fail_at=2
        original=copy.deepcopy(engine.messages)
        with self.assertRaises(ProviderError):engine.compact()
        self.assertEqual(engine.messages,original)
        resumed=Reducer(self.config);engine.provider=resumed;engine.scoped_provider=CallBudget(resumed,self.config.max_steps)
        self.assertTrue(engine.compact())
        packet=json.loads(resumed.requests[0][0][-1]['content'])
        self.assertEqual(packet['previous_memory'],MEMORY)
        self.assertGreater(packet['new_history'][0]['offset'],0)
        self.assertFalse(list((self.session.path/'compaction_jobs').glob('*.json')))

    def test_bad_summary_types_and_fabricated_overlong_summary_are_rejected(self):
        engine,_=self.engine();engine.messages=self.history()
        for broken in ({**MEMORY,'constraints':'not-a-list'}, {**MEMORY,'objective':'x'*10000}):
            provider=ScriptedProvider([{'text':json.dumps(broken)}]);engine.provider=provider;engine.scoped_provider=CallBudget(provider,24)
            with self.assertRaises(ProviderError):engine.compact()
        self.assertEqual(self.session.data['compactions'],0)

    def test_original_history_search_survives_summary_and_has_stable_pagination(self):
        engine,_=self.engine();engine.messages=self.history()
        for i in range(5):self.session.event('user',text=f'停止优先 原话 {i}')
        engine.compact()
        tools=Toolbox(self.session)
        first=tools.call('read_history',{'query':'停止优先 原话','kind':'user','max_events':2})
        second=tools.call('read_history',{'query':'停止优先 原话','kind':'user','max_events':2,'start_event':first['next_event']})
        self.assertIn('原话 0',first['events'][0]['content'])
        self.assertIn('原话 2',second['events'][0]['content'])
        self.assertTrue(first['has_more'])

    def test_pure_text_after_cancel_is_not_accepted_as_completion(self):
        provider=ScriptedProvider([{'text':'我完成了'},{'text':'新轮次正常'}])
        engine=Engine(self.session,self.config,provider)
        engine.notify=lambda kind,payload:engine.cancel() if kind=='delta' else None
        self.assertEqual(engine.run('执行'),'已停止')
        self.assertFalse(any(e['kind']=='assistant' for e in self.session.events()))
        engine.notify=lambda *_:None
        self.assertEqual(engine.run('继续'),'新轮次正常')

    def test_exact_sha_ledger_keeps_full_original_even_if_model_abbreviates(self):
        sha='12ab'*16
        engine,provider=self.engine();engine.messages=self.history()
        engine.messages[0]['content']='最新文件SHA='+sha+'；旧结果无效。'+('x'*12000)
        engine.compact()
        system=engine.system()['content']
        self.assertIn(sha,system)
        refs=self.session.data['context_references']
        self.assertEqual(refs[-1]['value'],sha)
        self.assertIn('最新文件SHA=',refs[-1]['original_excerpt'])

    def test_cancelled_last_tool_step_is_interrupted_not_step_limit(self):
        self.config.max_steps=1
        provider=ScriptedProvider([call('list_files',{})]);engine=Engine(self.session,self.config,provider)
        engine.notify=lambda kind,payload:engine.cancel() if kind=='tool_start' else None
        engine.run('查看项目')
        self.assertEqual(self.session.data['status'],'interrupted')


if __name__=='__main__':unittest.main()
