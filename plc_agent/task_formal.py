"""Proof execution and concrete counterexample confirmation; no model-owned verification model."""
from pathlib import Path
import hashlib
import uuid
from .formal_verify import verify,fingerprint
from .task_spec import digest
from .task_backend import get_backend,replay_identity
from .task_store import TaskStore
from .storage import atomic_json
from plc_probe.backend import BackendError

def check(source,spec,directory,*,backend=None,artifact=None,cancel_event=None):
    directory=Path(directory)
    options=spec.get('formal',{})
    report=verify(source,spec,directory,bound=options.get('bound',20),
                  timeout_seconds=options.get('timeout_seconds',20),cancel_event=cancel_event)
    if report['status']=='counterexample':
        backend=backend or get_backend(spec)
        try:
            if artifact is None:_,artifact=backend.evaluate(source,spec,cancel_event,())
            cases=[p['counterexample'] for p in report['properties'] if p['status']=='counterexample']
            first=backend.replay(artifact,spec,cases,cancel_event)
            second=backend.replay(artifact,spec,cases,cancel_event)
            atomic_json(directory/'counterexample_replay_1.json',first)
            atomic_json(directory/'counterexample_replay_2.json',second)
            same=replay_identity(first)==replay_identity(second)
            claims=[p for p in report['properties'] if p['status']=='counterexample']
            confirmed=(same and all(c['status']=='fail' and
                any(v.get('property')==claim['id'] for row in c['rows'] for v in row['violations']) and
                [row['actual'] for row in c['rows']]==[row['symbolic_actual'] for row in claim['symbolic_rows']]
                for c,claim in zip(first['cases'],claims)))
            report['counterexample_status']='confirmed' if confirmed else 'semantics_mismatch'
            report['status']='counterexample_confirmed' if confirmed else 'semantics_mismatch'
            report['confirmed_cases']=cases if confirmed else []
            report['replay_result']=first
            report['execution_fingerprint']=artifact.execution_fingerprint
        except (BackendError,ValueError) as exc:
            report['status']='counterexample_not_replayed'
            report['replay_error']=exc.result if isinstance(exc,BackendError) else str(exc)
    if hashlib.sha256(Path(source).read_bytes()).hexdigest()!=report['source_sha256']:
        report['status']='stale_source'
    atomic_json(directory/'formal.json',report)
    return report

def summary(report):
    return {k:v for k,v in report.items() if k not in ('queries','replay_result','confirmed_cases')}

def standalone(session,task_id,source=None,cancel_event=None):
    if session.data['mode']!='execute':
        return {'status':'planned','execution_started':False,'message':'Formal solver runs only in execution mode'}
    store=TaskStore(session);spec=store.load(task_id)
    if not store.accepted(task_id,spec):return {'status':'requires_contract_confirmation','task_id':task_id}
    latest_path=store.directory(task_id)/'latest.json'
    if source is None:
        import json
        source=json.loads(latest_path.read_text(encoding='utf-8'))['source'] if latest_path.exists() else f'code/{task_id}.st'
    path=(session.project.workspace/source).resolve()
    if not path.is_relative_to(session.project.workspace) or not path.is_file():raise ValueError('Expected a project source file')
    directory=store.directory(task_id)/'formal_runs'/uuid.uuid4().hex[:12]
    report=check(path,spec,directory,cancel_event=cancel_event)
    report.update(task_id=task_id,source=source,evidence_path=str(directory))
    atomic_json(directory/'formal.json',report)
    atomic_json(store.directory(task_id)/'formal_latest.json',report)
    session.data['last_formal']=summary(report);session.save()
    return summary(report)
