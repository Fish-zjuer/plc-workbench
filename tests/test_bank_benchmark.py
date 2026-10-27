from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from plc_agent.bank_contracts import KNOWN, UNSUPPORTED, interface, protocol, questions, scenarios
from plc_agent.bank_runner import test_bank as execute_bank
from plc_agent.benchmark import Budget
from plc_agent.config import ModelConfig
from plc_agent.provider import ProviderError
from plc_probe.config import cache_dir
from test_agent_provider import LocalAPI,event


class BankTests(unittest.TestCase):
    def test_all_twenty_ids_are_unique_and_protocol_was_frozen(self):
        self.assertEqual([q["id"] for q in questions()],[f"{n:02d}" for n in range(1,21)])
        current=protocol()
        self.assertEqual(len(current["questions"]),20)
        for q in questions():
            if q["id"] not in KNOWN and q["id"] not in UNSUPPORTED:
                self.assertTrue(scenarios(q),q["id"])

    def test_predefined_traces_supply_every_input_and_score_declared_outputs(self):
        for q in questions():
            inputs,outputs=interface(q)
            for case in scenarios(q):
                last=-1
                for row in case["trace"]:
                    self.assertGreater(row["time_ms"],last)
                    last=row["time_ms"]
                    self.assertEqual(set(row["inputs"]),set(inputs),q["id"])
                    self.assertLessEqual(set(row["expected"]),set(outputs),q["id"])

    def test_actual_hysteresis_reference_and_mutant_are_distinguished(self):
        source='''FUNCTION_BLOCK Q03
VAR_INPUT Value : REAL; hiLevel : REAL; loLevel : REAL; hystWindow : REAL; END_VAR
VAR_OUTPUT hiAlarm : BOOL; loAlarm : BOOL; error : BOOL; status : WORD; END_VAR
IF loLevel >= hiLevel THEN error := TRUE; status := 16#8001;
ELSIF hystWindow >= hiLevel-loLevel THEN error := TRUE; status := 16#8002;
ELSE error := FALSE; status := 0;
IF Value > hiLevel THEN hiAlarm := TRUE; ELSIF Value < hiLevel-hystWindow THEN hiAlarm := FALSE; END_IF;
IF Value < loLevel THEN loAlarm := TRUE; ELSIF Value > loLevel+hystWindow THEN loAlarm := FALSE; END_IF;
END_IF;
END_FUNCTION_BLOCK'''
        with tempfile.TemporaryDirectory(dir=cache_dir()) as directory:
            path=Path(directory)/'alarm.st';path.write_text(source,encoding='utf-8')
            self.assertEqual(execute_bank(path,'03')["status"],"pass")
            path.write_text(source.replace('Value < hiLevel-hystWindow','Value <= hiLevel-hystWindow'),encoding='utf-8')
            result=execute_bank(path,'03')
            self.assertEqual(result['status'],'fail')
            self.assertEqual(result['first_failure']['actual'],0)
            self.assertEqual(result['first_failure']['expected'],1)

    def test_budget_guard_reserves_concurrent_work_and_accounts_usage(self):
        budget=Budget(.1)
        reserve=budget.reserve([{'role':'user','content':'hello'}],1024)
        with self.assertRaises(ProviderError):
            budget.reserve([{'role':'user','content':'x'*100000}],8192)
        budget.settle(reserve,{'prompt_tokens':100,'completion_tokens':10})
        self.assertGreater(budget.used,0)
        self.assertEqual(budget.reserved,0)

    def test_extra_body_cannot_overwrite_tool_or_auth_protocol(self):
        config=ModelConfig(base_url='https://example.test',model='custom',extra_body={'thinking':{'type':'disabled'}})
        config.validate()
        with self.assertRaises(ValueError):
            replace(config,extra_body={'messages':[]}).validate()

    def test_reasoning_protocol_roundtrip_is_preserved_without_display(self):
        stream=event({'choices':[{'delta':{'reasoning_content':'protocol-reasoning'}}]})
        stream+=event({'choices':[{'delta':{'content':'ok'},'finish_reason':'stop'}]})+'data: [DONE]\n\n'
        with LocalAPI([(200,'text/event-stream',stream)]) as api:
            provider=api.provider(extra_body={'thinking':{'type':'enabled'}})
            deltas=[]
            result=provider.complete([],on_delta=deltas.append)
            self.assertEqual(result['reasoning_content'],'protocol-reasoning')
            self.assertEqual(deltas,['ok'])
            self.assertEqual(api.requests[0]['body']['thinking'],{'type':'enabled'})


if __name__=='__main__':
    unittest.main()
