"""Small real-service trial on new, independently specified software-control tasks.

No candidate ST is authored here. The configured weak model authors and reviews.
Private projects stay in PLC_AGENT_HOME; only sanitized experiment evidence is copied.
"""
from __future__ import annotations
from dataclasses import replace
import argparse
import json
from pathlib import Path
import shutil
import sys

from plc_agent.config import ModelConfig,ROOT,STATE_ROOT
from plc_agent.provider import ChatProvider
from plc_agent.storage import Project,Session,atomic_json
from plc_agent.task_store import TaskStore
from plc_agent.task_workflow import TaskWorkflow

def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser()
    parser.add_argument('--round',default='')
    parser.add_argument('--only',choices=('interlocked_start','restart_delay','acknowledge_latch'))
    parser.add_argument('--seed-source',type=Path)
    args=parser.parse_args()
    cfg=replace(ModelConfig.load(),max_steps=12,timeout=90)
    cfg.validate()
    out=ROOT/"experiments/general_tasks_r6";out.mkdir(parents=True,exist_ok=True)
    if args.round:
        if not args.round.isalnum():raise ValueError('Round name must be alphanumeric')
        out=out/args.round;out.mkdir(exist_ok=True)
    matrix=[]
    for name in ((args.only,) if args.only else ("interlocked_start","restart_delay","acknowledge_latch")):
        print("BEGIN "+name,flush=True)
        spec=json.loads((ROOT/"examples/tasks"/(name+".json")).read_text(encoding="utf-8"))
        project=Project.create("R6 real trial "+name,STATE_ROOT,kind="benchmark")
        session=Session.create(project,cfg.model);store=TaskStore(session)
        task_id=store.create(spec)["task_id"]
        if args.seed_source:
            if not args.only:raise ValueError('A seed source requires --only')
            candidate=project.workspace/'code'/f'{task_id}.st';candidate.parent.mkdir(exist_ok=True)
            candidate.write_bytes(args.seed_source.read_bytes())
        # Developer-owned fixture acceptance; not a model tool or model grading its own tests.
        store.accept(task_id);session.data["mode"]="execute";session.save()
        provider=ChatProvider(cfg)
        result=TaskWorkflow(session,cfg,provider,notify=lambda k,p:print(p.get("text",""),flush=True)).run(task_id,max_revisions=3)
        directory=store.directory(task_id)/"runs"/result["run_id"]
        public=out/name;public.mkdir(exist_ok=True)
        replacements=[(str(project.path),"<local_project>"),(str(STATE_ROOT),"<private_state>")]
        from plc_probe.config import base_cache_dir
        replacements.append((str(base_cache_dir()),"<compiler_cache>"))
        def clean(value):
            if isinstance(value,str):
                if cfg.api_key:value=value.replace(cfg.api_key,"[redacted]")
                for old,new in replacements:value=value.replace(old,new).replace(old.replace("\\","/"),new)
                return value
            if isinstance(value,list):return [clean(v) for v in value]
            if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
            return value
        for path in sorted(directory.iterdir()):
            if path.suffix==".json":
                atomic_json(public/path.name,clean(json.loads(path.read_text(encoding="utf-8"))))
            elif path.suffix==".st":shutil.copyfile(path,public/path.name)
        usage=[{k:m[k] for k in ("status","duration_seconds","usage","http_status") if k in m} for m in provider.metrics]
        item={"name":name,"status":result["status"],"source_sha256":result["source_sha256"],
              "contract_sha256":result["contract_sha256"],"revisions":len(result["attempts"]),
              "review_rounds":len(result["reviews"]),"model_requests":len(provider.metrics),
              "final_evaluation":clean(result.get("final_evaluation")),"target_compile":result["target_compile"],
              "usage":usage,"private_project_id":project.data["id"],"task_id":task_id}
        item['source_origin']='previous model candidate, then bounded repair/review' if args.seed_source else 'empty source'
        matrix.append(item);atomic_json(out/"results.json",{"model":cfg.model,"results":matrix,
            "scope":"Three new task fixtures; one run each from empty source, frozen developer-authored contracts. Not a broad accuracy estimate or vendor compilation."})
        print("END "+name+" "+result["status"],flush=True)
    return 0

if __name__=="__main__":raise SystemExit(main())
