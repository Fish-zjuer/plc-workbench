"""Fresh adversarial hypotheses for repaired sources; execute, do not self-certify."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
import math

from plc_probe.backend import compile_source,run_batch
from .bank_contracts import questions,interface
from .benchmark import Budget,MeteredProvider
from .config import ModelConfig
from .provider import json_value
from .storage import atomic_json
from .workflow_holdout import execute
from .workflow_benchmark import R2


def review_one(qid,config,budget):
    directory=R2/'tasks'/qid
    question=next(q for q in questions() if q['id']==qid)
    source=directory/'final.st';digest=hashlib.sha256(source.read_bytes()).hexdigest()
    packet={'requirements':question['text'],'candidate':source.read_text(encoding='utf-8'),'source_sha256':digest}
    provider=MeteredProvider(config,budget)
    prompt='''你是独立PLC/ST对抗审查者，仅有题面和候选源码，没有作者历史或测试结果。不要凑漏洞；可以返回空列表。
只输出JSON对象 {"findings":[...]}，最多2条。每条格式 {"id":"REV-01","title":"...","basis":"题面明确依据或歧义说明","scope":"specified或ambiguous","trace":[{"time_ms":0,"inputs":{"全部输入字段":0},"expected":{"要验证的输出":0}}]}。
每条序列最多20次调用，时间为严格递增非负整数毫秒；TIME输入用正整数毫秒，BOOL用0或1，其他输入按题面类型。每条trace至少一个expected字段。ipText仅可打印ASCII。
trace每行必须给齐全部输入，expected可只给相关输出。一次trace从全新FB开始，输出在每次调用后观察。你不执行程序，期望只是待核对假设。不要给代码修改指令。'''
    answer=provider.complete([{'role':'system','content':prompt},{'role':'user','content':json.dumps(packet,ensure_ascii=False)}])
    value=json_value(answer['text'])
    if not isinstance(value,dict) or not isinstance(value.get('findings'),list) or len(value['findings'])>2:
        raise ValueError('Review envelope invalid')
    inputs,outputs=interface(question);findings=[]
    for finding in value['findings']:
        record={'proposal':finding,'status':'invalid_proposal'}
        try:
            if finding['scope'] not in ('specified','ambiguous') or not finding.get('basis'):
                raise ValueError('Missing scope or requirement basis')
            trace=finding['trace']
            if not isinstance(trace,list) or not 1<=len(trace)<=20 or not any(row.get('expected') for row in trace):
                raise ValueError('Need 1..20 rows and an assertion')
            last=-1
            for row in trace:
                if type(row['time_ms']) is not int or not last<row['time_ms']<=2_000_000_000:
                    raise ValueError('Invalid time')
                last=row['time_ms']
                if set(row['inputs'])!=set(inputs) or set(row.get('expected',{}))-set(outputs):
                    raise ValueError('Invalid input/output fields')
                for name,kind in inputs.items():
                    v=row['inputs'][name]
                    if kind.startswith('STRING'):
                        valid=isinstance(v,str) and len(v)<=254 and all(32<=ord(c)<=126 for c in v)
                    else:
                        valid=type(v) in (int,float,bool) and math.isfinite(v)
                        if kind=='BOOL':valid=valid and v in (0,1)
                        if kind=='TIME':valid=valid and type(v) is int and 0<v<=2147483647
                        if kind=='INT':valid=valid and type(v) is int and -32768<=v<=32767
                    if not valid:raise ValueError('Input outside supported domain')
                if any(type(v) not in (int,float,bool) or not math.isfinite(v) for v in row.get('expected',{}).values()):
                    raise ValueError('Invalid expected numeric output')
            normalized=[{'time_ms':r['time_ms'],'inputs':r['inputs'],'expected':r.get('expected',{})} for r in trace]
            if qid=='14':
                runs=[run_batch(compile_source(source,'ipv4'),[{'name':finding['id'],'trace':[{'time_ms':r['time_ms'],'inputs':r['inputs']} for r in normalized]}])[0] for _ in range(2)]
            else:
                runs=[execute(source,qid,[{'name':finding['id'],'trace':normalized}])['cases'][0] for _ in range(2)]
            mismatches=[]
            for run in runs:
                mismatches.append([{'scan':i,'output':k,'expected':v,'actual':run['rows'][i]['actual'][k]}
                                   for i,row in enumerate(normalized) for k,v in row['expected'].items()
                                   if not math.isclose(run['rows'][i]['actual'][k],v,rel_tol=1e-5,abs_tol=1e-5)])
            record.update(status='needs_requirement_clarification' if finding['scope']=='ambiguous' else
                          'reproduced_pending_adjudication' if all(mismatches) else 'not_reproduced',
                          mismatches=mismatches,runs=runs)
        except (ValueError,KeyError,TypeError) as exc:
            record['message']=str(exc)
        findings.append(record)
    result={'question_id':qid,'source_sha256':digest,'reviewer_model':config.model,'findings':findings,
            'requests':provider.metrics,'scope':'Fresh review without tests or author history. Mismatch is not a confirmed requirement violation; separate adjudication required.'}
    atomic_json(directory/'independent_review.json',result)
    return result


def main():
    cfg=replace(ModelConfig.load(),max_output_tokens=4096,timeout=90)
    budget=Budget(.8)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda q:review_one(q,cfg,budget),['05','10','14','15']))
    atomic_json(R2/'independent_reviews.json',{'results':results})
    print(json.dumps({r['question_id']:[f['status'] for f in r['findings']] for r in results},ensure_ascii=False))


if __name__=='__main__':main()
