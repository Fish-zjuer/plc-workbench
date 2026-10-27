from pathlib import Path
import tempfile
import unittest

from plc_agent.config import ROOT
from plc_agent.struct_checks import test_struct,cases
from plc_probe.config import cache_dir


class StructBridgeTests(unittest.TestCase):
    def test_original_model_outputs_pass_new_supplemental_checks(self):
        for qid in ('07','17'):
            with self.subTest(question=qid):
                result=test_struct(ROOT/'experiments/deepseek_20/tasks'/qid/'final.st',qid)
                self.assertEqual(result['status'],'pass')
                self.assertIn('copy-in/copy-out',result['scope'])

    def test_pump_readonly_config_mutation_is_detected(self):
        code=(ROOT/'experiments/deepseek_20/tasks/07/final.st').read_text(encoding='utf-8')
        mutant=code.replace('END_FUNCTION_BLOCK','pumpGroup[1].priority := 32767;\nEND_FUNCTION_BLOCK')
        with tempfile.TemporaryDirectory(dir=cache_dir()) as directory:
            path=Path(directory)/'mutant.st';path.write_text(mutant,encoding='utf-8')
            result=test_struct(path,'07')
            self.assertEqual(result['status'],'fail')
            self.assertEqual(result['first_failure']['output'],'pump1.priority')

    def test_recipe_state_persists_across_idle_and_capacity_rejects_preserve_it(self):
        result=test_struct(ROOT/'experiments/deepseek_20/tasks/17/final.st','17')
        lifecycle=next(c for c in result['cases'] if c['name']=='lifecycle_and_lowest_free_slot')
        self.assertEqual(lifecycle['rows'][2]['actual']['recipe1.recipeID'],7)
        self.assertEqual(lifecycle['rows'][3]['actual']['recipe1.recipeID'],7)
        capacity=next(c for c in result['cases'] if c['name']=='capacity_and_duplicate_priority')
        self.assertEqual(capacity['rows'][20]['actual']['status'],0x8003)
        self.assertEqual(capacity['rows'][22]['actual']['status'],0x8002)
        self.assertEqual(capacity['rows'][26]['actual']['recipe4.recipeID'],11)

    def test_recipe_lowest_empty_slot_mutant_is_detected(self):
        code=(ROOT/'experiments/deepseek_20/tasks/17/final.st').read_text(encoding='utf-8')
        mutant=code.replace('AND emptySlot = 0','AND TRUE')
        self.assertNotEqual(mutant,code)
        with tempfile.TemporaryDirectory(dir=cache_dir()) as directory:
            path=Path(directory)/'mutant.st';path.write_text(mutant,encoding='utf-8')
            self.assertEqual(test_struct(path,'17')['status'],'fail')


if __name__=='__main__':unittest.main()
