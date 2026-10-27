"""Refresh saved candidate evidence on current code; author is never substituted."""
from dataclasses import replace
import json
from pathlib import Path
import shutil
import sys
from plc_agent.config import ModelConfig,ROOT,STATE_ROOT
from plc_agent.provider import ChatProvider
from plc_agent.storage import Project,Session,atomic_json
from plc_agent.task_workflow import TaskWorkflow
from plc_agent.task_store import TaskStore
from plc_probe.config import base_cache_dir

def main():
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    cfg=replace(ModelConfig.load(),max_steps=8,timeout=90)
    base=ROOT/"experiments/general_tasks_r6";out=base/"final_recheck";out.mkdir(exist_ok=True)
    initial=json.loads((base/"results.json").read_text(encoding="utf-8"))["results"]
    intake=json.loads((base/"intake/result.json").read_text(encoding="utf-8"))
    repair=json.loads((base/"zerorepair/results.json").read_text(encoding="utf-8"))["results"][0]
    selected=[r for r in initial if r["name"] in ("interlocked_start","acknowledge_latch")]
    selected += [{"name":"restart_delay",**{k:repair[k] for k in ("private_project_id","task_id")}},
                 {"name":"natural_language_intake",**{k:intake[k] for k in ("private_project_id","task_id")}}]
    matrix=[]
    for item in selected:
        print("BEGIN "+item["name"],flush=True)
        project=Project.load(item["private_project_id"])
        session=Session.load(project,project.data["last_session"]);session.data["mode"]="execute";session.save()
        provider=ChatProvider(cfg)
        result=TaskWorkflow(session,cfg,provider,notify=lambda k,p:print(p.get("text",""),flush=True)).run(item["task_id"])
        store=TaskStore(session);directory=store.directory(item["task_id"])/"runs"/result["run_id"]
        dest=out/item["name"];dest.mkdir(exist_ok=True)
        def clean(v):
            if isinstance(v,str):
                for old,new in ((str(project.path),"<local_project>"),(str(STATE_ROOT),"<private_state>"),
                                (str(base_cache_dir()),"<compiler_cache>")):
                    v=v.replace(old,new).replace(old.replace("\\","/"),new)
                if cfg.api_key:v=v.replace(cfg.api_key,"[redacted]")
                return v
            if isinstance(v,list):return [clean(x) for x in v]
            if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
            return v
        for path in directory.iterdir():
            if path.suffix==".json":atomic_json(dest/path.name,clean(json.loads(path.read_text(encoding="utf-8"))))
            elif path.suffix==".st":shutil.copyfile(path,dest/path.name)
        matrix.append({"name":item["name"],"status":result["status"],"new_code_revisions":len(result["attempts"]),
              "source_sha256":result["source_sha256"],"contract_sha256":result["contract_sha256"],
              "execution_fingerprint":result["execution_fingerprint"],"baseline":result.get("final_evaluation",{}).get("summary"),
              "review_rounds":len(result["reviews"]),"review_scenarios":sum(len(r["proposals"]) for r in result["reviews"]),
              "model_calls":len(provider.metrics),"target_compile":result["target_compile"]})
        atomic_json(out/"results.json",{"model":cfg.model,"results":matrix,
            "scope":"Recompile/replay saved weak-model candidates against their frozen contracts using current task implementation. Not independent regeneration or vendor verification."})
        print("END "+item["name"]+" "+result["status"],flush=True)

if __name__=="__main__":main()
