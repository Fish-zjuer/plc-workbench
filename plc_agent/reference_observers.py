"""Reviewed course 08/18 observers, independent of candidate private state.

The immutable source formulas are checked against the known specification.
Each G(state predicate) is monitored directly after one invocation; P01 of
FIFO checks startup emptiness *before* the first invocation, since a valid
first invocation can already enqueue an item. No candidate algorithm is
replaced by the reference model.
"""
from copy import deepcopy
from dataclasses import dataclass
import re

from plc_agent.ltl_adapter import Unsupported, properties
from plc_agent.st_source import mask_noncode, split_units


FORMULAS_08=[
    'G(rawArrayPreserved)', 'G(channelConfigPreserved)', 'G(unprocessedChannelsPreserved)',
    'G(enabledInvalidMode -> channelError8001)', 'G(enabledInvalidLimits -> channelError8002)',
    'G(enabledValidMode0 -> linearScalingOK)', 'G(enabledValidMode1 -> standardTemperatureOK)',
    'G(enabledValidMode2 -> climaticTemperatureOK)']
FORMULAS_18=[
    'G(initial -> queueEmpty)', 'G(reset -> queueEmpty & elementCountZero & statusZero)',
    'G(!reset & enqueueRise & notFull -> queueAfterAppendOK & statusZero)',
    'G(!reset & enqueueRise & full -> queueHeld & itemHeld & status8002)',
    'G(!reset & dequeueRise & notEmpty -> queueAfterPopOK & statusZero)',
    'G(!reset & dequeueRise & empty -> queueHeld & itemHeld & status8001)',
    'G(!reset & idleRequest -> queueHeld & statusZero)', 'G(countMatchesQueue)', 'G(countWithinCapacity)']


@dataclass
class Case:
    name: str
    task: dict
    shape: dict
    kind: str
    prefix: str = ''
    numeric_domain: str = 'ieee'

    def validate_source(self,source):
        units=split_units(source)
        main=next((u for u in units if u['kind']=='FUNCTION_BLOCK' and u['name'].lower()==self.task['block'].lower()),None)
        if main is None:raise Unsupported('Reference observer requires the declared function block')
        actual={}
        for section in re.finditer(r'\b(VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT)\b(.*?)\bEND_VAR\b',mask_noncode(main['declaration']),re.I|re.S):
            for field in section[2].split(';'):
                if not field.strip():continue
                m=re.fullmatch(r'\s*([A-Za-z_]\w*)\s*:\s*(.*?)\s*',field,re.S)
                if not m:raise Unsupported('Reference observer requires single-name interface declarations')
                key=m[1].lower()
                if key in actual:raise Unsupported('Duplicate source reference interface field')
                actual[key]=(section[1].upper(),re.sub(r'\s+','',m[2].split(':=',1)[0]).upper())
        directions={'Input':'VAR_INPUT','Output':'VAR_OUTPUT','Input/Output':'VAR_IN_OUT'}
        expected_ports={p['name'].lower():(directions[p['direction']],re.sub(r'\s+','',p['type']).upper()) for p in self.task['interface']}
        if actual!=expected_ports:raise Unsupported('Source interface differs from the reviewed reference observer contract')
        if self.kind!='analog':return
        types=[u for u in units if u['kind']=='TYPE' and u['name'].lower()=='st_analogchannel']
        if len(types)!=1:raise Unsupported('Analog observer requires the declared ST_AnalogChannel record')
        fields=re.findall(r'\b([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*)\s*;',mask_noncode(types[0]['declaration']))
        expected={'enable':'BOOL','hilim':'REAL','lolim':'REAL','bipolar':'BOOL','measuringmode':'INT','retval':'WORD','outputvalue':'REAL'}
        if len(fields)!=len(expected) or {k.lower():v.upper() for k,v in fields}!=expected:
            raise Unsupported('Analog observer requires the exact reviewed channel field names and types')

    def evidence(self):
        domain=('All INT raw values, BOOL enables, INT modes, WORD previous status; '
                'finite IEEE binary32 limits and previous outputs in [-1000000,1000000]; '
                '0<=count<=min(lengths). Limits and modes may both be invalid: either error is accepted.')
        if self.numeric_domain=='boundary':
            domain=('Explicit boundary input domain: raw in {-27648,-1,0,1,27648}; '
                    'hiLIM/loLIM cycle by (scan+channel)%3 through (73.25,-30.5),(-30.5,-30.5),(-30.5,73.25); previous output=-700.25; '
                    'all BOOL enables, INT modes, WORD previous statuses; 0<=count<=min(lengths). '
                    'This is not full IEEE value coverage.')
        return {'case':self.name,'kind':self.kind,'shape':self.shape,'numeric_domain':self.numeric_domain if self.kind=='analog' else 'all_payload_bits',
                'input_domain':(domain
                                if self.kind=='analog' else
                                'All BOOL request/reset sequences with !(enqueue && dequeue); all payload bit patterns; '
                                'fixed buffer association; item storage is separate from buffer; arbitrary initial buffer contents.'),
                'observer':'Independent mathematical model; candidate private fields are never read.',
                'startup':('FIFO P01 checks pre-first-call empty count, not post-first-enqueue emptiness.'
                           if self.kind=='fifo' else 'Each call receives fresh caller data and preserved-field snapshots.'),
                'arithmetic':('IEEE binary32 multiply-before-divide scaling; existing analog test tolerance 1e-6 * max(1,abs(actual),abs(expected)).'
                              if self.kind=='analog' else 'Payload preservation uses bit equality, including IEEE NaNs.')}

    def instrument(self,model,adapter):
        """Insert C hooks around exactly one generated harness invocation."""
        call='PVL_Harness(&instance);'
        if model.count(call)!=1:
            raise Unsupported('Reference observer requires exactly one generated harness call')
        declarations,before,after=self._analog() if self.kind=='analog' else self._fifo()
        signature='void VerificationLoop() {'
        if model.count(signature)!=1:
            raise Unsupported('Unknown generated scan loop for reference observer')
        model=model.replace(signature,declarations+'\n'+signature,1)
        return model.replace(call,before+'\n'+call+'\n'+after,1)

    def _analog(self):
        na,nc=self.shape['analog_length'],self.shape['channel_length']
        decl=f'''
typedef struct {{ bool enable; float hiLIM; float loLIM; bool bipolar; int16_t measuringMode; uint16_t retVal; float outputValue; }} PVL_ChannelSnapshot;
static int16_t pvl_raw[{na}];
static PVL_ChannelSnapshot pvl_channels[{nc}];
static bool pvl_analog_props[8];
static float pvl_abs(float x) {{ return x < 0.0f ? -x : x; }}
static bool pvl_float_bits(float a,float b) {{
  union {{ float f; uint32_t u; }} x,y; x.f=a; y.f=b; return x.u==y.u;
}}
static bool pvl_close(float a, float b) {{
  if(pvl_float_bits(a,b)) return true;
  float scale=pvl_abs(b); if(pvl_abs(a)>scale) scale=pvl_abs(a); if(scale < 1.0f) scale=1.0f;
  return pvl_abs(a-b) <= 0.000001f*scale;
}}
'''
        before=[f'__CPROVER_assume(instance.count >= 0 && instance.count <= {min(na,nc)});']
        for i in range(na):
            raw='nondet_int16_t()' if self.numeric_domain=='ieee' else '(nondet_bool() ? -27648 : (nondet_bool() ? -1 : (nondet_bool() ? 0 : (nondet_bool() ? 1 : 27648))))'
            before += [f'pvl_raw[{i}]={raw}; instance.PVL_Store_Raw[{i}]=pvl_raw[{i}];']
        for i in range(nc):
            s=f'pvl_channels[{i}]';a=f'instance.PVL_Store_Channels[{i}]'
            for field,fn in [('enable','nondet_bool'),('hiLIM','nondet_float'),('loLIM','nondet_float'),('bipolar','nondet_bool'),('measuringMode','nondet_int16_t'),('retVal','nondet_uint16_t'),('outputValue','nondet_float')]:
                value=fn+'()'
                if self.numeric_domain=='boundary' and field=='hiLIM':value=f'((pvl_tick+{i})%3==0 ? 73.25f : -30.5f)'
                if self.numeric_domain=='boundary' and field=='loLIM':value=f'((pvl_tick+{i})%3==2 ? 73.25f : -30.5f)'
                if self.numeric_domain=='boundary' and field=='outputValue':value='-700.25f'
                before += [f'{s}.{field}={value};']
                if field in ('hiLIM','loLIM','outputValue'):
                    before += [f'__CPROVER_assume({s}.{field} >= -1000000.0f && {s}.{field} <= 1000000.0f);']
                before += [f'{a}.{field}={s}.{field};']
        before += ['for(int p=0;p<8;++p) pvl_analog_props[p]=true;']
        after=[f'for(int i=0;i<{na};++i) pvl_analog_props[0] = pvl_analog_props[0] && instance.PVL_Store_Raw[i]==pvl_raw[i];']
        # Unroll record accesses: do not depend on the spelling/layout of the
        # candidate's C struct typedef or on any internal loop/index variable.
        for i in range(nc):
            s=f'pvl_channels[{i}]';a=f'instance.PVL_Store_Channels[{i}]'
            after += [f'''{{
bool cfg=({a}.enable=={s}.enable && pvl_float_bits({a}.hiLIM,{s}.hiLIM) && pvl_float_bits({a}.loLIM,{s}.loLIM) && {a}.bipolar=={s}.bipolar && {a}.measuringMode=={s}.measuringMode);
pvl_analog_props[1]=pvl_analog_props[1] && cfg;
bool processed=({i}<instance.count && {s}.enable);
if(!processed) pvl_analog_props[2]=pvl_analog_props[2] && {a}.retVal=={s}.retVal && pvl_float_bits({a}.outputValue,{s}.outputValue);
''']
            if i<na:
                after += [f'''
if(processed) {{
  bool mode=({s}.measuringMode>=0 && {s}.measuringMode<=2);
  bool limits=({s}.hiLIM>{s}.loLIM);
  bool output_held=pvl_float_bits({a}.outputValue,{s}.outputValue);
  if(!mode && limits) pvl_analog_props[3]=pvl_analog_props[3] && {a}.retVal==0x8001 && output_held;
  if(mode && !limits) pvl_analog_props[4]=pvl_analog_props[4] && {a}.retVal==0x8002 && output_held;
  if(!mode && !limits) {{ bool err=({a}.retVal==0x8001 || {a}.retVal==0x8002) && output_held; pvl_analog_props[3]=pvl_analog_props[3] && err; pvl_analog_props[4]=pvl_analog_props[4] && err; }}
  if(mode && limits) {{
    float raw=(float)pvl_raw[{i}]; float span={s}.hiLIM-{s}.loLIM; float expected;
    if({s}.measuringMode==0) expected={s}.loLIM + (span * ({s}.bipolar ? (float)((int32_t)pvl_raw[{i}]+27648) : raw)) / ({s}.bipolar ? 55296.0f : 27648.0f);
    else expected=raw/({s}.measuringMode==1 ? 10.0f : 100.0f);
    int prop=5+{s}.measuringMode;
    pvl_analog_props[prop]=pvl_analog_props[prop] && {a}.retVal==0 && pvl_close({a}.outputValue,expected);
  }}
}}
''']
            after += ['}']
        after += [f'instance.PVL_A{i}=pvl_analog_props[{i}];' for i in range(8)]
        return decl,'\n'.join(before),'\n'.join(after)

    def _fifo(self):
        capacity=self.shape['capacity'];dtype=self.shape['kind']
        ctype={'dint':'int32_t','bool':'bool','real':'float','record':'__PLCVERIF_ReferenceRecord'}[dtype]
        if dtype=='real':
            equal='union { float f; uint32_t u; } x,y; x.f=a; y.f=b; return x.u==y.u;'
            fresh='return nondet_float();'
        elif dtype=='record':
            equal='union { float f; uint32_t u; } x,y; x.f=a.value; y.f=b.value; return a.key==b.key && x.u==y.u;'
            fresh='PVL_Value v; v.key=nondet_int32_t(); v.value=nondet_float(); return v;'
        else:
            equal='return a==b;';fresh='return '+('nondet_bool()' if dtype=='bool' else 'nondet_int32_t()')+';'
        decl=f'''
typedef {ctype} PVL_Value;
static PVL_Value pvl_queue[{capacity}];
static int pvl_size=0;
static bool pvl_first=true, pvl_enq_prev=false, pvl_deq_prev=false;
static bool pvl_enq, pvl_deq, pvl_reset, pvl_rise_enq, pvl_rise_deq, pvl_start_empty;
static int pvl_old_size;
static PVL_Value pvl_item_before, pvl_popped;
static bool pvl_equal(PVL_Value a,PVL_Value b) {{ {equal} }}
static PVL_Value pvl_fresh(void) {{ {fresh} }}
static bool pvl_represents_queue(void) {{
  if(pvl_size==0) return true;
  bool some=false;
  for(int start=0;start<{capacity};++start) {{
    bool match=true;
    for(int j=0;j<{capacity};++j) if(j<pvl_size) match=match && pvl_equal(instance.PVL_Store_Buffer[(start+j)%{capacity}],pvl_queue[j]);
    some=some || match;
  }}
  return some;
}}
'''
        before=f'''
__CPROVER_assume(!(instance.enqueue && instance.dequeue));
if(pvl_first) {{ for(int i=0;i<{capacity};++i) instance.PVL_Store_Buffer[i]=pvl_fresh(); }}
instance.PVL_Store_Item=pvl_fresh(); pvl_item_before=instance.PVL_Store_Item;
pvl_enq=instance.enqueue; pvl_deq=instance.dequeue; pvl_reset=instance.reset;
pvl_rise_enq=pvl_enq && !pvl_enq_prev; pvl_rise_deq=pvl_deq && !pvl_deq_prev;
pvl_old_size=pvl_size; pvl_start_empty=(instance.PVL_Uut.elementCount==0);
if(pvl_reset) pvl_size=0;
else if(pvl_rise_enq && pvl_old_size<{capacity}) pvl_queue[pvl_size++]=pvl_item_before;
else if(pvl_rise_deq && pvl_old_size>0) {{
  pvl_popped=pvl_queue[0];
  for(int i=0;i<{capacity-1};++i) if(i+1<pvl_size) pvl_queue[i]=pvl_queue[i+1];
  --pvl_size;
}}
'''
        after=f'''
{{
bool count_ok=(instance.elementCount==pvl_size);
bool repr=pvl_represents_queue();
bool held=pvl_equal(instance.PVL_Store_Item,pvl_item_before);
bool zero=(instance.status==0);
instance.PVL_A0=(!pvl_first || pvl_start_empty);
instance.PVL_A1=(!pvl_reset || (count_ok && instance.elementCount==0 && zero));
instance.PVL_A2=(pvl_reset || !pvl_rise_enq || pvl_old_size=={capacity} || (repr && count_ok && held && zero));
instance.PVL_A3=(pvl_reset || !pvl_rise_enq || pvl_old_size!={capacity} || (repr && count_ok && held && instance.status==0x8002));
instance.PVL_A4=(pvl_reset || !pvl_rise_deq || pvl_old_size==0 || (repr && count_ok && pvl_equal(instance.PVL_Store_Item,pvl_popped) && zero));
instance.PVL_A5=(pvl_reset || !pvl_rise_deq || pvl_old_size!=0 || (repr && count_ok && held && instance.status==0x8001));
instance.PVL_A6=(pvl_reset || pvl_rise_enq || pvl_rise_deq || (repr && count_ok && held && zero));
instance.PVL_A7=count_ok && repr;
instance.PVL_A8=(instance.elementCount>=0 && instance.elementCount<={capacity});
pvl_first=false; pvl_enq_prev=pvl_enq; pvl_deq_prev=pvl_deq;
}}
'''
        return decl,before,after


def cases(task,numeric_domain='ieee'):
    """Only recognized frozen course contracts receive these trusted observers."""
    ident=task.get('original_id',task.get('id'))
    if numeric_domain not in ('ieee','boundary'):raise Unsupported('Unknown reference numeric input domain')
    if ident not in ('PUBLIC_08','PUBLIC_18'):
        return []
    execution=task.get('ltl',{}).get('execution',{})
    if (execution.get('bindings',{})!={} or any(execution.get(k,[])!=[] for k in ('declarations','entry','before','after','assumptions'))
            or set(execution)-{'requires_model','bindings','declarations','entry','before','after','assumptions'}):
        raise Unsupported('Course observer cannot replace custom execution bindings, steps or assumptions')
    expected=FORMULAS_08 if ident=='PUBLIC_08' else FORMULAS_18
    props=properties(task.get('ltl',{}))
    if [(p['id'],p['formula']) for p in props] != [(f'P{i+1:02}',formula) for i,formula in enumerate(expected)]:
        raise Unsupported('Course reference observer does not match supplied property IDs/formulas')
    required={'count':'DINT','analogValues':'ARRAY[*] OF INT','channels':'ARRAY[*] OF ST_AnalogChannel'} if ident=='PUBLIC_08' else {
        'enqueue':'BOOL','dequeue':'BOOL','reset':'BOOL','elementCount':'DINT','status':'WORD','item':'VARIANT','buffer':'VARIANT'}
    ports={p['name']:p['type'] for p in task['interface']}
    expected_directions=({'count':'Input','analogValues':'Input/Output','channels':'Input/Output'} if ident=='PUBLIC_08' else
                         {'enqueue':'Input','dequeue':'Input','reset':'Input','elementCount':'Output','status':'Output','item':'Input/Output','buffer':'Input/Output'})
    if ports!=required or len(ports)!=len(task['interface']) or {p['name']:p['direction'] for p in task['interface']}!=expected_directions:
        raise Unsupported('Course reference observer does not match the declared interface')
    result=[]
    # Shapes come from requirement-owned metadata, never candidate code or
    # expected-value rows. Numeric inputs remain nondeterministic.
    for shape in task.get('scenarios',[]):
        if ident=='PUBLIC_08':
            keys=('analog_length','analog_lower','channel_length','channel_lower')
            if any(type(shape.get(k)) is not int for k in keys):
                raise Unsupported('Analog reference case requires explicit integer bounds/lengths')
            data={k:shape[k] for k in keys}
            if not all(1<=data[k]<=8 for k in ('analog_length','channel_length')):
                raise Unsupported('Course analog observer supports reviewed lengths 1..8')
            na,nc=data['analog_length'],data['channel_length'];la,lc=data['analog_lower'],data['channel_lower']
            objects=[{'name':'PVL_Store_Raw','type':f'ARRAY[{la}..{la+na-1}] OF INT'},
                     {'name':'PVL_Store_Channels','type':f'ARRAY[{lc}..{lc+nc-1}] OF ST_AnalogChannel'}]
            bindings={'analogValues':'PVL_Store_Raw','channels':'PVL_Store_Channels'}
            kind='analog';prefix=''
        else:
            data={k:shape.get(k) for k in ('capacity','kind')}
            if type(data['capacity']) is not int or data['capacity'] not in (1,2,7) or data['kind'] not in ('dint','real','bool','record'):
                raise Unsupported('FIFO reference case requires a reviewed type and capacity 1,2,7')
            dtype={'dint':'DINT','real':'REAL','bool':'BOOL','record':'PLCVERIF_ReferenceRecord'}[data['kind']]
            objects=[{'name':'PVL_Store_Buffer','type':f"ARRAY[-3..{data['capacity']-4}] OF {dtype}"},
                     {'name':'PVL_Store_Item','type':dtype}]
            bindings={'buffer':'PVL_Store_Buffer','item':'PVL_Store_Item'}
            kind='fifo';prefix=('TYPE PLCVERIF_ReferenceRecord : STRUCT key : DINT; value : REAL; END_STRUCT END_TYPE\n' if data['kind']=='record' else '')
        name=shape.get('name')
        if not isinstance(name,str) or not name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in name):
            raise Unsupported('Unsafe reference case name')
        derived=deepcopy(task)
        derived['ltl']['execution']={'reference_model':{'version':1,'objects':objects,'bindings':bindings}}
        result.append(Case(name,derived,data,kind,prefix,numeric_domain))
    if not result or len({c.name for c in result})!=len(result):
        raise Unsupported('Reference verification requires nonempty unique case metadata')
    return result
