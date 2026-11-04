"""Review proposals cannot silently become ground truth or use a different backend."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from plc_agent import adversarial_review as review, dataset
from plc_probe.backend import BackendError


class Provider:
    def __init__(self, advice):
        self.advice = advice
        self.cancel_event = threading.Event()
        self.messages = []

    def complete(self, messages):
        self.messages.append(messages)
        return {'text': json.dumps(self.advice)}


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root/'candidate.st'
        self.source.write_text('immutable reviewed source', encoding='utf-8')
        self.task = dataset.load('CUSTOM_09')
        self.before = deepcopy(self.task)
        self.advice = {'summary': 'Maintenance exit must not skip waiting.', 'questions': [],
                       'scenarios': [{'name': 'exit', 'basis': 'Requirement 2: maintenance exit moves to state 0.',
                                     'trace': [{'time_ms': 0, 'inputs': {'Maintenance': True, 'CalibDone': True, 'MeasureReq': True},
                                                'expected': {'State': 2}}]}]}

    def tearDown(self):
        self.tmp.cleanup()

    def replay(self, status='fail', **extra):
        return {'status': status, 'source_sha256': hashlib.sha256(self.source.read_bytes()).hexdigest(),
                'test_backend': 'codesys', 'summary': {'scenarios': 1, 'scans': 1, 'failed': int(status == 'fail')},
                'cases': [{'name': 'exit', 'status': status, 'rows': [
                    {**deepcopy(self.advice['scenarios'][0]['trace'][0]), 'actual': {'State': 1 if status == 'fail' else 2},
                     'violations': [{'output': 'State'}] if status == 'fail' else []}]}], **extra}

    def run_review(self, evaluator=None, advice=None, provider=None):
        provider = provider or Provider(advice or self.advice)
        result = review.run(self.task, self.source, self.root/'review', provider,
                            evaluator or (lambda *_: self.replay()), backend='codesys')
        return result, provider

    def test_disagreement_is_advisory_and_uses_isolated_context(self):
        seen = []
        def evaluate(source, proposed):
            seen.append(deepcopy(proposed))
            return self.replay(vendor_evidence='different-'+str(len(seen)))
        result, provider = self.run_review(evaluate)
        self.assertEqual(result['status'], 'review_disagreement')
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0]['scenarios'], self.advice['scenarios'])
        self.assertEqual(self.task, self.before)
        self.assertEqual(self.source.read_text(), 'immutable reviewed source')
        self.assertEqual(result['expected_authority'], 'advisory_model_claim_only')
        packet = json.loads(provider.messages[0][1]['content'])
        self.assertEqual(len(provider.messages[0]), 2)
        self.assertNotIn('scenarios', packet)
        self.assertNotIn('ltl', packet)
        self.assertNotIn('actual_failure', packet)
        self.assertEqual(result['formal_status'], 'not_executed')

    def test_invalid_proposals_never_reach_executor(self):
        invalid = []
        missing = deepcopy(self.advice); del missing['scenarios'][0]['trace'][0]['inputs']['CalibDone']; invalid.append(missing)
        typed = deepcopy(self.advice); typed['scenarios'][0]['trace'][0]['inputs']['Maintenance'] = 1; invalid.append(typed)
        unknown = deepcopy(self.advice); unknown['scenarios'][0]['trace'][0]['expected'] = {'PrivateState': 1}; invalid.append(unknown)
        negative = deepcopy(self.advice); negative['scenarios'][0]['trace'][0]['time_ms'] = -1; invalid.append(negative)
        first = deepcopy(self.advice); first['scenarios'][0]['trace'][0]['time_ms'] = 1; invalid.append(first)
        empty = deepcopy(self.advice); empty['scenarios'][0]['trace'][0]['expected'] = {}; invalid.append(empty)
        long = deepcopy(self.advice); long['scenarios'][0]['trace'] *= 9; invalid.append(long)
        nobasis = deepcopy(self.advice); nobasis['scenarios'][0]['basis'] = ''; invalid.append(nobasis)
        for value in invalid:
            with self.subTest(value=value), patch.object(review, 'functional_replay') as execute:
                result, _ = self.run_review(execute, advice=value)
                self.assertEqual(result['status'], 'review_invalid'); execute.assert_not_called()

    def test_no_finding_and_ambiguity_are_not_proofs(self):
        for questions, expected in (([], 'review_no_findings'), (['Undefined fault policy'], 'review_questions')):
            with patch.object(review, 'functional_replay') as execute:
                result, _ = self.run_review(execute, advice={'summary': 'No justified new trace', 'questions': questions, 'scenarios': []})
                self.assertEqual(result['status'], expected); execute.assert_not_called()

    def test_mismatched_evidence_or_edited_source_is_rejected(self):
        result, _ = self.run_review(lambda *_: self.replay(source_sha256='other'))
        self.assertEqual(result['status'], 'review_invalid')
        result, _ = self.run_review(lambda *_: self.replay(test_backend='optional_local'))
        self.assertEqual(result['status'], 'review_invalid')
        def edit(*_):
            self.source.write_text('edited')
            return self.replay()
        result, _ = self.run_review(edit)
        self.assertEqual(result['status'], 'review_invalid')

    def test_non_deterministic_outputs_and_tool_errors(self):
        values = iter([self.replay('pass'), self.replay('fail')])
        result, _ = self.run_review(lambda *_: next(values))
        self.assertEqual(result['status'], 'review_non_deterministic')
        def broken(*_):
            raise BackendError({'status': 'timeout'})
        result, _ = self.run_review(broken)
        self.assertEqual(result['status'], 'review_tool_error')
        self.assertEqual(result['failure']['status'], 'timeout')
        with patch.object(Provider, 'complete', side_effect=review.ProviderError('HTTP 429')):
            result, _ = self.run_review()
        self.assertEqual(result['status'], 'review_model_error')

    def test_cancel_preserves_partial_evidence(self):
        provider = Provider(self.advice)
        def cancel(*_):
            provider.cancel_event.set()
            return self.replay()
        result, _ = self.run_review(cancel, provider=provider)
        self.assertEqual(result['status'], 'interrupted')
        self.assertTrue((self.root/'review/review.json').exists())

    def test_success_flags_without_observations_are_not_evidence(self):
        result, _ = self.run_review(lambda *_: self.replay('pass', cases=[]))
        self.assertEqual(result['status'], 'review_invalid')
        values = iter([self.replay(execution_fingerprint='first'), self.replay(execution_fingerprint='changed')])
        result, _ = self.run_review(lambda *_: next(values))
        self.assertEqual(result['status'], 'review_invalid')

    def test_complex_interfaces_do_not_silently_use_local_abi(self):
        self.task = dataset.load('PUBLIC_18')
        result, provider = self.run_review()
        self.assertEqual(result['status'], 'review_unsupported')
        self.assertEqual(provider.messages, [])

    def test_vendor_replay_never_falls_back_to_native_or_runs_formal(self):
        stop = threading.Event(); cfg = {'dedicated': 'vendor template'}
        with patch('plc_agent.codesys_dataset.compile_dataset', return_value={'target_compile': 'passed'}) as compile_, \
             patch('plc_agent.codesys_tests.evaluate', return_value=self.replay()) as execute, \
             patch('plc_agent.dataset.evaluate', side_effect=AssertionError('Native fallback forbidden')), \
             patch('plc_agent.dataset_formal.attach', side_effect=AssertionError('Advisory traces do not prove frozen LTL')):
            result = review.functional_replay(self.source, self.task, cfg, stop)
        self.assertEqual(result['test_backend'], 'codesys')
        compile_.assert_called_once_with(self.source, self.task, cfg, stop)
        execute.assert_called_once_with(self.source, self.task, cfg, stop)


if __name__ == '__main__':
    unittest.main()
