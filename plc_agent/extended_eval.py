"""Keep original benchmark predicates immutable; add separately named coverage."""
from .bank_runner import test_bank
from functools import lru_cache
import hashlib
import json
from .config import ROOT


def evaluation_fingerprint():
    names=('plc_agent/bank_contracts.py','plc_agent/bank_runner.py','plc_probe/contracts.py','plc_probe/scenarios.py',
           'plc_agent/struct_checks.py','plc_agent/reference_checks.py','plc_agent/duration_checks.py','plc_agent/extended_eval.py')
    signature=tuple((name,(ROOT/name).stat().st_size,(ROOT/name).stat().st_mtime_ns) for name in names)
    return _fingerprint(signature)


@lru_cache(maxsize=4)
def _fingerprint(signature):
    hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name,_,_ in signature}
    return hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()


def evaluate(source,question_id):
    if question_id in ('04','12'):
        from .backend_r4 import info
        if info():
            result=test_bank(source,question_id)
            if result['status']!='pass':return result
            from .duration_checks import test_durations
            extra=test_durations(source,question_id)
            extra['original_finite_status']=result['status']
            extra['original_finite_scans']=result['summary']['scans']
            extra['original_finite_summary']=result['summary']
            return extra
    if question_id in ('08','18'):
        from .backend_r4 import info
        if info():
            from .reference_checks import test_references
            return test_references(source,question_id)
    if question_id in ('07','17'):
        from .struct_checks import test_struct
        return test_struct(source,question_id)
    return test_bank(source,question_id)
