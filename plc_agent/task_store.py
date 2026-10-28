"""Task plans and acceptance live outside the model-writable workspace."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import uuid
import zipfile

from .storage import atomic_json, identifier, now
from .task_spec import digest, render_plan, validate_spec
from .task_backend import capabilities, get_backend

class TaskStore:
    def __init__(self,session):
        self.session=session;self.project=session.project
        self.root=self.project.path/"tasks"

    def directory(self,task_id):
        return self.root/identifier(task_id)

    def create(self,spec,source_paths=()):
        spec=validate_spec(spec)
        task_id=uuid.uuid4().hex[:12];directory=self.directory(task_id)
        directory.mkdir(parents=True)
        atomic_json(directory/"contract.json",spec)
        (directory/"plan.md").write_text(render_plan(spec),encoding="utf-8")
        sources=[]
        if len(source_paths)>8:raise ValueError('Use at most eight requirement snapshots')
        for i,value in enumerate(source_paths):
            path=(self.project.workspace/value).resolve()
            if not path.is_relative_to(self.project.workspace) or not path.is_file() or path.stat().st_size>2000000:
                raise ValueError("Requirement source must be a project file <=2 MB")
            data=path.read_bytes()
            saved=directory/"sources"/f"source_{i+1:02d}{path.suffix}"
            saved.parent.mkdir(exist_ok=True);saved.write_bytes(data)
            sources.append({"path":path.relative_to(self.project.workspace).as_posix(),
                            "sha256":hashlib.sha256(data).hexdigest(),"snapshot":saved.relative_to(directory).as_posix()})
        atomic_json(directory/"sources.json",{"files":sources})
        self.session.data["task_plan"]={"id":task_id,"title":spec["title"],"contract_sha256":digest(spec),"accepted":False}
        self.session.data.pop('planned_question_id',None)
        self.session.data.pop('planned_task',None)
        self.session.save()
        return self.show(task_id)

    def load(self,task_id):
        return validate_spec(json.loads((self.directory(task_id)/"contract.json").read_text(encoding="utf-8")))

    def regressions(self,task_id):
        path=self.directory(task_id)/'regressions.json'
        if not path.exists():return {'contract_sha256':digest(self.load(task_id)),'cases':[],'origins':[]}
        value=json.loads(path.read_text(encoding='utf-8'));spec=self.load(task_id)
        return self.validate_regressions(value,spec)

    def validate_regressions(self,value,spec):
        from .task_spec import validate_case
        if value['contract_sha256']!=digest(spec):raise ValueError('Regression cases belong to a different contract')
        for case in value['cases']:
            validate_case(case,spec)
            if any(row.get('expect') for row in case['trace']):raise ValueError('Automatic regressions may use frozen properties only')
        if len(value['cases'])>64 or sum(len(c['trace']) for c in value['cases'])>10000:raise ValueError('Regression scan budget exceeded')
        return value

    def save_regressions(self,task_id,value):
        self.validate_regressions(value,self.load(task_id))
        atomic_json(self.directory(task_id)/'regressions.json',value)

    def read_evidence(self,task_id,filename,start_line=1,max_lines=120):
        import re
        if not re.fullmatch(r'(receipt|evaluation_\d+|review_\d+_(replay_[12]|contract|decision))\.json|formal_\d+/(formal\.json|[A-Za-z_0-9]+\.smt2|counterexample_replay_[12]\.json)',filename):
            raise ValueError('Choose a receipt, evaluation, review or formal evidence record')
        latest=json.loads((self.directory(task_id)/'latest.json').read_text(encoding='utf-8'))
        path=self.directory(task_id)/'runs'/identifier(latest['run_id'])/filename
        lines=path.read_text(encoding='utf-8').splitlines()
        excerpt='\n'.join(lines[start_line-1:start_line-1+max_lines])
        return {'task_id':task_id,'file':filename,'run_id':latest['run_id'],'total_lines':len(lines),
                'start_line':start_line,'content':excerpt[:18000],
                'truncated':len(excerpt)>18000 or start_line-1+max_lines<len(lines)}

    def review_context(self,task_id):
        receipt=self.latest(task_id)
        if receipt['status'] not in ('review_questions','review_disagreement') or not receipt.get('reviews'):
            raise ValueError('No current unresolved review; changed code/contract/backend needs fresh verification')
        review=receipt['reviews'][-1]
        binding=digest({'source':receipt['source_sha256'],'contract':receipt['contract_sha256'],
            'backend':receipt.get('execution_fingerprint'),'proposals':review['proposals'],'questions':review['questions']})
        return receipt,review,binding

    def reject_review_item(self,task_id,item,reason):
        if not isinstance(reason,str) or not 1<=len(reason.strip())<=2000:raise ValueError('A concrete rejection reason is required')
        receipt,review,binding=self.review_context(task_id)
        possible={f'Q{i+1}' for i in range(len(review['questions']))}
        possible|={f'F{i+1}' for i,f in enumerate(review['findings']) if f['verdict']=='requires_requirement_decision'}
        if item not in possible:raise ValueError('Choose Q1.. or a disputed F1..; frozen-property violations cannot be rejected')
        path=self.directory(task_id)/'review_decisions.json'
        values=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'decisions':[]}
        values['decisions']=[d for d in values['decisions'] if (d['binding'],d['item'])!=(binding,item)]
        values['decisions'].append({'binding':binding,'item':item,'decision':'reject','reason':reason.strip(),'actor':'user_command','time':now()})
        atomic_json(path,values)
        return {'status':'review_item_rejected','task_id':task_id,'item':item,'reason':reason,
                'next_action':'Run this task again to recompile and replay the exact reviewed code; no new review model request is needed.'}

    def review_override(self,task_id):
        path=self.directory(task_id)/'review_decisions.json'
        if not path.exists():return None
        try:receipt,review,binding=self.review_context(task_id)
        except (OSError,ValueError,KeyError):return None
        values=json.loads(path.read_text(encoding='utf-8'))
        decisions=[d for d in values['decisions'] if d['binding']==binding and d.get('actor')=='user_command']
        return {'review':review,'decisions':decisions,'binding':binding} if decisions else None

    def accepted(self,task_id,spec=None):
        spec=spec or self.load(task_id)
        path=self.directory(task_id)/"acceptance.json"
        if not path.exists():return False
        value=json.loads(path.read_text(encoding="utf-8"))
        return (value.get("contract_sha256")==digest(spec) and value.get("actor")=="user_command"
                and value.get('requirements_sha256')==self.requirements_identity(task_id))

    def requirements_identity(self,task_id):
        directory=self.directory(task_id)
        sources=json.loads((directory/'sources.json').read_text(encoding='utf-8'))
        for item in sources['files']:
            path=(directory/item['snapshot']).resolve()
            if not path.is_relative_to(directory.resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
                raise ValueError('Requirement snapshot missing or changed')
        return digest(sources)

    def formal_status(self,task_id):
        path=self.directory(task_id)/'formal_latest.json'
        if not path.exists():return {'status':'not_executed'}
        from .formal_verify import fingerprint,evidence_valid
        from .task_formal import summary
        value=json.loads(path.read_text(encoding='utf-8'));source=(self.project.workspace/value['source']).resolve()
        valid=(source.is_relative_to(self.project.workspace) and source.is_file()
               and hashlib.sha256(source.read_bytes()).hexdigest()==value['source_sha256']
               and digest(self.load(task_id))==value['contract_sha256'] and fingerprint()==value.get('formal_fingerprint')
               and self.accepted(task_id) and evidence_valid(value,self.directory(task_id)/'formal_runs'))
        return summary(value) if valid else {**summary(value),'status':'stale_evidence','previous_status':value['status']}

    def accept(self,task_id):
        """Human command surface only. No model tool can invoke this operation."""
        spec=self.load(task_id)
        if spec["questions"]:raise ValueError("Resolve questions in a new task plan before accepting the contract")
        atomic_json(self.directory(task_id)/"acceptance.json",{
            "actor":"user_command","time":now(),"contract_sha256":digest(spec),
            "requirements_sha256":self.requirements_identity(task_id),
            "assumptions_accepted":spec["assumptions"]})
        self.session.data["task_plan"]={"id":task_id,"title":spec["title"],"contract_sha256":digest(spec),"accepted":True}
        self.session.save()
        return {"status":"contract_accepted","task_id":task_id,"contract_sha256":digest(spec)}

    def show(self,task_id,start_line=1,max_lines=120):
        spec=self.load(task_id);directory=self.directory(task_id)
        raw=json.dumps(spec,ensure_ascii=False,indent=2).splitlines()
        excerpt='\n'.join(raw[start_line-1:start_line-1+max_lines])
        return {"status":"task_plan","task_id":task_id,"title":spec["title"],"contract_sha256":digest(spec),
                "accepted":self.accepted(task_id,spec),"questions":spec["questions"],
                "capabilities":capabilities(spec),"plan":render_plan(spec)[:16000],
                "contract":{"start_line":start_line,"total_lines":len(raw),
                    "content":excerpt[:18000],
                    "truncated":len(excerpt)>18000 or start_line-1+max_lines<len(raw)},
                "plan_path":str(directory/"plan.md"),
                "next_action":f"/task accept {task_id} (review full plan/contract first), then /act and /task run {task_id}"}

    def latest(self,task_id):
        path=self.directory(task_id)/"latest.json"
        if not path.exists():return {"status":"not_run","task_id":task_id}
        receipt=json.loads(path.read_text(encoding="utf-8"));reasons=[]
        source=(self.project.workspace/receipt["source"]).resolve()
        if not source.is_relative_to(self.project.workspace):raise ValueError("Invalid receipt source")
        if not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest()!=receipt.get("source_sha256"):reasons.append("source_changed")
        if digest(self.load(task_id))!=receipt.get("contract_sha256"):reasons.append("contract_changed")
        formal=receipt.get('formal_verification')
        if isinstance(formal,dict):
            from .formal_verify import fingerprint,evidence_valid
            if (formal.get('formal_fingerprint')!=fingerprint() or formal.get('source_sha256')!=receipt['source_sha256']
                or formal.get('contract_sha256')!=receipt['contract_sha256'] or not evidence_valid(formal,self.directory(task_id)/'runs')):
                reasons.append('formal_evidence_changed')
        evaluation=receipt.get('final_evaluation') or {}
        if evaluation.get('vendor_evidence_files'):
            from .codesys import work_root
            vendor=Path(evaluation['vendor_evidence']).resolve()
            try:
                if not vendor.is_relative_to(work_root().resolve()):raise ValueError('Invalid vendor evidence root')
                for name,sha in evaluation['vendor_evidence_files'].items():
                    p=(vendor/name).resolve()
                    if not p.is_relative_to(vendor) or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise ValueError('Vendor evidence changed')
            except (ValueError,OSError):reasons.append('vendor_evidence_changed')
        try:
            if digest(self.regressions(task_id))!=receipt.get('regression_sha256'):reasons.append('regression_cases_changed')
        except (ValueError,OSError,KeyError):reasons.append('regression_cases_changed')
        try:
            fingerprint=get_backend(self.load(task_id)).fingerprint()
            if receipt.get("execution_fingerprint") and receipt["execution_fingerprint"]!=fingerprint:reasons.append("backend_or_evaluator_changed")
        except ValueError:reasons.append('execution_adapter_unavailable')
        try:
            if not self.accepted(task_id):reasons.append("contract_not_confirmed")
            if receipt.get('requirements_sha256')!=self.requirements_identity(task_id):reasons.append('requirements_changed')
        except (OSError,ValueError,KeyError):reasons.append('requirements_changed')
        if reasons:return {**receipt,"previous_status":receipt["status"],"status":"stale_evidence","stale_reasons":reasons}
        return receipt

    def export(self,task_id):
        """Export the exact evaluated snapshot, never whatever is currently at candidate.st."""
        directory=self.directory(task_id);receipt=self.latest(task_id)
        if "run_id" not in receipt:raise ValueError("No completed task attempt to export")
        run=directory/"runs"/identifier(receipt["run_id"])
        final=run/"candidate_final.st"
        if not final.exists() or hashlib.sha256(final.read_bytes()).hexdigest()!=receipt["source_sha256"]:
            raise ValueError("Evaluated source snapshot is missing or corrupted")
        files={"candidate.st":final.read_bytes(),"contract.json":(run/"contract.json").read_bytes(),
               "receipt.json":(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n").encode(),
               "README.md":self.delivery_readme(receipt).encode()}
        if (run/'regressions.json').exists():files['regressions.json']=(run/'regressions.json').read_bytes()
        for path in sorted(run.glob("*.json")):
            if path.name.startswith(("evaluation_","review_")):
                files["evidence/"+path.name]=path.read_bytes()
        for path in sorted(run.glob('formal_*/*')):
            if path.is_file() and path.suffix in ('.json','.smt2'):
                files['evidence/'+path.relative_to(run).as_posix()]=path.read_bytes()
        evaluation=receipt.get('final_evaluation') or {}
        if evaluation.get('vendor_evidence_files'):
            from .codesys import work_root
            vendor=Path(evaluation['vendor_evidence']).resolve()
            if not vendor.is_relative_to(work_root().resolve()):raise ValueError('Invalid vendor evidence root')
            for name,sha in evaluation['vendor_evidence_files'].items():
                p=(vendor/name).resolve()
                if not p.is_relative_to(vendor) or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise ValueError('Vendor evidence changed')
                files['evidence/codesys/'+name]=p.read_bytes()
        # Exact requirement snapshots from the task are included; credentials and sessions are not.
        for path in sorted((directory/"sources").glob("*")):
            files["requirements/"+path.name]=path.read_bytes()
        files["manifest.json"]=(json.dumps({name:hashlib.sha256(data).hexdigest() for name,data in files.items()},indent=2)+"\n").encode()
        out=self.project.workspace/"deliverables"/(task_id+"_"+receipt["run_id"]+".zip")
        out.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as archive:
            for name,data in files.items():archive.writestr(name,data)
        return {"status":"exported","task_id":task_id,"result_status":receipt["status"],
                "path":str(out),"sha256":hashlib.sha256(out.read_bytes()).hexdigest(),"files":len(files)}

    @staticmethod
    def delivery_readme(receipt):
        formal=receipt.get('formal_verification','not_executed')
        formal_status=formal.get('status','unknown') if isinstance(formal,dict) else formal
        return (f"# PLC 任务交付\n\n任务：{receipt['task_id']}\n\n状态：{receipt['status']}\n\n"
                f"源码 SHA256：{receipt['source_sha256']}\n\n约定 SHA256：{receipt['contract_sha256']}\n\n"
                "candidate.st 是本次记录对应的源码快照。contract.json 给出需求、接口、扫描轨迹和检查规则。\n\n"
                "evidence/ 保存基线执行及独立审查证据；manifest.json 给出归档文件校验值。\n\n"
                f"执行后端：{receipt.get('executor','offline')}。目标平台编译：{receipt.get('target_compile','not_executed')}。\n"
                f"形式化检查：{formal_status}。详见 evidence/ 中的形式化报告和 SMT 查询。\n"
                "证明仅覆盖报告中列出的性质及语义假设。实体 PLC 未执行；本地 STruC++ 结果不能代替目标厂商的编译记录。\n"
                "若状态包含 pending、stale、blocked、disagreement 或 error，应先处理记录中的问题，不能据此声明完成。\n")
