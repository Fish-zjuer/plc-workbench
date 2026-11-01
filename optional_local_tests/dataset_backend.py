"""OPTIONAL LOCAL TESTS — removable; never used by the CODESYS path."""
from plc_agent import dataset
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from plc_agent.dataset import validate_source, trace_driver, fingerprint, commands
from plc_agent.storage import atomic_json
from plc_probe.config import cache_dir, toolchain_dir
from plc_probe.backend import BackendError
from plc_probe.backend import _command
def compile_task(source,task):
    source=Path(source);validate_source(source,task)
    fmt=task['adapter_format'];qid=task['id'][-2:]
    if fmt=='struct_rows':
        from optional_local_tests.struct_checks import driver
        bridge=driver(qid);ins=[];outs=task['field_order']['outputs']
    elif fmt in ('analog_reference_rows','fifo_reference_rows'):
        from optional_local_tests.reference_checks import ANALOG_DRIVER,FIFO_DRIVER
        bridge=ANALOG_DRIVER if fmt=='analog_reference_rows' else FIFO_DRIVER;ins=[];outs=[]
    else:bridge,ins,outs=trace_driver(task)
    identity=fingerprint()
    data=source.read_bytes();key=hashlib.sha256(data+bridge.encode()+identity.encode()).hexdigest()[:24]
    directory=cache_dir()/'dataset_builds'/key;directory.mkdir(parents=True,exist_ok=True)
    exe=directory/('runner.exe' if os.name=='nt' else 'runner');meta=directory/'build.json'
    if not exe.is_file() or not meta.is_file():
        compiler=toolchain_dir()/('strucpp.exe' if os.name=='nt' else 'strucpp');cxx=os.environ.get('CXX') or shutil.which('g++')
        if not compiler.is_file() or not cxx:raise BackendError({'status':'missing_dependency','message':'Need selected STruC++ and g++'})
        (directory/'candidate.st').write_bytes(data);(directory/'driver.cpp').write_text(bridge,encoding='utf-8')
        logs=[_command([str(compiler),'candidate.st','-o','candidate.cpp'],directory,'st_to_cpp')]
        include=os.path.relpath(toolchain_dir()/'runtime/include',directory);flags=['-std=c++17','-O1']+(['-static'] if os.name=='nt' else [])
        logs.append(_command([cxx,*flags,'-I',include,'candidate.cpp','driver.cpp','-o',exe.name],directory,'native_compile'))
        atomic_json(meta,{'source_sha256':hashlib.sha256(data).hexdigest(),'execution_fingerprint':identity,'logs':logs})
    return {'executable':exe,'directory':directory,'source_sha256':hashlib.sha256(data).hexdigest(),'execution_fingerprint':identity,'inputs':ins,'outputs':outs,'build_evidence':str(meta)}

def evaluate(source,task):
    artifact=dataset.compile_task(source,task)
    try:run=subprocess.run([str(artifact['executable'])],input=commands(task,artifact),capture_output=True,text=True,encoding='utf-8',timeout=25,cwd=artifact['directory'])
    except subprocess.TimeoutExpired:raise BackendError({'status':'timeout','phase':'execution','message':'Dataset execution exceeded 25 seconds'}) from None
    if run.returncode:raise BackendError({'status':'runtime_error','phase':'execution','message':run.stderr[-2000:]})
    return dataset.judge_output(source,task,artifact,run.stdout.splitlines())
