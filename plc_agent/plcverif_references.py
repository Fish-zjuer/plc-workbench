"""Bound-storage frontend extension for PLCverif (not a vendor VARIANT ABI).

Inline one scan-entry FB into its harness, substituting reference parameters
with caller lvalues. No copy-in/copy-out: overlapping references stay shared.
Only explicitly configured fixed associations are accepted.
"""
import re

from plc_agent.ltl_adapter import Unsupported
from plc_agent.st_source import mask_noncode, split_units


IDENT = r'[A-Za-z_]\w*'
ARRAY = re.compile(r'ARRAY\s*\[\s*(-?\d+)\s*\.\.\s*(-?\d+)\s*\]\s+OF\s+(' + IDENT + r')', re.I)
SCALARS = set('BOOL BYTE WORD DWORD LWORD SINT INT DINT LINT USINT UINT UDINT ULINT REAL LREAL TIME'.split())


def _replace(source, pattern, replacement):
    changes = [(m.start(), m.end(), replacement(m)) for m in re.finditer(pattern, mask_noncode(source), re.I)]
    for start, end, value in reversed(changes):
        source = source[:start] + value + source[end:]
    return source


def configuration(task):
    """Validate a closed, finite storage contract without guessing bounds/types."""
    model = task.get('ltl', {}).get('execution', {}).get('reference_model')
    if model is None:
        return None
    if not isinstance(model, dict) or set(model) != {'version', 'objects', 'bindings'} or type(model['version']) is not int or model['version'] != 1:
        raise Unsupported('reference_model requires version=1, objects and bindings')
    objects, bindings = model['objects'], model['bindings']
    if not isinstance(objects, list) or not objects or not isinstance(bindings, dict):
        raise Unsupported('Reference objects must be a nonempty list and bindings an object')
    types = {}
    for obj in objects:
        if not isinstance(obj, dict) or set(obj) != {'name', 'type'}:
            raise Unsupported('Each reference object requires exactly name and type')
        name, dtype = obj['name'], obj['type']
        if not isinstance(name, str) or not re.fullmatch(r'PVL_Store_' + IDENT, name, re.I):
            raise Unsupported('Reference storage names must start with PVL_Store_')
        if name.lower() in types or not isinstance(dtype, str):
            raise Unsupported('Duplicate reference storage or invalid type')
        array = ARRAY.fullmatch(dtype.strip())
        if not array and not re.fullmatch(IDENT, dtype):
            raise Unsupported('Reference storage requires a scalar/UDT or fixed one-dimensional array')
        if array and not (-2147483648 <= int(array[1]) <= int(array[2]) <= 2147483647 and int(array[2])-int(array[1])+1 <= 256):
            raise Unsupported('Reference array bounds must fit DINT and length must be 1..256')
        types[name.lower()] = (name, dtype, array)
    ports = {p['name'].lower(): p for p in task['interface'] if p['direction'] == 'Input/Output'}
    if any(not isinstance(k, str) for k in bindings) or {k.lower() for k in bindings} != set(ports) or len(bindings) != len(ports):
        raise Unsupported('Every IN_OUT port must have exactly one reference binding')
    resolved = {}
    for parameter, target in bindings.items():
        if not isinstance(target, str):
            raise Unsupported('Reference target must be an lvalue')
        match = re.fullmatch(r'(' + IDENT + r')(?:\[(-?\d+)\])?', target)
        if not match or match[1].lower() not in types:
            raise Unsupported('Reference target must be declared storage or a constant-index element')
        name, dtype, array = types[match[1].lower()]
        if match[2] is not None:
            if not array or not int(array[1]) <= int(match[2]) <= int(array[2]):
                raise Unsupported('Reference binding index is outside storage bounds')
            target, dtype, array = name + '[' + str(int(match[2])-int(array[1])) + ']', array[3], None
        else:
            target = name
        declared = ports[parameter.lower()]['type']
        if declared.upper() != 'VARIANT':
            expected = re.sub(r'\s+', '', declared).upper()
            actual = re.sub(r'\s+', '', dtype).upper()
            if array:
                actual_open = 'ARRAY[*]OF' + array[3].upper()
            else:
                actual_open = actual
            if expected not in (actual, actual_open):
                raise Unsupported('Reference binding type mismatch: ' + parameter)
        resolved[parameter.lower()] = {'target': target, 'type': dtype, 'array': array,
                                       'variant': declared.upper() == 'VARIANT'}
    def storage_declaration(obj):
        a=ARRAY.fullmatch(obj['type'].strip())
        # Spaces prevent the STEP7 lexer treating a negative range as a
        # minus followed by one CONSTANT_RANGE token (e.g. -3..1).
        # The bundled structured C exporter assumes zero-based storage.
        # Keep original bounds in the binding descriptor, normalize storage
        # here and every parameter access below, including constant aliases.
        dtype=f'ARRAY[0 .. {int(a[2])-int(a[1])}] OF {a[3]}' if a else obj['type']
        return obj['name'] + ' : ' + dtype + ';'
    return {'declarations': [storage_declaration(o) for o in objects],
            'bindings': resolved, 'contract': model}


def _pv1(body, refs, local_types):
    """Lower this project's PV1 copy API, with guards and ordinal indices.

    Side-effecting calls must be a whole assignment RHS. Expressions that
    contain side effects or dynamic targets are rejected, never reordered.
    """
    def count(m):
        ref = refs.get(m[1].lower())
        if not ref or not ref['variant']:
            raise Unsupported('PV_COUNT requires a bound VARIANT')
        a = ref['array']
        return str(int(a[2])-int(a[1])+1) if a else '0'
    body = _replace(body, r'\bPV_COUNT\s*\(\s*(' + IDENT + r')\s*\)', count)

    def pair(buffer, item):
        a, b = refs.get(buffer.lower()), refs.get(item.lower())
        if not a or not b or not a['variant'] or not b['variant']:
            raise Unsupported('PV1 helpers require bound VARIANT parameters')
        valid = a['array'] is not None and b['array'] is None and a['array'][3].lower() == b['type'].lower()
        return a, b, valid

    def compatible(m):
        return 'TRUE' if pair(m[1], m[2])[2] else 'FALSE'
    body = _replace(body, r'\bPV_COMPATIBLE\s*\(\s*(' + IDENT + r')\s*,\s*(' + IDENT + r')\s*\)', compatible)

    pattern = (r'\b(' + IDENT + r')\s*:=\s*PV_(READ|WRITE)\s*\(\s*(' + IDENT +
               r')\s*,\s*(' + IDENT + r'|-?\d+)\s*,\s*(' + IDENT + r')\s*\)\s*;')
    def copy(m):
        a, b, valid = pair(m[3], m[5])
        if not valid:
            return m[1] + ' := FALSE;'
        bounds = a['array']; index = m[4]
        if re.fullmatch(r'-?\d+',index):
            index='DINT#'+index
        elif local_types.get(index.lower(),'').upper() != 'DINT':
            raise Unsupported('PV1 index must be a DINT variable or integer literal')
        length = int(bounds[2])-int(bounds[1])+1
        # Conversion is dominated by the range check, so cannot wrap a bad
        # index into the array. Storage is zero-based, PV1 uses ordinals.
        element = a['target'] + '[DINT_TO_INT(' + index + ')]'
        target, value = (b['target'], element) if m[2].upper() == 'READ' else (element, b['target'])
        # Write the result last: it may alias the source or index variable.
        return (f'IF ({index} >= DINT#0) AND ({index} < DINT#{length}) THEN\n'
                f'{target} := {value};\n{m[1]} := TRUE;\nELSE\n{m[1]} := FALSE;\nEND_IF;')
    body = _replace(body, pattern, copy)
    if re.search(r'\bPV_(?:COUNT|COMPATIBLE|READ|WRITE)\s*\(', mask_noncode(body), re.I):
        raise Unsupported('Unsupported PV1 expression; copy calls require result := PV_READ/PV_WRITE(buffer, index, item)')
    for name, ref in refs.items():
        if ref['variant'] and re.search(r'\b' + re.escape(name) + r'\b', mask_noncode(body), re.I):
            raise Unsupported('VARIANT is supported only through the explicit PV1 helper contract: ' + name)
    return body


def inline(source, task, plan):
    """Return a state-only FB declaration and its one-call harness statements."""
    units = split_units(source)
    unit = next((u for u in units if u['name'].lower() == task['block'].lower()), None)
    if unit is None or unit['kind'] != 'FUNCTION_BLOCK':
        raise Unsupported('Reference extension requires a function-block entry')
    # A source-owned caller or helper might access the removed parameter fields.
    # Only the framework-generated caller is covered by this version.
    others = [u for u in units if u['kind'] != 'TYPE' and u is not unit]
    if others:
        raise Unsupported('Reference extension currently accepts one FB plus TYPE declarations; helper POUs need separate reference analysis')
    if re.search(r'\bVAR_(?:TEMP|EXTERNAL|GLOBAL)\b', mask_noncode(unit['declaration']), re.I):
        raise Unsupported('Reference inlining does not yet support TEMP/EXTERNAL/GLOBAL declarations')
    for obj in plan['contract']['objects']:
        dtype = ARRAY.fullmatch(obj['type'].strip())
        dtype = dtype[3] if dtype else obj['type']
        if dtype.upper() not in SCALARS and not any(u['kind'] == 'TYPE' and u['name'].lower() == dtype.lower() for u in units):
            raise Unsupported('Reference storage type must be a scalar or source-declared TYPE: ' + dtype)
    declaration = unit['declaration']
    refs = plan['bindings']
    inouts = list(re.finditer(r'\bVAR_IN_OUT\b(.*?)\bEND_VAR\b', mask_noncode(declaration), re.I | re.S))
    if len(inouts) != 1:
        raise Unsupported('Reference entry requires exactly one VAR_IN_OUT section')
    actual = {}
    for field in inouts[0][1].split(';'):
        if not field.strip():
            continue
        m = re.fullmatch(r'\s*(' + IDENT + r')\s*:\s*(.*?)\s*', field, re.S)
        if not m:
            raise Unsupported('Reference declarations require one name per field')
        actual[m[1].lower()] = re.sub(r'\s+', '', m[2]).upper()
    expected = {p['name'].lower(): re.sub(r'\s+', '', p['type']).upper()
                for p in task['interface'] if p['direction'] == 'Input/Output'}
    if actual != expected:
        raise Unsupported('Source IN_OUT declarations do not match the reference interface')
    declaration = declaration[:inouts[0].start()] + declaration[inouts[0].end():]
    locals_ = {}; local_types = {}
    for section in re.finditer(r'\bVAR(?:_INPUT|_OUTPUT)?\b(.*?)\bEND_VAR\b', mask_noncode(declaration), re.I | re.S):
        for field in section[1].split(';'):
            if not field.strip():
                continue
            m = re.fullmatch(r'\s*(' + IDENT + r')\s*:\s*(.*?)\s*', field, re.S)
            if not m or m[1].lower() in locals_ or m[1].lower() in refs:
                raise Unsupported('Reference state declarations require unique single names')
            locals_[m[1].lower()] = 'PVL_Uut.' + m[1]
            local_types[m[1].lower()] = m[2].split(':=',1)[0].strip()
    body = unit['implementation']
    # RETURN inside a loop cannot be replaced by EXIT from the wrapper.
    loops = 0
    for token in re.finditer(r'\b(FOR|WHILE|REPEAT|END_FOR|END_WHILE|END_REPEAT|RETURN|GOTO)\b', mask_noncode(body), re.I):
        kind = token[1].upper()
        if kind == 'GOTO' or (kind == 'RETURN' and loops):
            raise Unsupported('Reference inlining rejects GOTO and RETURN inside loops')
        if kind in ('FOR', 'WHILE', 'REPEAT'):
            loops += 1
        elif kind.startswith('END_'):
            loops -= 1
    # EXIT outside an original loop would acquire new meaning in our wrapper.
    if re.search(r'\bEXIT\b', mask_noncode(body), re.I):
        raise Unsupported('Reference inlining currently rejects source EXIT statements')
    def bound(m):
        ref = refs.get(m[2].lower())
        if not ref or not ref['array'] or ref['variant']:
            raise Unsupported('Bound query requires a bound open/fixed array')
        return '(' + ref['array'][1 if m[1].upper() == 'LOWER' else 2] + ')'
    body = _replace(body, r'\b(LOWER|UPPER)_BOUND\s*\(\s*(' + IDENT + r')\s*,\s*1\s*\)', bound)
    if re.search(r'\b(?:LOWER|UPPER)_BOUND\s*\(', mask_noncode(body), re.I):
        raise Unsupported('Only dimension 1 bound queries on bound parameters are supported')
    for name, ref in refs.items():
        if ref['array'] and not ref['variant']:
            # Nested subscripts need an expression parser; reject them.
            body = _replace(body, r'\b' + re.escape(name) + r'\s*\[([^\[\]]+)\]',
                            lambda m: ref['target']+'[PLCVERIF_REF_INDEX_'+name.upper()+'('+m[1]+')]')
            if re.search(r'\b'+re.escape(name)+r'\b',mask_noncode(body),re.I):
                raise Unsupported('Array references must use simple element indexing or dimension-1 bound queries')
    body = _pv1(body, refs, local_types)
    # The STEP7 translator otherwise creates an INT#1 increment even for a
    # DINT loop counter, then fails when constructing the CFA addition.
    def loop_step(m):
        if local_types.get(m[1].lower(),'').upper()=='DINT' and not re.search(r'\bBY\b',m[2],re.I):
            return 'FOR '+m[1]+m[2]+' BY DINT#1 DO'
        return m[0]
    body=_replace(body,r'\bFOR\s+('+IDENT+r')(\s*:=\s*[^;]*?\bTO\b[^;]*?)\bDO\b',loop_step)
    # Calling another FB with a reference argument would reintroduce the
    # unsupported parameter mechanism. Only reviewed pure intrinsic families
    # may remain in this deliberately small frontend.
    for call in re.finditer(r'\b(' + IDENT + r')\s*\(', mask_noncode(body)):
        name=call[1].upper()
        if not name.startswith('PLCVERIF_REF_INDEX_') and name not in {'IF', 'ELSIF', 'WHILE', 'UNTIL', 'NOT', 'AND', 'OR', 'XOR', 'ABS', 'MIN', 'MAX', 'LIMIT'} and not re.fullmatch(
                r'(?:'+'|'.join(SCALARS)+r')_TO_(?:'+'|'.join(SCALARS)+r')',name):
            raise Unsupported('Reference inlining does not model calls to ' + call[1])
    names = {**locals_, **{k: v['target'] for k, v in refs.items()}}
    # One lexical pass; do not rewrite the field in obj.field or a typed literal.
    def substitute(m):
        if m.string[:m.start()].rstrip().endswith(('.', '#')):
            return m[0]
        return names.get(m[0].lower(), 'EXIT' if m[0].upper() == 'RETURN' else m[0])
    body = _replace(body, r'\b' + IDENT + r'\b', substitute)
    inputs = [p for p in task['interface'] if p['direction'] == 'Input']
    if any(p['name'].lower() not in locals_ for p in inputs):
        raise Unsupported('Reference entry input is missing from source declarations')
    pre = [locals_[p['name'].lower()] + ' := ' + p['name'] + ';' for p in inputs]
    state_source='\n'.join(u['declaration'] for u in units if u['kind'] == 'TYPE') + '\n' + declaration + '\nEND_FUNCTION_BLOCK\n'
    for name,ref in refs.items():
        helper='PLCVERIF_REF_INDEX_'+name.upper()
        if not re.search(r'\b'+helper+r'\s*\(',mask_noncode(body),re.I):continue
        # Invalid original indices remain invalid accesses (-1). Narrowing
        # occurs only after the original DINT bounds have been checked.
        lo,hi=ref['array'][1],ref['array'][2]
        state_source+=f'''
FUNCTION {helper} : INT
VAR_INPUT VALUE : DINT; END_VAR
IF (VALUE < DINT#{lo}) OR (VALUE > DINT#{hi}) THEN
    {helper} := INT#-1;
ELSE
    {helper} := DINT_TO_INT(VALUE - DINT#{lo});
END_IF;
END_FUNCTION
'''
    conversions=set(re.findall(r'\b('+'|'.join(SCALARS)+r')_TO_('+'|'.join(SCALARS)+r')\s*\(',mask_noncode(body+state_source),re.I))
    for src,dst in sorted(conversions):
        # The BUILTIN marker is essential: an empty ordinary function would
        # silently return zero instead of performing a conversion.
        state_source+=f'\nFUNCTION {src}_TO_{dst} : {dst}\nVAR_INPUT VALUE : {src}; END_VAR\n//#BUILTIN\nEND_FUNCTION\n'
    return state_source, pre + ['REPEAT', body, 'UNTIL TRUE END_REPEAT;']
