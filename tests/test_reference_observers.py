from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from plc_agent import plcverif_backend
from plc_agent.cbmc_model import monitor, order_structs
from plc_agent.dataset import load
from plc_agent.ltl_adapter import Adapter, Unsupported
from plc_agent.reference_observers import cases


class ObserverTests(unittest.TestCase):
    def test_all_case_shapes_have_all_original_properties_without_mutating_bank(self):
        for ident,count in [('PUBLIC_08',4),('PUBLIC_18',12)]:
            task=load(ident);saved=deepcopy(task)
            suite=cases(task)
            self.assertEqual(len(suite),count)
            for case in suite:
                a=Adapter(case.task,3,reference_observer=case).prepare()
                self.assertEqual([p['formula'] for p in a.properties],[p['formula'] for p in task['ltl']['properties']])
                self.assertTrue(all(p.get('ast') for p in a.properties))
                self.assertTrue(a.assumptions)
                self.assertIn('PVL:DOMAIN_WITNESS',monitor(a)[2])
                self.assertNotIn('requires_model',case.task['ltl']['execution'])
            self.assertEqual(task,saved)

    def test_unknown_formulas_directions_and_shapes_are_rejected(self):
        for change in ('formula','direction','shape','duplicate','empty','custom_observer'):
            task=load('PUBLIC_08')
            if change=='formula':task['ltl']['properties'][0]['formula']='G(TRUE)'
            if change=='direction':task['interface'][0]['direction']='Output'
            if change=='shape':task['scenarios'][0]['channel_length']=100000
            if change=='duplicate':task['scenarios'].append(deepcopy(task['scenarios'][0]))
            if change=='empty':task['scenarios']=[]
            if change=='custom_observer':task['ltl']['execution']['bindings']={'rawArrayPreserved':'TRUE'}
            with self.assertRaises(Unsupported,msg=change):cases(task)

    def test_case_metadata_never_reads_finite_expected_rows(self):
        task=load('PUBLIC_18');before=[c.evidence() for c in cases(task)]
        for scenario in task['scenarios']:scenario['rows']=[{'malformed':'not consumed'}]
        self.assertEqual(before,[c.evidence() for c in cases(task)])

    def test_imported_web_task_preserves_original_id_and_properties(self):
        task=load('PUBLIC_18');task.update(original_id='PUBLIC_18',id='IMPORT_frozen__PUBLIC_18')
        suite=cases(task)
        self.assertEqual(len(suite),12)
        self.assertEqual(suite[0].task['id'],task['id'])

    def test_channel_schema_must_match_before_tools_run(self):
        case=cases(load('PUBLIC_08'))[0]
        source=Path('examples/formal/Q08.st').read_text(encoding='utf-8')
        case.validate_source(source)
        with self.assertRaisesRegex(Unsupported,'field names and types'):
            case.validate_source(source.replace('hiLIM         : REAL','hiLIM         : LREAL'))
        with self.assertRaisesRegex(Unsupported,'Source interface'):
            case.validate_source(source.replace('count : DINT','count : BOOL'))

    def test_c_hooks_surround_only_the_candidate_invocation(self):
        case=cases(load('PUBLIC_18'))[4]
        a=Adapter(case.task,3,reference_observer=case).prepare()
        model=case.instrument('void VerificationLoop() { PVL_Harness(&instance); }',a)
        pos=model.index('PVL_Harness(&instance);')
        self.assertLess(model.index('instance.PVL_Store_Item=pvl_fresh()'),pos)
        self.assertGreater(model.index('instance.PVL_A7=count_ok && repr;'),pos)
        self.assertNotIn('diHead',model)
        self.assertNotIn('diTail',model)
        self.assertIn('pvl_equal',model)
        self.assertIn('x.u==y.u',model)

    def test_observer_rejects_unknown_generated_loop_shape(self):
        case=cases(load('PUBLIC_18'))[0]
        with self.assertRaises(Unsupported):case.instrument('void VerificationLoop() {}',None)

    def test_structs_are_ordered_by_value_dependencies(self):
        model='// Struct definitions\ntypedef struct { Child c; } Parent;\ntypedef struct { int x; } Child;\n// Global variables\nParent p;'
        result=order_structs(model)
        self.assertLess(result.index('} Child;'),result.index('} Parent;'))
        self.assertIn('Child c;',result)
        with self.assertRaises(Unsupported):
            order_structs('// Struct definitions\ntypedef struct { B b; } A; typedef struct { A a; } B;\n// Global variables')


class SuiteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source=self.root/'candidate.st';self.source.write_text('fixture',encoding='utf-8')
        self.task=load('PUBLIC_18')
        self.cfg={**plcverif_backend.DEFAULTS,'bound':4}

    def fake(self,task,source,directory,**kw):
        return {'status':'bounded_pass','mapped_assertions_total':9,
                'properties':[{**p,'status':'bounded_pass'} for p in task['ltl']['properties']]}

    def run_suite(self,side_effect):
        with patch.object(plcverif_backend,'validate'),patch.object(plcverif_backend,'_verify_one',side_effect=side_effect):
            return plcverif_backend.verify(self.task,self.source,self.root/'result',config=self.cfg)

    def test_all_cases_are_required_for_a_pass(self):
        result=self.run_suite(self.fake)
        self.assertEqual(result['status'],'bounded_pass')
        self.assertEqual(result['reference_cases_executed'],12)
        self.assertEqual(len(result['bounded_verified_property_ids']),9)
        self.assertFalse(result['full_ltl_proved'])

    def test_web_imported_tasks_use_the_same_case_suite(self):
        self.task.update(original_id='PUBLIC_18',id='IMPORT_frozen__PUBLIC_18')
        result=self.run_suite(self.fake)
        self.assertEqual(result['status'],'bounded_pass')
        self.assertEqual(result['reference_cases_executed'],12)
        self.assertEqual(result['task_id'],self.task['id'])

    def test_first_counterexample_stops_suite_without_passing_unexecuted_cases(self):
        def fail(*args,**kw):
            r=self.fake(*args,**kw);r['status']='counterexample'
            r['properties'][2].update(status='counterexample',counterexample={'raw':[]})
            return r
        result=self.run_suite(fail)
        self.assertEqual(result['status'],'counterexample')
        self.assertEqual(result['reference_cases_executed'],1)
        self.assertEqual(result['bounded_verified_property_ids'],[])
        self.assertEqual(result['properties'][2]['case'],'dint_capacity_1')

    def test_timeout_never_becomes_a_pass(self):
        def timeout(*args,**kw):
            r=self.fake(*args,**kw);r['status']='timeout'
            for p in r['properties']:p['status']='not_executed'
            return r
        result=self.run_suite(timeout)
        self.assertEqual(result['status'],'timeout')
        self.assertEqual(result['reference_cases_executed'],1)
        self.assertEqual({p['status'] for p in result['properties']},{'timeout'})

    def test_source_changes_invalidate_every_case(self):
        def changed(*args,**kw):
            self.source.write_text('changed',encoding='utf-8')
            return self.fake(*args,**kw)
        result=self.run_suite(changed)
        self.assertEqual(result['status'],'stale_source')
        self.assertFalse(result['bounded_all_properties_verified'])


if __name__=='__main__':unittest.main()
