"""Actual CODESYS compilation of dataset candidates; never substitutes local checks."""
import hashlib
from pathlib import Path
import re
import tempfile
from . import codesys, dataset
from .st_source import split_units
from .storage import atomic_json
from plc_probe.backend import BackendError


def compile_dataset(source, task, config=None, cancel_event=None):
    source=Path(source)
    dataset.validate_source(source,task)
    cfg=config if config is not None else codesys.load_config()
    codesys.validate_config(cfg)
    data=source.read_bytes()
    units=split_units(data.decode('utf-8-sig'))
    if any(u['name'].upper()=='PLC_PRG' for u in units): raise ValueError('PLC_PRG is reserved for the compile harness')
    declarations=['PROGRAM PLC_PRG','VAR','    WB_Uut : '+task['block']+';']
    bindings=[]
    for port in task['interface']:
        if port['direction']=='Input/Output':
            dtype=re.sub(r'ARRAY\[\*\]','ARRAY[0..2]',port['type'],flags=re.I)
            name='WB_'+port['name']
            declarations.append('    '+name+' : '+dtype+';')
            bindings.append(port['name']+' := '+name)
    declarations.append('END_VAR')
    before=codesys.fingerprint(cfg)
    attempts=[]
    for attempt in range(2):
        if cancel_event and cancel_event.is_set():
            from .provider import Cancelled
            raise Cancelled('CODESYS compilation cancelled')
        if source.read_bytes()!=data or before!=codesys.fingerprint(cfg):
            raise BackendError({'status':'stale_evidence','message':'Source or vendor environment changed before compilation'})
        directory=Path(tempfile.mkdtemp(prefix='dataset_compile_',dir=codesys.work_root()))
        try:
            value=codesys.invoke({'action':'compile','source_sha256':hashlib.sha256(data).hexdigest(),
                'block':task['block'],'template_project':cfg['template_project'],'units':units,
                'harness_declaration':'\n'.join(declarations),'harness_body':'WB_Uut('+', '.join(bindings)+');'},
                directory,config=cfg,cancel_event=cancel_event)
            attempts.append({'attempt':attempt+1,'status':'compiled','evidence_path':str(directory)})
            break
        except BackendError as exc:
            failure={**exc.result,'evidence_path':str(directory),
                'source_sha256':hashlib.sha256(data).hexdigest(),'dataset_sha256':task['dataset_sha256']}
            attempts.append({'attempt':attempt+1,**failure})
            atomic_json(directory/'attempt_failure.json',failure)
            # Only transient IDE execution timeouts; never retry compiler rejection.
            if failure.get('status')!='timeout' or failure.get('phase')!='codesys' or attempt==1:
                raise BackendError({**failure,'compile_attempts':attempts}) from exc
    if before!=codesys.fingerprint(cfg) or source.read_bytes()!=data:
        raise BackendError({'status':'stale_evidence','message':'Source or vendor environment changed'})
    result={'status':'compiled_unit','target_compile':value['target_compile'],
        'vendor_version':value['vendor_version'],'source_sha256':hashlib.sha256(data).hexdigest(),
        'dataset_sha256':task['dataset_sha256'],'execution_fingerprint':before,
        'evidence_path':str(directory),'compile_attempts':attempts,'diagnostics':value.get('diagnostics',[]),'behavior_tested':False}
    atomic_json(directory/'result.json',result)
    return result


def evaluate_candidate(source,task,vendor_config=None,cancel_event=None):
    """Identical checker feedback for both frameworks. Vendor stage is explicit."""
    result={'target_compile':'not_executed'}
    if vendor_config is not None:
        try: result['codesys']=compile_dataset(source,task,vendor_config,cancel_event)
        except BackendError as exc:
            return {**exc.result,'target_compile':'failed' if exc.result['status']=='compile_error' else 'not_executed'}
        except (ValueError,OSError) as exc:
            return {'status':'invalid_candidate','message':str(exc),'target_compile':'not_executed'}
        result['target_compile']='passed'
    try:
        if task.get('scenarios'):
            local=dataset.evaluate(source,task)
        else:
            dataset.compile_task(source,task)
            local={'status':'compiled_without_tests','message':'No functional tests supplied'}
    except BackendError as exc: local=exc.result
    except (ValueError,OSError) as exc: local={'status':'invalid_candidate','message':str(exc)}
    return {**local,**result}
