"""Real CODESYS CLI transport and a clock-independent simulation scan adapter.

Configuration is host-owned in PLC_AGENT_HOME; no model tool can set an executable.
No vendor result is fabricated when the IDE, profile, or simulation template is absent.
"""
from __future__ import annotations
from dataclasses import dataclass
from contextlib import contextmanager
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import uuid

from plc_probe.backend import BackendError
from plc_probe.config import base_cache_dir
from .config import STATE_ROOT
from .formal_st import parse,UnsupportedST,SUPPORTED
from .provider import Cancelled
from .storage import atomic_json
from .task_spec import digest,validate_source,validate_case
from .task_runner import monitor

def discover():
    result=[]
    for base in (Path(os.environ.get('ProgramFiles','C:/Program Files')),Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))):
        if base.is_dir():
            result.extend(p.resolve() for pattern in ('CODESYS*/CODESYS/Common/CODESYS.exe','CODESYS*/Common/CODESYS.exe') for p in base.glob(pattern))
    return sorted(set(result))

def load_config(home=STATE_ROOT):
    path=Path(home)/'codesys.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}

def validate_config(config,require_template=True):
    allowed={'executable','profile','additional_folder','template_project','timeout_seconds'}
    if not isinstance(config,dict) or config.keys()-allowed:raise ValueError('Invalid CODESYS configuration fields')
    exe=Path(config.get('executable',''))
    if not exe.is_file() or exe.suffix.lower()!='.exe':raise ValueError('Select the installed CODESYS.exe')
    if not isinstance(config.get('profile'),str) or not config['profile'].strip():raise ValueError('An exact installed CODESYS profile name is required')
    if any(c in config['profile'] for c in ('"','\r','\n')):raise ValueError('Invalid CODESYS profile value')
    for name in ('additional_folder','template_project'):
        if name in config and (not isinstance(config[name],str) or '\x00' in config[name]):raise ValueError('Invalid configured path')
    if config.get('additional_folder') and not Path(config['additional_folder']).is_dir():raise ValueError('The configured additional folder does not exist')
    if config.get('template_project') and (not Path(config['template_project']).is_file() or Path(config['template_project']).suffix.lower()!='.project'):
        raise ValueError('Select a saved CODESYS .project simulation template')
    if require_template and (not config.get('template_project') or not Path(config['template_project']).is_file()):
        raise ValueError('A dedicated Standard Project simulation template is required')
    if type(config.get('timeout_seconds',120)) is not int or not 5<=config.get('timeout_seconds',120)<=300:
        raise ValueError('CODESYS timeout must be 5..300 seconds')

def doctor():
    cfg=load_config()
    try:validate_config(cfg);ready=True;message='Configured; invoke probe to verify this installed profile and scripting engine.'
    except ValueError as exc:ready=False;message=str(exc)
    return {'status':'configured_not_probed' if ready else 'setup_required','installed_candidates':[str(p) for p in discover()],
            'message':message,'configuration':cfg,'vendor_compile_executed':False,
            'download':'https://store.codesys.com/en/codesys.html'}

def _identity_files(cfg):
    exe=Path(cfg['executable']);files=[exe,Path(__file__),Path(__file__).with_name('codesys_worker.py')]
    if cfg.get('template_project'):files.append(Path(cfg['template_project']))
    # Include profile/compiler DLLs in the IDE installation, with stat-keyed content hashing.
    for folder in (exe.parent,exe.parent.parent/'Profiles',exe.parent.parent/'PlugIns'):
        if folder.is_dir():files.extend(p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() in ('.dll','.profile','.config'))
    if cfg.get('additional_folder'):
        folder=Path(cfg['additional_folder'])
        if folder.is_dir():files.extend(p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() in ('.dll','.profile','.config','.library','.compiled-library'))
    return tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in sorted(set(files)) if p.is_file())

@lru_cache(maxsize=4)
def _identity(signature,config_json):
    return digest({'configuration':config_json,'files':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p,_,_ in signature}})

def fingerprint(config=None):
    cfg=load_config() if config is None else config
    validate_config(cfg)
    return _identity(_identity_files(cfg),json.dumps(cfg,sort_keys=True))

@contextmanager
def profile_lease(cfg,cancel_event=None):
    key=digest({k:cfg.get(k) for k in ('executable','profile','additional_folder')})
    path=work_root().parent/(key+'.lock')
    with path.open('a+b') as stream:
        if path.stat().st_size==0:stream.write(b'0');stream.flush()
        stream.seek(0)
        queued=time.monotonic()
        while True:
            if time.monotonic()-queued>1800:raise BackendError({'status':'timeout','phase':'codesys_queue','message':'CODESYS queue wait exceeded 1800 seconds'})
            if cancel_event and cancel_event.is_set():raise Cancelled('CODESYS queue cancelled')
            try:
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError:
                if cancel_event is None:
                    raise BackendError({'status':'backend_busy','message':'This CODESYS profile is already running another workbench invocation'}) from None
                cancel_event.wait(.1)
        try:yield
        finally:
            stream.seek(0)
            if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)

def invoke(payload,directory,config=None,cancel_event=None):
    cfg=load_config() if config is None else config
    validate_config(cfg,require_template=payload.get('action')!='probe')
    with profile_lease(cfg,cancel_event):return _invoke(payload,directory,cfg,cancel_event)

def _invoke(payload,directory,cfg,cancel_event):
    directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=True)
    if (directory/'response.json').exists():raise ValueError('Use a fresh CODESYS evidence directory')
    nonce=uuid.uuid4().hex
    request={**payload,'nonce':nonce,'output':str(directory/'response.json')}
    atomic_json(directory/'request.json',request)
    worker=Path(__file__).with_name('codesys_worker.py')
    args=[cfg['executable'],'--profile='+cfg['profile'],'--noUI','--runscript='+str(worker)]
    if cfg.get('additional_folder'):args.append('--additionalfolder='+cfg['additional_folder'])
    if os.name=='nt':
        # Nathan's vendor-tested CLI parses the raw command line. Quote option
        # values, rather than letting list2cmdline quote the entire option.
        args='"'+cfg['executable']+'" --noUI --profile="'+cfg['profile']+'" --runscript="'+str(worker)+'"'
        if cfg.get('additional_folder'):args+=' --additionalfolder="'+cfg['additional_folder']+'"'
    env={k:v for k,v in os.environ.items() if not k.startswith('PLC_AGENT_')}
    env['PLC_WORKBENCH_REQUEST']=str(directory/'request.json')
    env['PLC_WORKBENCH_EXECUTABLE']=str(Path(cfg['executable']).resolve())
    started=time.monotonic()
    process=subprocess.Popen(args,cwd=directory,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    try:
        while True:
            if cancel_event and cancel_event.is_set():raise Cancelled('CODESYS run cancelled')
            if time.monotonic()-started>cfg.get('timeout_seconds',120):
                raise BackendError({'status':'timeout','phase':'codesys','message':'CODESYS headless invocation timed out'})
            try:out,err=process.communicate(timeout=.25);break
            except subprocess.TimeoutExpired:pass
    finally:
        if process.poll() is None:
            if os.name=='nt':
                subprocess.run(['taskkill.exe','/PID',str(process.pid),'/T','/F'],capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            else:process.kill()
            process.communicate()
    (directory/'stdout.log').write_bytes(out);(directory/'stderr.log').write_bytes(err)
    response=directory/'response.json'
    if not response.is_file():
        raise BackendError({'status':'tool_error','phase':'codesys','returncode':process.returncode,
             'message':'CODESYS did not write an authenticated run response; inspect exact profile and script logs.',
             'stderr':err.decode('utf-8','replace')[-3000:], 'stdout':out.decode('utf-8','replace')[-3000:], 'evidence_path':str(directory)})
    try:value=json.loads(response.read_text(encoding='utf-8'))
    except (ValueError,OSError) as exc:raise BackendError({'status':'protocol_error','message':'Invalid CODESYS response JSON'}) from exc
    if not isinstance(value,dict):raise BackendError({'status':'protocol_error','message':'Expected a CODESYS response object'})
    if value.get('nonce')!=nonce or value.get('source_sha256')!=payload.get('source_sha256'):
        raise BackendError({'status':'protocol_error','message':'CODESYS response run/source identity mismatch'})
    if value.get('vendor')!='CODESYS' or not value.get('vendor_version'):
        raise BackendError({'status':'protocol_error','message':'Missing executing CODESYS version evidence'})
    if value.get('status') not in ('completed','probed') or process.returncode or value.get('compile_errors',0):
        raise BackendError({'status':'compile_error' if value.get('compile_errors') else 'tool_error','phase':'codesys',
             'message':value.get('message','CODESYS failed'),'diagnostics':value.get('diagnostics',[])})
    if payload.get('action')!='probe':
        app=directory/'compiled.app'
        if not app.is_file() or not app.stat().st_size or hashlib.sha256(app.read_bytes()).hexdigest()!=value.get('compiled_image_sha256'):
            raise BackendError({'status':'protocol_error','message':'Missing or changed CODESYS compiled application image'})
    return value

def split_source(code,block):
    # Position-preserving comments; do not cut at END_VAR mentioned in a comment.
    masked=list(code);i=0;depth=0
    while i<len(code):
        if depth:
            if code.startswith('(*',i):depth+=1;masked[i:i+2]='  ';i+=2
            elif code.startswith('*)',i):depth-=1;masked[i:i+2]='  ';i+=2
            else:
                if code[i]!='\n':masked[i]=' '
                i+=1
        elif code.startswith('(*',i):depth=1;masked[i:i+2]='  ';i+=2
        elif code.startswith('//',i):
            end=code.find('\n',i);end=len(code) if end<0 else end
            masked[i:end]=' '*(end-i);i=end
        elif code[i] in ("'",'"'):
            quote=code[i];masked[i]=' ';i+=1;closed=False
            while i<len(code):
                if code[i]=='$' and i+1<len(code):masked[i:i+2]='  ';i+=2;continue
                if code[i]==quote:
                    masked[i]=' '
                    if i+1<len(code) and code[i+1]==quote:masked[i+1]=' ';i+=2;continue
                    i+=1;closed=True;break
                if code[i]!='\n':masked[i]=' '
                i+=1
            if not closed:raise ValueError('Unclosed ST string literal')
        else:i+=1
    if depth:raise ValueError('Unclosed ST comment')
    clean=''.join(masked)
    head=re.match(r'\s*FUNCTION_BLOCK\s+'+re.escape(block)+r'\b',clean,re.I)
    if not head:raise ValueError('CODESYS import currently requires one complete FB without preceding TYPE/helper units')
    pos=head.end()
    while True:
        declaration=re.match(r'\s*VAR(?:_INPUT|_OUTPUT|_IN_OUT|_TEMP|_STAT|_EXTERNAL)?\b.*?\bEND_VAR\b',clean[pos:],re.I|re.S)
        if not declaration:break
        pos+=declaration.end()
    end=re.search(r'\bEND_FUNCTION_BLOCK\b\s*;?\s*$',clean,re.I)
    if not end or pos>end.start():raise ValueError('Cannot split complete FB declaration/implementation')
    return code[:pos],code[pos:end.start()]

def harness(spec,cases):
    count=sum(len(c['trace']) for c in cases)
    if not 1<=len(cases)<=128 or not 1<=count<=20000:raise ValueError('CODESYS scan budget exceeded')
    declaration=['PROGRAM PLC_PRG','VAR','WB_Done : BOOL := FALSE;']
    for i in range(len(cases)):declaration.append(f'WB_Uut{i} : {spec["block"]};')
    for i,(name,dtype) in enumerate(spec['outputs'].items()):declaration.append(f'WB_Out{i} : ARRAY[0..{count-1}] OF {dtype};')
    declaration.append('END_VAR')
    body=['IF NOT WB_Done THEN'];index=0
    for case_no,case in enumerate(cases):
        validate_case(case,spec)
        for row in case['trace']:
            for name,dtype in spec['inputs'].items():
                value=row['inputs'][name];literal=('TRUE' if value else 'FALSE') if dtype=='BOOL' else dtype+'#'+str(value)
                body.append(f'WB_Uut{case_no}.{name} := {literal};')
            body.append(f'WB_Uut{case_no}();')
            for i,name in enumerate(spec['outputs']):body.append(f'WB_Out{i}[{index}] := WB_Uut{case_no}.{name};')
            index+=1
    body.extend(['WB_Done := TRUE;','END_IF;'])
    return '\n'.join(declaration),'\n'.join(body)

def parse_value(text,dtype):
    text=str(text).strip().upper().replace('_','')
    if dtype=='BOOL':
        if text.startswith('BOOL#'):text=text[5:]
        if text not in ('TRUE','FALSE'):raise ValueError('Unexpected CODESYS BOOL output')
        return text=='TRUE'
    if '#' in text:
        parts=text.split('#')
        if parts[0] in SUPPORTED:parts=parts[1:]
        return int(parts[1],int(parts[0])) if len(parts)==2 else int(parts[0])
    return int(text)

@dataclass
class CodesysArtifact:
    source_sha256:str
    execution_fingerprint:str
    directory:Path
    spec:dict
    declaration:str
    implementation:str

class CodesysBackend:
    name='codesys'
    def fingerprint(self):return fingerprint()
    def capabilities(self,spec,code=''):
        blockers=[]
        try:validate_config(load_config())
        except ValueError as exc:blockers.append({'feature':'codesys_installation','message':str(exc),
            'actions':['Install the official IDE, then configure its exact executable/profile and a dedicated simulation template']})
        if spec['inouts'] or set([*spec['inputs'].values(),*spec['outputs'].values()])-SUPPORTED:
            blockers.append({'feature':'codesys_simulation_bridge','message':'Current simulation bridge supports clock-independent BOOL/integer FBs.',
                'actions':['Use CODESYS compile-only for other interfaces','Add an explicitly timed/typed execution adapter; do not substitute the local backend']})
        if code:
            try:parse(code)
            except UnsupportedST as exc:blockers.append({'feature':'clock_independent_scan_bridge','message':str(exc),
                'actions':['Use compile-only for this program','A timer/external-FB simulation driver is not yet validated']})
        return {'status':'blocked' if blockers else 'ready_for_codesys_simulation','executor':'CODESYS CLI + local simulation',
                'target':spec['target'],'target_compile':'not_executed','blockers':blockers,
                'scope':'Actual vendor compile and clock-independent simulation; no physical PLC or virtualized timer claims.'}
    def evaluate(self,source,spec,cancel_event=None,extra_cases=()):
        code=Path(source).read_bytes();validate_source(code.decode('utf-8-sig'),spec)
        parse(code.decode('utf-8-sig')) # Fail closed on unsupported execution semantics.
        declaration,implementation=split_source(code.decode('utf-8-sig'),spec['block'])
        directory=Path(tempfile.mkdtemp(prefix='run_',dir=work_root()))
        artifact=CodesysArtifact(hashlib.sha256(code).hexdigest(),self.fingerprint(),directory,spec,declaration,implementation)
        result=self.replay(artifact,spec,spec['scenarios']+list(extra_cases),cancel_event)
        result.update(source_sha256=artifact.source_sha256,execution_fingerprint=artifact.execution_fingerprint,
                      behavior_tested=True,target_compile='passed',vendor_evidence=str(directory))
        return result,artifact
    def replay(self,artifact,spec,cases,cancel_event=None):
        cfg=load_config();declaration,body=harness(spec,cases)
        directory=artifact.directory/uuid.uuid4().hex[:12]
        request={'action':'simulate','source_sha256':artifact.source_sha256,'block':spec['block'],
                 'template_project':cfg['template_project'],'declaration':artifact.declaration,
                 'implementation':artifact.implementation,'harness_declaration':declaration,'harness_body':body,
                 'output_names':list(spec['outputs']),'row_count':sum(len(c['trace']) for c in cases)}
        response=invoke(request,directory,cancel_event=cancel_event)
        if response.get('target_compile')!='passed' or response.get('simulation') is not True:
            raise BackendError({'status':'protocol_error','message':'CODESYS did not verify simulation compilation/execution'})
        if fingerprint()!=artifact.execution_fingerprint:raise BackendError({'status':'backend_changed','message':'CODESYS identity changed during run'})
        raw=response.get('actual_rows',[])
        if len(raw)!=request['row_count']:raise BackendError({'status':'protocol_error','message':'Wrong CODESYS row count'})
        try:actual=[{name:parse_value(row[name],dtype) for name,dtype in spec['outputs'].items()} for row in raw]
        except (ValueError,KeyError,TypeError) as exc:
            raise BackendError({'status':'protocol_error','message':'Invalid CODESYS output row: '+str(exc)}) from exc
        evidence={str(p.relative_to(artifact.directory)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in artifact.directory.glob('*/*') if p.is_file() and p.name in ('request.json','response.json','stdout.log','stderr.log','compiled.app')}
        return {**monitor(spec,cases,actual),'vendor':'CODESYS','vendor_version':response['vendor_version'],
                'target_compile':'passed','simulation':True,'vendor_evidence':str(artifact.directory),
                'vendor_evidence_files':evidence}

def work_root():
    root=base_cache_dir().parent/'plc-agent/codesys/runs';root.mkdir(parents=True,exist_ok=True);return root

def compile_unit(source,spec,cancel_event=None):
    data=Path(source).read_bytes();validate_source(data.decode('utf-8-sig'),spec)
    declaration,implementation=split_source(data.decode('utf-8-sig'),spec['block'])
    cfg=load_config();validate_config(cfg)
    identity=fingerprint(cfg)
    directory=Path(tempfile.mkdtemp(prefix='compile_',dir=work_root()))
    value=invoke({'action':'compile','source_sha256':hashlib.sha256(data).hexdigest(),'block':spec['block'],
        'template_project':cfg['template_project'],'declaration':declaration,'implementation':implementation,
        'harness_declaration':'PROGRAM PLC_PRG\nVAR WB_Uut : '+spec['block']+'; END_VAR','harness_body':'(* Compile-only anchor; no behavioral execution. *)'},directory,cancel_event=cancel_event)
    if value.get('target_compile')!='passed':raise BackendError({'status':'protocol_error','message':'No CODESYS compilation evidence'})
    if identity!=fingerprint() or hashlib.sha256(Path(source).read_bytes()).hexdigest()!=hashlib.sha256(data).hexdigest():
        raise BackendError({'status':'stale_evidence','message':'Source or CODESYS changed during compilation'})
    return {'status':'compiled_unit','source_sha256':hashlib.sha256(data).hexdigest(),'target_compile':'passed',
            'behavior_tested':False,'execution_fingerprint':identity,'vendor_version':value['vendor_version'],
            'evidence_path':str(directory),'simulation':True}
