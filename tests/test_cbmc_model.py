import unittest

from plc_agent.cbmc_model import monitor
from plc_agent.dataset import load
from plc_agent.ltl_adapter import Adapter


class CbmcMonitorTests(unittest.TestCase):
    def test_global_atoms_use_equivalent_online_conjunction(self):
        adapter = Adapter(load('PUBLIC_02'), 20, 10).prepare()
        declaration, sample, finish = monitor(adapter)
        self.assertNotIn('pvl_history_', declaration)
        self.assertNotIn('pvl_node_', declaration)
        self.assertNotIn('PVL:DOMAIN_WITNESS', finish)
        for index in range(7):
            prop = f'P0{index + 1}'
            atom = f'PVL_A{index}'
            self.assertIn(f'bool pvl_invariant_{prop} = true;', declaration)
            self.assertIn(
                f'pvl_invariant_{prop} = pvl_invariant_{prop} && instance.{atom};',
                sample)
            self.assertIn(
                f'__CPROVER_assert(!pvl_domain || pvl_invariant_{prop}, "PVL:LTL:{prop}");',
                finish)

    def test_online_invariant_has_same_finite_prefix_truth_table(self):
        for values in ([True], [False], [True, True, True],
                       [True, False, True], [False, True, True]):
            online = True
            for value in values:
                online = online and value
            backward_ltl = True
            for value in reversed(values):
                backward_ltl = value and backward_ltl
            self.assertEqual(online, backward_ltl)

    def test_constrained_input_domain_retains_reachability_witness(self):
        adapter = Adapter(load('PUBLIC_04'), 20, 10).prepare()
        self.assertTrue(adapter.assumptions)
        _, _, finish = monitor(adapter)
        self.assertIn('__CPROVER_assert(!pvl_domain, "PVL:DOMAIN_WITNESS");', finish)


if __name__ == '__main__':
    unittest.main()
