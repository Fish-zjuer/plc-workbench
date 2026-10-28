"""Z3 bounded reachability and k-induction over a strict, source-derived ST subset."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import time
from functools import lru_cache
from .formal_st import parse,UnsupportedST,INTEGER_TYPES
from .task_spec import digest,validate_source
from .storage import atomic_json
from .provider import Cancelled

def fingerprint():
    try:
        import z3
        lib=Path(z3.__file__).parent
        files=[Path(__file__),Path(__file__).with_name('formal_st.py'),Path(z3.__file__)]
        files+=list((lib/'lib').glob('*z3*.dll'))
        signature=tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in files)
        return _identity(z3.get_version_string(),signature)
    except ImportError:return None

@lru_cache(maxsize=8)
def _identity(version,signature):
    return digest({'version':version,'files':{name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name,_,_ in signature}})

def replay_query(path):
    import z3
    solver=z3.Solver();solver.set(timeout=20000)
    solver.from_string(Path(path).read_text(encoding='utf-8'))
    return str(solver.check())

def verify(source,spec,directory,*,bound=20,timeout_seconds=20,cancel_event=None):
    if type(bound) is not int or not 2<=bound<=64:raise ValueError('Formal bound must be 2..64 scans')
    if type(timeout_seconds) not in (int,float) or not 1<=timeout_seconds<=60:raise ValueError('Formal timeout must be 1..60 seconds')
    source=Path(source);directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    data=source.read_bytes();source_sha=hashlib.sha256(data).hexdigest()
    report={'schema':'plc-formal-v1','source_sha256':source_sha,'contract_sha256':digest(spec),
            'evidence_path':str(directory.resolve()),
            'queries':[],'evidence_sha256':digest([]),
            'status':'not_executed','backend':'Z3','bound_scans':bound,'properties':[],
            'scope':'Only the listed properties of the parsed ST transition model. Not all natural-language requirements or hardware correctness.',
            'semantics':{'types':'BOOL and 8/16/32-bit integers/bitstrings','state':'FB outputs and VAR persist between scans; declared initial values',
               'arithmetic':'same-type assignment additions/subtractions modulo declared width; arithmetic in comparisons refused',
               'excluded':'REAL/LREAL, TIME/LTIME, timers, other FB/function calls, arrays, references, loops, I/O and interrupts'},
            'assumptions':['Single sequential FB invocation per scan; all inputs assigned before invocation.',
                           'No concurrent writes, retained warm-start state, physical I/O or hardware faults modeled.']}
    try:
        import z3
    except ImportError:
        report.update(status='missing_dependency',message='Install the pinned z3-solver wheel.')
        atomic_json(directory/'formal.json',report);return report
    report.update(solver_version=z3.get_version_string(),formal_fingerprint=fingerprint())
    started=time.monotonic();queries=[]
    try:
        validate_source(data.decode('utf-8-sig'),spec)
        program=parse(data.decode('utf-8-sig'))
        actual={section:{n.upper():t for n,t in spec[section].items()} for section in ('inputs','outputs','inouts')}
        if actual['inouts']:raise UnsupportedST('VAR_IN_OUT is not in formal subset')
        for section in ('inputs','outputs'):
            if {n:t for n,t in program.types.items() if program.directions[n]==section}!=actual[section]:
                raise UnsupportedST('Formal frontend interface mismatch')
        if not spec['properties']:
            report.update(status='no_properties',message='No confirmed invariant properties; scenario examples are not universal properties.')
            atomic_json(directory/'formal.json',report);return report
        initials=program.initial_state(z3)
        inputs={n:t for n,t in program.types.items() if program.directions[n]=='inputs'}
        state_types={n:t for n,t in program.types.items() if program.directions[n]!='inputs'}
        state_types.update({'$prev_'+n:t for n,t in inputs.items()})
        def state(prefix):
            return {**{n:program.variable(prefix+n,t,z3) for n,t in state_types.items()},
                    '$valid':program.variable(prefix+'$valid','BOOL',z3)}
        def input_at(prefix):return {n:program.variable(prefix+n,t,z3) for n,t in inputs.items()}
        def transition(s,inp):
            env=program.execute({**{n:s[n] for n in initials},**inp},z3)
            return {**{n:env[n] for n in initials},**{'$prev_'+n:v for n,v in inp.items()},
                    '$valid':program.value(True,'BOOL',z3)}
        def initialized(s):
            return z3.And(*[s[n].term==v.term for n,v in initials.items()],z3.Not(s['$valid'].term))
        def equal_state(a,b):return z3.And(*[a[n].term==b[n].term for n in a])
        def ref(name,s,inp,nxt):
            previous=name.startswith('previous.')
            if previous:name=name[len('previous.'):]
            parts=name.split('.')
            if len(parts)!=2:raise UnsupportedST('Clock/property reference outside formal subset: '+name)
            section,field=parts;field=field.upper()
            if section=='inputs':return s['$prev_'+field] if previous else inp[field]
            if section=='outputs':return s[field] if previous else nxt[field]
            raise UnsupportedST('Property reference unsupported: '+name)
        def comparison(v,expected):
            op,value=(expected['op'],expected['value']) if isinstance(expected,dict) else ('eq',expected)
            literal=program.value(value,v.dtype,z3)
            if op in ('eq','ne'):return v.term==literal.term if op=='eq' else v.term!=literal.term
            if v.dtype=='BOOL':raise UnsupportedST('BOOL ordering not supported')
            if not INTEGER_TYPES[v.dtype][1]:
                return {'lt':z3.ULT,'le':z3.ULE,'gt':z3.UGT,'ge':z3.UGE}[op](v.term,literal.term)
            return {'lt':lambda a,b:a<b,'le':lambda a,b:a<=b,'gt':lambda a,b:a>b,'ge':lambda a,b:a>=b}[op](v.term,literal.term)
        def property_terms(prop,s,inp,nxt):
            before=z3.And(*[comparison(ref(k,s,inp,nxt),v) for k,v in prop['when'].items()])
            if any(k.startswith('previous.') for side in ('when','then') for k in prop[side]):
                before=z3.And(s['$valid'].term,before)
            after=z3.And(*[comparison(ref(k,s,inp,nxt),v) for k,v in prop['then'].items()])
            return z3.Implies(before,after),before
        def check(solver,name):
            if cancel_event and cancel_event.is_set():raise Cancelled('Formal verification cancelled')
            remaining=timeout_seconds-(time.monotonic()-started)
            if remaining<=0:raise TimeoutError('Formal total time budget exhausted')
            solver.set(timeout=max(1,min(1500,int(remaining*1000))))
            path=directory/(name+'.smt2');path.write_text(solver.to_smt2(),encoding='utf-8')
            result=solver.check()
            queries.append({'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'result':str(result)})
            return result
        def plain(model,value):
            term=model.eval(value.term,model_completion=True)
            if value.dtype=='BOOL':return z3.is_true(term)
            number=term.as_long();width,signed=INTEGER_TYPES[value.dtype]
            return number-(1<<width) if signed and number>=(1<<(width-1)) else number
        for prop in spec['properties']:
            pid=prop['id'];record={'id':pid,'requirement':prop['requirement'],'status':'unknown'}
            solver=z3.Solver();s=state(pid+'_base_0_');solver.add(initialized(s));trace=[]
            hit=False;unknown=False
            for index in range(bound):
                inp=input_at(pid+f'_input_{index}_');nxt=transition(s,inp)
                claim,antecedent=property_terms(prop,s,inp,nxt)
                trace.append((s,inp,nxt))
                solver.push();solver.add(z3.Not(claim))
                answer=check(solver,pid+f'_base_{index+1:02d}')
                if answer==z3.sat:
                    model=solver.model()
                    rows=[{'time_ms':i,'inputs':{original:plain(model,inputs_row[original.upper()]) for original in spec['inputs']},
                           'symbolic_actual':{original:plain(model,next_row[original.upper()]) for original in spec['outputs']}}
                          for i,(_,inputs_row,next_row) in enumerate(trace)]
                    record.update(status='counterexample',first_failing_scan=index,
                                  counterexample={'name':'formal_'+pid,'covers':[prop['requirement']],
                                      'trace':[{'time_ms':r['time_ms'],'inputs':r['inputs']} for r in rows]},
                                  symbolic_rows=rows)
                    solver.pop();hit=True;break
                if answer==z3.unknown:
                    record.update(status='unknown',reason=solver.reason_unknown());solver.pop();unknown=True;break
                solver.pop()
                new=state(pid+f'_base_{index+1}_');solver.add(equal_state(new,nxt));s=new
            if not hit and not unknown:
                record.update(status='bounded_only',checked_scans=bound)
                # An induction SAT model is only an arbitrary-state witness, never a reachable bug.
                for depth in range(1,min(8,bound-1)+1):
                    induction=z3.Solver();s=state(pid+f'_ind_{depth}_0_')
                    for i in range(depth+1):
                        inp=input_at(pid+f'_ind_input_{depth}_{i}_');nxt=transition(s,inp)
                        claim,_=property_terms(prop,s,inp,nxt)
                        induction.add(claim if i<depth else z3.Not(claim))
                        new=state(pid+f'_ind_{depth}_{i+1}_');induction.add(equal_state(new,nxt));s=new
                    answer=check(induction,pid+f'_induction_{depth:02d}')
                    if answer==z3.unsat:record.update(status='proved',induction_depth=depth);break
                    if answer==z3.unknown:record['induction_reason']=induction.reason_unknown();break
            report['properties'].append(record)
        statuses={r['status'] for r in report['properties']}
        report['status']='counterexample' if 'counterexample' in statuses else 'proved' if statuses=={'proved'} else 'unknown' if 'unknown' in statuses else 'bounded_only'
    except UnsupportedST as exc:report.update(status='unsupported',message=str(exc))
    except TimeoutError as exc:report.update(status='timeout',message=str(exc))
    except Cancelled:
        report.update(status='cancelled');raise
    finally:
        report['elapsed_seconds']=round(time.monotonic()-started,3);report['queries']=queries
        report['proved_property_ids']=[r['id'] for r in report['properties'] if r['status']=='proved']
        report['evidence_sha256']=digest(queries)
        if hashlib.sha256(source.read_bytes()).hexdigest()!=source_sha:report.update(status='stale_source',message='Source changed while solving')
        atomic_json(directory/'formal.json',report)
    return report

def evidence_valid(record,root):
    """Verify the saved report and every SMT query under a host-owned evidence root."""
    try:
        directory=Path(record['evidence_path']).resolve();root=Path(root).resolve()
        if not directory.is_relative_to(root):return False
        saved=json.loads((directory/'formal.json').read_text(encoding='utf-8'))
        from .task_formal import summary
        if digest(summary(saved))!=digest(summary(record)):return False
        queries=saved.get('queries',[])
        if saved.get('evidence_sha256')!=digest(queries):return False
        for item in queries:
            path=(directory/item['file']).resolve()
            if path.parent!=directory or path.suffix!='.smt2' or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
                return False
        return True
    except (ValueError,OSError,KeyError,TypeError):return False
