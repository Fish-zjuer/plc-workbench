"""Accepted-task compile evidence, kept separate from behavioral task receipts."""
import hashlib
import json
from .codesys import compile_unit,fingerprint
from .task_spec import digest
from .task_store import TaskStore
from .storage import atomic_json

def standalone_compile(session,task_id,source=None,cancel_event=None):
    if session.data['mode']!='execute':return {'status':'blocked_by_plan_mode','execution_started':False}
    store=TaskStore(session);spec=store.load(task_id)
    if not store.accepted(task_id,spec):return {'status':'requires_contract_confirmation','task_id':task_id}
    latest=store.directory(task_id)/'latest.json'
    if source is None:source=json.loads(latest.read_text(encoding='utf-8'))['source'] if latest.exists() else f'code/{task_id}.st'
    path=(session.project.workspace/source).resolve()
    if not path.is_relative_to(session.project.workspace) or path.suffix.lower()!='.st' or not path.is_file() or path.stat().st_size>200000:
        raise ValueError('Expected a project ST file <=200 KB')
    result=compile_unit(path,spec,cancel_event)
    result.update(task_id=task_id,source=source,contract_sha256=digest(spec))
    atomic_json(store.directory(task_id)/'codesys_latest.json',result)
    session.data['last_codesys_compile']=result;session.save()
    return result

def status(session,task_id):
    from pathlib import Path
    store=TaskStore(session);path=store.directory(task_id)/'codesys_latest.json'
    if not path.exists():return {'status':'not_executed','target_compile':'not_executed'}
    value=json.loads(path.read_text(encoding='utf-8'));valid=False
    try:
        source=(session.project.workspace/value['source']).resolve();directory=Path(value['evidence_path'])
        response=json.loads((directory/'response.json').read_text(encoding='utf-8'))
        valid=(source.is_relative_to(session.project.workspace) and hashlib.sha256(source.read_bytes()).hexdigest()==value['source_sha256']
            and digest(store.load(task_id))==value['contract_sha256'] and fingerprint()==value['execution_fingerprint']
            and store.accepted(task_id) and response.get('source_sha256')==value['source_sha256']
            and hashlib.sha256((directory/'compiled.app').read_bytes()).hexdigest()==response['compiled_image_sha256'])
    except (ValueError,OSError,KeyError,TypeError):pass
    return value if valid else {**value,'status':'stale_evidence','previous_status':value['status'],'target_compile':'stale'}
