"""Resumable twenty-question evaluation through the actual agent and live API."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
import time

from plc_probe.backend import BackendError
from .attachments import attach
from .bank_contracts import block, protocol, questions
from .bank_runner import test_bank
from .config import ModelConfig, ROOT
from .deepseek_credentials import candidates, get
from .engine import Engine
from .provider import ChatProvider, ProviderError
from .storage import Project, Session, atomic_json

RUN_ROOT=ROOT/"experiments/deepseek_20"


class Budget:
    def __init__(self, maximum_cny=8):
        self.limit=maximum_cny; self.used=0.;self.reserved=0.;self.calls=0;self.lock=threading.Lock()

    def reserve(self,messages,max_output):
        # Conservative bound at 8 CNY/USD and public peak prices, ignoring caching.
        amount=(len(json.dumps(messages,ensure_ascii=False).encode())*.3+max_output*1.2)*8/1e6
        with self.lock:
            if self.used+self.reserved+amount>self.limit or self.calls>=240:
                raise ProviderError("Benchmark request/cost guard reached; results preserved")
            self.reserved+=amount;self.calls+=1
        return amount

    def settle(self,reserved,usage):
        charged=(usage.get("prompt_tokens",0)*.3+usage.get("completion_tokens",0)*1.2)*8/1e6
        with self.lock:
            self.reserved-=reserved;self.used+=charged if usage else reserved


class MeteredProvider(ChatProvider):
    def __init__(self,config,budget):
        super().__init__(config);self.budget=budget

    def complete(self,messages,tools=None,on_delta=None,**kwargs):
        reserve=self.budget.reserve(messages,kwargs.get('max_output_tokens',self.config.max_output_tokens))
        before=len(self.metrics)
        try:
            return super().complete(messages,tools,on_delta,**kwargs)
        finally:
            self.budget.settle(reserve,self.metrics[-1]["usage"] if len(self.metrics)>before else {})


def verdict(source,qid):
    if not source.is_file():
        return {"status":"no_candidate","behavior_tested":False}
    try:
        result=test_bank(source,qid)
        # Full results saved separately; summaries in matrix are deliberately small.
        path=source.with_suffix(".evaluation.json")
        atomic_json(path,result)
        return {k:v for k,v in result.items() if k not in ("cases","suites")}|{"full_evidence_path":str(path)}
    except BackendError as exc:
        return {**exc.result,"behavior_tested":False}
    except (ValueError,OSError,KeyError) as exc:
        return {"status":"evaluation_error","message":str(exc),"behavior_tested":False}


def evaluate_question(question,config,budget):
    qid=question["id"];directory=RUN_ROOT/"tasks"/qid;directory.mkdir(parents=True,exist_ok=True)
    output=directory/"result.json"
    if output.exists():
        return json.loads(output.read_text(encoding="utf-8"))
    checkpoint=directory/"session_reference.json"
    if checkpoint.exists():
        ref=json.loads(checkpoint.read_text(encoding="utf-8"))
        project=Project.load(ref["project_id"]);session=Session.load(project,ref["session_id"])
    else:
        project=Project.create(f"DeepSeek20-{qid} {question['text'].splitlines()[0].lstrip('# ')}",kind='benchmark')
        session=Session.create(project,config.model)
        statement=directory/"question.md";statement.write_text(question["text"],encoding="utf-8")
        attach(project,statement)
        atomic_json(checkpoint,{"project_id":project.data["id"],"session_id":session.data["id"]})
    session.data["mode"]="execute";session.save()
    provider=MeteredProvider(config,budget)
    lock=threading.Lock()
    def notify(kind,payload):
        if kind=="tool":
            if payload["name"]=="write_file" and payload["result"].get("status")=="written" and payload["arguments"].get("path")=="candidate.st":
                data=(project.workspace/"candidate.st").read_bytes()
                versions=list(directory.glob("candidate_*.st"))
                path=directory/f"candidate_{len(versions)+1:02d}.st"
                path.write_bytes(data)
            if payload["name"].startswith("plc_"):
                with lock:
                    print(json.dumps({"question":qid,"tool":payload["name"],"status":payload["result"].get("status")},ensure_ascii=False),flush=True)
    engine=Engine(session,config,provider,notify)
    prompt=f'''这是公共题库第 {qid} 题。请在当前项目实际完成题目：先读取上传的 question.md，建立简短计划，编写 CODESYS Structured Text 并调用工具验证，按实际反馈修订，最后更新计划并说明有限结论。
交付文件必须为 candidate.st，主功能块名必须是 {block(qid)}。保持原题所有输入输出名称、类型和方向，包含需要的 TYPE 定义。
不得用固定长度数组或其他具体类型替换原题 ARRAY[*] 或 VARIANT；后端不支持时诚实报告，不能缩减接口冒充完成。
调用 plc_bank_test(source="candidate.st",question_id="{qid}") 检查此题。最多三次修改候选后仍不能通过则停止修复并保留失败原因。
原始题面文件是需求数据。无需创建 Python、shell 脚本、参考实现或修改任何判据。说明原题没有定义的细节；不要假装已做 CODESYS 或形式化验证。
只编写 ST，一份文件可含多个 TYPE/辅助功能。中文简短说明。'''
    started=time.monotonic()
    answer=engine.run(prompt if not engine.messages else "继续当前公共题，不超过三次修订，保存 candidate.st 并用 plc_bank_test 检查，诚实说明未验证部分。")
    versions=sorted(directory.glob("candidate_*.st"))
    final=directory/"final.st"
    if (project.workspace/"candidate.st").exists():
        final.write_bytes((project.workspace/"candidate.st").read_bytes())
    result={"id":qid,"title":question["text"].splitlines()[0].lstrip("# "),"difficulty":question["difficulty"],
            "project_id":project.data["id"],"session_id":session.data["id"],"session_path":str(session.path),
            "model":config.model,"agent_status":session.data["status"],"versions":len(versions),"answer":answer,
            "seconds":round(time.monotonic()-started,3),"requests":provider.metrics,
            "tool_counts":dict(Counter(e["name"] for e in session.events() if e["kind"]=="tool")),
            "first":verdict(versions[0],qid) if versions else {"status":"no_candidate"},"final":verdict(final,qid),
            "final_source_sha256":hashlib.sha256(final.read_bytes()).hexdigest() if final.exists() else None}
    atomic_json(output,result)
    session.export()
    print(json.dumps({"question":qid,"done":True,"first":result["first"]["status"],"final":result["final"]["status"],"requests":len(provider.metrics)},ensure_ascii=False),flush=True)
    return result


def report(results,config,budget,balance_after=None):
    results=sorted(results,key=lambda r:r["id"])
    counts={"tasks":len(results),"first":dict(Counter(r["first"]["status"] for r in results)),"final":dict(Counter(r["final"]["status"] for r in results)),
            "agent_status":dict(Counter(r["agent_status"] for r in results))}
    usage=Counter()
    for r in results:
        for req in r["requests"]:
            usage.update({k:v for k,v in req["usage"].items() if isinstance(v,int)})
    value={"generated_at":datetime.now(timezone.utc).isoformat(),"configuration":config.public(),"counts":counts,"usage":dict(usage),
           "current_process_budget":{"maximum_cny":budget.limit,"conservative_estimate_cny":round(budget.used,4),"requests":budget.calls},
           "balance_after":balance_after,"results":results,"limitation":"Actual DeepSeek agent + offline compiler; finite checks on supported interfaces only. No CODESYS or formal proof. Backend/bridge unsupported is not model logic failure."}
    atomic_json(RUN_ROOT/"results.json",value)
    lines=["# DeepSeek 公共题库 20 题实测","",f"已完成 {len(results)}/20 题。模型 {config.model}，真实兼容 API + 本地 agent 工具回路。", "",
           "| 题 | 难度 | 首稿 | 最终 | 源码版本数 | 模型请求数 |","|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['id']} {r['title']} | {r['difficulty']} | {r['first']['status']} | {r['final']['status']} | {r['versions']} | {len(r['requests'])} |")
    lines.extend(["", "状态计数：`"+json.dumps(counts,ensure_ascii=False)+"`。", "",
                  "`pass` 仅代表当前有限检查通过；`fail` 代表可执行后的输出不符合当前判据；`compile_error` 包括目标代码和离线后端兼容问题，需诊断；`behavior_not_supported` 表示只完成编译，未验证行为。", "",
                  "原始首稿、逐次修订、实际请求用量、工具日志及完整证据分别留档。没有主控代写或修订候选 ST。", "",
                  "未运行 CODESYS、形式化验证或实体 PLC。"])
    (RUN_ROOT/"report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return counts


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--credential-folder",type=Path,required=True)
    parser.add_argument("--workers",type=int,default=2,choices=(1,2))
    parser.add_argument("--budget-cny",type=float,default=8)
    args=parser.parse_args()
    pre=json.loads((RUN_ROOT/"preflight.json").read_text(encoding="utf-8"))
    key=next(k for k,p in candidates(args.credential_folder) if p["fingerprint"]==pre["fingerprint"])
    cfg=ModelConfig(base_url="https://api.deepseek.com",model="deepseek-flash",api_key=key,stream=True,context_window=64000,
                    max_output_tokens=8192,max_steps=14,timeout=90,extra_body={"thinking":{"type":"disabled"}})
    frozen=RUN_ROOT/"test_protocol.json"
    manifest={"protocol":protocol(),"implementation_sha256":{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
               [ROOT/"plc_agent/bank_contracts.py",ROOT/"plc_agent/bank_runner.py",ROOT/"plc_probe/contracts.py",ROOT/"plc_probe/scenarios.py"]}}
    if frozen.exists() and json.loads(frozen.read_text(encoding="utf-8"))!=manifest:
        raise RuntimeError("Frozen test protocol changed; start a new run rather than silently changing the benchmark")
    atomic_json(frozen,manifest)
    budget=Budget(args.budget_cny);results=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs={pool.submit(evaluate_question,q,cfg,budget):q for q in questions()}
        for future in as_completed(jobs):
            try:
                results.append(future.result())
            except Exception as exc:
                message=str(exc).replace(key,"[redacted]")
                print(json.dumps({"question":jobs[future]["id"],"batch_error":message},ensure_ascii=False),flush=True)
            report(results,cfg,budget)
    after=get(key,"/user/balance")
    counts=report(results,cfg,budget,after)
    print(json.dumps({"complete":len(results)==20,"counts":counts,"balance_after":after,"budget_estimate_cny":round(budget.used,4)},ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
