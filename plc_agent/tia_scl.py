"""Bounded, fail-closed SCL declaration handling at the TIA platform boundary.

No solver, standard instruction or reference/VARIANT model is defined here.
"""
import itertools
import re

from .ltl_adapter import Unsupported
from .st_source import mask_noncode

SCALARS = frozenset('BOOL SINT USINT INT UINT DINT UDINT LINT ULINT BYTE WORD DWORD LWORD REAL LREAL TIME'.split())
MAX_TEMP_LEAVES = 256


def fields(text):
    """Read declarations, retaining aggregate types and rejecting initializers."""
    clean = mask_noncode(text)
    pos = 0
    while clean[pos:].strip():
        match = re.match(r'\s*([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*:\s*', clean[pos:])
        if not match:
            raise Unsupported('Unsupported SCL field declaration: '+clean[pos:pos+80].strip())
        start = pos + match.end()
        depth = 0
        end = None
        for token in re.finditer(r'\bSTRUCT\b|\bEND_STRUCT\b|;', clean[start:], re.I):
            word = token[0].upper()
            if word == 'STRUCT': depth += 1
            elif word == 'END_STRUCT': depth -= 1
            elif depth == 0:
                end = start + token.start()
                break
            if depth < 0: raise Unsupported('Unbalanced STRUCT declaration')
        if end is None: raise Unsupported('Unterminated SCL field declaration')
        dtype = text[start:end].strip()
        if ':=' in clean[start:end]:
            raise Unsupported('Temporary/type initializers require explicit lifetime semantics')
        for name in match[1].split(','):
            yield name.strip(), dtype
        pos = end + 1


def type_definitions(units):
    definitions = {}
    for unit in units:
        if unit['kind'] != 'TYPE': continue
        match = re.fullmatch(r'\s*TYPE\s+\w+\s*:\s*(.*?)\s*;?\s*END_TYPE\s*',
                             mask_noncode(unit['declaration']), re.I | re.S)
        if not match: raise Unsupported('Unsupported SCL type definition: '+unit['name'])
        definitions[unit['name'].lower()] = match[1].rstrip().removesuffix(';').strip()
    return definitions


def leaves(dtype, definitions, trail=()):
    """Enumerate exact fixed aggregate members; never narrow an open array."""
    text = mask_noncode(dtype).strip()
    if text.upper() in SCALARS: return [('', text.upper())]
    key = text.lower()
    if key in definitions:
        if key in trail or len(trail) >= 16: raise Unsupported('Recursive/deep SCL type: '+text)
        return leaves(definitions[key], definitions, trail+(key,))
    array = re.fullmatch(r'ARRAY\s*\[([^]]+)\]\s+OF\s+(.+)', text, re.I | re.S)
    if array:
        dimensions = []
        count = 1
        for dimension in array[1].split(','):
            bound = re.fullmatch(r'\s*([+-]?[\d_]+)\s*\.\.\s*([+-]?[\d_]+)\s*', dimension)
            if not bound: raise Unsupported('Temporary arrays require explicit integer bounds; open/reference arrays are unchanged')
            lo, hi = (int(x.replace('_', '')) for x in bound.groups())
            if hi < lo: raise Unsupported('Reversed temporary array bounds')
            count *= hi-lo+1
            if count > MAX_TEMP_LEAVES: raise Unsupported('Temporary expansion exceeds '+str(MAX_TEMP_LEAVES)+' scalar leaves')
            dimensions.append(range(lo, hi+1))
        members = leaves(array[2], definitions, trail)
        if count*len(members) > MAX_TEMP_LEAVES: raise Unsupported('Temporary expansion exceeds '+str(MAX_TEMP_LEAVES)+' scalar leaves')
        return [('['+','.join(map(str, indices))+']'+suffix, typ)
                for indices in itertools.product(*dimensions) for suffix, typ in members]
    struct = re.fullmatch(r'STRUCT\b(.*?)\bEND_STRUCT', text, re.I | re.S)
    if struct:
        result = []; names = set()
        for name, typ in fields(struct[1]):
            if name.lower() in names: raise Unsupported('Duplicate temporary struct member: '+name)
            names.add(name.lower())
            result += [('.'+name+suffix, scalar) for suffix, scalar in leaves(typ, definitions, trail)]
            if len(result) > MAX_TEMP_LEAVES: raise Unsupported('Temporary expansion exceeds '+str(MAX_TEMP_LEAVES)+' scalar leaves')
        if not result: raise Unsupported('Empty temporary structure')
        return result
    raise Unsupported('Temporary type needs a platform lifetime model: '+text)


def helper_initializes_temporaries(unit, members):
    """Prove a straight-line initialization prefix before any temporary read.

    Helpers can be called repeatedly inside one scan. Reusing one nondeterministic
    scan input there would be unsound, so only fully initialized helpers pass.
    """
    body = mask_noncode(unit['implementation'])
    remaining = {re.sub(r'\s+', '', name).lower() for name in members}
    roots = {re.match(r'\w+', name)[0].lower() for name in remaining}
    body = re.sub(r'^\s*BEGIN\b', '', body, flags=re.I)
    for statement in body.split(';'):
        if not remaining: return True
        assignment = re.fullmatch(r'\s*([A-Za-z_]\w*(?:\s*\[[\d\s,+-]+\]|\s*\.\s*\w+)*)\s*:=\s*(.+)\s*', statement, re.S)
        if not assignment: return False
        target = re.sub(r'\s+', '', assignment[1]).lower()
        # Conservatively reject a read of any partially initialized aggregate.
        for name in remaining:
            root = re.match(r'\w+', name)[0]
            if re.search(r'\b'+re.escape(root)+r'\b', assignment[2], re.I): return False
        if re.match(r'\w+', target)[0] in roots:
            remaining = {name for name in remaining if name != target and
                         not name.startswith(target+'.') and not name.startswith(target+'[')}
    return not remaining


def lower_temporaries(source, units, block, notes):
    definitions = type_definitions(units)
    additions = []
    edits = []
    offset = 0
    for unit in units:
        declaration = unit['declaration']
        spans = list(re.finditer(r'\bVAR_TEMP\b(.*?)\bEND_VAR\b', mask_noncode(declaration), re.I | re.S))
        if not spans: continue
        members = []
        for span in spans:
            # Keep original declarations; only enumeration uses masked text.
            for name, dtype in fields(declaration[span.start(1):span.end(1)]):
                members += [(name+suffix, scalar) for suffix, scalar in leaves(dtype, definitions)]
        is_entry = unit['kind'] == 'FUNCTION_BLOCK' and unit['name'].lower() == block.lower()
        if not is_entry:
            if not helper_initializes_temporaries(unit, [name for name, _ in members]):
                raise Unsupported('Helper '+unit['name']+' must initialize every temporary before use; per-call fresh modeling is not supplied')
            notes.append({'kind':'initialized_helper_temporaries','block':unit['name'],
                          'semantics':'All temporary members assigned in a straight-line prefix before any read'})
            continue
        if len(additions)+len(members) > MAX_TEMP_LEAVES:
            raise Unsupported('Temporary expansion exceeds '+str(MAX_TEMP_LEAVES)+' scalar leaves')
        resets = []
        for member, scalar in members:
            fresh = 'WBTEMP_'+str(len(additions))
            additions.append({'direction':'Input','name':fresh,'type':scalar})
            resets.append(member+' := '+fresh+';')
        for span in reversed(spans):
            declaration = declaration[:span.start()]+'VAR'+declaration[span.start()+len('VAR_TEMP'):span.end()]+declaration[span.end():]
        declaration += '\nVAR_INPUT\n'+'\n'.join(p['name']+' : '+p['type']+';' for p in additions)+'\nEND_VAR\n'
        implementation = unit['implementation']
        begin = re.search(r'\bBEGIN\b', mask_noncode(implementation), re.I)
        if not begin: raise Unsupported('TIA FB must have BEGIN for temporary modeling')
        implementation = implementation[:begin.end()]+'\n'+'\n'.join(resets)+implementation[begin.end():]
        old = unit['declaration']+unit['implementation']
        start = source.find(old, offset)
        if start < 0: raise Unsupported('Cannot locate temporary declaration in its source unit')
        edits.append((start, start+len(old), declaration+implementation)); offset = start+len(old)
    for start, end, replacement in reversed(edits): source = source[:start]+replacement+source[end:]
    if additions:
        notes.append({'kind':'fresh_temporary_inputs','interface_additions':additions,
                      'semantics':'Fresh independent scalar values at each entry FB call; exact fixed array/struct members, no zero or retained-state assumption'})
    return source


def inline_readonly_data(source, notes):
    """Resolve self-contained immutable scalar DB values, never missing globals.

    Only direct rvalues outside call arguments are admitted. This excludes
    IN_OUT aliases, output bindings, mutable globals and hidden template values.
    """
    masked = mask_noncode(source)
    blocks = list(re.finditer(r'\bDATA_BLOCK\s+(\w+)\b(.*?)\bEND_DATA_BLOCK\b', masked, re.I | re.S))
    values = {}; edits = []
    for db in blocks:
        body = db[2]
        body = re.sub(r'(?im)^\s*VERSION\s*:\s*[\d.]+\s*$', '', body)
        match = re.fullmatch(r'\s*VAR\b(.*?)\bEND_VAR\s*BEGIN\s*', body, re.I | re.S)
        if not match: raise Unsupported('External DB '+db[1]+' must be self-contained scalar storage with declaration initializers only')
        for field in re.finditer(r'\s*(\w+)\s*:\s*(\w+)\s*(?::=\s*([^;]+))?\s*;', match[1]):
            key = (db[1]+'.'+field[1]).lower(); dtype = field[2].upper()
            if key in values: raise Unsupported('Duplicate external DB member: '+key)
            if dtype not in SCALARS: raise Unsupported('External DB constants currently require elementary scalar fields: '+key)
            literal = (field[3] or ('FALSE' if dtype=='BOOL' else 'T#0ms' if dtype=='TIME' else '0')).strip()
            if dtype == 'BOOL':
                if not re.fullmatch(r'(?:BOOL#)?(?:TRUE|FALSE)', literal, re.I): raise Unsupported('External BOOL needs a literal initializer: '+key)
            elif dtype == 'TIME':
                if not re.fullmatch(r'(?:T|TIME)#[\d_]+(?:MS|S|M|H|D)', literal, re.I): raise Unsupported('External TIME needs a literal initializer: '+key)
            else:
                typed = re.fullmatch(r'(?:(\w+)#)?([+-]?[\d_]+(?:\.[\d_]+)?(?:[Ee][+-]?\d+)?)', literal)
                if not typed or (typed[1] and typed[1].upper()!=dtype): raise Unsupported('External constant needs a same-type numeric literal: '+key)
                if dtype not in ('REAL','LREAL') and re.search(r'[.Ee]',typed[2]): raise Unsupported('Integer DB initializer must be integral: '+key)
                literal = dtype+'#'+typed[2]
            values[key] = literal
        rest = re.sub(r'\s*\w+\s*:\s*\w+\s*(?::=\s*[^;]+)?\s*;', '', match[1])
        if rest.strip(): raise Unsupported('Unsupported external DB declaration: '+db[1])
        edits.append((db.start(),db.end(),'\n'))
    for start, end, replacement in reversed(edits): source = source[:start]+replacement+source[end:]
    masked = mask_noncode(source)
    for db in blocks:
        for reference in re.finditer(r'\b'+re.escape(db[1])+r'\s*\.\s*(\w+)\b', masked, re.I):
            key = (db[1]+'.'+reference[1]).lower()
            if key not in values: raise Unsupported('Missing external DB member: '+key)
            before = masked[:reference.start()]; after = masked[reference.end():]
            statement = before[before.rfind(';')+1:]
            # A function argument may alias the original storage. Restrict to
            # direct expression rvalues rather than guessing parameter modes.
            if re.search(r'\b\w+\s*\(', statement) or not re.search(r':=', statement) or re.match(r'\s*(?::=|=>|\[|\.)',after):
                raise Unsupported('External DB access must be a direct immutable rvalue, not a write/alias: '+key)
    replacements = []
    for db in blocks:
        pattern = re.compile(r'\b'+re.escape(db[1])+r'\s*\.\s*(\w+)\b', re.I)
        for reference in pattern.finditer(masked):
            replacements.append((reference.start(),reference.end(),values[(db[1]+'.'+reference[1]).lower()]))
        residual = pattern.sub('', masked)
        if re.search(r'\b'+re.escape(db[1])+r'\b', residual, re.I): raise Unsupported('Unmodeled external DB use: '+db[1])
    for start,end,value in sorted(replacements,reverse=True): source=source[:start]+value+source[end:]
    if values:
        notes.append({'kind':'immutable_source_data_blocks','values':values,
                      'assumptions':['Only the supplied closed program and test caller execute; no external DB writers or asynchronous updates'],
                      'semantics':'Literal-initialized DB members used only as direct rvalues; mutable/aliased/missing external storage is refused'})
    return source
