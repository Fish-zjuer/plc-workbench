"""Lossless ST import helpers shared by validation and CODESYS batching."""
import re
from .bank_contracts import block


def mask_noncode(source):
    """Preserve offsets while hiding nested comments, strings and attributes."""
    chars = list(source)
    i = 0
    while i < len(source):
        start = i
        if source.startswith('(*', i):
            depth = 1
            i += 2
            while i < len(source) and depth:
                if source.startswith('(*', i): depth += 1; i += 2
                elif source.startswith('*)', i): depth -= 1; i += 2
                else: i += 1
            if depth: raise ValueError('Unterminated ST comment')
        elif source.startswith('//', i):
            end = source.find('\n', i)
            i = len(source) if end < 0 else end
        elif source[i] in "'\"":
            quote = source[i]
            i += 1
            closed = False
            while i < len(source):
                if source[i] == '$': i += 2
                elif source[i] == quote:
                    i += 1
                    if i < len(source) and source[i] == quote: i += 1
                    else: closed = True; break
                else: i += 1
            if not closed: raise ValueError('Unterminated ST string')
        elif source[i] == '{':
            end = source.find('}', i + 1)
            if end < 0: raise ValueError('Unterminated ST attribute')
            i = end + 1
        else:
            i += 1
            continue
        for pos in range(start, min(i, len(chars))):
            if chars[pos] not in '\r\n': chars[pos] = ' '
    return ''.join(chars)


def split_units(source):
    """Split the file wrappers required by CODESYS' textual editor API.

    Candidate expressions and declarations are preserved verbatim. Unsupported
    top-level syntax raises an import error rather than being silently dropped.
    """
    masked = mask_noncode(source)
    cursor = 0
    units = []
    pattern = re.compile(r'\b(TYPE|FUNCTION_BLOCK|FUNCTION|PROGRAM)\s+([A-Za-z_]\w*)\b', re.I)
    while True:
        match = pattern.search(masked, cursor)
        if match is None:
            if masked[cursor:].strip(' ;\t\r\n'):
                raise ValueError('Unsupported text outside ST units')
            break
        if masked[cursor:match.start()].strip(' ;\t\r\n'):
            raise ValueError('Unsupported ST unit before ' + match.group(2))
        kind, name = match.group(1).upper(), match.group(2)
        end = re.search(r'\bEND_' + kind + r'\b', masked[match.end():], re.I)
        if end is None: raise ValueError('Missing END_' + kind)
        end_start = match.end() + end.start()
        end_offset = match.end() + end.end()
        if kind == 'TYPE':
            if not re.match(r'\s*:', masked[match.end():end_start]):
                raise ValueError('TYPE must contain a named single declaration')
            units.append({'kind': kind, 'name': name, 'declaration': source[cursor:end_offset]})
        else:
            variables = list(re.finditer(r'\bVAR(?:_INPUT|_OUTPUT|_IN_OUT|_TEMP|_EXTERNAL|_GLOBAL)?\b.*?\bEND_VAR\b',
                                         masked[match.end():end_start], re.I | re.S))
            if variables:
                decl_end = match.end() + variables[-1].end()
            else:
                decl_end = masked.find('\n', match.end(), end_start)
                if decl_end < 0: raise ValueError('POU header requires a newline')
            unit = {'kind': kind, 'name': name, 'declaration': source[cursor:decl_end],
                    'implementation': source[decl_end:end_start]}
            if kind == 'FUNCTION':
                returns = masked[match.end():decl_end].split('VAR', 1)[0].strip()
                if not returns.startswith(':'): raise ValueError('FUNCTION return type missing')
                unit['return_type'] = returns[1:].strip()
            units.append(unit)
        cursor = end_offset
    if not units: raise ValueError('No importable ST units')
    names = [u['name'].upper() for u in units]
    if len(names) != len(set(names)): raise ValueError('Duplicate ST unit names')
    return units


def caller(question):
    declarations = ['PROGRAM PLC_PRG', 'VAR', '  uut : ' + block(question['id']) + ';']
    bindings = []
    for name, dtype in re.findall(r'^\| Input/Output \| `([^`]+)` \| `([^`]+)`', question['text'], re.M):
        # An open array is bound to real caller storage, without narrowing the
        # candidate FB interface. The size is only a compile-driver choice.
        concrete = re.sub(r'ARRAY\[\*\]', 'ARRAY[0..2]', dtype, flags=re.I)
        variable = 'caller_' + name
        declarations.append('  ' + variable + ' : ' + concrete + ';')
        bindings.append(name + ' := ' + variable)
    declarations.append('END_VAR')
    return {'declaration': '\n'.join(declarations),
            'implementation': 'uut(' + ', '.join(bindings) + ');'}


