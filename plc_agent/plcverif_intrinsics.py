"""Typed lowering for a small, shared subset of CODESYS ST intrinsics."""

import re
from decimal import Decimal

from plc_agent.ltl_adapter import Unsupported, parse
from plc_agent.st_source import mask_noncode


INTEGER_RANGES = {'INT': (-32768, 32767), 'DINT': (-2147483648, 2147483647),
                  'UDINT': (0, 4294967295)}
NUMBER_TYPES = {*INTEGER_RANGES, 'LREAL'}
CALL = re.compile(r'(?<![.\w])(MIN|MAX|SEL|SQRT|DINT_TO_LREAL|TO_LREAL)\s*\(', re.I)
UNITS = re.compile(r'\b(FUNCTION_BLOCK|FUNCTION|PROGRAM)\s+(\w+)\b(.*?)\bEND_\1\b', re.I | re.S)
DECLARATIONS = re.compile(r'\bVAR(?:_\w+)?\b(.*?)\bEND_VAR\b', re.I | re.S)
TYPED_LITERAL = re.compile(r'\b(INT|DINT|UDINT|LREAL)#-?(?:\d+(?:\.\d+)?)(?:E[+-]?\d+)?\b', re.I)
HELPER = 'PLCVERIF_NUM_'


def _literal_type(value, expected):
    if not expected:
        return None
    if expected == 'LREAL':
        # Only exact standalone constants may be widened at a call boundary.
        # Literals within an already-typed expression remain in the expression.
        number = Decimal(value)
        return expected if abs(number) <= 16777216 and number == int(number) else None
    if expected in INTEGER_RANGES and '.' not in value:
        low, high = INTEGER_RANGES[expected]
        if low <= int(value) <= high:
            return expected
    return None


def _expression_type(text, types, shadowed, expected=None):
    names = dict(types)

    def literal(match):
        placeholder = f'PLCVERIF_NUM_LITERAL_{len(names)}'
        names[placeholder] = match[1].upper()
        return placeholder

    try:
        expression = parse(TYPED_LITERAL.sub(literal, text))
    except (Unsupported, RecursionError):
        return None

    def kind(node, context=None):
        op = node[0]
        if op == 'number':
            return _literal_type(node[1], context)
        if op == 'name':
            name = node[1].upper()
            return 'BOOL' if name in ('TRUE', 'FALSE') else names.get(name)
        if op == 'call':
            name = node[1].upper()
            args = node[2:]
            if name in shadowed:
                return None
            if name in ('DINT_TO_LREAL', 'TO_LREAL') and len(args) == 1 and kind(args[0]) == 'DINT':
                return 'LREAL'
            if name == 'SQRT' and len(args) == 1 and kind(args[0]) == 'LREAL':
                return 'LREAL'
            if name in ('MIN', 'MAX') and len(args) == 2:
                return common_type(*args, context)
            if name == 'SEL' and len(args) == 3 and kind(args[0]) == 'BOOL':
                return common_type(*args[1:], context)
        if op in ('+', '-') and len(node) == 2:
            if op == '-' and node[1][0] == 'number':
                return _literal_type('-' + node[1][1], context)
            return kind(node[1], context)
        if op in ('+', '-', '*', '/') and len(node) == 3:
            left, right = node[1:]
            lhs, rhs = kind(left), kind(right)
            inferred = lhs or rhs or context
            if inferred in NUMBER_TYPES and lhs in (inferred, None) and rhs in (inferred, None):
                # Keep the original literal spelling and arithmetic context.
                if all(dtype == inferred or (inferred == 'LREAL' and part[0] == 'number')
                       or kind(part, inferred) == inferred
                       for part, dtype in ((left, lhs), (right, rhs))):
                    return inferred
        return None

    def common_type(left, right, context):
        expected_type = kind(left) or kind(right) or context
        if expected_type in NUMBER_TYPES and kind(left, expected_type) == kind(right, expected_type) == expected_type:
            return expected_type
        return None

    return kind(expression, expected)


def _arguments(masked, start, stop):
    depth = 1
    begin = start
    arguments = []
    for i in range(start, min(stop, start + 4096)):
        char = masked[i]
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if not depth:
                return [*arguments, (begin, i)], i + 1
        elif char == ',' and depth == 1:
            arguments.append((begin, i))
            begin = i + 1
        elif char == ';':
            break
    return None


def _definition(name, op, dtype):
    if op == 'SQRT':
        # A typed marker. The CBMC exporter must replace this exact body.
        return f'FUNCTION {name} : LREAL\nVAR_INPUT Value : LREAL; END_VAR\n{name} := Value;\nEND_FUNCTION\n'
    if op == 'SEL':
        ports = f'ChooseRight : BOOL; Left : {dtype}; Right : {dtype};'
        expression, yes, no = 'ChooseRight', 'Right', 'Left'
    else:
        ports = f'Left : {dtype}; Right : {dtype};'
        expression = 'Left <= Right' if op == 'MIN' else 'Left >= Right'
        yes, no = 'Left', 'Right'
    return (f'FUNCTION {name} : {dtype}\nVAR_INPUT {ports} END_VAR\n'
            f'IF {expression} THEN {name} := {yes}; ELSE {name} := {no}; END_IF;\nEND_FUNCTION\n')


def lower_intrinsics(source, *, engine):
    """Normalize calls with known types in candidate and observer alike."""
    masked = mask_noncode(source)
    if re.search(r'\b' + HELPER, masked, re.I):
        raise Unsupported('PLCVERIF_NUM_ prefix is reserved for typed verification intrinsics')
    units = list(UNITS.finditer(masked))
    functions = {u[2].upper() for u in units if u[1].upper() == 'FUNCTION'}
    definitions = {}
    replacements = []
    counts = {}
    for unit in units:
        scopes = list(DECLARATIONS.finditer(unit[3]))
        types = {}
        for scope in scopes:
            for names, dtype in re.findall(r'\b(\w+(?:\s*,\s*\w+)*)\s*:\s*(\w+)', scope[1]):
                types.update((name.strip().upper(), dtype.upper()) for name in names.split(','))
        offset = unit.start(3) + (scopes[-1].end() if scopes else 0)
        shadowed = functions | types.keys()
        for call in CALL.finditer(masked, offset, unit.end(3)):
            op = call[1].upper()
            if op in shadowed:
                continue
            found = _arguments(masked, call.end(), unit.end(3))
            if found is None:
                continue
            spans, _ = found
            args = [masked[a:b].strip() for a, b in spans]
            params = ()
            if op in ('MIN', 'MAX', 'SEL'):
                if len(args) != (3 if op == 'SEL' else 2):
                    continue
                if op == 'SEL' and _expression_type(args[0], types, shadowed) != 'BOOL':
                    continue
                left, right = args[-2:]
                dtype = _expression_type(left, types, shadowed) or _expression_type(right, types, shadowed)
                if not dtype and op == 'SEL':
                    # Exactly representable floating constants (e.g. -1.0, 1.0).
                    dtype = 'LREAL' if '.' in left and '.' in right else None
                if (dtype not in NUMBER_TYPES or _expression_type(left, types, shadowed, dtype) != dtype
                        or _expression_type(right, types, shadowed, dtype) != dtype):
                    continue
                if dtype in INTEGER_RANGES and not all(
                        re.fullmatch(r'(?:[A-Za-z_]\w*|-?\d+)', arg) or TYPED_LITERAL.fullmatch(arg)
                        for arg in (left, right)):
                    # A helper parameter would narrow a native-width
                    # integer expression before the comparison.
                    continue
                if dtype == 'LREAL' and op != 'SEL' and engine != 'cbmc':
                    continue
                name = f'{HELPER}{op}_{dtype}'
                params = ('ChooseRight', 'Left', 'Right') if op == 'SEL' else ('Left', 'Right')
                definitions[name] = _definition(name, op, dtype)
            elif op == 'SQRT':
                if engine != 'cbmc' or len(args) != 1 or _expression_type(args[0], types, shadowed) != 'LREAL':
                    continue
                name = HELPER + 'SQRT_LREAL'
                definitions[name] = _definition(name, op, 'LREAL')
            else:
                if ('DINT_TO_LREAL' in shadowed or len(args) != 1
                        or _expression_type(args[0], types, shadowed) != 'DINT'):
                    continue
                name = 'DINT_TO_LREAL'
                if name not in functions:
                    definitions[name] = f'FUNCTION {name} : LREAL\nVAR_INPUT in : DINT; END_VAR\n//#BUILTIN\nEND_FUNCTION\n'
            if name != op:
                replacements.append((call.start(1), call.end(1), name))
            for (start, _), param in zip(spans, params):
                replacements.append((start, start, param + ' := '))
            counts[name] = counts.get(name, 0) + 1
    for start, end, value in sorted(replacements, reverse=True):
        source = source[:start] + value + source[end:]
    notes = [{'kind': 'typed_intrinsics', 'calls': counts}] if counts else []
    return ''.join(definitions.values()) + source, notes
