"""统一形式化入口：全部题目逐条读取LTL，编译/测试与有界验证分别记录。"""
from pathlib import Path


def attach(result, task, source, directory, *, cancel_event=None, timeout_seconds=None, config=None, verifier=None):
    """保留独立编译/测试结论；源模型反例须复核，不能当作已在CODESYS复现。"""
    import hashlib
    from plc_agent.storage import atomic_json
    from plc_agent.provider import Cancelled
    from plc_agent.run_output import event
    from plc_agent import plcverif_backend
    backend='plcverif+'+(config or plcverif_backend.configuration()).get('engine','nuxmv')
    if cancel_event is not None and cancel_event.is_set():
        raise Cancelled('Formal verification cancelled')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    spec=task.get('ltl',{})
    atomic_json(directory/'requirements.json',spec)
    from plc_agent.ltl_adapter import properties, Unsupported
    spec_error=None
    try:declared=properties(spec)
    except Unsupported as exc:declared=[];spec_error=str(exc)
    if spec_error:
        raw=spec.get('properties',[]) if isinstance(spec,dict) else []
        report={'status':'invalid_spec','backend':backend,'model_calls':0,
                'declared_ltl_total':len(raw) if isinstance(raw,list) else 0,'properties':[],
                'bounded_verified_property_ids':[],'proved_property_ids':[],
                'mapped_assertions_total':0,'full_ltl_proved':False,'message':spec_error}
        atomic_json(directory/'formal.json',report)
    elif result.get('status') not in ('pass','compiled_without_tests'):
        report={'status':'not_executed','backend':backend,'model_calls':0,
                'source_sha256':hashlib.sha256(Path(source).read_bytes()).hexdigest() if Path(source).is_file() else None,
                'declared_ltl_total':len(declared),
                'properties':[{**p,'status':'not_executed'} for p in declared],
                'bounded_verified_property_ids':[],'proved_property_ids':[],'mapped_assertions_total':0,
                'full_ltl_proved':False,'message':'Repair compilation or functional tests before formal verification.'}
        atomic_json(directory/'formal.json',report)
    else:
        report=(verifier or plcverif_backend.verify)(task,source,directory,cancel_event=cancel_event,timeout_seconds=timeout_seconds,config=config)
    event(directory.parent,'formal_result',status=report['status'],backend=report.get('backend'),bound=report.get('bound'),
          unwind=report.get('unwind'),unwind_complete=report.get('unwind_complete'),
          valid_domain_witness=report.get('valid_domain_witness'),
          properties=report['properties'],message=report.get('message'),evidence_path=str(directory.resolve()))
    combined={**result,'formal_verification':report,'ltl_status':report['status'],
              'finite_test_status':result.get('status')}
    if report['status']=='counterexample':
        combined.update(status='formal_blocked',message='PLCverif source-model counterexample requires CODESYS replay before automatic code repair.')
    return combined
