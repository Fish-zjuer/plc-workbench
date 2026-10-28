"""Trusted host-side backend registry; models cannot register executable adapters.

R5 can register a CODESYS implementation without replacing the task orchestrator.
An adapter owns capabilities, evaluate(source,spec,cancel,extra), replay and fingerprint.
"""
from .task_spec import capability_report
from .task_runner import evaluate_task,execute_task,execution_fingerprint

def replay_identity(result):
    """Compare observed behavior, ignoring per-invocation evidence paths/nonces."""
    from .task_spec import digest
    return digest({k:v for k,v in result.items() if k not in ('vendor_evidence','vendor_evidence_files')})

class OfflineBackend:
    name="offline"
    def capabilities(self,spec,code=""):return capability_report(spec,code)
    def evaluate(self,source,spec,cancel_event=None,extra_cases=()):
        return evaluate_task(source,spec,cancel_event,extra_cases)
    def replay(self,artifact,spec,cases,cancel_event=None):
        return execute_task(artifact,spec,cases,cancel_event)
    def fingerprint(self):return execution_fingerprint()

from .codesys import CodesysBackend
_FACTORIES={"offline":OfflineBackend,'codesys':CodesysBackend}

def register_backend(name,factory):
    from .task_spec import identifier
    identifier(name)
    if name in _FACTORIES:raise ValueError("Backend already registered: "+name)
    _FACTORIES[name]=factory

def get_backend(spec):
    name=spec.get("executor","offline")
    if name not in _FACTORIES:raise ValueError("Requested execution adapter is not installed: "+name)
    return _FACTORIES[name]()

def capabilities(spec,code=""):
    try:return get_backend(spec).capabilities(spec,code)
    except ValueError as exc:
        return {"status":"blocked","target":spec["target"],"executor":spec.get("executor","offline"),
                "target_compile":"not_executed","blockers":[{"feature":"adapter_not_installed","message":str(exc),
                "actions":["Install/register the matching trusted platform adapter; no silent backend fallback"]}]}
