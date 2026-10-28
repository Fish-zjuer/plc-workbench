"""Human task commands; contract acceptance is deliberately absent from model tools."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from .task_store import TaskStore

def perform(session,config,operation,value,*,source=None,max_revisions=3,base=None,provider=None,notify=None,already_leased=False,item=None,reason=None):
    if not already_leased:
        with session.lease():
            return perform(session,config,operation,value,source=source,max_revisions=max_revisions,
                           base=base,provider=provider,notify=notify,already_leased=True,item=item,reason=reason)
    store=TaskStore(session)
    if operation=="plan":
        path=Path(value)
        if not path.is_absolute():path=(base or Path.cwd())/path
        if path.stat().st_size>800000:raise ValueError("Task contract exceeds 800 KB")
        return store.create(json.loads(path.read_text(encoding="utf-8-sig")))
    if operation=="show":return store.show(value)
    if operation=="accept":return store.accept(value)
    if operation=="status":
        from .task_codesys import status
        return {**store.latest(value),'separate_formal_check':store.formal_status(value),'separate_codesys_compile':status(session,value)}
    if operation=='reject':return store.reject_review_item(value,item,reason)
    if operation=='verify':
        from .task_formal import standalone
        return standalone(session,value,source,provider.cancel_event if provider else None)
    if operation=='compile':
        from .toolbox import Toolbox
        return Toolbox(session,workflow_provider=provider).call('plc_codesys_compile',{'task_id':value,**({'source':source} if source else {})})
    if operation=="export":
        if session.data["mode"]!="execute":return {"status":"blocked_by_plan_mode","message":"Switch to execution mode before exporting files"}
        return store.export(value)
    if operation=="run":
        from .task_workflow import TaskWorkflow
        return TaskWorkflow(session,config,provider,notify).run(value,source,max_revisions,already_leased=True)
    raise ValueError("Use /task plan <contract.json> | show/accept/run/status/export <task-id>")

def main(argv=None):
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description="General PLC tasks: plan → accept → run → status/export")
    sub=parser.add_subparsers(dest="operation",required=True)
    for name in ("plan","show","accept","run","status","export","reject","verify","compile"):
        item=sub.add_parser(name);item.add_argument("value")
        item.add_argument("--project");item.add_argument("--session");item.add_argument("--new")
        if name=='reject':item.add_argument('item');item.add_argument('reason')
        if name in ("run","export","verify","compile"):item.add_argument("--mode",choices=("plan","execute"),default="plan")
        if name in ('verify','compile'):item.add_argument('--source')
        if name=="run":
            item.add_argument("--source");item.add_argument("--max-revisions",type=int,choices=range(1,6),default=3)
    args=parser.parse_args(argv)
    try:
        from .__main__ import select_session
        from .config import ModelConfig
        cfg=ModelConfig.load()
        session=select_session(args.project,args.session,args.new,cfg.model)
        if hasattr(args,"mode"):session.data["mode"]=args.mode;session.save()
        result=perform(session,cfg,args.operation,args.value,source=getattr(args,"source",None),
                       max_revisions=getattr(args,"max_revisions",3),
                       item=getattr(args,'item',None),reason=getattr(args,'reason',None),
                       notify=lambda kind,payload:print(payload.get("text",""),file=sys.stderr))
        print(json.dumps({"project_id":session.project.data["id"],**result},ensure_ascii=False,indent=2))
        return 0 if result["status"] in ("task_plan","contract_accepted","planned","exported",
                    "reviewed_offline_pass","offline_pass_target_pending","not_run","review_item_rejected","reviewed_target_pass","proved","compiled_unit") else 1
    except (OSError,ValueError,RuntimeError) as exc:
        print(str(exc),file=sys.stderr);return 1

if __name__=="__main__":raise SystemExit(main())
