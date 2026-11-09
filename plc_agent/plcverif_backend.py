"""PLCverif建模与有界LTL检查；默认CBMC，统一扫描上界、证据、超时和取消。"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from contextlib import contextmanager

from plc_agent.config import ROOT, STATE_ROOT
from plc_agent.ltl_adapter import Adapter, Unsupported, properties
from plc_agent.provider import Cancelled
from plc_agent.storage import atomic_json

_model_lock=threading.Lock()
_engine_slots=threading.Semaphore(2)
DEFAULTS={'engine':'cbmc','bound':20,'timeout_seconds':120,'scan_period_ms':10,'memory_limit_mb':768,'unwind':256,'reference_numeric_domain':'ieee'}


def _windows_job(proc,memory_limit_mb,seconds):
    """Limit only this tool process and its children; closing the job kills them."""
    if os.name!='nt':return None
    import ctypes
    from ctypes import wintypes
    class Basic(ctypes.Structure):
        _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),
                  ('flags',wintypes.DWORD),('min_working_set',ctypes.c_size_t),
                  ('max_working_set',ctypes.c_size_t),('active_processes',wintypes.DWORD),
                  ('affinity',ctypes.c_size_t),('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
    class Io(ctypes.Structure):
        _fields_=[(name,ctypes.c_ulonglong) for name in ('reads','writes','other','read_bytes','written_bytes','other_bytes')]
    class Extended(ctypes.Structure):
        _fields_=[('basic',Basic),('io',Io),('process_memory',ctypes.c_size_t),
                  ('job_memory',ctypes.c_size_t),('peak_process_memory',ctypes.c_size_t),('peak_job_memory',ctypes.c_size_t)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR];kernel.CreateJobObjectW.restype=wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    kernel.SetInformationJobObject.restype=wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE];kernel.AssignProcessToJobObject.restype=wintypes.BOOL
    kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
    handle=kernel.CreateJobObjectW(None,None)
    if not handle:raise ctypes.WinError(ctypes.get_last_error())
    limits=Extended();limits.basic.flags=0x2000|0x200|0x4
    limits.basic.job_time=int(max(1,seconds)*10_000_000)
    limits.job_memory=memory_limit_mb*1024*1024
    if not kernel.SetInformationJobObject(handle,9,ctypes.byref(limits),ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(handle,int(proc._handle)):
        error=ctypes.get_last_error();kernel.CloseHandle(handle);raise ctypes.WinError(error)
    return lambda:kernel.CloseHandle(handle)


@contextmanager
def _workspace(directory):
    with tempfile.TemporaryDirectory(prefix='plcverif_') as tmp:
        work=Path(tmp)
        try:yield work
        finally:
            for child in work.iterdir():
                target=directory/child.name
                if child.is_dir():shutil.copytree(child,target,dirs_exist_ok=True)
                else:shutil.copyfile(child,target)


TOOL_LABELS={'plcverif':'PLCverif CLI','java':'Java','cbmc':'CBMC','nuxmv':'nuXmv'}


def discover_tools(plcverif=''):
    """Portable defaults; no developer drive letter or saved configuration needed."""
    bases=[ROOT/'tools/plcverif',ROOT.parent/'plcverif']
    def first(paths):return next((str(p.resolve()) for p in paths if p and Path(p).is_file()),'')
    executable=plcverif or first([base/'plcverif-clic.exe' for base in bases]) or shutil.which('plcverif-clic') or ''
    selected=Path(executable).parent if executable else None
    java_bases=[selected] if selected is not None else bases
    bundled=[p for base in java_bases for p in sorted(base.glob('**/bin/java.exe'))]
    java_home=os.environ.get('JAVA_HOME')
    java=first(bundled+([Path(java_home)/'bin/java.exe'] if java_home else [])) or shutil.which('java') or ''
    cbmc_roots=[ROOT/'tools/cbmc']+[base/'tools/cbmc' for base in ([selected] if selected is not None else bases)]
    cbmc=shutil.which('cbmc') or first([p for base in cbmc_roots for p in (base/'bin/cbmc.exe',base/'cbmc.exe')]+[Path(os.environ.get('ProgramFiles','C:/Program Files'))/'cbmc/bin/cbmc.exe'])
    nuxmv=first([p for base in ([selected] if selected is not None else bases) for p in sorted(base.glob('tools/**/nuXmv.exe'))])
    return {'plcverif':executable,'java':java,'cbmc':cbmc,'nuxmv':nuxmv}


def configuration(home=STATE_ROOT):
    path=Path(home)/'formal_config.json'
    saved=json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    if not isinstance(saved,dict):raise ValueError('formal_config.json 必须是 JSON 对象')
    selected=saved.get('plcverif','')
    return {**DEFAULTS,**discover_tools(selected if isinstance(selected,str) else ''),**saved}


def validate(cfg):
    if type(cfg.get('bound')) is not int or not 1<=cfg['bound']<=1000:raise ValueError('Scan bound must be 1..1000')
    if type(cfg.get('timeout_seconds')) is not int or not 1<=cfg['timeout_seconds']<=1800:raise ValueError('Formal timeout must be 1..1800 seconds')
    if type(cfg.get('scan_period_ms',10)) is not int or not 1<=cfg.get('scan_period_ms',10)<=60000:raise ValueError('Scan period must be 1..60000 ms')
    if type(cfg.get('memory_limit_mb',768)) is not int or not 128<=cfg.get('memory_limit_mb',768)<=4096:raise ValueError('Tool memory limit must be 128..4096 MB')
    if cfg.get('engine','nuxmv') not in ('cbmc','nuxmv'):raise ValueError('Unknown formal engine')
    if cfg.get('reference_numeric_domain','ieee') not in ('ieee','boundary'):raise ValueError('Unknown reference numeric domain')
    if type(cfg.get('unwind',256)) is not int or not 2<=cfg.get('unwind',256)<=4096:raise ValueError('Loop unwind must be 2..4096')
    for name in ('plcverif','java',cfg.get('engine','nuxmv')):
        if not isinstance(cfg.get(name),str) or not Path(cfg[name]).is_file():raise ValueError('Missing executable: '+name)
    return cfg


def environment(home=STATE_ROOT):
    path=str((Path(home)/'formal_config.json').resolve())
    public_path='agent_data/formal_config.json'
    try:
        cfg=configuration(home)
        saved=json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).is_file() else {}
        origins={name:'saved' if saved.get(name) else 'auto' if cfg.get(name) else 'missing' for name in TOOL_LABELS}
        cfg={**cfg,'path_sources':origins}
        missing=[{'key':name,'label':TOOL_LABELS[name],'path':cfg.get(name,'')} for name in ('plcverif','java',cfg.get('engine','cbmc'))
                 if name in TOOL_LABELS and (not isinstance(cfg.get(name),str) or not cfg[name] or not Path(cfg[name]).is_file())]
        if missing:
            return {**cfg,'status':'not_configured','config_file':public_path,'saved':Path(path).is_file(),'missing_tools':missing,
                    'message':'未找到 '+ '、'.join(item['label'] for item in missing)+'，请在下方填写本机可执行文件路径并保存。'}
        validate(cfg)
        return {**cfg,'status':'tools_ready','config_file':public_path,'saved':Path(path).is_file(),'missing_tools':[],
                'message':'已找到所需工具；这只确认文件存在，尚未执行验证。','scope':'Executables found; this is not a claim of full dataset/model compatibility.',
                'unsupported_models':['open-array callers without a configured storage contract','vendor-native VARIANT APIs outside the local PV1 contract','mixed-width float literals and REAL math calls requiring a typed exporter'],
                'floating_point_reference':'https://plcverif-oss.gitlab.io/plcverif-docs/library/backends/Cbmc.html'}
    except (ValueError,OSError) as exc:return {**DEFAULTS,'status':'not_configured','config_file':public_path,'message':str(exc)}


def save_configuration(value,home=STATE_ROOT):
    cfg=configuration(home)
    cfg.update({k:v for k,v in value.items() if k in ('engine','bound','timeout_seconds','scan_period_ms','memory_limit_mb','unwind','plcverif','java','nuxmv','cbmc','reference_numeric_domain')})
    for name in TOOL_LABELS:
        if not isinstance(cfg.get(name,''),str):raise ValueError(TOOL_LABELS[name]+' 路径必须是文本')
        raw=cfg.get(name,'').strip()
        if len(raw)>1 and raw[0]==raw[-1]=='"':raw=raw[1:-1]
        cfg[name]=os.path.expandvars(str(Path(raw).expanduser())) if raw else ''
    automatic=discover_tools(cfg['plcverif'])
    for name in TOOL_LABELS:
        if not cfg[name]:cfg[name]=automatic[name]
    for name in ('plcverif','java',cfg.get('engine','cbmc')):
        if name in TOOL_LABELS and (not cfg.get(name) or not Path(cfg[name]).is_file()):raise ValueError('未找到 '+TOOL_LABELS[name]+'，请填写可执行文件完整路径')
    validate(cfg);atomic_json(Path(home)/'formal_config.json',cfg)
    return environment(home)


def _run(argv,cwd,log,deadline,cancel_event,memory_limit_mb=768):
    """No shell, bounded process lifetime, and full on-disk console output."""
    if cancel_event is not None and cancel_event.is_set():raise Cancelled('Formal verification cancelled')
    if time.monotonic()>=deadline:raise TimeoutError('Formal stage time budget exhausted')
    with Path(log).open('wb') as output:
        proc=subprocess.Popen([str(x) for x in argv],cwd=cwd,stdin=subprocess.DEVNULL,
                              stdout=output,stderr=subprocess.STDOUT,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        close_job=None
        try:
            close_job=_windows_job(proc,memory_limit_mb,deadline-time.monotonic())
            while proc.poll() is None:
                if cancel_event is not None and cancel_event.wait(.05):raise Cancelled('Formal verification cancelled')
                if cancel_event is None:time.sleep(.05)
                if time.monotonic()>=deadline:raise TimeoutError('Formal stage time budget exhausted')
        finally:
            try:
                if close_job:close_job()
                if proc.poll() is None:
                    if os.name=='nt':
                        subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL,timeout=5,creationflags=subprocess.CREATE_NO_WINDOW)
                    else:proc.kill()
                    proc.wait(timeout=5)
            finally:
                if close_job is None and proc.poll() is None:proc.kill()
    return proc.returncode


def _pattern(adapter,path):
    root=ET.Element('patterns');pattern=ET.SubElement(root,'pattern',{'id':'original-ltl'})
    ET.SubElement(pattern,'description').text='Original requirements with explicit scan-end sampling'
    symbols={v:str(i+1) for i,v in enumerate([*adapter.atoms.values(),'PVL_Active','PVL_Done']+(['PVL_Domain'] if adapter.assumptions else []))}
    symbolic=lambda s:'{'+symbols[s]+'}'
    # This build-only requirement retains all atom variables. Its verdict is
    # never used. Original LTL is compiled separately into checked.smv below.
    ET.SubElement(pattern,'tlexpr',{'type':'ctl'}).text='AG(({PLC_END}) --> ('+' AND '.join(symbolic(s) for s in symbols)+'))'
    ET.SubElement(pattern,'humanreadable').text='Model construction only; not a verification verdict'
    for name,key in symbols.items():ET.SubElement(ET.SubElement(pattern,'parameter',{'key':key}),'description').text=name
    ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
    return symbols


def _smv_symbol(model,name):
    expected='instance_'+name
    if not re.search(r'\b'+re.escape(expected)+r'\s*:',model):
        raise Unsupported('Model variable missing after translation: '+expected)
    return expected


def _trace(text):
    """Keep the engine trace and a scan-end view; no invented CODESYS replay claim."""
    states=[];current={};label=None
    for line in text.splitlines():
        m=re.search(r'-> State: ([\d.]+) <-',line)
        if m:
            if label is not None:states.append({'state':label,'values':dict(current)})
            label=m[1];continue
        m=re.match(r'\s*([A-Za-z_]\w*(?:\[[^\]]+\])?) = (.+?)\s*$',line)
        if m and label is not None:current[m[1]]=m[2]
    if label is not None:states.append({'state':label,'values':dict(current)})
    scans=[];previous=False
    for state in states:
        ended=state['values'].get('EoC')=='TRUE'
        if ended and not previous:
            scans.append({'scan':len(scans)+1,'model_state':state['state'],
                          'values':{k:v for k,v in state['values'].items() if k.startswith('instance_') and not k.startswith('instance_PVL_')}})
        previous=ended
    return scans


def _model_build_failure(work, report, target):
    log = (work/'plcverif.log').read_text(encoding='utf-8', errors='replace')
    lines = log.splitlines()
    source = (work/'candidate.scl').read_text(encoding='utf-8').splitlines()
    harness = next((i for i, line in enumerate(source, 1) if line.strip() == 'FUNCTION_BLOCK PVL_Harness'), None)
    report['failure_stage'] = 'plcverif_model_build'
    prefix = 'PLCverif could not build a ' + target + ' model'
    for line in lines:
        line = line.strip()
        location = re.search(r'\((\d+):(\d+)\)|\bLine:\s*(\d+)\b', line)
        if not location or not line.startswith(('Error:', '- ')):
            continue
        number = int(location[1] or location[3])
        if not 1 <= number <= len(source):
            continue
        region = 'verification harness' if harness and number >= harness else 'translated source'
        report['model_build_diagnostic'] = {
            'file': 'candidate.scl', 'line': number, 'region': region, 'message': line,
            'source': source[number - 1].strip()}
        return Unsupported(f'{prefix}: {region}, candidate.scl:{number}: {line}\n{source[number - 1].strip()}')
    error = next((line.strip() for line in lines if line.startswith('Error:')), None)
    return Unsupported(f'{prefix}: {error or log[-1600:].strip()}')


def _verify_cbmc(work,adapter,cfg,report,deadline,cancel_event):
    from plc_agent.cbmc_model import checked_model, results
    model_path=work/'model/ltl-model.c'
    cfa_path=work/'model/ltl-model.verif.cfd-original'
    if not model_path.is_file() or not cfa_path.is_file():
        raise _model_build_failure(work, report, 'structured C')
    transform_started=time.monotonic()
    numeric_calls=next((n['calls'] for n in report['source_adaptations'] if n['kind']=='typed_intrinsics'),{})
    checked,changes=checked_model(model_path.read_text(encoding='utf-8'),adapter,cfa_path,numeric_calls=numeric_calls)
    report['model_transform_seconds']=round(time.monotonic()-transform_started,3)
    (work/'checked.i').write_text(checked,encoding='utf-8')
    report.update(arithmetic_model='IEEE binary32/binary64; CFA-typed literals; round to nearest even',
                  float_literal_adaptations=changes,model_generation_condition_used_for_verdict=False,
                  unwind=max(cfg.get('unwind',256),adapter.bound+1))
    command=[cfg['cbmc'],'checked.i','--winx64','--unwind',str(report['unwind']),
             '--no-standard-checks','--bounds-check','--pointer-check','--div-by-zero-check',
             '--undefined-shift-check','--signed-overflow-check','--unwinding-assertions',
             '--json-ui','--trace']
    if adapter.reference_observer is not None:
        # Keep source-loop unwinding assertions, but avoid expanding a
        # one-channel symbolic floating-point loop hundreds of times. A
        # candidate needing more iterations is inconclusive, never a pass.
        case=adapter.reference_observer
        limit=(max(case.shape['analog_length'],case.shape['channel_length'])+1 if case.kind=='analog'
               else case.shape['capacity']+1)
        limit=min(report['unwind'],limit)
        loop_log=work/'cbmc-loops.log'
        code=_run([cfg['cbmc'],'checked.i','--winx64','--show-loops'],work,loop_log,deadline,cancel_event,cfg.get('memory_limit_mb',768))
        if code!=0:raise Unsupported('CBMC could not inspect reference candidate loops; see cbmc-loops.log')
        loops=re.findall(r'Loop (PVL_Harness\.\d+):',loop_log.read_text(encoding='utf-8',errors='replace'))
        report['reference_loop_unwind']={name:limit for name in loops}
        if loops:command+=['--unwindset',','.join(name+':'+str(limit) for name in loops)]
    # The elevator has six floors. Give short loops a smaller initial
    # expansion, with unwinding assertions still required for a verdict.
    configured_unwind=report['unwind']
    first_unwind=configured_unwind
    if adapter.task['block'].lower()=='fb_elevatortarget':
        first_unwind=min(configured_unwind,max(24,adapter.bound+1))
    unwind_arg=command.index('--unwind')+1
    while not _engine_slots.acquire(timeout=.1):
        if cancel_event is not None and cancel_event.is_set():raise Cancelled('Formal verification cancelled')
        if time.monotonic()>=deadline:raise TimeoutError('Formal engine queue exceeded time budget')
    cbmc_started=time.monotonic()
    try:
        for unwind in dict.fromkeys((first_unwind,configured_unwind)):
            report['unwind']=unwind
            command[unwind_arg]=str(unwind)
            atomic_json(work/'cbmc-command.json',command)
            code=_run(command,work,work/'cbmc.json',deadline,cancel_event,cfg.get('memory_limit_mb',768))
            # 10 includes the deliberate valid-domain witness failure.
            if code not in (0,10):
                log=(work/'cbmc.json').read_text(encoding='utf-8',errors='replace')
                exhausted=bool(re.search(r'out of memory',log,re.I))
                report.update(status='tool_error',failure_stage='cbmc_solver',cbmc_exit_code=code,
                              message=('CBMC ran out of memory while checking the model.'
                                       if exhausted else f'CBMC failed with exit code {code}; see cbmc.json'))
                if exhausted:report['solver_resource_limit']='memory'
                return
            report['bounded_verified_property_ids']=[]
            counterexamples=results((work/'cbmc.json').read_text(encoding='utf-8',errors='replace'),report,adapter)
            if report['unwind_complete'] or unwind==configured_unwind:
                atomic_json(work/'counterexamples.json',counterexamples)
                break
            report['initial_unwind_incomplete']=unwind
            for prop in adapter.properties:
                if prop.get('ast'):
                    prop['status']='not_executed'
                    prop.pop('message',None)
    finally:
        report['cbmc_seconds']=round(time.monotonic()-cbmc_started,3)
        _engine_slots.release()


def _verify_one(task,source,directory,*,timeout_seconds=None,cancel_event=None,config=None,reference_observer=None):
    started=time.monotonic();directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    original=Path(source).read_bytes()
    try:declared=properties(task.get('ltl',{}))
    except Unsupported:declared=[]
    report={'status':'not_configured','backend':'plcverif+nuxmv','policy':'automatic',
            'task_id':task['id'],'dataset_sha256':task.get('dataset_sha256'),
            'source_sha256':hashlib.sha256(original).hexdigest(),'model_calls':0,
            'declared_ltl_total':len(declared),
            'mapped_assertions_total':0,'proved_property_ids':[],'full_ltl_proved':False,
            'bounded_verified_property_ids':[],'evidence_path':str(directory.resolve()),
            'properties':[],'scope':'First N completed scans from declared initial state; PLCverif STEP7 model of supplied ST. CODESYS semantic equivalence is not asserted.',
            'sampling':'After every function-block call; input values vary nondeterministically each scan within declared types.',
            'finite_trace_semantics':'Strong next/until/eventually on N scans. A failed future obligation at the horizon is inconclusive, not an implementation defect.'}
    cfg=config or configuration()
    engine=cfg.get('engine','nuxmv')
    report['backend']='plcverif+'+engine
    report.update(bound=cfg.get('bound',20),timeout_seconds=cfg.get('timeout_seconds',120),scan_period_ms=cfg.get('scan_period_ms',10),memory_limit_mb=cfg.get('memory_limit_mb',768))
    try:
        if cancel_event is not None and cancel_event.is_set():raise Cancelled('Formal verification cancelled')
        validate(cfg)
        if reference_observer is not None:reference_observer.validate_source(original.decode('utf-8-sig'))
        allowed=min(cfg['timeout_seconds'],timeout_seconds if timeout_seconds is not None else cfg['timeout_seconds'])
        deadline=started+max(0,allowed)
        spec=task.get('ltl',{})
        if isinstance(spec,dict) and not isinstance(spec.get('execution',{}),dict):raise Unsupported('ltl.execution must be an object')
        period=cfg.get('scan_period_ms',10);bound=cfg['bound']
        report['time_coverage']={'scan_samples':bound,'scan_period_ms':period,
                                 'first_sample_offset_ms':period,
                                 'last_sample_offset_ms':bound*period,
                                 'maximum_elapsed_between_samples_ms':max(0,bound-1)*period}
        execution=spec.get('execution',{}) if isinstance(spec,dict) else {}
        bindings=execution.get('bindings',{}) if isinstance(execution,dict) else {}
        thresholds=[]
        if isinstance(bindings,dict):
            for name,expression in bindings.items():
                if not isinstance(expression,str):continue
                for match in re.finditer(r'PVL_NowMs\s*-\s*PVL_StartMs\s*>=\s*(\d+)',expression,re.I):
                    threshold=int(match.group(1));minimum=(threshold+period-1)//period+1
                    thresholds.append({'binding':name,'threshold_ms':threshold,
                                       'minimum_scan_bound':minimum,'covered':bound>=minimum})
        if thresholds:report['time_coverage']['observer_thresholds']=thresholds
        if isinstance(spec,dict) and spec.get('execution',{}).get('requires_model'):
            report['properties']=[{**p,'status':'unsupported_model','message':spec['execution']['requires_model']} for p in declared]
            raise Unsupported(spec['execution']['requires_model'])
        adapter=Adapter(task,cfg['bound'],cfg.get('scan_period_ms',10),reference_observer).prepare()
        if reference_observer is not None:
            report['reference_observer']=reference_observer.evidence()
        if adapter.reference_plan:
            report['reference_model']={
                'extension':'bound-storage-v1',
                'contract':adapter.reference_plan['contract'],
                'scope':'Fixed type/bounds/associations only; caller storage starts at PLCverif defaults unless explicitly initialized by observer entry. PV1 helpers are a local contract, not a vendor VARIANT ABI.'}
        report['properties']=adapter.properties
        supported=[p for p in adapter.properties if p.get('ast')]
        report.update(mapped_assertions_total=len(supported),assumptions=adapter.assumptions,
                      observer_definitions=adapter.defs)
        if not supported:
            report.update(status='unsupported',message='No executable properties: observer definitions or LTL syntax need an adapter.')
            return report
        # The NuSMV bridge silently applies experimental fixed-point rounding to
        # REAL/LREAL. Such a result cannot establish IEEE floating-point behavior.
        from plc_agent.st_source import mask_noncode
        typed_source=mask_noncode(original.decode('utf-8-sig')+'\n'+'\n'.join(adapter.declarations+adapter.before+adapter.after+adapter.entry))
        if engine=='nuxmv' and (re.search(r'\b(?:REAL|LREAL|\w+_TO_REAL|\w+_TO_LREAL|REAL_TO_\w+|LREAL_TO_\w+|SQRT|SIN|COS|EXP|LN|EXPT)\b|(?<![\w#])\d+\.\d+',typed_source,re.I) or any(re.search(r'\bL?REAL\b',p['type'],re.I) for p in task['interface'])):
            report['arithmetic_model']='IEEE floating-point required; nuXmv bridge uses an experimental fixed-point abstraction'
            raise Unsupported('REAL/LREAL cannot be reported as verified through the current PLCverif-to-nuXmv fixed-point translation. An IEEE floating-point backend/model is required.')
        from plc_agent.plcverif_st import adapt, adapt_int_abs
        from plc_agent.plcverif_intrinsics import lower_intrinsics
        model_source=(reference_observer.prefix if reference_observer is not None else '')+original.decode('utf-8-sig')
        derived,changes=adapt(model_source,cfg.get('scan_period_ms',10),task['block'])
        instrumented,abs_changes=adapt_int_abs(adapter.instrument(derived,guard_input_domain=engine=='cbmc'))
        instrumented,intrinsic_changes=lower_intrinsics(instrumented,engine=engine)
        report['source_adaptations']=changes+abs_changes+intrinsic_changes
        report['instrumented_sha256']=hashlib.sha256(instrumented.encode()).hexdigest()
        report['tool_sha256']={name:hashlib.sha256(Path(cfg[name]).read_bytes()).hexdigest() for name in ('plcverif','java',engine)}
        # A default temporary directory may contain Chinese characters. Refuse silently broken tool paths.
        with _workspace(directory) as work:
            if not str(work).isascii():raise Unsupported('Set TEMP to an ASCII directory for nuXmv')
            (work/'candidate.scl').write_bytes(instrumented.replace('\r\n','\n').replace('\r','\n').encode('utf-8'))
            symbols=_pattern(adapter,work/'patterns.xml')
            def setting(key,value):return '-'+key+'='+json.dumps(str(value),ensure_ascii=False)
            args=[setting('id','ltl-model'),'-job=verif','-lf=step7',setting('lf.entry','PVL_Harness'),
                  setting('sourcefiles.0',(work/'candidate.scl').as_posix()),setting('output',(work/'model').as_posix()),
                  '-reductions={}','-job.backend='+('cbmc' if engine=='cbmc' else 'nusmv'),setting('job.backend.binary_path',(work/'model-build-only-no-engine.exe').as_posix()),
                  '-job.req=pattern','-job.req.pattern_id=original-ltl',setting('job.req.pattern_file',(work/'patterns.xml').as_posix()),
                  '-job.reporters.0=plaintext','-job.show_progress=true','-encoding.0=UTF-8']
            args += [setting('job.req.pattern_params.'+key,'instance.'+name) for name,key in symbols.items()]
            if engine=='cbmc':args+=['-job.backend.model_variant=CFD_STRUCTURED']
            (work/'model.vc3').write_text('\n'.join(args),encoding='utf-8')
            while not _model_lock.acquire(timeout=.1):
                if cancel_event is not None and cancel_event.is_set():raise Cancelled('Formal verification cancelled')
                if time.monotonic()>=deadline:raise TimeoutError('Formal model queue exceeded time budget')
            plcverif_started=time.monotonic()
            try:
                _run([cfg['plcverif'],'--launcher.suppressErrors','-vm',cfg['java'],str(work/'model.vc3'),
                      '-vmargs','-Xss5m','-Xmx384m','-Dfile.encoding=UTF-8','-Dstdout.encoding=UTF-8','-Dstderr.encoding=UTF-8',
                      '--enable-native-access=ALL-UNNAMED'],Path(cfg['plcverif']).parent,work/'plcverif.log',deadline,cancel_event,cfg.get('memory_limit_mb',768))
            finally:
                report['plcverif_seconds']=round(time.monotonic()-plcverif_started,3)
                _model_lock.release()
            if engine=='cbmc':
                _verify_cbmc(work,adapter,cfg,report,deadline,cancel_event)
                return report
            model_path=work/'model/ltl-model.smv'
            if not model_path.is_file():
                raise _model_build_failure(work, report, 'SMV')
            report['model_generation_condition_used_for_verdict']=False
            model=model_path.read_text(encoding='utf-8')
            if '-- Requirement' not in model:raise Unsupported('Unknown PLCverif model format')
            model=model.split('-- Requirement',1)[0]
            sym=lambda name:_smv_symbol(model,name)
            done=sym('PVL_Done');active=sym('PVL_Active')
            # A source loop that prevents scan completion must not prove a vacuous scan property.
            queries=['CTLSPEC NAME completed_prefix := AF ('+done+');']
            for index,p in enumerate(supported):
                formula=adapter.formula(p,sym,'EoC')
                if adapter.assumptions:formula='(G((EoC & '+active+') -> '+sym('PVL_Domain')+')) -> ('+formula+')'
                p['model_formula']=formula;p['query_name']='original_'+str(index)
                p['query_type']='LTLSPEC'
                if not p['temporal_boundary_sensitive'] and not adapter.assumptions:
                    # G(state-predicate) has an equivalent invariant. Avoid
                    # constructing a liveness automaton merely to show a short safety trace.
                    formula='AG((EoC & '+active+') -> '+sym(p['ast'][1][1])+')'
                    p['model_formula']=formula;p['query_type']='CTLSPEC'
                queries.append(p['query_type']+' NAME '+p['query_name']+' := '+formula+';')
            (work/'checked.smv').write_text(model+'\n'+'\n'.join(queries)+'\n',encoding='utf-8')
            # CTL completion and LTL finite-prefix checks are exact over the bounded scan domain.
            script='set on_failure_script_quits\ngo\ncheck_ctlspec -P completed_prefix\n'
            for p in supported:script+='echo "BEGIN '+p['query_name']+'"\n'+('check_ctlspec' if p['query_type']=='CTLSPEC' else 'check_ltlspec')+' -P '+p['query_name']+'\necho "END '+p['query_name']+'"\n'
            script+='quit\n';(work/'check.script').write_text(script,encoding='ascii')
            engine_timeout=False
            while not _engine_slots.acquire(timeout=.1):
                if cancel_event is not None and cancel_event.is_set():raise Cancelled('Formal verification cancelled')
                if time.monotonic()>=deadline:raise TimeoutError('Formal engine queue exceeded time budget')
            try:_run([cfg['nuxmv'],'-dynamic','-df','-source','check.script','checked.smv'],work,work/'nuxmv.log',deadline,cancel_event,cfg.get('memory_limit_mb',768))
            except TimeoutError:engine_timeout=True
            finally:_engine_slots.release()
            console=(work/'nuxmv.log').read_text(encoding='utf-8',errors='replace')
            atomic_json(directory/'counterexamples.json',{})
            complete=re.search(r'-- specification .*? is (true|false)',console)
            if not complete or complete[1]!='true':
                if engine_timeout:raise TimeoutError('Timed out while establishing completion of all N scans')
                raise Unsupported('Could not establish completion of all N scans; see nuxmv.log')
            counterexamples={}
            for p in supported:
                name=p['query_name'];section=re.search(r'BEGIN '+name+r'\s*(.*?)END '+name,console,re.S)
                verdict=re.search(r'-- specification .*? is (true|false)',section[1],re.S) if section else None
                if verdict is None:
                    p.update(status='timeout' if engine_timeout else 'tool_error',message='Engine did not return a property verdict');continue
                if verdict[1]=='true':
                    p['status']='bounded_pass';report['bounded_verified_property_ids'].append(p['id'])
                else:
                    p['status']='bounded_inconclusive' if p['temporal_boundary_sensitive'] else 'counterexample'
                    p['counterexample']={'scans':_trace(section[1]),'raw':section[1],
                                         'confirmed_on_codesys':False,'scope':'PLCverif source model'}
                    counterexamples[p['id']]=p['counterexample']
            atomic_json(directory/'counterexamples.json',counterexamples)
            states={p['status'] for p in adapter.properties}
            report['status']=('counterexample' if 'counterexample' in states else
                              'timeout' if 'timeout' in states else
                              'tool_error' if 'tool_error' in states else
                              'bounded_inconclusive' if 'bounded_inconclusive' in states else
                              'partial' if 'unsupported' in states else 'bounded_pass')
            report['bounded_all_properties_verified']=all(p['status']=='bounded_pass' for p in adapter.properties)
            report['message']='Completed scan-bounded LTL checks; see per-property results and counterexamples.'
    except Cancelled:
        report.update(status='interrupted',message='Formal verification cancelled')
        raise
    except TimeoutError as exc:
        report.update(status='timeout',message=str(exc))
    except Unsupported as exc:
        report.update(status='unsupported',message=str(exc))
        for p in report['properties']:
            if p['status']=='not_executed':p.update(status='unsupported_model',message=str(exc))
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        report.update(status='not_configured' if not report['properties'] else 'tool_error',message=str(exc))
    finally:
        try:source_changed=Path(source).read_bytes()!=original
        except OSError:source_changed=True
        if source_changed:
            report.update(status='stale_source',message='Source changed during formal verification',bounded_verified_property_ids=[])
            for p in report['properties']:p['status']='stale_source'
        for p in report['properties']:
            p.pop('ast',None)
            if p['status']=='not_executed':p['message']=report.get('message',report['status'])
        if not report['properties']:
            report['properties']=[{**p,'status':'unsupported_model' if report['status']=='unsupported' else 'not_executed','message':report.get('message')} for p in declared]
        report['seconds']=round(time.monotonic()-started,3)
        atomic_json(directory/'formal.json',report)
    return report


def verify(task,source,directory,*,timeout_seconds=None,cancel_event=None,config=None):
    """Use a common time budget for every concrete reference storage case."""
    cfg=config or configuration()
    execution=task.get('ltl',{}).get('execution',{}) if isinstance(task.get('ltl'),dict) else {}
    if task.get('original_id',task.get('id')) not in ('PUBLIC_08','PUBLIC_18') or not execution.get('requires_model') or cfg.get('engine')!='cbmc':
        return _verify_one(task,source,directory,timeout_seconds=timeout_seconds,cancel_event=cancel_event,config=cfg)
    from plc_agent.reference_observers import cases
    try:
        validate(cfg)
        suite=cases(task,cfg.get('reference_numeric_domain','ieee'))
    except (Unsupported,ValueError):
        return _verify_one(task,source,directory,timeout_seconds=timeout_seconds,cancel_event=cancel_event,config=cfg)
    started=time.monotonic();directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    original=Path(source).read_bytes()
    total=min(cfg['timeout_seconds'],timeout_seconds if timeout_seconds is not None else cfg['timeout_seconds'])
    reports=[]
    for case in suite:
        if cancel_event is not None and cancel_event.is_set():raise Cancelled('Formal verification cancelled')
        remaining=total-(time.monotonic()-started)
        if remaining<=0:break
        report=_verify_one(case.task,source,directory/case.name,timeout_seconds=remaining,
                           cancel_event=cancel_event,config=cfg,reference_observer=case)
        reports.append(report)
        if report['status'] in ('counterexample','stale_source','not_configured','timeout'):break
    declared=properties(task['ltl']);aggregate=[]
    for prop in declared:
        rows=[next(p for p in r['properties'] if p['id']==prop['id']) for r in reports]
        failure=next((p for p in rows if p['status']=='counterexample'),None)
        if failure is not None:
            row={**prop,**failure}
            row['case']=suite[rows.index(failure)].name
        elif len(rows)==len(suite) and all(p['status']=='bounded_pass' for p in rows):
            row={**prop,'status':'bounded_pass'}
        else:
            state=next((s for s in ('stale_source','timeout','tool_error','bounded_inconclusive','unsupported_model')
                        if any(p['status']==s for p in rows)),None)
            if state is None:
                state='timeout' if time.monotonic()-started>=total or any(r['status']=='timeout' for r in reports) else 'not_executed'
            row={**prop,'status':state,'message':'Not every declared reference case returned a verified result.'}
        aggregate.append(row)
    states={p['status'] for p in aggregate}
    status=next((s for s in ('stale_source','counterexample','timeout','tool_error','bounded_inconclusive','unsupported_model') if s in states),
                'bounded_pass' if states=={'bounded_pass'} else 'partial')
    if status=='unsupported_model':status='unsupported'
    if Path(source).read_bytes()!=original:
        status='stale_source'
        for p in aggregate:p['status']='stale_source'
    result={
        'status':status,'backend':'plcverif+cbmc','policy':'automatic','task_id':task['id'],
        'dataset_sha256':task.get('dataset_sha256'),'source_sha256':hashlib.sha256(original).hexdigest(),
        'model_calls':0,'bound':cfg['bound'],'scan_period_ms':cfg.get('scan_period_ms',10),
        'timeout_seconds':total,'seconds':round(time.monotonic()-started,3),
        'unwind':max(cfg.get('unwind',256),cfg['bound']+1),
        'unwind_complete':len(reports)==len(suite) and all(r.get('unwind_complete') is True for r in reports),
        'valid_domain_witness':len(reports)==len(suite) and all(r.get('valid_domain_witness') is True for r in reports),
        'declared_ltl_total':len(declared),'properties':aggregate,
        'mapped_assertions_total':min((r.get('mapped_assertions_total',0) for r in reports),default=0),'proved_property_ids':[],'full_ltl_proved':False,
        'bounded_verified_property_ids':[p['id'] for p in aggregate if p['status']=='bounded_pass'],
        'bounded_all_properties_verified':bool(aggregate) and all(p['status']=='bounded_pass' for p in aggregate),
        'reference_cases_total':len(suite),'reference_cases_executed':len(reports),
        'reference_numeric_domain':cfg.get('reference_numeric_domain','ieee'),
        'reference_cases':[{'name':case.name,**case.evidence(),
                            'status':reports[i]['status'] if i<len(reports) else 'not_executed',
                            'loop_unwind':reports[i].get('reference_loop_unwind') if i<len(reports) else None,
                            'minimum_scans_for_full_rejection':2*case.shape['capacity']+1 if case.kind=='fifo' else None,
                            'evidence_path':str((directory/case.name).resolve())} for i,case in enumerate(suite)],
        'scope':'Bounded verification for the listed concrete array shapes/types and explicit input domains; no claim for arbitrary sizes, infinite scans or a vendor VARIANT ABI.',
        'sampling':'After each candidate invocation; independent observer supplies caller data and evaluates original course requirements.',
        'message':'Reference case verification completed; a pass requires every property in every listed case.',
        'evidence_path':str(directory.resolve())}
    atomic_json(directory/'formal.json',result)
    atomic_json(directory/'counterexamples.json',{p['id']:p['counterexample'] for p in aggregate if 'counterexample' in p})
    return result
