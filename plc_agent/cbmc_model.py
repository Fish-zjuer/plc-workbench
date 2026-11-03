"""PLCverif C 模型的有限扫描 LTL 监视器；保留原模型，生成独立 checked.i。"""
import json
import re
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

from plc_agent.ltl_adapter import Unsupported


def typed_floats(model, cfa):
    """Use CFA literal widths; never guess when a spelling has mixed widths."""
    xsi='{http://www.w3.org/2001/XMLSchema-instance}type'
    widths={}
    elements=list(ET.parse(cfa).iter())
    for item in elements:
        if item.get(xsi)=='expr:FloatLiteral':
            kinds=[int(t.get('bits','0')) for t in item if t.get(xsi)=='expr:FloatType']
            if len(kinds)!=1 or kinds[0] not in (32,64):
                raise Unsupported('Unknown CFA floating-point literal width')
            try:number=Decimal(item.get('value','0.0'))
            except InvalidOperation:raise Unsupported('Unknown CFA floating literal encoding') from None
            if not number.is_finite():raise Unsupported('Non-finite CFA literals require an explicit IEEE constant adapter')
            widths.setdefault(number,set()).add(kinds[0])
    # Ignore comments and strings. All other exporter literals must have known
    # CFA widths or be exact zero initializers, which are width independent.
    token=re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\b(?:\d+\.\d*(?:[Ee][+-]?\d+)?|\d+[Ee][+-]?\d+)\b',re.S)
    changes=[]
    def replace(match):
        value=match[0]
        if value.startswith(('//','/*','"')):return value
        number=Decimal(value);bits=widths.get(number)
        if bits is None:
            if number==0:return value
            raise Unsupported('C floating literal has no CFA type: '+value)
        if len(bits)!=1:raise Unsupported('Mixed REAL/LREAL literal needs a type-directed exporter: '+value)
        if bits=={32}:
            changes.append(value+' -> '+value+'f');return value+'f'
        return value
    model=token.sub(replace,model)
    model=model.replace('double nondet_float(void);','float nondet_float(void);')
    # The current exporter emits double math calls. Require a reviewed adapter
    # before claiming REAL math-library rounding is preserved.
    has_real=any(item.get(xsi)=='expr:FloatType' and item.get('bits')=='32' for item in elements)
    if has_real and re.search(r'\b(?:sqrt|sin|cos|tan|exp|log|pow|fabs)\s*\(',model):
        raise Unsupported('REAL math-library calls need a typed float-function adapter')
    return model,sorted(set(changes))


def monitor(adapter):
    """Evaluate LTLf backwards on exactly N completed FB calls."""
    bound=adapter.bound;nodes=[];ids={}
    def add(node):
        if node in ids:return ids[node]
        for child in node[1:]:
            if isinstance(child,tuple):add(child)
        ids[node]=len(nodes);nodes.append(node);return ids[node]
    supported=[p for p in adapter.properties if p.get('ast')]
    # G(atom) is exactly a conjunction of the sampled atom over the finite
    # prefix.  Accumulate it online instead of materializing N history and
    # syntax-node arrays.  This preserves the LTLf formula and every CBMC
    # safety check while avoiding hundreds of redundant array bounds checks.
    invariants=[p for p in supported if p['ast'][0]=='G' and p['ast'][1][0]=='atom']
    temporal=[p for p in supported if p not in invariants]
    for prop in temporal:add(prop['ast'])
    declarations=['int pvl_tick;','bool pvl_domain = true;']
    temporal_atoms={node[1] for node in nodes if node[0]=='atom'}
    for name in temporal_atoms:declarations.append(f'bool pvl_history_{name}[{bound}];')
    for prop in invariants:declarations.append(f'bool pvl_invariant_{prop["id"]} = true;')
    for i in range(len(nodes)):declarations.append(f'bool pvl_node_{i}[{bound+1}];')
    sample=[f'pvl_history_{name}[pvl_tick] = instance.{name};' for name in temporal_atoms]
    sample += [f'pvl_invariant_{prop["id"]} = pvl_invariant_{prop["id"]} && instance.{prop["ast"][1][1]};'
               for prop in invariants]
    if adapter.assumptions:sample.append('pvl_domain = pvl_domain && instance.PVL_Domain;')
    end=[]
    if adapter.assumptions:end.append('__CPROVER_assert(!pvl_domain, "PVL:DOMAIN_WITNESS");')
    def ref(node,t):return f'pvl_node_{ids[node]}[{t}]'
    for i,node in enumerate(nodes):end.append(f'pvl_node_{i}[{bound}] = '+('true' if node[0]=='G' else 'false')+';')
    for t in range(bound-1,-1,-1):
        for node in nodes:
            op=node[0];cur=ref(node,t);nxt=ref(node,t+1)
            a=ref(node[1],t) if isinstance(node[1],tuple) else ''
            if op=='atom':value=f'pvl_history_{node[1]}[{t}]'
            elif op=='G':value=f'({a} && {nxt})'
            elif op=='F':value=f'({a} || {nxt})'
            elif op=='X':value=ref(node[1],t+1) if t+1<bound else 'false'
            elif op=='R1':value=f'({a} || '+(ref(node[1],t+1) if t+1<bound else 'false')+')'
            elif op in ('!','~'):value='!'+a
            elif op=='U':value=f'({ref(node[2],t)} || ({a} && {nxt}))'
            elif op in ('&','&&','|','||','->','<->'):
                b=ref(node[2],t)
                value=f'(!{a} || {b})' if op=='->' else f'({a} '+{'&':'&&','&&':'&&','|':'||','||':'||','<->':'==' }[op]+f' {b})'
            else:raise Unsupported('Unsupported temporal Boolean operator: '+op)
            end.append(cur+' = '+value+';')
    for prop in invariants:
        label='PVL:LTL:'+prop['id']
        end.append('__CPROVER_assert(!pvl_domain || pvl_invariant_'+prop['id']+', '+json.dumps(label)+');')
        prop['model_formula']=label
    for prop in temporal:
        label='PVL:LTL:'+prop['id']
        end.append('__CPROVER_assert(!pvl_domain || '+ref(prop['ast'],0)+', '+json.dumps(label)+');')
        prop['model_formula']=label
    return '\n'.join(declarations), '\n'.join(sample), '\n'.join(end)


def order_structs(model):
    """Repair exporter declaration order without changing fields or types."""
    if '// Struct definitions' not in model or '// Global variables' not in model:
        return model
    head,tail=model.split('// Struct definitions',1)
    section,rest=tail.split('// Global variables',1)
    blocks=list(re.finditer(r'typedef\s+struct\s*\{([^{}]*)\}\s*(\w+)\s*;',section,re.S))
    remaining=re.sub(r'typedef\s+struct\s*\{[^{}]*\}\s*\w+\s*;','',section,flags=re.S)
    if remaining.strip():raise Unsupported('Unknown C struct declaration format')
    pending={b[2]:b for b in blocks}
    if len(pending)!=len(blocks):raise Unsupported('Duplicate exported struct typedef')
    ordered=[]
    while pending:
        ready=[name for name,b in pending.items() if not (set(re.findall(r'\b\w+\b',b[1])) & set(pending))]
        if not ready:raise Unsupported('Cyclic exported value-struct dependencies')
        for name in ready:ordered.append(pending.pop(name)[0])
    return head+'// Struct definitions\n'+'\n\n'.join(ordered)+'\n\n// Global variables'+rest


def checked_model(model,adapter,cfa):
    model=order_structs(model)
    model,float_changes=typed_floats(model,cfa)
    if adapter.reference_observer is not None:
        model=adapter.reference_observer.instrument(model,adapter)
    declaration,sample,finish=monitor(adapter)
    # Restrict modifications to the exact generated VerificationLoop definition.
    signature='void VerificationLoop() {'
    if model.count(signature)!=1:raise Unsupported('Unknown PLCverif VerificationLoop format')
    head,loop=model.split(signature)
    if loop.count('while (true)')!=1:raise Unsupported('Unknown generated scan-loop shape')
    # Exactly one build-only requirement must be replaced, never candidate code.
    marker='VerificationLoop_prepare_EoC: {'
    if loop.count(marker)!=1:raise Unsupported('Missing scan-end marker in generated C')
    start=loop.index(marker)+len(marker)
    match=re.match(r'\s*assert\(([^;]+)\);',loop[start:])
    if not match:raise Unsupported('Missing build-only assertion at scan end')
    loop=loop[:start]+ '\n'+sample+'\n'+loop[start+match.end():]
    if not re.search(r'EoC\s*=\s*false;\s*}\s*return;',loop):raise Unsupported('Unknown scan-loop exit')
    loop=loop.replace('while (true)',f'for (pvl_tick = 0; pvl_tick < {adapter.bound}; ++pvl_tick)',1)
    loop=re.sub(r'(EoC\s*=\s*false;\s*})\s*return;',lambda m:m[1]+'\n'+finish+'\nreturn;',loop,count=1)
    model=head+declaration+'\n'+signature+loop
    # .i is already-preprocessed C: avoid GCC/MSVC system-header dependencies.
    # Fixed-width aliases are checked by CBMC's target type system below.
    model=re.sub(r'^\s*#include\s*<(stdbool|stdint|assert|math)\.h>\s*$', '',model,flags=re.M)
    if re.search(r'^\s*#',model,re.M):raise Unsupported('Unexpected preprocessor directive in model')
    model=re.sub(r'typedef struct\s*\{\s*}', 'typedef struct { unsigned char pvl_empty; }',model)
    prefix='''typedef _Bool bool;
enum { false = 0, true = 1 };
typedef signed char int8_t; typedef unsigned char uint8_t;
typedef short int16_t; typedef unsigned short uint16_t;
typedef int int32_t; typedef unsigned int uint32_t;
typedef long long int64_t; typedef unsigned long long uint64_t;
_Static_assert(sizeof(int8_t)==1 && sizeof(int16_t)==2 && sizeof(int32_t)==4 && sizeof(int64_t)==8, "PLC integer widths");
_Static_assert(sizeof(float)==4 && sizeof(double)==8, "PLC float widths");
double sqrt(double); double sin(double); double cos(double); double tan(double);
double exp(double); double log(double); double pow(double,double); double fabs(double);
double floor(double); double ceil(double); double round(double);
void assert(bool value) { __CPROVER_assert(value, "PLC assertion"); }
'''
    return prefix+model,float_changes


def scan_trace(trace,adapter):
    ports={p['name'] for p in adapter.task['interface']};values={};scans=[]
    if adapter.reference_plan:
        ports.update(obj['name'] for obj in adapter.reference_plan['contract']['objects'])
    for step in trace:
        if step.get('stepType')!='assignment':continue
        lhs=step.get('lhs','');value=step.get('value',{}).get('data')
        if lhs.startswith('instance.') and re.split(r'[.\[]',lhs[9:],maxsplit=1)[0] in ports:
            values[lhs[9:]]=value
        if lhs=='EoC' and str(value).upper() in ('TRUE','1'):
            scans.append({'scan':len(scans)+1,'values':dict(values)})
    return scans


def results(console,report,adapter):
    """A property is verified only with completed scans, a valid domain and no failed guards."""
    try:items=json.loads(console)
    except ValueError:raise Unsupported('CBMC did not return complete JSON; see cbmc.json')
    for item in items:
        message=item.get('messageText','')
        missing=re.search(r'no body for (?:callee|function) [\x27\x22]?([\w$]+)',message,re.I)
        if missing and not missing[1].startswith(('nondet_','__CPROVER_')):
            raise Unsupported('Unmodelled generated function: '+missing[1])
    rows=[row for item in items for row in item.get('result',[])]
    if not rows:
        errors=[item.get('messageText','') for item in items if item.get('messageType')=='ERROR']
        raise Unsupported('CBMC returned no property results: '+'; '.join(errors)[-2500:])
    witness=[r for r in rows if r.get('description')=='PVL:DOMAIN_WITNESS']
    guards=[r for r in rows if not r.get('description','').startswith('PVL:')]
    bad_guards=[r for r in guards if r.get('status')!='SUCCESS']
    report['model_checks']=guards
    valid_domain=(not adapter.assumptions) or (len(witness)==1 and witness[0].get('status')=='FAILURE')
    report['valid_domain_witness']=valid_domain
    report['valid_domain_basis']=('unrestricted_input_domain' if not adapter.assumptions else
                                  'cbmc_counterexample_to_empty_domain_assertion')
    report['unwind_complete']=not any('unwind' in r.get('property','').lower() for r in bad_guards)
    counterexamples={}
    for prop in adapter.properties:
        if not prop.get('ast'):continue
        found=[r for r in rows if r.get('description')=='PVL:LTL:'+prop['id']]
        if bad_guards or not valid_domain:
            prop.update(status='bounded_inconclusive',message='Model safety/unwinding checks failed or no valid N-scan input trace exists')
        elif len(found)!=1 or found[0].get('status') not in ('SUCCESS','FAILURE'):
            prop.update(status='tool_error',message='CBMC omitted a definitive property result')
        elif found[0]['status']=='SUCCESS':
            prop['status']='bounded_pass';report['bounded_verified_property_ids'].append(prop['id'])
        else:
            prop['status']='bounded_inconclusive' if prop['temporal_boundary_sensitive'] else 'counterexample'
            trace=found[0].get('trace',[])
            prop['counterexample']={'raw':trace,'scans':scan_trace(trace,adapter),'confirmed_on_codesys':False,'scope':'PLCverif source model'}
            counterexamples[prop['id']]=prop['counterexample']
    states={p['status'] for p in adapter.properties}
    report['status']=next((s for s in ('counterexample','tool_error','bounded_inconclusive') if s in states),'partial' if 'unsupported' in states else 'bounded_pass')
    report['bounded_all_properties_verified']=bool(adapter.properties) and all(p['status']=='bounded_pass' for p in adapter.properties)
    report['message']='Completed CBMC scan-bounded LTL checks; model guards and domain reachability are recorded separately.'
    return counterexamples
