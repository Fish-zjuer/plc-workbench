"""Conservative TIA SCL input adapter for the existing PLCverif STEP7 frontend.

Only spelling/packaging is normalized. Native timers, references and external
memory require a reviewed model; they must never be silently replaced by ST code.
"""
import re

from .ltl_adapter import Unsupported
from .st_source import mask_noncode, split_units
from .tia_scl import inline_readonly_data, lower_temporaries


def _bound_queries(source, notes):
    """Normalize vendor ARR/DIM spelling, leaving storage lowering shared."""
    masked = mask_noncode(source)
    edits = []
    for match in re.finditer(r'\b(LOWER_BOUND|UPPER_BOUND)\s*\(', masked, re.I):
        pos = start = match.end(); depth = 1; spans = []
        while pos < len(masked) and depth:
            char = masked[pos]
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
            elif char == ',' and depth == 1:
                spans.append((start, pos)); start = pos+1
            pos += 1
        if depth:
            raise Unsupported('Unclosed Siemens array-bound query')
        spans.append((start, pos-1))
        if len(spans) != 2:
            raise Unsupported('Array-bound queries require ARR and explicit dimension 1')
        visible = [masked[a:b].strip() for a, b in spans]
        if any(':=' in arg for arg in visible):
            args = {}
            for arg in visible:
                named = re.fullmatch(r'(ARR|DIM)\s*:=\s*(.*?)\s*', arg, re.I|re.S)
                if not named or named[1].upper() in args:
                    raise Unsupported('Expected unique ARR/DIM array-bound arguments')
                args[named[1].upper()] = named[2]
            if set(args) != {'ARR', 'DIM'}:
                raise Unsupported('Expected ARR and DIM array-bound arguments')
            array, dimension = args['ARR'], args['DIM']
        else:
            array, dimension = visible
        if not re.fullmatch(r'[A-Za-z_]\w*', array):
            raise Unsupported('Array-bound ARR must be a simple bound parameter')
        if not re.fullmatch(r'(?:(?:U?SINT|U?INT|U?DINT|U?LINT)\s*#\s*)?1', dimension, re.I):
            raise Unsupported('Only literal dimension 1 array-bound queries are supported')
        if ':=' in ''.join(visible) or dimension != '1':
            # Arguments are pure symbols/constants. Comments can be retained
            # outside the normalized call without changing their evaluation.
            comments = ''.join(ch if visible.isspace() else ' ' for ch, visible in
                               zip(source[match.end():pos-1], masked[match.end():pos-1])).strip()
            replacement = match[1]+'('+array+', 1)'
            if comments: replacement += '\n'+comments+'\n'
            edits.append((match.start(), pos, replacement))
    for start, end, replacement in reversed(edits):
        source = source[:start]+replacement+source[end:]
    if edits:
        notes.append({'kind': 'array_bound_arguments', 'count': len(edits),
                      'dimension': 1, 'semantics': 'Original bound parameter and bounds; delegated to shared reference model'})
    return source


def _named_shifts(source, notes):
    count = 0
    def normalize(text, level=0):
        nonlocal count
        if level > 32: raise Unsupported('Shift call nesting exceeds the SCL adapter limit')
        masked = mask_noncode(text); output = []; cursor = 0
        pattern = re.compile(r'\b(SHL|SHR|ROL|ROR)\s*\(', re.I)
        while True:
            match = pattern.search(masked, cursor)
            if not match: break
            pos = match.end(); start = pos; depth = 1; brackets = 0; spans = []
            while pos < len(masked) and depth:
                char = masked[pos]
                if char == '(': depth += 1
                elif char == ')': depth -= 1
                elif char == '[': brackets += 1
                elif char == ']': brackets -= 1
                elif char == ',' and depth == 1 and brackets == 0:
                    spans.append((start, pos)); start = pos+1
                pos += 1
            if depth: raise Unsupported('Unclosed Siemens shift call')
            spans.append((start, pos-1))
            parts = [(text[a:b], masked[a:b]) for a, b in spans]
            named = any(':=' in visible for _, visible in parts)
            if named:
                args = {}
                for original, visible in parts:
                    name = re.match(r'\s*(IN|N)\s*:=', visible, re.I)
                    if not name or name[1].upper() in args: raise Unsupported('Expected unique IN/N shift arguments')
                    args[name[1].upper()] = normalize(original[name.end():].strip(' \t'), level+1)
                if set(args) != {'IN', 'N'}: raise Unsupported('Expected IN and N shift arguments')
                replacement = match[1]+'('+args['IN']+', '+args['N']+')'; count += 1
            else:
                replacement = text[match.start():match.end()]+', '.join(normalize(original, level+1) for original, _ in parts)+')'
            output += [text[cursor:match.start()], replacement]; cursor = pos
        return ''.join(output)+text[cursor:]
    result = normalize(source)
    if count: notes.append({'kind':'named_shift_arguments','count':count,'semantics':'Delegated to shared ST adapter'})
    return result


def adapt(source, *, block=None):
    # Tokenize strings/comments separately: # inside a typed literal or a string
    # is not a local-variable prefix. Preserve comments and literals verbatim.
    source = source.replace('\r\n','\n').replace('\r','\n')
    token = re.compile(r"//[^\n]*|\(\*|'(?:\$[\s\S]|''|[^'])*'|\"(?:[^\"]|\"\")*\"|\{[^}]*\}|#[A-Za-z_]\w*", re.S)
    changes = []
    # Mask comments/literals before collecting headers, retaining quoted names.
    # Header-looking text in a comment must not authorize an external symbol.
    visible = list(source)
    lexical = re.compile(r"//[^\n]*|\(\*|\"(?:\$[\s\S]|\"\"|[^\"])*\"|'(?:\$[\s\S]|''|[^'])*'", re.S)
    cursor = 0
    while cursor < len(source):
        item = lexical.search(source, cursor)
        if not item: break
        end = item.end()
        if item[0] == '(*':
            depth = 1
            while end < len(source) and depth:
                if source.startswith('(*', end): depth += 1; end += 2
                elif source.startswith('*)', end): depth -= 1; end += 2
                else: end += 1
            if depth: raise Unsupported('Unterminated SCL comment')
        if not item[0].startswith('"'):
            visible[item.start():end] = ['\n' if c=='\n' else ' ' for c in source[item.start():end]]
        cursor = end
    headers = re.findall(r'\b(?:FUNCTION_BLOCK|FUNCTION|TYPE|DATA_BLOCK)\s+(?:"([A-Za-z_]\w*)"|([A-Za-z_]\w*))', ''.join(visible), re.I)
    units = set()
    units.update(a or b for a, b in headers)
    masked = mask_noncode(source)
    if re.search(r'\b(?:POINTER|REF_TO|AT|RD_SYS_T|RD_LOC_T)\b|%|\bORGANIZATION_BLOCK\b', masked, re.I):
        raise Unsupported('TIA external-memory/reference syntax requires a platform adapter; no replacement model is supplied.')
    output = []; cursor = 0
    while cursor < len(source):
        match = token.search(source, cursor)
        if not match:
            output.append(source[cursor:]); break
        output.append(source[cursor:match.start()]); text = match[0]; end = match.end()
        if text == '(*':
            depth = 1
            while end < len(source) and depth:
                if source.startswith('(*', end): depth += 1; end += 2
                elif source.startswith('*)', end): depth -= 1; end += 2
                else: end += 1
            if depth: raise Unsupported('Unterminated SCL comment')
            text = source[match.start():end]
        elif text.startswith('"'):
            name = text[1:-1]
            prefix = source[:match.start()].rstrip()
            suffix = source[end:]
            local = prefix.endswith('#')
            field = prefix.endswith('.')
            prefix_mask = mask_noncode(source[:match.start()])
            sections = list(re.finditer(r'\b(?:VAR(?:_INPUT|_OUTPUT|_IN_OUT|_TEMP)?|END_VAR|BEGIN)\b', prefix_mask, re.I))
            in_declaration = bool(sections and sections[-1][0].upper().startswith('VAR'))
            declared = in_declaration and bool(re.match(r'\s*(?:,\s*(?:"[A-Za-z_]\w*"|\w+)\s*)*:(?!=)', suffix))
            if not re.fullmatch(r'[A-Za-z_]\w*', name) or (not local and not field and not declared and name.lower() not in {n.lower() for n in units}):
                raise Unsupported('Missing or unmodeled external symbol: '+text+'; include its supported declaration in the same SCL source')
            if local:
                # The # preceding a quoted local was not consumed by the token.
                output[-1] = output[-1][:-1]
            changes.append({'kind': 'symbol_spelling', 'symbol': name}); text = name
        elif text.startswith('{'):
            if not re.fullmatch(r"\{\s*S7_Optimized_Access\s*:=\s*'TRUE'\s*\}", text, re.I):
                raise Unsupported('Unmodeled Siemens system attribute: '+text)
            changes.append({'kind': 'layout_attribute', 'attribute': 'S7_Optimized_Access',
                            'reason': 'No absolute memory, pointers or references admitted by this adapter'})
            text = ' '
        elif text.startswith('#'):
            # The preceding token distinguishes #local from DWORD#16#FF etc.
            if match.start() == 0 or not re.match(r'[\w#]', source[match.start()-1]):
                changes.append({'kind': 'local_symbol_prefix', 'symbol': text[1:]}); text = text[1:]
        output.append(text); cursor = end
    result = inline_readonly_data(''.join(output), changes)
    # Map Siemens timer spellings to the shared ST frontend. Timer semantics,
    # admissible call shapes and support limits belong to plcverif_st, not here.
    timer_edits=[]
    for m in re.finditer(r'\b(TON|TOF|TP)_TIME\b|\b([A-Za-z_]\w*)\.(TON|TOF|TP)\s*\(',mask_noncode(result),re.I):
        timer_edits.append((m.start(),m.end(),m[1] if m[1] else m[2]+'('))
    for start,end,text in reversed(timer_edits):result=result[:start]+text+result[end:]
    if timer_edits:changes.append({'kind':'timer_spelling','count':len(timer_edits),'semantics':'Delegated to shared ST adapter'})
    # The shared ST interface owns shift modeling. Normalize only named argument
    # syntax; never add an empty built-in or a substitute SHL/SHR implementation.
    result = _named_shifts(result, changes)
    result = _bound_queries(result, changes)
    # The legacy STEP7 lexer can tokenize adjacent range dots as a REAL.
    # Separating punctuation changes neither the bounds nor executable values.
    ranges = list(re.finditer(r'\.\.', mask_noncode(result)))
    for match in reversed(ranges): result=result[:match.start()]+' .. '+result[match.end():]
    if ranges: changes.append({'kind':'range_token_spacing','count':len(ranges)})
    # TIA TYPE headers use a VERSION line and omit the classic ':' separator.
    result = re.sub(r'(?im)^(\s*TYPE\s+\w+)\s*\n\s*VERSION\s*:\s*[\d.]+\s*\n', r'\1 :\n', result)
    # VERSION is metadata, not executable source. Retain BEGIN until temporary
    # initialization is modeled below; preserve types/executable expressions.
    result = re.sub(r'(?im)^\s*VERSION\s*:\s*[\d.]+\s*$', '', result)
    try: parsed = split_units(result)
    except ValueError as exc: raise Unsupported('SCL unit packaging: '+str(exc)) from exc
    for unit in parsed:
        for section in re.finditer(r'\bVAR(?:_INPUT|_OUTPUT|_IN_OUT|_TEMP)?\b(.*?)\bEND_VAR\b',mask_noncode(unit['declaration']),re.I|re.S):
            for name in re.findall(r'\b(\w+)\s*:',section[1]):
                if name.lower() in {n.lower() for n in units}:
                    raise Unsupported('Local/global symbol collision needs namespace-preserving modeling: '+name)
    for loop in re.finditer(r'\bFOR\s+(\w+)\s*:=.*?\bTO\b(.*?)\bDO\b',mask_noncode(result),re.I|re.S):
        if re.search(r'\b'+re.escape(loop[1])+r'\b',loop[2],re.I) or re.search(r'\b\w+\s*\(',loop[2]):
            raise Unsupported('TIA FOR final-bound evaluation requires a dedicated model for this expression')
    if re.search(r'\bWBTEMP_\w*', mask_noncode(result), re.I): raise Unsupported('WBTEMP_ is reserved for fresh temporary-value inputs')
    # Fresh nondeterministic inputs model undefined VAR_TEMP storage per call.
    # Assigned-before-read candidates overwrite these values naturally. No zero
    # initialization or scan-to-scan retention is assumed for Siemens temps.
    if block is None:
        entries = [unit['name'] for unit in parsed if unit['kind']=='FUNCTION_BLOCK']
        if len(entries)!=1: raise Unsupported('Specify the entry block for SCL temporary lifetime modeling')
        block = entries[0]
    result = lower_temporaries(result, parsed, block, changes)
    parsed = split_units(result)
    # Shared reference inlining embeds the implementation in a REPEAT body.
    # Siemens BEGIN is a POU delimiter, never an executable nested statement.
    # Remove only the leading delimiter of each parsed POU, not arbitrary words.
    begin_edits = []; offset = 0
    for unit in parsed:
        if 'implementation' not in unit: continue
        old = unit['declaration']+unit['implementation']
        start = result.find(old, offset)
        if start < 0: raise Unsupported('Cannot locate SCL POU boundary')
        marker = re.match(r'\s*BEGIN\b', mask_noncode(unit['implementation']), re.I)
        if marker:
            pos = start+len(unit['declaration'])+marker.end()-len('BEGIN')
            begin_edits.append((pos, pos+len('BEGIN')))
        offset = start+len(old)
    for start, end in reversed(begin_edits): result=result[:start]+' '*len('BEGIN')+result[end:]
    if begin_edits:
        changes.append({'kind':'pou_begin_delimiter','count':len(begin_edits)})
        parsed = split_units(result)
    return result, changes


def verify(task, source, directory, *, cancel_event=None, timeout_seconds=None, config=None):
    """Normalize SCL at the boundary, then call the unchanged shared verifier."""
    import hashlib
    from pathlib import Path
    from . import plcverif_backend
    from .ltl_adapter import properties
    from .storage import atomic_json
    source=Path(source);directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    original=source.read_bytes();source_hash=hashlib.sha256(original).hexdigest()
    try:
        normalized,notes=adapt(original.decode('utf-8-sig'),block=task['block'])
        # The installed structured-C exporter emits raw indices for arrays with
        # negative lower bounds. Do not let an adapter expansion produce an
        # apparent proof over invalid C storage; leave the shared model intact.
        if re.search(r'\bARRAY\s*\[\s*-|\bARRAY\s*\[[^]]*,\s*-',mask_noncode(normalized),re.I):
            raise Unsupported('Shared structured-C exporter needs reviewed negative-array-bound lowering; TIA does not replace that model')
    except Unsupported as exc:
        declared=properties(task.get('ltl',{}))
        report={'status':'unsupported','backend':'plcverif+'+(config or plcverif_backend.configuration()).get('engine','cbmc'),
                'task_id':task['id'],'dataset_sha256':task.get('dataset_sha256'),'source_sha256':source_hash,
                'declared_ltl_total':len(declared),'mapped_assertions_total':0,'proved_property_ids':[],
                'bounded_verified_property_ids':[],'full_ltl_proved':False,'model_calls':0,
                'properties':[{**p,'status':'unsupported_model','message':str(exc)} for p in declared],
                'message':str(exc),'evidence_path':str(directory.resolve())}
    else:
        # The shared exporter writes Windows newlines. Keep this intermediate
        # file LF-only so raw-byte reads cannot introduce doubled CRs.
        model=directory/'normalized.st';model.write_text(normalized,encoding='utf-8',newline='\n')
        additional=[p for note in notes for p in note.get('interface_additions',[])]
        model_task={**task,'interface':task['interface']+additional}
        report=plcverif_backend.verify(model_task,model,directory/'shared',cancel_event=cancel_event,
                                      timeout_seconds=timeout_seconds,config=config)
        report.update(model_source_sha256=report.get('source_sha256'),source_sha256=source_hash,
                      platform_adaptations=notes,source_dialect='siemens_scl',
                      platform_assumptions=[value for note in notes for value in note.get('assumptions',[])],
                      scope='Shared PLCverif source model after explicit SCL normalization; no native replay/equivalence claim.')
    if source.read_bytes()!=original:
        report.update(status='stale_source',bounded_verified_property_ids=[],message='SCL changed during verification')
        for prop in report['properties']:prop['status']='stale_source'
    atomic_json(directory/'formal.json',report)
    return report
