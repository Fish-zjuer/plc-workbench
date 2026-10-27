"""New fixed R4 checks for caller-owned open arrays and generic FIFO storage.

These are separate from the frozen original twenty-task predicates. Values are
read from the actual caller's storage; no copy-in/copy-out substitute is used.
VARIANT uses the documented local PV descriptor ABI, not a vendor binary ABI.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess

from plc_probe.backend import BackendError,_command
from plc_probe.config import cache_dir,toolchain_dir
from .storage import atomic_json

FIELDS=('enable','hiLIM','loLIM','bipolar','measuringMode','retVal','outputValue')


def analog_cases():
    rng=random.Random(20261028);cases=[]
    for alen,alo,clen,clo in [(1,-5,1,4),(3,7,5,-8),(7,-4,4,20),(8,0,8,-15)]:
        rows=[]
        for scan in range(80):
            records=[];raw=[]
            for i in range(alen):raw.append(rng.choice([-27648,0,27648,rng.randrange(-27648,27649)]))
            for i in range(clen):
                mode=(scan+i)%5;lo=-30.5;hi=73.25
                if mode==3:mode=9
                elif mode==4:mode=0;hi=lo
                bipolar=int((scan+i)%2==0);enabled=int((scan+i)%7!=0)
                records.append([enabled,hi,lo,bipolar,mode,0x1234,-700.25-i])
                if i<alen and mode==0 and not bipolar:raw[i]=abs(raw[i])
            count=scan%(min(alen,clen)+1)
            expected=[list(r) for r in records]
            for i in range(count):
                enabled,hi,lo,bipolar,mode,_,_=records[i]
                if not enabled:continue
                if mode not in (0,1,2):expected[i][5]=0x8001;continue
                if hi<=lo:expected[i][5]=0x8002;continue
                expected[i][5]=0
                expected[i][6]=(lo+(hi-lo)*(raw[i]+27648)/55296 if bipolar else lo+(hi-lo)*raw[i]/27648) if mode==0 else raw[i]/10 if mode==1 else raw[i]/100
            rows.append({'count':count,'raw':raw,'channels':records,'expected':expected})
        cases.append({'name':f'bounds_{alo}_{clo}_lengths_{alen}_{clen}','analog_length':alen,'analog_lower':alo,
                      'channel_length':clen,'channel_lower':clo,'rows':rows})
    return cases


def fifo_cases():
    rng=random.Random(20261028);cases=[]
    for kind in ('dint','real','record','bool'):
        for capacity in (1,2,7):
            def value(index):
                if kind=='dint':return index*1000003-1000000000
                if kind=='real':return index*.375-999.25
                if kind=='record':return [index*31-10000,index*.0625+17.25]
                return index%2
            rows=[{'enqueue':0,'dequeue':0,'reset':0,'item':value(0)}]
            def edge(enq,deq,reset=0):
                rows.append({'enqueue':enq,'dequeue':deq,'reset':reset,'item':value(len(rows))})
            edge(0,1);edge(0,1);edge(0,0)
            for _ in range(capacity+2):edge(1,0);edge(1,0);edge(0,0)
            for _ in range(capacity+2):edge(0,1);edge(0,1);edge(0,0)
            # Several wraps, resets while a request is held, and ordinary random calls.
            for i in range(150):
                operation=rng.randrange(5)
                edge(int(operation==1),int(operation==2),int(i%31==0))
            edge(1,0,1);edge(1,0,0);edge(0,0);edge(0,1)
            cases.append({'name':f'{kind}_capacity_{capacity}','kind':kind,'capacity':capacity,'rows':rows})
    return cases


ANALOG_DRIVER=r'''#include "candidate.hpp"
#include <vector>
#include <memory>
#include <iostream>
#include <iomanip>
int main(){std::cout<<std::setprecision(17);std::string command;
std::unique_ptr<strucpp::Q08> uut;std::vector<strucpp::IEC_INT> raw;std::vector<strucpp::ST_ANALOGCHANNEL> channels;
while(std::cin>>command){
 if(command=="R"){int alen,alo,clen,clo;std::cin>>alen>>alo>>clen>>clo;
  uut=std::make_unique<strucpp::Q08>();raw.assign(alen,{});channels.assign(clen,{});
  uut->ANALOGVALUES=strucpp::ArrayView1D<strucpp::IEC_INT>(raw.data(),alo,alo+alen-1);
  uut->CHANNELS=strucpp::ArrayView1D<strucpp::ST_ANALOGCHANNEL>(channels.data(),clo,clo+clen-1);continue;}
 if(command!="S"||!uut)return 2;
 int count;std::cin>>count;uut->COUNT=count;
 for(auto &v:raw){int x;std::cin>>x;v=x;}
 for(auto &r:channels){int en,bi,mode,ret;double hi,lo,out;std::cin>>en>>hi>>lo>>bi>>mode>>ret>>out;
  r.ENABLE=en;r.HILIM=hi;r.LOLIM=lo;r.BIPOLAR=bi;r.MEASURINGMODE=mode;r.RETVAL=ret;r.OUTPUTVALUE=out;}
 (*uut)();
 for(auto &v:raw)std::cout<<static_cast<int>(v)<<" ";
 for(auto &r:channels)std::cout<<static_cast<int>(r.ENABLE)<<" "<<static_cast<double>(r.HILIM)<<" "<<static_cast<double>(r.LOLIM)<<" "<<static_cast<int>(r.BIPOLAR)<<" "<<static_cast<int>(r.MEASURINGMODE)<<" "<<static_cast<int>(r.RETVAL)<<" "<<static_cast<double>(r.OUTPUTVALUE)<<" ";
 std::cout<<"\n";
}}
'''

FIFO_DRIVER=r'''#include "candidate.hpp"
#include <vector>
#include <memory>
#include <iostream>
#include <iomanip>
struct Payload { int key=0;double value=0; };
template<class T> void read_value(T &v){double x;std::cin>>x;v=x;}
template<> void read_value(Payload &v){std::cin>>v.key>>v.value;}
template<class T> void print_value(const T &v){std::cout<<static_cast<double>(v)<<" ";}
template<> void print_value(const Payload &v){std::cout<<v.key<<" "<<v.value<<" ";}
struct Base {virtual ~Base()=default;virtual void scan()=0;};
template<class T> struct Runner:Base {
 strucpp::Q18 uut;std::vector<T> buffer;T item{};
 explicit Runner(int cap):buffer(cap){uut.BUFFER.bind_array(buffer.data(),cap);uut.ITEM.bind_scalar(item);}
 void scan() override {int e,d,r;std::cin>>e>>d>>r;read_value(item);uut.ENQUEUE=e;uut.DEQUEUE=d;uut.RESET=r;
  uut();std::cout<<static_cast<int>(uut.ELEMENTCOUNT)<<" "<<static_cast<int>(uut.STATUS)<<" ";print_value(item);
  for(auto &v:buffer)print_value(v);std::cout<<"\n";}
};
int main(){std::cout<<std::setprecision(17);std::string command;std::unique_ptr<Base> runner;
while(std::cin>>command){if(command=="R"){std::string kind;int cap;std::cin>>kind>>cap;
 if(kind=="dint")runner=std::make_unique<Runner<strucpp::IEC_DINT>>(cap);
 else if(kind=="real")runner=std::make_unique<Runner<strucpp::IEC_REAL>>(cap);
 else if(kind=="bool")runner=std::make_unique<Runner<strucpp::IEC_BOOL>>(cap);
 else if(kind=="record")runner=std::make_unique<Runner<Payload>>(cap);else return 2;continue;}
 if(command!="S"||!runner)return 3;runner->scan();}
}
'''


def compile_reference(source,qid):
    source=Path(source).resolve();code=source.read_bytes();driver=ANALOG_DRIVER if qid=='08' else FIFO_DRIVER
    compiler=toolchain_dir()/('strucpp.exe' if os.name=='nt' else 'strucpp');cxx=os.environ.get('CXX') or shutil.which('g++')
    if not compiler.exists() or not cxx:raise BackendError({'status':'missing_dependency','message':'Need reference-capable ST compiler and g++'})
    key=hashlib.sha256(code+driver.encode()+str(toolchain_dir()).encode()).hexdigest()[:24]
    directory=cache_dir()/'builds'/('refs_'+key);directory.mkdir(parents=True,exist_ok=True)
    exe=directory/('runner.exe' if os.name=='nt' else 'runner');meta=directory/'build.json'
    if not exe.exists() or not meta.exists():
        (directory/'candidate.st').write_bytes(code);(directory/'driver.cpp').write_text(driver,encoding='utf-8')
        logs=[_command([str(compiler),'candidate.st','-o','candidate.cpp'],directory,'st_to_cpp')]
        include=os.path.relpath(toolchain_dir()/'runtime/include',directory)
        flags=['-std=c++17','-O1']+(['-static'] if os.name=='nt' else [])
        logs.append(_command([cxx,*flags,'-I',include,'candidate.cpp','driver.cpp','-o',exe.name],directory,'native_compile'))
        atomic_json(meta,{'source_sha256':hashlib.sha256(code).hexdigest(),'logs':logs,'scope':'Caller-owned references; local PLC-R4 runtime ABI'})
    return exe,meta


def equal(left,right,kind):
    if isinstance(right,list):return isinstance(left,list) and all(equal(a,b,'dint' if i==0 else 'lreal') for i,(a,b) in enumerate(zip(left,right)))
    if kind in ('dint','bool'):return left==right
    return math.isclose(left,right,rel_tol=1e-6 if kind=='real' else 1e-12,abs_tol=1e-6 if kind=='real' else 1e-12)


def test_references(source,qid):
    source=Path(source).resolve();exe,meta=compile_reference(source,qid)
    cases=analog_cases() if qid=='08' else fifo_cases();commands=[]
    def tokens(value):return ' '.join(map(str,value)) if isinstance(value,list) else str(value)
    for case in cases:
        commands.append('R '+(' '.join(str(case[k]) for k in ('analog_length','analog_lower','channel_length','channel_lower')) if qid=='08' else f"{case['kind']} {case['capacity']}"))
        for row in case['rows']:
            commands.append('S '+(str(row['count'])+' '+' '.join(map(str,row['raw']))+' '+' '.join(str(v) for r in row['channels'] for v in r) if qid=='08' else
                                 f"{row['enqueue']} {row['dequeue']} {row['reset']} "+tokens(row['item'])))
    try:run=subprocess.run([str(exe)],input='\n'.join(commands)+'\n',capture_output=True,text=True,encoding='utf-8',timeout=20,cwd=exe.parent)
    except subprocess.TimeoutExpired:raise BackendError({'status':'timeout','phase':'execution','message':'Reference cases exceeded 20 seconds'}) from None
    if run.returncode:raise BackendError({'status':'runtime_error','phase':'execution','stderr':run.stderr[:2000]})
    lines=run.stdout.splitlines()
    if len(lines)!=sum(len(c['rows']) for c in cases):raise BackendError({'status':'runtime_error','message':'Reference output scan count mismatch'})
    cursor=0;results=[]
    for case in cases:
        rows=[];first=None;queue=[];previous_enqueue=previous_dequeue=0;previous_buffer=None
        for scan,row in enumerate(case['rows']):
            values=[float(x) for x in lines[cursor].split()];cursor+=1;violations=[]
            if qid=='08':
                alen=case['analog_length'];clen=case['channel_length']
                if len(values)!=alen+clen*7:raise BackendError({'status':'runtime_error','message':'Analog field count mismatch'})
                actual={'raw':values[:alen],'channels':[values[alen+i*7:alen+(i+1)*7] for i in range(clen)]}
                for i,(a,b) in enumerate(zip(actual['raw'],row['raw'])):
                    if a!=b:violations.append({'output':f'analogValues[{i}]','expected':b,'actual':a,'property':'readonly_input'})
                for i,record in enumerate(row['expected']):
                    for j,expected in enumerate(record):
                        actual_value=actual['channels'][i][j]
                        if not equal(actual_value,expected,'real' if j in (1,2,6) else 'dint'):
                            violations.append({'output':f'channels[{i}].{FIELDS[j]}','expected':expected,'actual':actual_value})
            else:
                kind=case['kind'];width=2 if kind=='record' else 1;cap=case['capacity']
                if len(values)!=2+width*(cap+1):raise BackendError({'status':'runtime_error','message':'FIFO field count mismatch'})
                payloads=[values[2+i*width:2+(i+1)*width] if width==2 else values[2+i] for i in range(cap+1)]
                actual={'elementCount':int(values[0]),'status':int(values[1]),'item':payloads[0],'buffer':payloads[1:]}
                rising_enqueue=row['enqueue'] and not previous_enqueue;rising_dequeue=row['dequeue'] and not previous_dequeue
                previous_enqueue=row['enqueue'];previous_dequeue=row['dequeue'];status=0;expected_item=row['item'];check_item=True;must_preserve=False
                if row['reset']:queue.clear();check_item=False
                elif rising_enqueue:
                    if len(queue)==cap:status=0x8002;must_preserve=True
                    else:
                        queue.append(row['item'])
                        if not any(equal(v,row['item'],kind) for v in actual['buffer']):
                            violations.append({'property':'enqueue_writes_caller_buffer','expected':row['item'],'actual':actual['buffer']})
                elif rising_dequeue:
                    if not queue:status=0x8001;must_preserve=True
                    else:expected_item=queue.pop(0)
                else:must_preserve=True
                if actual['elementCount']!=len(queue):violations.append({'output':'elementCount','expected':len(queue),'actual':actual['elementCount']})
                if actual['status']!=status:violations.append({'output':'status','expected':status,'actual':actual['status']})
                if check_item and not equal(actual['item'],expected_item,kind):violations.append({'output':'item','expected':expected_item,'actual':actual['item']})
                if must_preserve and previous_buffer is not None and not all(equal(a,b,kind) for a,b in zip(actual['buffer'],previous_buffer)):
                    violations.append({'property':'idle_or_rejection_preserves_buffer','expected':previous_buffer,'actual':actual['buffer']})
                previous_buffer=actual['buffer']
            rows.append({**row,'actual':actual,'violations':violations})
            if first is None and violations:first={'scan':scan,**violations[0]}
        results.append({'name':case['name'],'status':'fail' if first else 'pass','first_failure':first,'rows':rows})
    return {'status':'fail' if any(c['first_failure'] for c in results) else 'pass','question_id':qid,
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'behavior_tested':True,
            'summary':{'scenarios':len(cases),'scans':len(lines),'failed':sum(c['status']=='fail' for c in results)},'cases':results,
            'first_failure':next(({'scenario':c['name'],**c['first_failure']} for c in results if c['first_failure']),None),
            'build_evidence':str(meta),'scope':'Fixed finite caller-reference tests. VARIANT uses local PV descriptor ABI; not a Siemens/CODESYS binary-compatibility proof.'}
