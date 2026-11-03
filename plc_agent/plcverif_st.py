"""CODESYS到STEP7的有限语法适配；原源码保留，模型副本的转换逐项记录。"""
import re
from plc_agent.st_source import mask_noncode, split_units
from plc_agent.ltl_adapter import Unsupported


_SHIFT_BUILTINS = ('SHL', 'SHR', 'ROL', 'ROR')
_SHL_ONE_HELPER = 'PLCVERIF_SHL_DWORD_ONE'


def _adapt_ton(source, scan_period_ms, entry_block):
    """Provide an exact scan-clock TON model for a deliberately narrow form.

    PLCverif's STEP7 parser does not supply TON.  A timer invocation advances
    once per harness scan only when every instance is called exactly once at
    the POU's top level with a fixed TIME literal.  Anything less constrained
    could turn call count into elapsed time and is therefore rejected.
    """
    masked = mask_noncode(source)
    if not re.search(r':\s*TON\b', masked, re.I):
        return source, []
    if re.search(r'\bFUNCTION_BLOCK\s+TON\b', masked, re.I):
        return source, []
    if type(scan_period_ms) is not int or scan_period_ms <= 0:
        raise Unsupported('TON scan period must be a positive integer number of milliseconds')
    units = split_units(source)
    ton_units = [unit for unit in units if 'implementation' in unit and
                 re.search(r':\s*TON\b', mask_noncode(unit['declaration']), re.I)]
    if entry_block is None:
        if len(ton_units) != 1 or ton_units[0]['kind'] != 'FUNCTION_BLOCK':
            raise Unsupported('TON model requires an unambiguous scan-entry function block')
        entry_block = ton_units[0]['name']
    instances = []
    for unit in units:
        if 'implementation' not in unit:
            continue
        declaration = mask_noncode(unit['declaration'])
        if re.search(r':\s*TON\b', declaration, re.I) and (
                unit['kind'] != 'FUNCTION_BLOCK' or unit['name'].lower() != entry_block.lower()):
            raise Unsupported('TON model is only exact inside the function block called once per formal scan: ' + entry_block)
        implementation = unit['implementation']
        impl_masked = mask_noncode(implementation)
        for declared in re.finditer(r'\b([A-Za-z_]\w*)\s*:\s*TON\s*;', declaration, re.I):
            name = declared.group(1)
            calls = list(re.finditer(r'\b' + re.escape(name) + r'\s*\(', impl_masked, re.I))
            if len(calls) != 1:
                raise Unsupported('TON instance ' + name + ' must be called exactly once per scan for an exact PLCverif model')
            call = calls[0]
            open_pos = impl_masked.find('(', call.start(), call.end())
            depth = 1
            pos = open_pos + 1
            while pos < len(impl_masked) and depth:
                if impl_masked[pos] == '(':
                    depth += 1
                elif impl_masked[pos] == ')':
                    depth -= 1
                pos += 1
            if depth:
                raise Unsupported('Unclosed TON call: ' + name)
            arguments = impl_masked[open_pos + 1:pos - 1]
            parts = []
            start = 0
            nested = 0
            for offset, char in enumerate(arguments):
                if char in '([':
                    nested += 1
                elif char in ')]':
                    nested = max(0, nested - 1)
                elif char == ',' and nested == 0:
                    parts.append(arguments[start:offset])
                    start = offset + 1
            parts.append(arguments[start:])
            named = {}
            for part in parts:
                parameter = re.fullmatch(r'\s*([A-Za-z_]\w*)\s*:=\s*(.*?)\s*', part, re.S)
                if not parameter or parameter.group(1).upper() in named:
                    raise Unsupported('TON instance ' + name + ' requires unique named IN and PT arguments')
                named[parameter.group(1).upper()] = parameter.group(2)
            if set(named) != {'IN', 'PT'} or not re.fullmatch(
                    r'T(?:IME)?#[0-9_]+(?:MS|S|M|H|D)', named.get('PT', ''), re.I):
                raise Unsupported('TON instance ' + name + ' requires named IN and a fixed TIME-literal PT for an exact PLCverif model')
            if '=>' in arguments:
                raise Unsupported('TON output bindings are not supported by the exact PLCverif model: ' + name)
            prefix = impl_masked[:call.start()]
            if re.search(r'\b(?:RETURN|GOTO)\b', prefix, re.I):
                raise Unsupported('TON instance ' + name + ' is not provably called on every scan')
            nesting = 0
            controls = re.compile(r'\b(END_IF|END_FOR|END_WHILE|END_REPEAT|END_CASE|IF|FOR|WHILE|REPEAT|CASE)\b', re.I)
            for token in controls.finditer(prefix):
                nesting += -1 if token.group(1).upper().startswith('END_') else 1
                nesting = max(0, nesting)
            if nesting:
                raise Unsupported('TON instance ' + name + ' must be an unconditional top-level call for an exact PLCverif model')
            instances.append(name)
    if not instances:
        raise Unsupported('PLCverif TON declarations could not be associated with executable instances')
    tick = f'T#{scan_period_ms}ms'
    model = f'''FUNCTION_BLOCK TON
VAR_INPUT IN : BOOL; PT : TIME; END_VAR
VAR_OUTPUT Q : BOOL := FALSE; ET : TIME := T#0ms; END_VAR
VAR PLCVERIF_TON_RUNNING : BOOL := FALSE; END_VAR
IF NOT IN THEN
    Q := FALSE;
    ET := T#0ms;
    PLCVERIF_TON_RUNNING := FALSE;
ELSIF NOT PLCVERIF_TON_RUNNING THEN
    PLCVERIF_TON_RUNNING := TRUE;
    ET := T#0ms;
    Q := PT <= T#0ms;
ELSIF PT <= T#0ms THEN
    Q := TRUE;
    ET := T#0ms;
ELSIF Q THEN
    ET := PT;
ELSIF PT <= {tick} THEN
    Q := TRUE;
    ET := PT;
ELSIF ET >= PT - {tick} THEN
    Q := TRUE;
    ET := PT;
ELSE
    ET := ET + {tick};
END_IF;
END_FUNCTION_BLOCK
'''
    note = {'kind': 'standard_timer_model', 'block': 'TON',
            'clock': 'scan', 'scan_period_ms': scan_period_ms,
            'requirements': 'one unconditional call per scan and fixed TIME-literal PT',
            'instances': instances}
    return model + source, [note]


def _adapt_shift_calls(source):
    """Lower the proven-safe SHL(DWORD#1, 0..31) bit-scan pattern.

    Declaring PLCverif's empty SHL builtin makes its generated return value
    always zero, so that apparent syntax fix is not semantics preserving. This
    narrow lowering is allowed only when the count is the controlling variable
    of an enclosing FOR 0 TO 31 loop. Other forms are explicitly unsupported.
    """
    masked=mask_noncode(source);changes=[];scopes=[];stack=[]
    blocks=re.compile(r'\bFOR\s+(\w+)\s*:=\s*(?:INT#)?0\s+TO\s+(?:INT#)?31\s+DO\b|\bFOR\b|\bEND_FOR\b',re.I)
    for token in blocks.finditer(masked):
        if token[0].upper().startswith('END_FOR'):
            if stack:
                start,var=stack.pop();scopes.append((start,token.end(),var))
        else:stack.append((token.start(),token[1] if token[1] else None))
    calls=re.compile(r'\b('+'|'.join(_SHIFT_BUILTINS)+r')\s*\(',re.I)
    for match in calls.finditer(masked):
        open_pos=masked.find('(',match.start(),match.end());depth=1;brackets=0;commas=[];pos=open_pos+1
        while pos<len(masked) and depth:
            char=masked[pos]
            if char=='(':depth+=1
            elif char==')':
                depth-=1
                if depth==0:break
            elif char=='[':brackets+=1
            elif char==']':brackets=max(0,brackets-1)
            elif char==',' and depth==1 and brackets==0:commas.append(pos)
            pos+=1
        if depth:raise Unsupported('Unclosed '+match[1].upper()+' call')
        if len(commas)!=1 or ':=' in masked[open_pos+1:pos]:
            raise Unsupported('PLCverif cannot safely model '+match[1].upper()+' with this argument form')
        comma=commas[0];left=source[open_pos+1:comma];right=source[comma+1:pos]
        variable=right.strip()
        safe=(match[1].upper()=='SHL' and re.fullmatch(r'DWORD#1',left.strip(),re.I)
              and re.fullmatch(r'[A-Za-z_]\w*',variable)
              and any(start<match.start()<end and var and var.lower()==variable.lower() for start,end,var in scopes))
        if not safe:
            raise Unsupported('PLCverif cannot safely preserve '+match[1].upper()+' semantics; supported lowering is DWORD#1 shifted by an enclosing FOR 0 TO 31 variable')
        changes.append((match.start(),pos+1,_SHL_ONE_HELPER+'('+right+')'))
    for start,end,value in reversed(changes):source=source[:start]+value+source[end:]
    if not changes:return source,[]
    if re.search(r'\b(?:FUNCTION|FUNCTION_BLOCK)\s+'+_SHL_ONE_HELPER+r'\b',mask_noncode(source),re.I):
        raise Unsupported('Reserved PLCverif shift helper is already declared')
    cases='\n'.join(f'    {index}: {_SHL_ONE_HELPER} := DWORD#{1 << index};' for index in range(32))
    helper=f'''FUNCTION {_SHL_ONE_HELPER} : DWORD
VAR_INPUT N : INT; END_VAR
CASE N OF
{cases}
END_CASE;
END_FUNCTION
'''
    note={'kind':'bounded_shift_lowering','operation':'SHL','input':'DWORD#1','count_range':[0,31],'count':len(changes)}
    return helper+source,[note]


def adapt(source, scan_period_ms=10, entry_block=None):
    notes=[];masked=mask_noncode(source);replacements=[];constants={};types={}
    pattern=re.compile(r'\bTYPE\s+(\w+)\s*:\s*\((.*?)\)\s*(INT|UINT|SINT|USINT|DINT|UDINT|BYTE|WORD|DWORD)?\s*;?\s*END_TYPE\b',re.I|re.S)
    for m in pattern.finditer(masked):
        name,items,base=m[1],m[2],(m[3] or 'INT').upper();members=[];value=-1
        for item in items.split(','):
            member=re.fullmatch(r'\s*(\w+)\s*(?::=\s*(-?\d+))?\s*',item)
            if not member:raise Unsupported('Enum requires explicit constant model: '+name)
            value=int(member[2]) if member[2] is not None else value+1
            members.append((member[1],value))
        if not any(v==0 for _,v in members):raise Unsupported('Nonzero enum default initializer needs an explicit model: '+name)
        types[name]=base
        for member,value in members:
            qualified=name+'.'+member
            constants[qualified]=f'{base}#{value}'
            if member in constants:raise Unsupported('Ambiguous unqualified enum member: '+member)
            constants[member]=f'{base}#{value}'
        replacements.append((m.start(),m.end(),''))
        notes.append({'kind':'enum_lowering','type':name,'base':base,'values':dict(members),'default':0})
    for start,end,value in reversed(replacements):source=source[:start]+value+source[end:]
    if constants:
        masked=mask_noncode(source)
        declarations='\n'.join(m[0] for m in re.finditer(r'\b(?:VAR(?:_INPUT|_OUTPUT|_IN_OUT|_TEMP|_EXTERNAL|_GLOBAL)?\b.*?\bEND_VAR|STRUCT\b.*?\bEND_STRUCT)\b',masked,re.I|re.S))
        for name in (n for n in constants if '.' not in n):
            if re.search(r'\b'+re.escape(name)+r'\s*:',declarations,re.I):raise Unsupported('Enum member is shadowed by a variable: '+name)
        values={k.lower():v for k,v in {**constants,**types}.items()};changes=[]
        for m in re.finditer(r'\b\w+(?:\.\w+)*\b',masked):
            if m[0].lower() in values:changes.append((m.start(),m.end(),values[m[0].lower()]))
        for start,end,value in reversed(changes):source=source[:start]+value+source[end:]
    # These attributes constrain source typing/names, already checked by CODESYS;
    # they do not change the executable semantics of the model copy.
    for m in reversed(list(re.finditer(r"\{\s*attribute\s+'(?:strict|qualified_only)'\s*\}",source,re.I))):
        probe=source[:m.start()]+'A'*len(m[0])+source[m.end():]
        if mask_noncode(probe)[m.start():m.end()]=='A'*len(m[0]):
            source=source[:m.start()]+source[m.end():]
    masked=mask_noncode(source);changes=[]
    for m in re.finditer(r'\b(?:END_IF|END_CASE|END_FOR|END_WHILE|END_REPEAT|RETURN|EXIT)\b',masked,re.I):
        if not masked[m.end():].lstrip().startswith(';'):changes.append(m.end())
    for pos in reversed(changes):source=source[:pos]+';'+source[pos:]
    if changes:notes.append({'kind':'statement_terminators','count':len(changes)})
    if re.search(r':\s*R_TRIG\b',mask_noncode(source),re.I) and not re.search(r'\bFUNCTION_BLOCK\s+R_TRIG\b',mask_noncode(source),re.I):
        source='''FUNCTION_BLOCK R_TRIG
VAR_INPUT CLK : BOOL; END_VAR
VAR_OUTPUT Q : BOOL; END_VAR
VAR M : BOOL := FALSE; END_VAR
Q := CLK AND NOT M;
M := CLK;
END_FUNCTION_BLOCK
'''+source
        notes.append({'kind':'standard_library_model','block':'R_TRIG','initial_history':False})
    source,ton_notes=_adapt_ton(source,scan_period_ms,entry_block);notes+=ton_notes
    source,shift_notes=_adapt_shift_calls(source);notes+=shift_notes
    return source,notes
