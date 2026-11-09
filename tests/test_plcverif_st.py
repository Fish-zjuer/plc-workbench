import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from plc_agent.dataset import load
from plc_agent.ltl_adapter import Adapter
from plc_agent.plcverif_backend import DEFAULTS, verify
from plc_agent.plcverif_intrinsics import lower_intrinsics
from plc_agent.plcverif_st import adapt, adapt_int_abs


class PlcverifStTests(unittest.TestCase):
    def test_candidate_and_property_min_are_both_lowered_without_changing_formula(self):
        source = '''FUNCTION_BLOCK Example
VAR_INPUT value : UDINT; END_VAR
VAR_OUTPUT capped : UDINT; END_VAR
capped := MIN(60000, value);
END_FUNCTION_BLOCK
'''
        task = {'block': 'Example', 'interface': [
            {'direction': 'Input', 'name': 'value', 'type': 'UDINT'},
            {'direction': 'Output', 'name': 'capped', 'type': 'UDINT'}],
            'ltl': {'text': 'P01: G(capped=min(60000,value))'}}
        adapter = Adapter(task, 20).prepare()
        lowered, notes = lower_intrinsics(adapter.instrument(source), engine='cbmc')
        self.assertEqual(adapter.properties[0]['formula'], 'G(capped=min(60000,value))')
        self.assertNotIn('MIN(', lowered)
        self.assertEqual(notes, [{'kind': 'typed_intrinsics', 'calls': {'PLCVERIF_NUM_MIN_UDINT': 1}}])

    def test_nested_intrinsics_preserve_precision_and_leave_mixed_types_alone(self):
        source = '''FUNCTION_BLOCK Example
VAR_INPUT x : LREAL; k : DINT; END_VAR
VAR_OUTPUT y : LREAL; END_VAR
// MAX(0.0, x)
y := MAX(0.0, MIN(x, TO_LREAL(k)));
y := SQRT(y);
y := MIN(x, k);
END_FUNCTION_BLOCK
'''
        lowered, _ = lower_intrinsics(source, engine='cbmc')
        self.assertIn('PLCVERIF_NUM_MAX_LREAL(Left := 0.0,Right :=  PLCVERIF_NUM_MIN_LREAL', lowered)
        self.assertIn('FUNCTION DINT_TO_LREAL : LREAL', lowered)
        self.assertIn('y := PLCVERIF_NUM_SQRT_LREAL(y);', lowered)
        self.assertIn('y := MIN(x, k);', lowered)
        self.assertIn('// MAX(0.0, x)', lowered)

    def test_abs_model_only_rewrites_calls_with_known_int_operands(self):
        source = '''FUNCTION_BLOCK Example
VAR a, b : INT; distance : INT; x : REAL; y : REAL; END_VAR
// ABS(a - b) in a comment
distance := ABS(a - b);
y := ABS(x);
END_FUNCTION_BLOCK
'''
        adapted, notes = adapt_int_abs(source)
        self.assertEqual(notes, [{'kind': 'int_abs_model', 'count': 1}])
        self.assertIn('distance := PLCVERIF_ABS_INT(a - b);', adapted)
        self.assertIn('y := ABS(x);', adapted)
        self.assertIn('// ABS(a - b) in a comment', adapted)

    @staticmethod
    def _reference_ton(inputs, pt, tick):
        """Independent elapsed-since-rising-edge scan-clock definition."""
        started_at = None
        result = []
        for scan, enabled in enumerate(inputs):
            if not enabled:
                started_at = None
                result.append((False, 0))
                continue
            if started_at is None:
                started_at = scan
            elapsed = (scan - started_at) * tick
            result.append((elapsed >= pt, min(elapsed, max(pt, 0))))
        return result

    @staticmethod
    def _adapted_ton(inputs, pt, tick):
        """Execute the branches emitted by plcverif_st._adapt_ton."""
        running = False
        q = False
        et = 0
        result = []
        for enabled in inputs:
            if not enabled:
                q, et, running = False, 0, False
            elif not running:
                running, et, q = True, 0, pt <= 0
            elif pt <= 0:
                q, et = True, 0
            elif q:
                et = pt
            elif pt <= tick:
                q, et = True, pt
            elif et >= pt - tick:
                q, et = True, pt
            else:
                et += tick
            result.append((q, et))
        return result

    def test_bounded_shift_uses_explicit_equivalent_lookup(self):
        source = '''FUNCTION_BLOCK Edge
VAR_INPUT value : DWORD; END_VAR
VAR mask : DWORD; bitIndex : INT; END_VAR
FOR bitIndex := 0 TO 31 DO
    mask := SHL(DWORD#1, bitIndex);
END_FOR;
END_FUNCTION_BLOCK
'''
        adapted, notes = adapt(source)
        self.assertIn('FUNCTION PLCVERIF_SHL_DWORD_ONE : DWORD', adapted)
        self.assertIn('mask := PLCVERIF_SHL_DWORD_ONE( bitIndex);', adapted)
        for index in range(32):
            self.assertIn(f'{index}: PLCVERIF_SHL_DWORD_ONE := DWORD#{1 << index};', adapted)
        self.assertEqual(notes, [{'kind': 'bounded_shift_lowering', 'operation': 'SHL',
                                  'input': 'DWORD#1', 'count_range': [0, 31], 'count': 1}])

    def test_noncode_shift_text_is_unchanged(self):
        source = '''FUNCTION_BLOCK Comments
// SHL(not, code)
END_FUNCTION_BLOCK
'''
        adapted, _ = adapt(source)
        self.assertIn('// SHL(not, code)', adapted)
        self.assertNotIn('PLCVERIF_SHL_DWORD_ONE', adapted)

    def test_unbounded_shift_is_explicitly_unsupported(self):
        source = '''FUNCTION_BLOCK Unsafe
VAR x : DWORD; n : INT; y : DWORD; END_VAR
y := SHL(x, n);
END_FUNCTION_BLOCK
'''
        with self.assertRaisesRegex(ValueError, 'cannot safely preserve SHL semantics'):
            adapt(source)

    def test_ton_uses_configured_scan_clock_for_safe_call_shape(self):
        source = '''FUNCTION_BLOCK Delay
VAR_INPUT enable : BOOL; END_VAR
VAR_OUTPUT ready : BOOL; END_VAR
VAR timer : TON; END_VAR
timer(IN := enable, PT := T#5s);
ready := timer.Q;
END_FUNCTION_BLOCK
'''
        adapted, notes = adapt(source, scan_period_ms=25)
        self.assertIn('FUNCTION_BLOCK TON', adapted)
        self.assertIn('VAR_OUTPUT Q : BOOL := FALSE; ET : TIME := T#0ms;', adapted)
        self.assertIn('ELSIF PT <= T#25ms THEN', adapted)
        self.assertIn('ELSIF ET >= PT - T#25ms THEN', adapted)
        self.assertEqual(notes[0]['kind'], 'standard_timer_model')
        self.assertEqual(notes[0]['scan_period_ms'], 25)
        self.assertEqual(notes[0]['instances'], ['timer'])

    def test_ton_boundary_matches_independent_elapsed_time_reference(self):
        inputs = [True] * 502
        expected = self._reference_ton(inputs, pt=5000, tick=10)
        actual = self._adapted_ton(inputs, pt=5000, tick=10)
        self.assertEqual(actual, expected)
        self.assertEqual(actual[0], (False, 0))
        self.assertEqual(actual[499], (False, 4990))
        self.assertEqual(actual[500], (True, 5000))
        self.assertEqual(actual[501], (True, 5000))

    def test_ton_disconnect_resets_and_next_rise_restarts_from_zero(self):
        inputs = [True, True, True, False, True, True, True, True]
        expected = self._reference_ton(inputs, pt=30, tick=10)
        actual = self._adapted_ton(inputs, pt=30, tick=10)
        self.assertEqual(actual, expected)
        self.assertEqual(actual[3], (False, 0))
        self.assertEqual(actual[4], (False, 0))
        self.assertEqual(actual[6], (False, 20))
        self.assertEqual(actual[7], (True, 30))

    def test_ton_subscan_and_zero_presets_keep_first_scan_edge_semantics(self):
        self.assertEqual(self._adapted_ton([True, True], pt=5, tick=10),
                         [(False, 0), (True, 5)])
        self.assertEqual(self._reference_ton([True, True], pt=5, tick=10),
                         [(False, 0), (True, 5)])
        self.assertEqual(self._adapted_ton([True], pt=0, tick=10), [(True, 0)])
        self.assertEqual(self._reference_ton([True], pt=0, tick=10), [(True, 0)])

    def test_conditional_ton_call_is_explicitly_unsupported(self):
        source = '''FUNCTION_BLOCK Delay
VAR_INPUT enable : BOOL; END_VAR
VAR timer : TON; END_VAR
IF enable THEN
    timer(IN := TRUE, PT := T#5s);
END_IF;
END_FUNCTION_BLOCK
'''
        with self.assertRaisesRegex(ValueError, 'unconditional top-level call'):
            adapt(source)

    def test_variable_ton_preset_is_explicitly_unsupported(self):
        source = '''FUNCTION_BLOCK Delay
VAR_INPUT enable : BOOL; preset : TIME; END_VAR
VAR timer : TON; END_VAR
timer(IN := enable, PT := preset);
END_FUNCTION_BLOCK
'''
        with self.assertRaisesRegex(ValueError, 'fixed TIME-literal PT'):
            adapt(source)

    def test_ton_in_non_scan_entry_block_is_explicitly_unsupported(self):
        source = '''FUNCTION_BLOCK Helper
VAR timer : TON; END_VAR
timer(IN := TRUE, PT := T#5s);
END_FUNCTION_BLOCK
FUNCTION_BLOCK Main
VAR helper : Helper; END_VAR
helper();
END_FUNCTION_BLOCK
'''
        with self.assertRaisesRegex(ValueError, 'only exact inside'):
            adapt(source, entry_block='Main')

    def test_public08_missing_channel_schema_is_rejected_without_tool_execution(self):
        source = '''FUNCTION_BLOCK Q08
VAR_INPUT count : DINT; END_VAR
VAR_IN_OUT
analogValues : ARRAY[*] OF INT;
channels : ARRAY[*] OF ST_AnalogChannel;
END_VAR
END_FUNCTION_BLOCK
'''
        with TemporaryDirectory(dir='.') as temporary:
            root = Path(temporary)
            candidate = root / 'candidate.st'
            candidate.write_text(source, encoding='utf-8')
            tools = {}
            for name in ('plcverif', 'java', 'cbmc'):
                path = root / (name + '.exe')
                path.touch()
                tools[name] = str(path)
            result = verify(load('PUBLIC_08'), candidate, root / 'result',
                            config={**DEFAULTS, **tools})
            self.assertEqual(result['status'], 'unsupported')
            self.assertEqual(result['mapped_assertions_total'], 0)
            self.assertEqual(len(result['properties']), 8)
            self.assertEqual({p['status'] for p in result['properties']}, {'unsupported_model'})
            self.assertFalse((root / 'result' / 'plcverif.log').exists())
            self.assertFalse((root / 'result' / 'cbmc.json').exists())

    def test_public18_unmodeled_vendor_api_is_rejected_without_tool_execution(self):
        source = '''FUNCTION_BLOCK Q18
VAR_INPUT enqueue : BOOL; dequeue : BOOL; reset : BOOL; END_VAR
VAR_OUTPUT elementCount : DINT; status : WORD; END_VAR
VAR_IN_OUT item : VARIANT; buffer : VARIANT; END_VAR
elementCount := CountOfElements(buffer);
END_FUNCTION_BLOCK
'''
        with TemporaryDirectory(dir='.') as temporary:
            root = Path(temporary)
            candidate = root / 'candidate.st'
            candidate.write_text(source, encoding='utf-8')
            tools = {}
            for name in ('plcverif', 'java', 'cbmc'):
                path = root / (name + '.exe')
                path.touch()
                tools[name] = str(path)
            result = verify(load('PUBLIC_18'), candidate, root / 'result',
                            config={**DEFAULTS, **tools})
            self.assertEqual(result['status'], 'unsupported')
            self.assertEqual(result['mapped_assertions_total'], 9)
            self.assertEqual(len(result['properties']), 9)
            self.assertEqual({p['status'] for p in result['properties']}, {'unsupported_model'})
            self.assertFalse((root / 'result' / 'plcverif.log').exists())
            self.assertFalse((root / 'result' / 'cbmc.json').exists())


if __name__ == '__main__':
    unittest.main()
