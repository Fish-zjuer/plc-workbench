"""CODESYS到STEP7的有限语法适配；原源码保留，模型副本的转换逐项记录。"""
import re
from plc_agent.st_source import mask_noncode
from plc_agent.ltl_adapter import Unsupported


def adapt(source):
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
    return source,notes
