import unittest
from plc_agent.config import ModelConfig
from plc_agent.inference import inference_config

class InferenceTests(unittest.TestCase):
    def setUp(self):self.cfg=ModelConfig.dmxapi(model='test',max_output_tokens=16384)
    def test_deepseek_modes(self):
        c=inference_config(self.cfg,'deepseek-v4.1-flash-1017',{'mode':'off'})
        self.assertEqual(c.extra_body['thinking'],{'type':'disabled'})
        c=inference_config(self.cfg,'deepseek-v4.1-flash-1017',{'mode':'high'})
        self.assertEqual(c.extra_body['reasoning_effort'],'high')
        self.assertEqual(c.extra_body['thinking']['type'],'enabled')
    def test_qwen_budget_and_stream(self):
        c=inference_config(self.cfg,'qwen3.8-flash',{'mode':'on','budget':4000})
        self.assertTrue(c.stream);self.assertEqual(c.extra_body,{'enable_thinking':True,'thinking_budget':4000})
    def test_default_preserves_explicit_setting_and_off_removes_conflict(self):
        self.cfg.extra_body={'thinking':{'type':'enabled'},'reasoning_effort':'high'}
        c=inference_config(self.cfg,'deepseek-v4.1-flash-1017')
        self.assertEqual(c.extra_body,self.cfg.extra_body)
        c=inference_config(self.cfg,'deepseek-v4.1-flash-1017',{'mode':'off'})
        self.assertNotIn('reasoning_effort',c.extra_body)
        self.assertEqual(self.cfg.extra_body['reasoning_effort'],'high')
    def test_other_model_requires_explicit_custom_parameters(self):
        with self.assertRaises(ValueError):inference_config(self.cfg,'unknown',{'mode':'high'})
        c=inference_config(self.cfg,'unknown',{'mode':'custom','parameters':{'reasoning_effort':'low'}})
        self.assertEqual(c.extra_body['reasoning_effort'],'low')
    def test_invalid_or_protected_settings_rejected(self):
        for settings in ({'mode':'custom','parameters':{'api_key':'secret'}},{'mode':'on','budget':True},{'mode':'off','budget':4000},{'mode':'high'},{'mode':'on','budget':20000}):
            with self.assertRaises(ValueError):inference_config(self.cfg,'qwen3.8-flash',settings)

if __name__=='__main__':unittest.main()
