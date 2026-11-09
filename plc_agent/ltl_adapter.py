"""原始LTL的语法、扫描采样及独立观察器；不修改题库或推测未知命题。"""
import re
from plc_agent.st_source import split_units, mask_noncode


class Unsupported(ValueError):
    pass


TOKEN = re.compile(r'\s*(<->|->|<=|>=|!=|<>|&&|\|\||[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*|\d+(?:\.\d+)?|[()\[\],!~&|=<>+*/%^-])')
PRECEDENCE = {'<->': 1, '->': 2, '|': 3, '||': 3, '&': 4, '&&': 4,
              'U': 5, '=': 6, '!=': 6, '<>': 6, '<': 6, '>': 6, '<=': 6, '>=': 6,
              '+': 7, '-': 7, '*': 8, '/': 8, '%': 8}
INTEGER_TYPES = frozenset(('SINT', 'INT', 'DINT', 'LINT', 'USINT', 'UINT', 'UDINT', 'ULINT'))


def parse(text):
    tokens=[]; pos=0
    while pos<len(text):
        if not text[pos:].strip(): break
        m=TOKEN.match(text,pos)
        if not m: raise Unsupported('Unsupported LTL syntax near '+text[pos:pos+35])
        tokens.append(m[1]);pos=m.end()
    index=0
    def expr(level=0):
        nonlocal index
        if index>=len(tokens): raise Unsupported('Incomplete LTL expression')
        token=tokens[index];index+=1
        if token=='(':
            node=expr()
            if index>=len(tokens) or tokens[index]!=')': raise Unsupported('Unbalanced LTL parentheses')
            index+=1
        elif token in ('!','~','-','G','F','X','R1'):
            node=(token,expr(9))
        elif re.fullmatch(r'\d+(?:\.\d+)?',token): node=('number',token)
        elif re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*',token):
            if index<len(tokens) and tokens[index]=='(':
                index+=1;args=[]
                if index<len(tokens) and tokens[index]!=')':
                    args.append(expr())
                    while index<len(tokens) and tokens[index]==',': index+=1;args.append(expr())
                if index>=len(tokens) or tokens[index]!=')': raise Unsupported('Unclosed function call')
                index+=1;node=('call',token,*args)
            else: node=('name',token)
        else: raise Unsupported('Unexpected LTL token '+token)
        while index<len(tokens) and tokens[index] in PRECEDENCE and PRECEDENCE[tokens[index]]>=level:
            op=tokens[index];index+=1;p=PRECEDENCE[op]
            node=(op,node,expr(p if op=='->' else p+1))
        return node
    result=expr()
    if index!=len(tokens): raise Unsupported('Unsupported trailing LTL syntax: '+' '.join(tokens[index:]))
    return result


def temporal(node):
    return node[0] in ('G','F','X','U','R1') or any(temporal(n) for n in node[1:] if isinstance(n,tuple))


def observers(task):
    """Reviewed definitions are independent of candidate private variables."""
    execution=task.get('ltl',{}).get('execution')
    if execution is not None:
        if not isinstance(execution,dict):raise Unsupported('ltl.execution must be an object')
        defs=execution.get('bindings',{})
        if not isinstance(defs,dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in defs.items()):
            raise Unsupported('LTL bindings must map symbols to expressions')
        lists=[execution.get(k,[]) for k in ('declarations','before','after','assumptions')]
        if not all(isinstance(v,list) and all(isinstance(s,str) for s in v) for v in lists):
            raise Unsupported('Observer declarations, steps and assumptions must be string lists')
        # Imported observers may only assign their own reserved storage.
        entry=execution.get('entry',[])
        if not isinstance(entry,list) or not all(isinstance(x,str) for x in entry):raise Unsupported('Observer entry must be a string list')
        for step in lists[1]+lists[2]+entry:
            if re.search(r'\bPVL_Uut\s*\(',mask_noncode(step),re.I):raise Unsupported('Observer cannot invoke the candidate')
            for target in re.findall(r'([A-Za-z_]\w*(?:\[[^\]]+\])?(?:\.[A-Za-z_]\w*)*)\s*:=',mask_noncode(step)):
                root=re.split(r'[.\[]',target)[0].lower()
                reserved=root in ('pvl_uut','pvl_scan','pvl_active','pvl_done','pvl_nowms','pvl_dtms','pvl_domain') or re.fullmatch(r'pvl_a\d+',root)
                if not target.upper().startswith('PVL_') or reserved:raise Unsupported('Observer cannot write candidate/harness storage '+target)
            ports={p['name'].lower() for p in task['interface']}
            for name in re.findall(r'\bPVL_Uut\.(\w+)',mask_noncode(step),re.I):
                if name.lower() not in ports:raise Unsupported('Observer cannot read candidate private storage '+name)
        return dict(defs),*map(list,lists)
    return {},[],[],[],[]


class Adapter:
    def __init__(self,task,bound,scan_period_ms=10,reference_observer=None):
        spec=task.get('ltl',{})
        if isinstance(spec,str):spec={'text':spec}
        if not isinstance(spec,dict):raise Unsupported('Invalid LTL specification')
        self.task={**task,'ltl':spec};self.bound=bound;self.scan_period_ms=scan_period_ms
        self.defs,self.declarations,self.before,self.after,self.assumptions=observers(self.task)
        self.entry=spec.get('execution',{}).get('entry',[])
        self.reference_observer=reference_observer
        if reference_observer is not None:
            # The C observer constrains the domain before the candidate runs;
            # request an actual N-scan reachability witness from CBMC.
            self.assumptions.append('TRUE')
        from plc_agent.plcverif_references import configuration
        self.reference_plan=configuration(self.task)
        if self.reference_plan:
            existing={line.split(':')[0].strip().lower() for line in self.declarations}
            storage=self.reference_plan['declarations']
            if any(line.split(':')[0].strip().lower() in existing for line in storage):
                raise Unsupported('Reference storage collides with observer declarations')
            self.declarations+=storage
        self.call_defs={parse(k):(k,v) for k,v in self.defs.items() if '(' in k}
        self.names={p['name'].lower():p['name'] for p in task['interface']}
        self.integer_types = {p['name'].lower(): p['type'].upper()
                              for p in task['interface'] if p['type'].upper() in INTEGER_TYPES}
        self.names.update({'pvl_nowms':'PVL_NowMs','pvl_dtms':'PVL_DtMs'})
        self.integer_types.update(pvl_nowms='DINT', pvl_dtms='DINT')
        for line in self.declarations:
            self.names[line.split(':')[0].strip().lower()]=line.split(':')[0].strip()
            declaration = re.fullmatch(r'\s*(\w+)\s*:\s*(\w+)\s*(?::=.*)?;', line)
            if declaration and declaration[2].upper() in INTEGER_TYPES:
                self.integer_types[declaration[1].lower()] = declaration[2].upper()
        if self.reference_plan:
            self.names.update({name:ref['target'] for name,ref in self.reference_plan['bindings'].items()})
        self.atoms={};self.properties=[]

    def expand(self,node,seen=()):
        if node in self.call_defs:
            name,value=self.call_defs[node]
            if name in seen:raise Unsupported('Recursive observer definition: '+name)
            return self.expand(parse(value),seen+(name,))
        if node[0]=='name':
            name=node[1]
            if name in self.defs:
                if name in seen: raise Unsupported('Recursive observer definition: '+name)
                return self.expand(parse(self.defs[name]),seen+(name,))
        return (node[0],*(self.expand(x,seen) if isinstance(x,tuple) else x for x in node[1:]))

    def _integer_term_types(self, node):
        op = node[0]
        if op == 'number' and node[1].isdecimal():
            return set()
        if op == 'name':
            dtype = self.integer_types.get(node[1].lower())
            return {dtype} if dtype else None
        if op in ('+', '-') and len(node) == 3:
            left = self._integer_term_types(node[1])
            right = self._integer_term_types(node[2])
            if left is not None and right is not None:
                return left | right
        return None

    def st(self,n):
        op=n[0]
        if op=='number': return n[1]
        if op=='name':
            name=n[1]
            if name.lower() in ('true','false'): return name.upper()
            # Accept optional interface prefixes, without changing stored formulas.
            if name.split('.')[0] in ('inputs','outputs','instance'): name=name.split('.',1)[1]
            if name.lower() not in self.names: raise Unsupported('Observer/variable not implemented: '+n[1])
            return self.names[name.lower()]
        if op=='call':
            if n[1].lower() not in ('abs','min','max'): raise Unsupported('Unsupported LTL function: '+n[1])
            return n[1].upper()+'('+', '.join(self.st(x) for x in n[2:])+')'
        if len(n)==2:
            if op not in ('!','~','-'): raise Unsupported('Unexpected temporal operator in state predicate')
            return ('NOT ' if op in ('!','~') else '-')+'('+self.st(n[1])+')'
        if op == '=':
            value, call = n[1:]
            if value[0] == 'call':
                value, call = call, value
            if call[0] == 'call' and len(call) == 4 and call[1].lower() in ('min', 'max'):
                types = [self._integer_term_types(term) for term in (value, *call[2:])]
                if all(t is not None for t in types) and len(set.union(*types)) == 1:
                    # Keep arithmetic in the comparisons, without an
                    # intermediate narrowing conversion at a helper call.
                    left, right = call[2:]
                    choose_left = ('<=' if call[1].lower() == 'min' else '>=', left, right)
                    return self.st(('|', ('&', choose_left, ('=', value, left)),
                                         ('&', ('!', choose_left), ('=', value, right))))
        a,b=self.st(n[1]),self.st(n[2])
        if op=='->': return '(NOT ('+a+') OR ('+b+'))'
        if op=='<->': return '(('+a+') = ('+b+'))'
        ops={'&':'AND','&&':'AND','|':'OR','||':'OR','!=':'<>','%':'MOD'}
        return '(('+a+') '+ops.get(op,op)+' ('+b+'))'

    def atom(self,node):
        value=self.st(node)
        if value not in self.atoms:self.atoms[value]='PVL_A'+str(len(self.atoms))
        return ('atom',self.atoms[value])

    def abstract(self,node):
        if not temporal(node): return self.atom(node)
        return (node[0],*(self.abstract(x) if isinstance(x,tuple) else x for x in node[1:]))

    def prepare(self):
        if self.reference_observer is not None:
            for i,prop in enumerate(properties(self.task['ltl'])):
                oracle='PVL_Oracle'+str(i);atom='PVL_A'+str(i)
                self.declarations.append(oracle+' : BOOL;')
                self.atoms[oracle]=atom
                self.properties.append({**prop,'status':'not_executed','ast':('G',('atom',atom)),
                                        'temporal_boundary_sensitive':False,
                                        'observer_mapping':'Reviewed per-invocation predicate; see reference_observer evidence'})
            return self
        for prop in properties(self.task.get('ltl',{})):
            result={'id':prop['id'],'formula':prop['formula'],'status':'not_executed'}
            old=dict(self.atoms)
            try:
                node=self.expand(parse(prop['formula']));ast=self.abstract(node)
                result.update(ast=ast,temporal_boundary_sensitive=not (node[0]=='G' and not temporal(node[1])))
            except (Unsupported,RecursionError) as exc:
                self.atoms=old;result.update(status='unsupported',message=str(exc))
            self.properties.append(result)
        return self

    def sampled(self,n,symbol=lambda s:'instance.'+s,end='{PLC_END}'):
        """Strong finite-trace semantics at scan ends, independent of CFA step count."""
        op=n[0];active=symbol('PVL_Active');tick=end
        if op=='atom': return symbol(n[1])
        if op=='G': return 'G(('+tick+' & '+active+') -> '+self.sampled(n[1],symbol,end)+')'
        if op=='F': return 'F('+tick+' & '+active+' & '+self.sampled(n[1],symbol,end)+')'
        if op=='X': return 'X((!'+tick+') U ('+tick+' & '+active+' & '+self.sampled(n[1],symbol,end)+'))'
        if op=='R1': return '('+self.sampled(n[1],symbol,end)+' | '+self.sampled(('X',n[1]),symbol,end)+')'
        if op=='U': return '((('+active+') & (!'+tick+' | '+self.sampled(n[1],symbol,end)+')) U ('+tick+' & '+active+' & '+self.sampled(n[2],symbol,end)+'))'
        if len(n)==2: return '!('+self.sampled(n[1],symbol,end)+')'
        return '('+self.sampled(n[1],symbol,end)+' '+{'&&':'&','||':'|'}.get(op,op)+' '+self.sampled(n[2],symbol,end)+')'

    def formula(self,p,symbol=lambda s:'instance.'+s,end='{PLC_END}'):
        return '(!'+end+') U ('+end+' & '+self.sampled(p['ast'],symbol,end)+')'

    def _input_domain(self):
        """Recognize bounds that can be evaluated before calling the candidate."""
        inputs = {p['name'].lower() for p in self.task['interface']
                  if p['direction'] == 'Input' and p['type'].upper() in ('INT', 'DINT')}

        def operand(node):
            if node[0] == 'name':
                return node[1].lower() in inputs
            if node[0] == '-':
                node = node[1]
            return node[0] == 'number' and node[1].isdecimal()

        def bound(node):
            if node[0] in ('&', '&&', '|', '||'):
                return bound(node[1]) and bound(node[2])
            return node[0] in ('<', '<=', '>', '>=', '=', '!=', '<>') and all(map(operand, node[1:]))

        nodes = [parse(a) for a in self.assumptions]
        if nodes and all(map(bound, nodes)):
            return ' AND '.join(self.st(node) for node in nodes)
        return None

    def instrument(self,source,*,guard_input_domain=False):
        if re.search(r'\bPVL_\w*',mask_noncode(source),re.I): raise Unsupported('PVL_ prefix is reserved for formal observers')
        if not any(u['name'].lower()==self.task['block'].lower() for u in split_units(source)):
            raise Unsupported('Required function block missing')
        # A separate caller keeps observers running even if the candidate RETURNs.
        # The supplied candidate's executable statements remain byte-for-byte intact.
        decl=['FUNCTION_BLOCK PVL_Harness']
        for direction,kind in [('Input','VAR_INPUT'),('Input/Output','VAR_INPUT'),('Output','VAR_OUTPUT')]:
            if direction=='Input/Output' and self.reference_plan:continue
            ports=[p for p in self.task['interface'] if p['direction']==direction]
            if ports:decl += [kind]+[p['name']+' : '+p['type']+';' for p in ports]+['END_VAR']
        ds=['PVL_Uut : '+self.task['block']+';']+self.declarations+['PVL_Scan : DINT := 0;', 'PVL_Active : BOOL;', 'PVL_Done : BOOL;',f'PVL_DtMs : DINT := {self.scan_period_ms};',f'PVL_NowMs : DINT := -{self.scan_period_ms};']+[v+' : BOOL;' for v in self.atoms.values()]
        if self.assumptions:ds+=['PVL_Domain : BOOL := TRUE;']
        decl+=['VAR']+ds+['END_VAR']
        if self.reference_plan:
            from plc_agent.plcverif_references import inline
            source,call=inline(source,self.task,self.reference_plan)
        else:
            if any(p['direction']=='Input/Output' for p in self.task['interface']):
                raise Unsupported('IN_OUT verification requires an explicit reference_model storage contract; value-copy fallback is disabled')
            call=['PVL_Uut('+', '.join(p['name']+' := '+p['name'] for p in self.task['interface'] if p['direction']!='Output')+');']
        body=['PVL_NowMs := PVL_NowMs + PVL_DtMs;']+list(self.entry)+call
        body += [p['name']+' := PVL_Uut.'+p['name']+';' for p in self.task['interface'] if p['direction']=='Output']
        body+=self.before
        advance=[f'IF PVL_Scan <= {self.bound} THEN PVL_Scan := PVL_Scan + 1; END_IF;',
               f'PVL_Active := PVL_Scan <= {self.bound}; PVL_Done := PVL_Scan >= {self.bound};']
        body+=advance
        input_domain = self._input_domain() if guard_input_domain else None
        if self.assumptions and input_domain is None:
            body+=['PVL_Domain := PVL_Domain AND ('+' AND '.join(self.st(parse(a)) for a in self.assumptions)+');']
        body += [v+' := '+expr+';' for expr,v in self.atoms.items()]+self.after
        if input_domain is not None:
            # Invalid prefixes cannot contribute to a verdict. Advance the
            # harness clock without executing the candidate on excluded inputs.
            body = ['PVL_Domain := PVL_Domain AND ('+input_domain+');', 'IF PVL_Domain THEN'] + body + ['ELSE'] + advance + ['END_IF;']
        body=[f'IF PVL_Scan < {self.bound} THEN']+body+['ELSE PVL_Active := FALSE; PVL_Done := TRUE; END_IF;']
        return source+'\n\n'+'\n'.join(decl+body+['END_FUNCTION_BLOCK'])+'\n'


def properties(spec):
    """One reader for JSON property arrays and one-formula-per-line .ltl files."""
    if isinstance(spec,str):spec={'text':spec}
    if not isinstance(spec,dict):raise Unsupported('LTL specification must be an object or text')
    props=spec.get('properties')
    if props is None:
        props=[]
        if not isinstance(spec.get('text',''),str):raise Unsupported('LTL text must be a string')
        for line in spec.get('text','').splitlines():
            line=line.strip()
            if not line or line.startswith(('#','//')):continue
            m=re.match(r'^([A-Za-z_]\w*)\s*:\s*(.+)$',line)
            props.append({'id':m[1] if m else 'P'+str(len(props)+1),'formula':m[2] if m else line})
    if not isinstance(props,list):raise Unsupported('LTL properties must be a list')
    seen=set()
    for p in props:
        if not isinstance(p,dict) or not isinstance(p.get('id'),str) or not isinstance(p.get('formula'),str):
            raise Unsupported('Each property needs a string id and formula')
        if p['id'] in seen:raise Unsupported('Duplicate property ID: '+p['id'])
        seen.add(p['id'])
    return props


def property_count(spec):
    try:return len(properties(spec))
    except Unsupported:
        raw=spec.get('properties',[]) if isinstance(spec,dict) else []
        return len(raw) if isinstance(raw,list) else 0
