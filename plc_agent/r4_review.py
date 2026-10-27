"""Fresh-context adversarial proposals, validated and independently executed twice."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
import math
from unittest.mock import patch

from .bank_contracts import questions,interface
from .benchmark import Budget,MeteredProvider
from .config import ModelConfig
from .provider import json_value
from .reference_checks import test_references
from .r4_benchmark import OUT
from .storage import atomic_json
from .workflow_holdout import execute


def review_one(qid,cfg,budget):
    directory=OUT/'tasks'/qid;source=directory/'final.st'
    question=next(q for q in questions() if q['id']==qid)
    packet={'question_id':qid,'requirements':question['text'],'candidate':source.read_text(encoding='utf-8'),
            'sampling':'Outputs after invocation; fresh instance per trace; time_ms and TIME arguments in milliseconds.',
            'time_conversions':'R4 uses signed int64 nanoseconds internally; TIME_TO_LINT returns milliseconds; LTIME_TO_LINT returns nanoseconds. TON resets when IN is false and elapsed=0 at first eligible invocation; repeated invocation within a scan sees the same clock.',
            'local_variant_primitives':'PV_COUNT=actual capacity; PV_READ/WRITE transfer one element by zero-based ordinal; return BOOL, do not implement queue; PV_COMPATIBLE checks bound types.'}
    prompt='''你是独立对抗审查者。只看到题面、候选和后端语义，没有作者对话、测试结果或原测试输入。不要求凑漏洞。
只返回JSON {"findings":[...]}，最多2项，每项id,title,basis,scope(specified或ambiguous)。
04/12另提供trace，1..20次调用，时间time_ms严格递增非负整数；每行inputs给齐所有输入，TIME为正整数毫秒；expected写待验证输出，数值有限。
18另提供element_type(dint/real/bool/record)、capacity(1..8)、steps(1..30行，每行enqueue/dequeue/reset为0或1，item为数字或record时为[整数,浮点])。enqueue/dequeue不能同时为1，不提供期望计数，宿主独立判定FIFO实际元素值。
08另提供analog_lower、channel_lower以及steps(1..15行，每行count、raw整数数组、channels二维数组，通道字段依次为enable,hiLIM,loLIM,bipolar,measuringMode,retVal,outputValue)，长度1..8且每行相同；count在0..较小长度；不提供期望，宿主独立按题意判定。非温度有效原始值按单/双极范围。
题面未明确的初始调用行为、保持延长、溢出等用ambiguous，不能伪装明确规定。无漏洞可返回空数组。'''
    examples={
      '04':{'id':'ADV-1','title':'...','basis':'...','scope':'specified','trace':[{'time_ms':0,'inputs':{'VISCOSITY_OK':1,'PASTE_E_STOP_NC':1,'DebounceTime':100,'CycleTime':10},'expected':{'VFD_RUN':0}}]},
      '12':{'id':'ADV-1','title':'...','basis':'...','scope':'specified','trace':[{'time_ms':0,'inputs':{'THICKNESS_FAULT':0,'THICKNESS_SIGNAL_VALID':1,'CUTTING_RUN':1,'FaultTimestamp':0,'CycleTime':10},'expected':{'THICKNESS_ALARM':0}}]},
      '08':{'id':'ADV-1','title':'...','basis':'...','scope':'specified','analog_lower':-2,'channel_lower':7,'steps':[{'count':1,'raw':[1000],'channels':[[1,100,0,0,0,0,0]]}]},
      '18':{'id':'ADV-1','title':'...','basis':'...','scope':'specified','element_type':'dint','capacity':2,'steps':[{'enqueue':1,'dequeue':0,'reset':0,'item':17}]}}
    prompt+='\n本次仅审查第'+qid+'题。每条必须包含该题可执行数据字段，连ambiguous也不能省略。无法给合法序列就删除该项，返回空数组也可以。结构示例只用于字段说明，不是需要重复的反例：'+json.dumps(examples[qid],ensure_ascii=False)
    provider=MeteredProvider(cfg,budget)
    answer=provider.complete([{'role':'system','content':prompt},{'role':'user','content':json.dumps(packet,ensure_ascii=False)}])
    atomic_json(directory/'review_raw.json',{'text':answer['text'],'requests':provider.metrics})
    value=json_value(answer['text']);findings=[]
    if not isinstance(value,dict) or not isinstance(value.get('findings'),list) or len(value['findings'])>2:raise ValueError('Invalid review envelope')
    for proposal in value['findings']:
        record={'proposal':proposal,'status':'invalid_proposal'}
        try:
            if proposal['scope'] not in ('specified','ambiguous') or not isinstance(proposal['basis'],str):raise ValueError('Missing requirement basis/scope')
            if qid in ('04','12'):
                inputs,outputs=interface(question);last=-1;trace=proposal['trace']
                if not isinstance(trace,list) or not 1<=len(trace)<=20:raise ValueError('Bad trace length')
                for row in trace:
                    if type(row['time_ms']) is not int or not last<row['time_ms']<=10000000000:raise ValueError('Invalid clock')
                    last=row['time_ms']
                    if set(row['inputs'])!=set(inputs) or set(row.get('expected',{}))-set(outputs):raise ValueError('Invalid fields')
                    for name,kind in inputs.items():
                        v=row['inputs'][name]
                        if type(v) not in (bool,int,float) or not math.isfinite(v):raise ValueError('Invalid scalar')
                        if kind=='BOOL' and v not in (0,1):raise ValueError('BOOL outside domain')
                        if kind=='TIME' and (type(v) is not int or not 0<v<=4294967295):raise ValueError('TIME outside domain')
                    if any(type(v) not in (bool,int,float) or not math.isfinite(v) for v in row.get('expected',{}).values()):raise ValueError('Bad assertion')
                if not any(r.get('expected') for r in trace):raise ValueError('No assertions')
                trace=[{**r,'expected':r.get('expected',{})} for r in trace]
                runs=[execute(source,qid,[{'name':proposal['id'],'trace':trace}]) for _ in range(2)]
                failed=all(run['status']=='fail' for run in runs)
            elif qid=='18':
                kind=proposal['element_type'];cap=proposal['capacity'];steps=proposal['steps']
                if kind not in ('dint','real','bool','record') or type(cap) is not int or not 1<=cap<=8 or not 1<=len(steps)<=30:raise ValueError('Invalid FIFO domain')
                for row in steps:
                    if any(type(row[k]) is not int or row[k] not in (0,1) for k in ('enqueue','dequeue','reset')) or row['enqueue'] and row['dequeue']:raise ValueError('Bad requests')
                    values=row['item'] if kind=='record' else [row['item']]
                    if not isinstance(values,list) or len(values)!=(2 if kind=='record' else 1) or any(type(v) not in (int,float) or not math.isfinite(v) for v in values):raise ValueError('Invalid item')
                    if kind=='bool' and row['item'] not in (0,1):raise ValueError('BOOL outside domain')
                    if kind=='dint' and (type(row['item']) is not int or not -2147483648<=row['item']<=2147483647):raise ValueError('DINT outside domain')
                tests=[{'name':proposal['id'],'kind':kind,'capacity':cap,'rows':steps}]
                with patch('plc_agent.reference_checks.fifo_cases',return_value=tests):runs=[test_references(source,qid) for _ in range(2)]
                failed=all(run['status']=='fail' for run in runs)
            else:
                steps=proposal['steps'];alo=proposal['analog_lower'];clo=proposal['channel_lower']
                if type(alo) is not int or type(clo) is not int or abs(alo)>1000 or abs(clo)>1000 or not 1<=len(steps)<=15:raise ValueError('Bad analog bounds')
                alen=len(steps[0]['raw']);clen=len(steps[0]['channels'])
                if not 1<=alen<=8 or not 1<=clen<=8:raise ValueError('Bad analog length')
                rows=[]
                for row in steps:
                    if len(row['raw'])!=alen or len(row['channels'])!=clen or type(row['count']) is not int or not 0<=row['count']<=min(alen,clen):raise ValueError('Bad count/length')
                    if any(type(v) is not int or not -32768<=v<=32767 for v in row['raw']):raise ValueError('Bad raw INT')
                    expected=[]
                    for i,channel in enumerate(row['channels']):
                        if len(channel)!=7 or any(type(v) not in (int,float) or not math.isfinite(v) for v in channel):raise ValueError('Bad channel')
                        en,hi,lo,bi,mode,ret,out=channel
                        if en not in (0,1) or bi not in (0,1):raise ValueError('Bad BOOL')
                        result=list(channel)
                        if i<row['count'] and en:
                            if mode not in (0,1,2):result[5]=0x8001
                            elif hi<=lo:result[5]=0x8002
                            else:
                                raw=row['raw'][i]
                                if mode==0 and not (-27648<=raw<=27648 if bi else 0<=raw<=27648):raise ValueError('Raw outside valid scaling domain')
                                result[5]=0;result[6]=(lo+(hi-lo)*(raw+27648)/55296 if bi else lo+(hi-lo)*raw/27648) if mode==0 else raw/10 if mode==1 else raw/100
                        expected.append(result)
                    rows.append({**row,'expected':expected})
                tests=[{'name':proposal['id'],'analog_length':alen,'analog_lower':alo,'channel_length':clen,'channel_lower':clo,'rows':rows}]
                with patch('plc_agent.reference_checks.analog_cases',return_value=tests):runs=[test_references(source,qid) for _ in range(2)]
                failed=all(run['status']=='fail' for run in runs)
            record.update(status='ambiguous' if proposal['scope']=='ambiguous' else 'reproduced_pending_adjudication' if failed else 'not_reproduced',runs=runs)
        except (ValueError,TypeError,KeyError,OverflowError) as exc:record['message']=str(exc)
        findings.append(record)
    result={'question_id':qid,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'findings':findings,
            'requests':provider.metrics,'scope':'New independent model context, no author history/test results; hypotheses are not self-certified defects.'}
    atomic_json(directory/'independent_review.json',result);return result


def main():
    cfg=replace(ModelConfig.load(),max_output_tokens=8192,timeout=120,extra_body={'thinking':{'type':'disabled'}})
    budget=Budget(1)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda q:review_one(q,cfg,budget),['04','08','12','18']))
    atomic_json(OUT/'independent_reviews.json',{'results':results})
    print(json.dumps({r['question_id']:[f['status'] for f in r['findings']] for r in results}))


if __name__=='__main__':main()
