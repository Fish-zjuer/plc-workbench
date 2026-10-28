"""Explicit, reviewed safety-property mappings; no automatic claim of full LTL support."""
from pathlib import Path
from . import dataset
from .task_spec import validate_spec
from .formal_verify import verify

def specification(ident):
    task=dataset.load(ident);properties=[]
    def prop(name,when,then):properties.append({'id':name,'requirement':'R1','when':when,'then':then})
    if ident=='CUSTOM_09':
        prop('P02_maintenance',{'inputs.Maintenance':True},{'outputs.State':2})
        prop('P03_exit_maintenance',{'inputs.Maintenance':False,'previous.outputs.State':2},{'outputs.State':0})
        prop('P04_calibrated',{'inputs.Maintenance':False,'previous.outputs.State':0,'inputs.CalibDone':True},{'outputs.State':1})
        prop('P05_wait_calibration',{'inputs.Maintenance':False,'previous.outputs.State':0,'inputs.CalibDone':False},{'outputs.State':0})
        prop('P06_qualified_stays',{'inputs.Maintenance':False,'previous.outputs.State':1},{'outputs.State':1})
        for state in (0,1,2):
            prop('P07_calib_'+str(state),{'outputs.State':state},{'outputs.CalibReq':state==0})
            prop('P08_lamp_'+str(state),{'outputs.State':state},{'outputs.MaintLamp':state==2})
            prop('P09_permit_'+str(state),{'outputs.State':state,'inputs.MeasureReq':True},{'outputs.MeasurePermit':state==1})
        prop('P09_no_request',{'inputs.MeasureReq':False},{'outputs.MeasurePermit':False})
    elif ident=='CUSTOM_10':
        prop('P04_cancel',{'inputs.Cancel':True},{'outputs.Pending':False,'outputs.Dispatched':False,'outputs.RequestLamp':False})
        for pending in (False,True):prop('P03_lamp_'+str(int(pending)),{'outputs.Pending':pending},{'outputs.RequestLamp':pending})
        prop('P07_exclusion',{'outputs.Pending':True},{'outputs.Dispatched':False})
        prop('P02_busy',{'inputs.Busy':True},{'outputs.Dispatched':False})
        prop('P02_not_ready',{'inputs.ServiceReady':False},{'outputs.Dispatched':False})
        prop('P05_retain',{'inputs.Cancel':False,'previous.outputs.Pending':True,'inputs.Busy':True},{'outputs.Pending':True,'outputs.Dispatched':False})
    else:raise ValueError('No reviewed source-level formal mapping for '+ident)
    case=task['scenarios'][0]
    return validate_spec({'schema':'plc-task-v1','title':task['title'],'block':task['block'],'target':'offline',
        'requirements':[{'id':'R1','text':task['requirements']}],
        'inputs':dataset.ports(task,'Input'),'outputs':dataset.ports(task,'Output'),
        'scenarios':[{'name':'supplied_formal_fixture','covers':['R1'],'trace':[{'time_ms':r['time_ms'],'inputs':r['inputs'],'expect':r.get('expected',{})} for r in case['trace']]}],
        'properties':properties,'formal':{'mode':'required','bound':20}})

def check(ident,source,directory):
    spec=specification(ident)
    from .storage import atomic_json
    atomic_json(Path(directory)/'contract.json',spec)
    result=verify(source,spec,directory,bound=20)
    result['mapping_scope']='Only these explicit safety-property mappings of supplied LTL; full LTL, macros and liveness not proved.'
    atomic_json(Path(directory)/'formal.json',result);return result
