"""TIA-specific semantic boundary tests, independent of solver/model changes."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from plc_agent.tia_formal import adapt
from plc_agent.ltl_adapter import Unsupported
from plc_agent.tia_runtime import infrastructure_details, vendor_lease, VendorBusy


def fb(temps='', body='#y := #x;', before=''):
    return before+'''FUNCTION_BLOCK "Demo"
{ S7_Optimized_Access := 'TRUE' }
VERSION : 0.1
VAR_INPUT x : DINT; END_VAR
VAR_OUTPUT y : DINT; END_VAR
'''+('VAR_TEMP '+temps+' END_VAR\n' if temps else '')+'BEGIN\n'+body+'\nEND_FUNCTION_BLOCK\n'


def fresh(notes):
    return [p for note in notes for p in note.get('interface_additions',[])]


class SclBoundaryTests(unittest.TestCase):
    def test_pou_begin_delimiter_is_removed_before_reference_inlining(self):
        source=fb(body='// BEGIN inside comment\n#y := #x;')
        code, notes=adapt(source,block='Demo')
        from plc_agent.st_source import mask_noncode, split_units
        self.assertNotIn('BEGIN',mask_noncode(split_units(code)[0]['implementation']))
        self.assertIn('// BEGIN inside comment',code)
        self.assertEqual(next(n['count'] for n in notes if n['kind']=='pou_begin_delimiter'),1)

    def test_named_bound_queries_keep_parameter_dimension_and_comments(self):
        source = fb(body='''// LOWER_BOUND(ARR := fake, DIM := 9)
#y := LOWER_BOUND(ARR := #a (* outer (* nested *) end *), DIM := UDINT#1)
    + UPPER_BOUND(DIM := UINT#1, ARR := #a);''')
        code, notes = adapt(source, block='Demo')
        self.assertIn('LOWER_BOUND(a, 1)', code)
        self.assertIn('UPPER_BOUND(a, 1)', code)
        self.assertIn('(* outer (* nested *) end *)', code)
        self.assertIn('// LOWER_BOUND(ARR := fake, DIM := 9)', code)
        self.assertEqual(next(n['count'] for n in notes if n['kind']=='array_bound_arguments'), 2)
        positional, _ = adapt(fb(body='#y := LOWER_BOUND(#a, UDINT#1);'), block='Demo')
        self.assertIn('LOWER_BOUND(a, 1)', positional)
        for args in ('ARR := #a', 'ARR := #a, ARR := #a', 'ARR := #a, DIM := 2',
                     'ARR := #a, DIM := #x', '#a, DIM := 1', 'ARR := f(), DIM := 1',
                     'ARR := #a, DIM := REAL#1'):
            with self.subTest(args=args), self.assertRaises(Unsupported):
                adapt(fb(body='#y := LOWER_BOUND('+args+');'), block='Demo')

    def test_negative_bounds_do_not_enter_a_shared_exporter_with_raw_negative_indices(self):
        from plc_agent.tia_formal import verify
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'candidate.scl'
            source.write_text(fb('a : ARRAY[-1..0] OF DINT;'))
            task={'block':'Demo','id':'fixture','interface':[],
                  'ltl':{'properties':[{'id':'p','formula':'G(TRUE)'}]}}
            with patch('plc_agent.plcverif_backend.verify') as shared:
                result=verify(task,source,Path(folder)/'evidence',config={'engine':'cbmc'})
            self.assertEqual(result['status'],'unsupported');shared.assert_not_called()
            self.assertIn('negative-array-bound',result['message'])

    def test_nested_named_shift_arguments_are_normalized_without_losing_inner_calls(self):
        code, notes=adapt(fb(body='#y := SHL(IN := SHL(IN := DWORD#1, N := 2), N := 3);'),block='Demo')
        self.assertIn('SHL(SHL(DWORD#1, 2), 3)',code)
        self.assertEqual(next(n['count'] for n in notes if n['kind']=='named_shift_arguments'),2)
        commented,_=adapt(fb(body='#y := SHL(IN := DWORD#1 // retain newline\n, N := 3);'),block='Demo')
        self.assertIn('// retain newline\n',commented)
        self.assertIn(', 3)',commented)

    def test_fixed_multidimensional_array_preserves_bounds_and_independent_values(self):
        code, notes = adapt(fb('a : ARRAY[-1..0, 2..3] OF DINT;', '#a[-1,2] := #x; #y := #a[-1,2];'), block='Demo')
        self.assertEqual(len(fresh(notes)),4)
        for i, target in enumerate(('a[-1,2]','a[-1,3]','a[0,2]','a[0,3]')):
            self.assertIn(target+' := WBTEMP_'+str(i)+';',code)
        self.assertIn('ARRAY[-1 .. 0, 2 .. 3] OF DINT',code)
        self.assertNotIn('VAR_TEMP',code)

    def test_nested_struct_and_named_type_are_fresh_at_every_entry(self):
        before='''TYPE "Pair"
VERSION : 0.1
STRUCT value : DINT; flags : ARRAY[1..2] OF BOOL; END_STRUCT;
END_TYPE
'''
        code, notes=adapt(fb('work : ARRAY[-2..-1] OF "Pair";', '#work[-2].value := #x; #y := #work[-2].value;',before),block='Demo')
        self.assertEqual([p['type'] for p in fresh(notes)],['DINT','BOOL','BOOL']*2)
        self.assertIn('work[-2].flags[1] := WBTEMP_1;',code)
        self.assertLess(code.index('work[-2].value := WBTEMP_0;'),code.index('work[-2].value := x;'))

    def test_quoted_locals_fields_and_comments_do_not_authorize_missing_globals(self):
        code, _ = adapt(fb('"work" : STRUCT "value" : DINT; END_STRUCT;', '#"work"."value" := #x; #y := #"work"."value";'),block='Demo')
        self.assertIn('work.value := x;',code)
        for suffix in ('// FUNCTION_BLOCK "Missing"\n', "(* DATA_BLOCK \"Missing\" *)\n", "// TYPE \"Missing\"\n"):
            with self.assertRaisesRegex(Unsupported,'Missing'):
                adapt(fb(body='#y := "Missing".x;',before=suffix),block='Demo')
        with self.assertRaisesRegex(Unsupported,'Missing'):
            adapt(fb(body='"Missing" := #x; #y := #x;'),block='Demo')

    def test_helper_temporaries_require_assignment_before_every_read(self):
        helper='''FUNCTION "Twice" : DINT
VAR_INPUT x : DINT; END_VAR
VAR_TEMP a : ARRAY[0..1] OF DINT; END_VAR
BEGIN
#a[0] := #x; #a[1] := #x; #Twice := #a[0] + #a[1];
END_FUNCTION
'''
        code, notes=adapt(fb(body='#y := "Twice"(x := #x);',before=helper),block='Demo')
        self.assertEqual(fresh(notes),[])
        self.assertTrue(any(n['kind']=='initialized_helper_temporaries' for n in notes))
        for broken in (helper.replace('#a[1] := #x;', ''),helper.replace('#a[0] := #x;', '#a[0] := #a[1];')):
            with self.assertRaisesRegex(Unsupported,'initialize'):
                adapt(fb(body='#y := "Twice"(x := #x);',before=broken),block='Demo')

    def test_unsafe_or_unbounded_temporary_types_remain_unsupported(self):
        for dtype in ('ARRAY[*] OF DINT','VARIANT','POINTER TO DINT','ARRAY[0..999999] OF BOOL',
                      'STRUCT x : ARRAY[*] OF DINT; END_STRUCT','DINT := 1'):
            with self.assertRaises(Unsupported):adapt(fb('a : '+dtype+';'),block='Demo')

    def test_readonly_self_contained_db_keeps_values_and_records_assumptions(self):
        db='''DATA_BLOCK "Limits"
{ S7_Optimized_Access := 'TRUE' }
VERSION : 0.1
VAR threshold : DINT := 7; enabled : BOOL := TRUE; END_VAR
BEGIN
END_DATA_BLOCK
'''
        code,notes=adapt(fb(body='#y := #x + "Limits".threshold;',before=db),block='Demo')
        self.assertIn('y := x + DINT#7;',code)
        self.assertNotIn('DATA_BLOCK',code)
        self.assertTrue(any(n.get('assumptions') for n in notes))
        for body in ('"Limits".threshold := #x;', '#y := F(x := "Limits".threshold);',
                     '#y := F((#x), "Limits".threshold);','#y := "Limits".absent;'):
            with self.assertRaises(Unsupported):adapt(fb(body=body,before=db),block='Demo')
        with self.assertRaises(Unsupported):adapt(fb(body='#y := "Limits".threshold;'),block='Demo')


class RuntimeBoundaryTests(unittest.TestCase):
    def test_cross_process_lease_releases_after_exit_and_supports_busy(self):
        with tempfile.TemporaryDirectory() as folder:
            lock=Path(folder)/'lease'
            script=('import sys,time; from plc_agent.tia_runtime import vendor_lease; '
                    'ctx=vendor_lease(1,lock_path=sys.argv[1]); ctx.__enter__(); '
                    'print("locked",flush=True); sys.stdin.readline(); ctx.__exit__(None,None,None)')
            child=subprocess.Popen([sys.executable,'-c',script,str(lock)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(),'locked')
                with self.assertRaises(VendorBusy):
                    with vendor_lease(.1,lock_path=lock):pass
            finally:
                child.communicate('\n',timeout=10)
            with vendor_lease(.1,lock_path=lock):pass

    def test_timeout_phase_is_evidence_based_and_security_is_not_logic_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'bridge_progress.json').write_text(json.dumps({'phase':'starting_portal'}))
            original={'status':'timeout','message':'Bridge exceeded timeout'}
            result=infrastructure_details(original,root)
            self.assertEqual(result['phase'],'starting_portal');self.assertEqual(result['message'],original['message'])
            result=infrastructure_details({'status':'bridge_error','message':'EngineeringSecurityException'},root)
            self.assertEqual(result['failure_kind'],'openness_access')
            result=infrastructure_details({'status':'simulation_error','phase':'power_on','message':'PowerOn: Timeout'},root)
            self.assertEqual(result['phase'],'power_on');self.assertEqual(result['failure_kind'],'startup_timeout')
            self.assertIn('若出现',result['recovery_hint'])
            self.assertIn('不能据 Timeout',result['recovery_hint'])


if __name__=='__main__':unittest.main()
