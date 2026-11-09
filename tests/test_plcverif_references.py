import copy
import unittest

from plc_agent.ltl_adapter import Adapter, Unsupported
from plc_agent.plcverif_st import adapt


def task(variant=False):
    return {'id':'REFERENCE_DEMO','block':'Demo','interface':[
        {'direction':'Input','name':'x','type':'DINT'},
        {'direction':'Output','name':'y','type':'DINT'},
        {'direction':'Input/Output','name':'a','type':'VARIANT' if variant else 'ARRAY[*] OF DINT'},
        {'direction':'Input/Output','name':'b','type':'VARIANT' if variant else 'DINT'}],
        'ltl':{'properties':[{'id':'P1','formula':'G(y = x)'}], 'execution':{
            'reference_model':{'version':1,'objects':[{'name':'PVL_Store_Data','type':'ARRAY[-3..1] OF DINT'}],
                               'bindings':{'a':'PVL_Store_Data','b':'PVL_Store_Data[-3]'}}}}}


def source(body, variant=False):
    return ('FUNCTION_BLOCK Demo\nVAR_INPUT x : DINT; END_VAR\n'
            'VAR_OUTPUT y : DINT; END_VAR\nVAR_IN_OUT\n' +
            ('a : VARIANT; b : VARIANT;' if variant else 'a : ARRAY[*] OF DINT; b : DINT;') +
            '\nEND_VAR\nVAR copyDone : BOOL; idx : DINT; END_VAR\n' + body + '\nEND_FUNCTION_BLOCK')


def instrument(t, s):
    return Adapter(t, 3).prepare().instrument(adapt(s, entry_block='Demo')[0])


class ReferenceTests(unittest.TestCase):
    def test_alias_and_negative_bounds_use_same_storage(self):
        t=task(); saved=copy.deepcopy(t)
        model=instrument(t,source('a[LOWER_BOUND(a, 1)] := x; y := b;'))
        self.assertIn('PVL_Store_Data[PLCVERIF_REF_INDEX_A((-3))] := PVL_Uut.x;',model)
        self.assertIn('PVL_Uut.y := PVL_Store_Data[0];',model)
        self.assertNotIn('VAR_IN_OUT',model)
        self.assertNotIn('ARRAY[*]',model)
        self.assertNotIn('PVL_Uut(',model)
        self.assertEqual(t,saved)

    def test_return_leaves_call_but_observer_still_runs(self):
        model=instrument(task(),source('IF x = 0 THEN RETURN; END_IF; y := b;'))
        self.assertIn('THEN EXIT;',model)
        self.assertIn('UNTIL TRUE END_REPEAT;',model)
        self.assertGreater(model.index('PVL_A0 :='),model.index('UNTIL TRUE END_REPEAT;'))

    def test_return_in_loop_is_rejected(self):
        with self.assertRaisesRegex(Unsupported,'RETURN inside loops'):
            instrument(task(),source('FOR idx := 0 TO 4 DO RETURN; END_FOR;'))

    def test_pv1_copy_keeps_guard_and_relative_index(self):
        model=instrument(task(True),source('idx := 0; copyDone := PV_WRITE(a, idx, b); y := PV_COUNT(a);',True))
        self.assertIn('PVL_Uut.idx < DINT#5',model)
        self.assertIn('PVL_Store_Data[DINT_TO_INT(PVL_Uut.idx)] := PVL_Store_Data[0];',model)
        self.assertIn('PVL_Uut.copyDone := FALSE;',model)
        self.assertIn('PVL_Uut.y := 5;',model)
        self.assertNotIn('VARIANT',model)

    def test_pv1_type_mismatch_has_no_copy(self):
        t=task(True)
        t['ltl']['execution']['reference_model']['objects'].append({'name':'PVL_Store_Item','type':'REAL'})
        t['ltl']['execution']['reference_model']['bindings']['b']='PVL_Store_Item'
        model=instrument(t,source('copyDone := PV_READ(a, idx, b);',True))
        self.assertIn('PVL_Uut.copyDone := FALSE;',model)
        self.assertNotIn('PVL_Store_Item :=',model)

    def test_pv1_expression_with_side_effects_is_rejected(self):
        with self.assertRaisesRegex(Unsupported,'Unsupported PV1 expression'):
            instrument(task(True),source('IF PV_READ(a, idx, b) THEN y := 1; END_IF;',True))

    def test_unknown_variant_api_is_rejected(self):
        with self.assertRaisesRegex(Unsupported,'PV1 helper contract'):
            instrument(task(True),source('y := CountOfElements(a);',True))

    def test_binding_must_be_complete_in_bounds_and_type_correct(self):
        for change in ('missing','bounds','type','dynamic'):
            t=task(); cfg=t['ltl']['execution']['reference_model']
            if change=='missing':del cfg['bindings']['b']
            if change=='bounds':cfg['bindings']['b']='PVL_Store_Data[99]'
            if change=='type':cfg['objects'][0]['type']='ARRAY[-3..1] OF REAL'
            if change=='dynamic':cfg['bindings']['b']='PVL_Store_Data[x]'
            with self.assertRaises(Unsupported,msg=change):instrument(t,source('y := b;'))

    def test_missing_contract_never_falls_back_to_value_copy(self):
        t=task();t['ltl']['execution']={}
        with self.assertRaisesRegex(Unsupported,'explicit reference_model'):
            instrument(t,source('y := b;'))

    def test_struct_member_named_like_local_is_not_rewritten(self):
        t=task(); cfg=t['ltl']['execution']['reference_model']
        cfg['objects'][0]['type']='ARRAY[-3..1] OF Rec'
        t['interface'][2]['type']='ARRAY[*] OF Rec';t['interface'][3]['type']='Rec'
        s=source('a[-3]. x := x; y := b.x;').replace('OF DINT','OF Rec').replace('b : DINT','b : Rec')
        model=instrument(t,'TYPE Rec : STRUCT x : DINT; END_STRUCT END_TYPE\n'+s)
        self.assertIn('PVL_Store_Data[PLCVERIF_REF_INDEX_A(-3)]. x := PVL_Uut.x;',model)
        self.assertIn('PVL_Uut.y := PVL_Store_Data[0].x;',model)


if __name__=='__main__':unittest.main()
