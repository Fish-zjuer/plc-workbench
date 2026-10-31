import copy
import unittest
from plc_agent import dataset

class ImportedExecutionTests(unittest.TestCase):
    def test_preloaded_struct_data_is_identical_after_import(self):
        original=dataset.load('PUBLIC_17')
        imported=copy.deepcopy(original)
        imported['original_id']='PUBLIC_17'
        imported['id']='IMPORT_example__PUBLIC_17'
        a=dataset.commands(original,{})
        b=dataset.commands(imported,{})
        self.assertEqual(a,b)
        self.assertIn('D ',b)

    def test_custom_float_comparison_does_not_loosen_after_import(self):
        task={'id':'CUSTOM_01','interface':[{'direction':'Output','name':'X','type':'REAL'}], 'adapter_format':'bank_trace'}
        imported={**task,'id':'IMPORT_example__CUSTOM_01','original_id':'CUSTOM_01'}
        self.assertEqual(dataset.equal(1000001.,1000000.,task,'X'),dataset.equal(1000001.,1000000.,imported,'X'))

if __name__=='__main__':unittest.main()
