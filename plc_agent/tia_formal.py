"""Conservative TIA SCL input adapter for the existing PLCverif STEP7 frontend.

Only spelling/packaging is normalized. Native timers, references and external
memory require a reviewed model; they must never be silently replaced by ST code.
"""
import re

from .ltl_adapter import Unsupported
from .st_source import mask_noncode, split_units


def _named_shifts(source, notes):
    masked=mask_noncode(source);changes=[]
    for match in re.finditer(r'\b(SHL|SHR|ROL|ROR)\s*\(',masked,re.I):
        start=match.end();depth=1;pos=start;parts=[];cursor=start
        while pos<len(masked) and depth:
            if masked[pos] in '([':depth+=1
            elif masked[pos] in ')]':depth-=1
            elif masked[pos]==',' and depth==1:parts.append(source[cursor:pos]);cursor=pos+1
            pos+=1
        if depth:raise Unsupported('Unclosed Siemens shift call')
        parts.append(source[cursor:pos-1])
        if not any(':=' in p for p in parts):continue
        args={}
        for part in parts:
            item=re.fullmatch(r'\s*(IN|N)\s*:=\s*(.*?)\s*',part,re.I|re.S)
            if not item or item[1].upper() in args:raise Unsupported('Expected unique IN/N shift arguments')
            args[item[1].upper()]=item[2]
        if set(args)!={'IN','N'}:raise Unsupported('Expected IN and N shift arguments')
        changes.append((match.start(),pos,match[1]+'('+args['IN']+', '+args['N']+')'))
    for start,end,text in reversed(changes):source=source[:start]+text+source[end:]
    if changes:notes.append({'kind':'named_shift_arguments','count':len(changes),'semantics':'Delegated to shared ST adapter'})
    return source


def adapt(source, *, block=None):
    # Tokenize strings/comments separately: # inside a typed literal or a string
    # is not a local-variable prefix. Preserve comments and literals verbatim.
    token = re.compile(r"//[^\n]*|\(\*|'(?:\$[\s\S]|''|[^'])*'|\"(?:[^\"]|\"\")*\"|\{[^}]*\}|#[A-Za-z_]\w*", re.S)
    changes = []
    units = set(re.findall(r'\b(?:FUNCTION_BLOCK|FUNCTION|TYPE)\s+"?([A-Za-z_]\w*)', mask_noncode(source.replace('"', ' ')), re.I))
    # Use the actual lexical tokens for quoted unit declarations.
    headers = re.findall(r'\b(?:FUNCTION_BLOCK|FUNCTION|TYPE)\s+(?:"([A-Za-z_]\w*)"|([A-Za-z_]\w*))', source, re.I)
    units.update(a or b for a, b in headers)
    masked = mask_noncode(source)
    if re.search(r'\b(?:POINTER|REF_TO|AT|RD_SYS_T|RD_LOC_T)\b|%|\b(?:DATA_BLOCK|ORGANIZATION_BLOCK)\b', masked, re.I):
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
            if not re.fullmatch(r'[A-Za-z_]\w*', name) or name.lower() not in {n.lower() for n in units}:
                raise Unsupported('Quoted external symbol needs explicit modeling: '+text)
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
    result = ''.join(output)
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
    # TIA TYPE headers use a VERSION line and omit the classic ':' separator.
    result = re.sub(r'(?im)^(\s*TYPE\s+\w+)\s*\n\s*VERSION\s*:\s*[\d.]+\s*\n', r'\1 :\n', result)
    # VERSION is metadata, not executable source. Keep BEGIN, types and all
    # executable expressions for the native STEP7 frontend.
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
    additions = []
    for unit in parsed:
        if not re.search(r'\bVAR_TEMP\b', mask_noncode(unit['declaration']), re.I): continue
        if unit['kind'] != 'FUNCTION_BLOCK' or (block and unit['name'].lower() != block.lower()):
            raise Unsupported('Helper-block VAR_TEMP requires call-local nondeterministic modeling')
        if not block: block = unit['name']
        decl = unit['declaration']; resets = []
        def lower_temps(match):
            body = match[1]; consumed = 0; fields = []
            for field in re.finditer(r'\s*([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*:\s*(BOOL|SINT|USINT|INT|UINT|DINT|UDINT|LINT|ULINT|BYTE|WORD|DWORD|LWORD|REAL|LREAL|TIME)\s*;', body, re.I):
                if body[consumed:field.start()].strip(): raise Unsupported('Unsupported temporary declaration')
                consumed = field.end()
                for name in field[1].split(','):
                    name=name.strip(); new='WBTEMP_'+str(len(additions))
                    additions.append({'direction':'Input','name':new,'type':field[2].upper()})
                    fields.append(name+' : '+field[2]+';'); resets.append(name+' := '+new+';')
            if body[consumed:].strip(): raise Unsupported('Temporary array/struct/initializer requires an explicit model')
            return 'VAR\n'+'\n'.join(fields)+'\nEND_VAR'
        # Comments are whitespace in the model declaration; literal defaults are
        # refused above instead of giving them an invented lifetime.
        masked_decl = mask_noncode(decl)
        spans = list(re.finditer(r'\bVAR_TEMP\b(.*?)\bEND_VAR\b', masked_decl, re.I|re.S))
        for match in reversed(spans):
            lowered = lower_temps(match)
            decl = decl[:match.start()]+lowered+decl[match.end():]
        extra='\nVAR_INPUT\n'+'\n'.join(p['name']+' : '+p['type']+';' for p in additions)+'\nEND_VAR\n'
        impl = unit['implementation']
        begin = re.search(r'\bBEGIN\b', mask_noncode(impl), re.I)
        if not begin: raise Unsupported('TIA FB must have BEGIN for temporary modeling')
        impl = impl[:begin.end()]+'\n'+'\n'.join(resets)+impl[begin.end():]
        old=unit['declaration']+unit['implementation']
        result=result.replace(old,decl+extra+impl,1)
    if additions: changes.append({'kind':'fresh_temporary_inputs','interface_additions':additions,
                                  'semantics':'Fresh nondeterministic values at each FB call, including the first call'})
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
    except Unsupported as exc:
        declared=properties(task.get('ltl',{}))
        report={'status':'unsupported','backend':'plcverif+'+(config or plcverif_backend.configuration()).get('engine','cbmc'),
                'task_id':task['id'],'dataset_sha256':task.get('dataset_sha256'),'source_sha256':source_hash,
                'declared_ltl_total':len(declared),'mapped_assertions_total':0,'proved_property_ids':[],
                'bounded_verified_property_ids':[],'full_ltl_proved':False,'model_calls':0,
                'properties':[{**p,'status':'unsupported_model','message':str(exc)} for p in declared],
                'message':str(exc),'evidence_path':str(directory.resolve())}
    else:
        model=directory/'normalized.st';model.write_text(normalized,encoding='utf-8')
        additional=[p for note in notes for p in note.get('interface_additions',[])]
        model_task={**task,'interface':task['interface']+additional}
        report=plcverif_backend.verify(model_task,model,directory/'shared',cancel_event=cancel_event,
                                      timeout_seconds=timeout_seconds,config=config)
        report.update(model_source_sha256=report.get('source_sha256'),source_sha256=source_hash,
                      platform_adaptations=notes,source_dialect='siemens_scl',
                      scope='Shared PLCverif source model after explicit SCL normalization; no native replay/equivalence claim.')
    if source.read_bytes()!=original:
        report.update(status='stale_source',bounded_verified_property_ids=[],message='SCL changed during verification')
        for prop in report['properties']:prop['status']='stale_source'
    atomic_json(directory/'formal.json',report)
    return report
