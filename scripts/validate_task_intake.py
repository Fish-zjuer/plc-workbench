"""Real-service file upload -> natural-language planning -> accepted task -> execution trial."""
from dataclasses import replace
import argparse
import json
from pathlib import Path
import sys
from plc_agent.attachments import attach
from plc_agent.config import ModelConfig,ROOT,STATE_ROOT
from plc_agent.engine import Engine
from plc_agent.provider import ChatProvider
from plc_agent.storage import Project,Session,atomic_json
from plc_agent.task_store import TaskStore
from plc_agent.task_runner import evaluate_task

REQUIREMENTS="""Build FUNCTION_BLOCK FanHysteresis.
VAR_INPUT temperature: REAL; enabled: BOOL; VAR_OUTPUT fan: BOOL.
fan is initially FALSE. On each scan enabled=FALSE forces fan=FALSE.
When enabled=TRUE, temperature>=30.0 sets fan=TRUE, temperature<=25.0 sets fan=FALSE.
Strictly between 25.0 and 30.0 retain the previous fan state.
After disabling and enabling again in this intermediate band, fan stays FALSE until temperature reaches 30.0.
The temperature input is a finite REAL value. No timing, hardware or safety-rated function is required.
"""

def main():
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    cfg=replace(ModelConfig.load(),max_steps=16,timeout=90)
    parser=argparse.ArgumentParser();parser.add_argument('--resume-project');args=parser.parse_args()
    project=Project.load(args.resume_project) if args.resume_project else Project.create("R6 natural language intake",STATE_ROOT,kind="benchmark")
    session=Session.load(project,project.data['last_session']) if args.resume_project else Session.create(project,cfg.model)
    provider=ChatProvider(cfg)
    out=ROOT/"experiments/general_tasks_r6/intake";out.mkdir(parents=True,exist_ok=True)
    req=out/"requirements.txt";req.write_text(REQUIREMENTS,encoding="utf-8")
    if not args.resume_project:attach(project,req)
    engine=Engine(session,cfg,provider,notify=lambda k,p:print(k+": "+str(p.get("text",p.get("name","")))[:220],flush=True) if k!="delta" else None)
    if not session.data.get('task_plan'):
        engine.run("继续读取上传的requirements.txt，这是题库之外的新PLC需求。在计划模式调用plc_task_schema和plc_task_plan，保留附件原定的接口，规划可执行扫描测试并保存通用任务。target选portable。合约必须有schema=plc-task-v1；采样由运行器固定，合约不要额外增加sampling字段。现在不要生成或执行ST。")
    if not session.data.get("task_plan"):raise RuntimeError("Natural-language intake did not create a task plan")
    task_id=session.data["task_plan"]["id"];store=TaskStore(session);spec=store.load(task_id)
    if spec["block"]!="FanHysteresis" or spec["inputs"]!={"temperature":"REAL","enabled":"BOOL"} or spec["outputs"]!={"fan":"BOOL"}:
        raise RuntimeError("Planner changed the explicitly supplied interface")
    if list(project.workspace.rglob("*.st")):raise RuntimeError("Planning unexpectedly created ST")
    # The fixture requirements above are developer-specified; acceptance is a human command surface.
    store.accept(task_id);session.data["mode"]="execute";session.save()
    engine.run("我已确认通用任务 "+task_id+" 的需求和测试约定。现在请通过plc_task_run完整实现并验证该任务，按实际工具结论说明结果。")
    receipt=store.latest(task_id)
    if receipt["status"]!="offline_pass_target_pending":raise RuntimeError("Task did not reach the expected finite-check stage: "+receipt["status"])
    # Fixed holdout inputs/expected outputs were not included in either author or reviewer requests.
    pairs=[(-10,True,False),(29.9,True,False),(30,True,True),(27,True,True),
           (25.1,True,True),(25,True,False),(26,True,False),(30.1,False,False),
           (27,True,False),(30,True,True),(26,False,False),(29,True,False)]
    case={"name":"withheld_threshold_and_reenable","covers":[r["id"] for r in spec["requirements"]],
          "trace":[{"time_ms":i*10,"inputs":{"temperature":float(t),"enabled":e},"expect":{"fan":f}} for i,(t,e,f) in enumerate(pairs)]}
    holdout=spec.copy();holdout["scenarios"]=[case]
    result,_=evaluate_task(project.workspace/receipt["source"],holdout)
    def clean(v):
        if isinstance(v,str):
            v=v.replace(str(project.path),"<local_project>").replace(str(STATE_ROOT),"<private_state>")
            if cfg.api_key:v=v.replace(cfg.api_key,"[redacted]")
            return v
        if isinstance(v,list):return [clean(x) for x in v]
        if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
        return v
    atomic_json(out/"planned_contract.json",spec)
    atomic_json(out/"receipt.json",clean(receipt))
    atomic_json(out/"holdout.json",clean(result))
    atomic_json(out/"conversation.json",clean(engine.messages))
    (out/"candidate_final.st").write_bytes((project.workspace/receipt["source"]).read_bytes())
    summary={"status":receipt["status"],"holdout_status":result["status"],"holdout_scans":len(pairs),
             "model":cfg.model,"model_requests":len(provider.metrics),"planning_created_code":False,
             "private_project_id":project.data["id"],"task_id":task_id}
    atomic_json(out/"result.json",summary)
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=="__main__":main()
