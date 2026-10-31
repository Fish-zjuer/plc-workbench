"""Trusted worker executed ONLY by CODESYS --runscript (IronPython 2.7 compatible).

This file never opens a physical target: simulation must be set and read back before login.
"""
from __future__ import print_function
import codecs
import hashlib
import json
import os
import shutil
import time
import traceback

def main():
    from scriptengine import projects,system,online,OnlineChangeOption,ResetOption,Severity
    from System.Diagnostics import FileVersionInfo
    request_path=os.environ['PLC_WORKBENCH_REQUEST']
    with codecs.open(request_path,'r','utf-8') as stream:request=json.load(stream)
    result={'vendor':'CODESYS','vendor_version':FileVersionInfo.GetVersionInfo(os.environ.get('PLC_WORKBENCH_EXECUTABLE',system.executable_filename)).FileVersion,
            'nonce':request['nonce'],'source_sha256':request.get('source_sha256'),
            'status':'error','target_compile':'not_executed','simulation':False}
    project=None
    def stage(name):
        path=os.path.join(os.path.dirname(request['output']),'progress.json')
        with codecs.open(path,'w','utf-8') as stream:
            stream.write(json.dumps({'stage':name,'timestamp':time.time()},ensure_ascii=True))
    stage('worker_started')
    def messages():
        records=[]
        for category in system.get_message_categories():
            for message in system.get_message_objects(category):
                records.append({'severity':str(message.severity),'text':str(message.text),
                    'position':str(message.position_text) if message.position_text else ''})
        return records
    try:
        if request['action']=='probe':
            result.update(status='probed',scripting_engine=True)
        else:
            folder=os.path.dirname(request['output'])
            local=os.path.join(folder,'work.project')
            shutil.copyfile(request['template_project'],local)
            stage('opening_project')
            project=projects.open(local)
            apps=[obj for obj in project.get_children(True) if hasattr(obj,'is_application') and obj.is_application]
            if len(apps)!=1:raise RuntimeError('Template must contain exactly one application')
            app=apps[0]
            device=app
            for unused in range(12):
                if hasattr(device,'set_simulation_mode'):break
                device=device.parent
                if device is None:raise RuntimeError('No application device found')
            if not hasattr(device,'set_simulation_mode'):raise RuntimeError('No simulation-capable application device')
            stage('enabling_simulation')
            device.set_simulation_mode(True)
            if not device.get_simulation_mode():raise RuntimeError('Simulation mode was not enabled; online login is forbidden')
            result['simulation']=True
            existing=app.find(request['block'],True)
            if existing:raise RuntimeError('Dedicated template unexpectedly already contains the candidate block')
            if request.get('units'):
                from scriptengine import PouType
                for unit in request['units']:
                    if app.find(unit['name'],True):raise RuntimeError('Template name conflict: '+unit['name'])
                    if unit['kind']=='TYPE':candidate=app.create_dut(name=unit['name'])
                    else:
                        kwargs={'name':unit['name'],'type':{'FUNCTION_BLOCK':PouType.FunctionBlock,
                            'FUNCTION':PouType.Function,'PROGRAM':PouType.Program}[unit['kind']]}
                        if unit.get('return_type'):kwargs['return_type']=unit['return_type']
                        candidate=app.create_pou(**kwargs)
                    candidate.textual_declaration.replace(unit['declaration'])
                    if 'implementation' in unit:candidate.textual_implementation.replace(unit['implementation'])
            else:
                candidate=app.create_function_block(request['block'])
                candidate.textual_declaration.replace(request['declaration'])
                candidate.textual_implementation.replace(request['implementation'])
            programs=[obj for obj in app.find('PLC_PRG',True)
                      if hasattr(obj,'textual_declaration') and hasattr(obj,'textual_implementation')]
            if len(programs)!=1:raise RuntimeError('Template must schedule exactly one empty PLC_PRG program')
            harness=programs[0]
            harness.textual_declaration.replace(request['harness_declaration'])
            harness.textual_implementation.replace(request['harness_body'])
            for category in system.get_message_categories():system.clear_messages(category)
            stage('rebuilding')
            app.rebuild()
            stage('generating_code')
            app.generate_code()
            result['diagnostics']=messages()
            result['compile_errors']=sum(len(system.get_message_objects(c,Severity.Error)) for c in system.get_message_categories())
            if result['compile_errors']:raise RuntimeError('CODESYS reported compiler errors')
            image=os.path.join(folder,'compiled.app')
            stage('creating_boot_image')
            app.create_boot_application(image)
            if not os.path.isfile(image) or os.path.getsize(image)==0:raise RuntimeError('CODESYS produced no compiled application image')
            with open(image,'rb') as stream:result['compiled_image_sha256']=hashlib.sha256(stream.read()).hexdigest()
            result['target_compile']='passed'
            stage('saving_project')
            project.save()
            if request['action']=='simulate':
                # Simulation is rechecked immediately before every online operation.
                if not device.get_simulation_mode():raise RuntimeError('Simulation mode changed before login')
                with online.create_online_application(app) as connection:
                    connection.login(OnlineChangeOption.Never,False)
                    try:
                        connection.reset(ResetOption.Cold)
                        connection.start()
                        started=time.time()
                        while str(connection.read_value('PLC_PRG.WB_Done')).upper() not in ('TRUE','BOOL#TRUE'):
                            if time.time()-started>30:raise RuntimeError('Simulation harness did not complete in 30 seconds')
                            system.delay(50)
                        connection.stop()
                        rows=[]
                        for index in range(request['row_count']):
                            row={}
                            # IronPython 2 dictionaries do not preserve the host's port order.
                            for output_no,name in enumerate(request['output_names']):
                                row[name]=str(connection.read_value('PLC_PRG.WB_Out{0}[{1}]'.format(output_no,index)))
                            rows.append(row)
                        result['actual_rows']=rows
                    finally:
                        try:connection.stop()
                        finally:connection.logout()
            result['status']='completed'
    except Exception as exc:
        result['message']=str(exc)
        result['traceback']=traceback.format_exc()
        try:result['diagnostics']=messages()
        except Exception:pass
    finally:
        if project is not None:
            try:
                stage('closing_project')
                project.close()
            except Exception:pass
        with codecs.open(request['output'],'w','utf-8') as stream:
            stream.write(json.dumps(result,ensure_ascii=True,indent=2))
    stage('response_written')
    if result['status']=='error':system.exit(1)

if __name__=='__main__':main()
