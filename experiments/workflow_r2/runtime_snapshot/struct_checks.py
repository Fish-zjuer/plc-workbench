"""Supplemental single-FB copy-in/copy-out checks for fixed struct arrays.

The pinned transpiler lowers these IN_OUT parameters to value members. The bridge
explicitly transfers caller-owned arrays around each invocation. This does not
test reference aliasing, concurrency or CODESYS calling semantics.
"""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import random
import shutil
import subprocess

from plc_probe.backend import BackendError,_command
from plc_probe.config import VERSION,cache_dir,toolchain_dir
from .storage import atomic_json

RECIPE_FIELDS=('recipeID','ingredientType','ingredientRatio','productionTemperature')


def specification(qid):
    if qid=='07':
        return {'inputs':('mode','start','stop',*[f'pump{i}.{f}' for i in range(1,6) for f in ('priority','selection')]),
                'outputs':tuple(f'pump{i}.{f}' for i in range(1,6) for f in ('priority','selection','RunComd'))}
    if qid=='17':
        return {'inputs':('addRecipe','deleteRecipe','modifyRecipe','queryRecipe',*[f'recipeIn.{f}' for f in RECIPE_FIELDS]),
                'outputs':('recipeAdded','recipeDeleted','recipeModified','error','status',*[f'query.{f}' for f in RECIPE_FIELDS],
                           *[f'recipe{i}.{f}' for i in range(1,11) for f in RECIPE_FIELDS])}
    raise ValueError('Only fixed struct-array tasks 07 and 17')


def cases(qid):
    if qid=='07':
        rng=random.Random(20261027);rows=[]
        for i in range(80):
            priorities=rng.sample(range(-200,201),5)
            selections=[rng.randrange(2) for _ in range(5)]
            mode=i%2;stop=int(i%7==0)
            best=set(sorted(range(5),key=lambda j:priorities[j],reverse=True)[:3])
            expected={}
            for j in range(5):
                expected.update({f'pump{j+1}.priority':priorities[j],f'pump{j+1}.selection':selections[j],
                                 f'pump{j+1}.RunComd':0 if stop else int(j in best) if mode else selections[j]})
            rows.append({'inputs':[mode,1,stop,*[v for p,s in zip(priorities,selections) for v in (p,s)]],'expected':expected})
        return [{'name':'manual_auto_priorities_stop_readonly_fields','rows':rows}]
    result=[]
    def recipe(ident,temp=300):return [ident,ident%4,.25,temp]
    def scenario(name,operations,initial=None):
        database=[list(r) for r in initial] if initial else [[0,0,0.,0.] for _ in range(10)]
        rows=[]
        for operation,record in operations:
            ident=record[0];found=next((i for i,r in enumerate(database) if r[0]==ident and ident!=0),None)
            empty=next((i for i,r in enumerate(database) if r[0]==0),None)
            signals=[int(operation==name) for name in ('add','delete','modify','query')]
            expected={};error=0
            if operation=='add':
                if found is not None:error=0x8002
                elif empty is None:error=0x8003
                else:database[empty]=list(record);expected['recipeAdded']=1
            elif operation=='delete':
                if found is None:error=0x8004
                else:database[found][0]=0;expected['recipeDeleted']=1
            elif operation=='modify':
                if found is None:error=0x8005
                else:database[found]=list(record);expected['recipeModified']=1
            elif operation=='query':
                if found is None:error=0x8001
                else:expected.update({f'query.{f}':v for f,v in zip(RECIPE_FIELDS,database[found])})
            expected['error']=int(bool(error))
            if error:expected['status']=error
            for i,r in enumerate(database,1):
                expected[f'recipe{i}.recipeID']=r[0]
                if r[0]!=0:expected.update({f'recipe{i}.{f}':v for f,v in zip(RECIPE_FIELDS,r)})
            rows.append({'inputs':[*signals,*record],'expected':expected})
            # Idle scan separates request pulses; do not invent unspecified flags.
            retained={k:v for k,v in expected.items() if k.startswith('recipe') and '.' in k}
            rows.append({'inputs':[0,0,0,0,*record],'expected':retained})
        result.append({'name':name,'initial':initial or [[0,0,0.,0.] for _ in range(10)],'rows':rows})
    scenario('lifecycle_and_lowest_free_slot',[
        ('query',recipe(7)),('add',recipe(7)),('add',recipe(7)),('query',recipe(7)),
        ('modify',recipe(7,450.5)),('query',recipe(7)),('delete',recipe(7)),('query',recipe(7)),
        ('delete',recipe(7)),('modify',recipe(7)),('add',recipe(8)),('add',recipe(9)),('delete',recipe(8)),('add',recipe(10))])
    scenario('capacity_and_duplicate_priority',[("add",recipe(i)) for i in range(1,11)]+
             [('add',recipe(11)),('add',recipe(5)),('delete',recipe(4)),('add',recipe(11)),('query',recipe(11))])
    initial=[[0,0,0.,0.] for _ in range(10)];initial[1]=recipe(42);initial[7]=recipe(88)
    scenario('caller_preloaded_database',[('query',recipe(42)),('add',recipe(9)),('query',recipe(88))],initial)
    return result


def driver(qid):
    common='''#include "candidate.hpp"
#include <iostream>
#include <iomanip>
#include <memory>
#include <string>
int main(){ std::cout<<std::setprecision(17);
auto uut=std::make_unique<strucpp::QID>();
decltype(uut->ARRAY) caller{};
std::string command;
while(std::cin>>command){
if(command=="R"){uut=std::make_unique<strucpp::QID>(); caller=decltype(caller){};continue;}
BODY
}
}'''
    if qid=='07':
        body='''if(command!="S")return 2;
int mode,start,stop;std::cin>>mode>>start>>stop;
for(int i=1;i<=5;i++){int p,s;std::cin>>p>>s;caller.at(i).PRIORITY=p;caller.at(i).SELECTION=s;}
uut->MODE=mode;uut->START=start;uut->STOP=stop;
uut->PUMPGROUP=caller;(*uut)();caller=uut->PUMPGROUP;
for(int i=1;i<=5;i++)std::cout<<static_cast<int>(caller.at(i).PRIORITY)<<" "<<static_cast<int>(caller.at(i).SELECTION)<<" "<<static_cast<int>(caller.at(i).RUNCOMD)<<" ";
std::cout<<"\\n";'''
        return common.replace('QID','Q07').replace('ARRAY','PUMPGROUP').replace('BODY',body)
    body='''if(command=="D"){
for(int i=1;i<=10;i++){int id,type;double ratio,temp;std::cin>>id>>type>>ratio>>temp;caller.at(i).RECIPEID=id;caller.at(i).INGREDIENTTYPE=type;caller.at(i).INGREDIENTRATIO=ratio;caller.at(i).PRODUCTIONTEMPERATURE=temp;}
continue;}
if(command!="S")return 2;
int a,d,m,q,id,type;double ratio,temp;std::cin>>a>>d>>m>>q>>id>>type>>ratio>>temp;
uut->ADDRECIPE=a;uut->DELETERECIPE=d;uut->MODIFYRECIPE=m;uut->QUERYRECIPE=q;
uut->RECIPEIN.RECIPEID=id;uut->RECIPEIN.INGREDIENTTYPE=type;uut->RECIPEIN.INGREDIENTRATIO=ratio;uut->RECIPEIN.PRODUCTIONTEMPERATURE=temp;
uut->RECIPE=caller;(*uut)();caller=uut->RECIPE;
std::cout<<static_cast<int>(uut->RECIPEADDED)<<" "<<static_cast<int>(uut->RECIPEDELETED)<<" "<<static_cast<int>(uut->RECIPEMODIFIED)<<" "<<static_cast<int>(uut->ERROR)<<" "<<static_cast<int>(uut->STATUS)<<" ";
std::cout<<static_cast<int>(uut->RECIPEQUERYRESULT.RECIPEID)<<" "<<static_cast<int>(uut->RECIPEQUERYRESULT.INGREDIENTTYPE)<<" "<<static_cast<double>(uut->RECIPEQUERYRESULT.INGREDIENTRATIO)<<" "<<static_cast<double>(uut->RECIPEQUERYRESULT.PRODUCTIONTEMPERATURE)<<" ";
for(int i=1;i<=10;i++)std::cout<<static_cast<int>(caller.at(i).RECIPEID)<<" "<<static_cast<int>(caller.at(i).INGREDIENTTYPE)<<" "<<static_cast<double>(caller.at(i).INGREDIENTRATIO)<<" "<<static_cast<double>(caller.at(i).PRODUCTIONTEMPERATURE)<<" ";
std::cout<<"\\n";'''
    return common.replace('QID','Q17').replace('ARRAY','RECIPE').replace('BODY',body)


def test_struct(source:Path,qid):
    source=Path(source).resolve();code=source.read_bytes();bridge=driver(qid)
    cxx=os.environ.get('CXX') or shutil.which('g++');compiler=toolchain_dir()/('strucpp.exe' if os.name=='nt' else 'strucpp')
    if not cxx or not compiler.exists():raise BackendError({'status':'missing_dependency','message':'Need STruC++ and g++'})
    key=hashlib.sha256(code+bridge.encode()+f'{VERSION}|{cxx}'.encode()).hexdigest()[:24]
    directory=cache_dir()/'builds'/('struct_'+key);directory.mkdir(parents=True,exist_ok=True)
    exe=directory/('runner.exe' if os.name=='nt' else 'runner');meta=directory/'build.json'
    if not exe.exists() or not meta.exists():
        (directory/'candidate.st').write_bytes(code);(directory/'driver.cpp').write_text(bridge,encoding='utf-8')
        logs=[_command([str(compiler),'candidate.st','-o','candidate.cpp'],directory,'st_to_cpp')]
        include=os.path.relpath(toolchain_dir()/'runtime/include',directory)
        flags=['-std=c++17','-O1']+(['-static'] if os.name=='nt' else [])
        logs.append(_command([cxx,*flags,'-I',include,'candidate.cpp','driver.cpp','-o',exe.name],directory,'native_compile'))
        atomic_json(meta,{'source_sha256':hashlib.sha256(code).hexdigest(),'logs':logs,'scope':'Single FB with explicit caller-array copy-in/copy-out'})
    tests=cases(qid);commands=[]
    for case in tests:
        commands.append('R')
        if qid=='17':commands.append('D '+' '.join(str(x) for r in case['initial'] for x in r))
        for row in case['rows']:commands.append('S '+' '.join(str(x) for x in row['inputs']))
    try:run=subprocess.run([str(exe)],input='\n'.join(commands)+'\n',capture_output=True,text=True,encoding='utf-8',timeout=15,cwd=directory)
    except subprocess.TimeoutExpired:raise BackendError({'status':'timeout','phase':'execution','message':'Struct scan test exceeded 15 seconds'}) from None
    if run.returncode:raise BackendError({'status':'runtime_error','message':run.stderr[:1500]})
    lines=run.stdout.splitlines();spec=specification(qid)
    if len(lines)!=sum(len(t['rows']) for t in tests):raise BackendError({'status':'runtime_error','message':'Struct output scan count mismatch'})
    cursor=0;results=[]
    for test in tests:
        rows=[];first=None
        for i,row in enumerate(test['rows']):
            values=lines[cursor].split();cursor+=1
            if len(values)!=len(spec['outputs']):raise BackendError({'status':'runtime_error','message':'Struct output field count mismatch'})
            actual={k:float(v) for k,v in zip(spec['outputs'],values)}
            failed=[{'output':k,'expected':v,'actual':actual[k]} for k,v in row['expected'].items() if not math.isclose(actual[k],v,rel_tol=1e-5,abs_tol=1e-5)]
            rows.append({**row,'actual':actual,'violations':failed})
            if failed and first is None:first={'scan':i,**failed[0]}
        results.append({'name':test['name'],'status':'fail' if first else 'pass','first_failure':first,'rows':rows})
    return {'status':'fail' if any(r['first_failure'] for r in results) else 'pass','question_id':qid,'source_sha256':hashlib.sha256(code).hexdigest(),
            'behavior_tested':True,'summary':{'scenarios':len(results),'scans':len(lines),'failed':sum(r['status']=='fail' for r in results)},
            'first_failure':next(({'scenario':r['name'],**r['first_failure']} for r in results if r['first_failure']),None),'cases':results,
            'build_evidence':str(meta),'scope':'Supplemental fixed-array single-FB tests with copy-in/copy-out. Does not verify reference aliasing, multiple FB owners, concurrency, or CODESYS.'}
