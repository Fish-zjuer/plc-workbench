"""Reproduce TIA adapter positive/negative controls without model/API requests."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plc_agent import tia, tia_formal, tia_workflow
from plc_agent.config import STATE_ROOT
from plc_agent.plcverif_backend import configuration
from plc_agent.storage import atomic_json


def task_fixture():
    """Explicitly authored boundary test, not a course task/model experiment."""
    task = {'id':'TIA_ADAPTER_BOUNDARY','title':'Authored TIA adapter acceptance fixture',
            'block':'WB_AdapterBoundary','requirements':'Y = 2*X + 7 when Enable, otherwise 2*X.',
            'adapter_format':'complete_input_trace','source_origin':'Authored adapter fixture, not model-generated course code',
            'interface':[{'direction':'Input','name':'X','type':'SINT'},
                         {'direction':'Input','name':'Enable','type':'BOOL'},
                         {'direction':'Output','name':'Y','type':'DINT'}],
            'scenarios':[{'name':'toggle','trace':[
                {'time_ms':i*10,'inputs':{'X':x,'Enable':enable},'expected':{'Y':2*x+(7 if enable else 0)}}
                for i,(x,enable) in enumerate([(0,False),(0,True),(3,True),(-5,False),(-5,True),(12,False)])]}],
            'ltl':{'properties':[{'id':'enabled','formula':'G(Enable -> enabled_value)'},
                                  {'id':'disabled','formula':'G(!Enable -> disabled_value)'}],
                   'execution':{'bindings':{'enabled_value':'PVL_Enabled','disabled_value':'PVL_Disabled'},
                                'declarations':['PVL_Expected : DINT;','PVL_Enabled : BOOL;','PVL_Disabled : BOOL;'],
                                'before':['PVL_Expected := X + X;','PVL_Enabled := Y = PVL_Expected + 7;',
                                          'PVL_Disabled := Y = PVL_Expected;']}}}
    task['dataset_sha256']=hashlib.sha256(json.dumps(task,sort_keys=True).encode()).hexdigest()
    return task


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',type=Path,default=STATE_ROOT)
    parser.add_argument('--output',type=Path,required=True,help='New evidence directory; refuses to overwrite prior runs')
    parser.add_argument('--native',action='store_true',help='Also run real TIA compilation and PLCSIM positive/negative controls')
    parser.add_argument('--bound',type=int,default=3)
    args=parser.parse_args(argv)
    args.output.mkdir(parents=True,exist_ok=False)
    task=task_fixture();source=ROOT/'examples/tia/AdapterBoundary.scl'
    bad=args.output/'negative.scl'
    original=source.read_text(encoding='utf-8-sig')
    bad.write_text(original.replace('"WB_AdapterLimits".threshold;','"WB_AdapterLimits".threshold + 1;'),encoding='utf-8')
    cfg={**configuration(args.home),'bound':args.bound}
    atomic_json(args.output/'task.json',task)
    summary={'source_origin':task['source_origin'],'model_calls':0,'source_sha256':tia.sha256(source),'bound':args.bound,'checks':{}}
    def record(name,result):
        fields=('status','target_compile','behavior_tested','ltl_status','summary','phase','failure_kind','message')
        summary['checks'][name]={k:result[k] for k in fields if k in result}
        if 'properties' in result:
            summary['checks'][name]['properties']=[{k:p[k] for k in ('id','status') if k in p} for p in result['properties']]
        atomic_json(args.output/'summary.json',summary)
        print(name,result['status'],flush=True)
    positive=tia_formal.verify(task,source,args.output/'positive-formal',config=cfg)
    record('positive_formal',positive)
    negative=tia_formal.verify(task,bad,args.output/'negative-formal',config=cfg)
    record('negative_formal',negative)
    valid=positive['status']=='bounded_pass' and negative['status']=='counterexample'
    if args.native:
        vendor=tia.load_config(args.home)
        actual=tia_workflow.evaluate_candidate(source,task,vendor,directory=args.output/'positive-full',formal_config=cfg)
        record('positive_full',actual)
        valid=valid and actual['status']=='pass' and actual.get('behavior_tested') and actual.get('ltl_status')=='bounded_pass'
        if actual['status']=='pass':
            wrong=tia_workflow.evaluate_candidate(bad,task,vendor,directory=args.output/'negative-full',formal_config=cfg)
            record('negative_full',wrong)
            valid=valid and wrong['status']=='fail' and wrong.get('behavior_tested') and wrong.get('ltl_status')=='not_executed'
    summary['acceptance_passed']=bool(valid)
    atomic_json(args.output/'summary.json',summary)
    return 0 if valid else 1


if __name__=='__main__':raise SystemExit(main())
