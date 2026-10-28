"""Executed by the CODESYS IronPython scripting engine; no PLC connection."""
from __future__ import print_function
import io
import json
import os
import shutil
import time
import traceback
from scriptengine import PouType, Severity


def write(path, value):
    encoded = unicode(json.dumps(value, ensure_ascii=True, indent=2))
    with io.open(path, 'w', encoding='utf-8') as stream:
        stream.write(encoded)


def clear():
    for category in system.get_message_categories():
        system.clear_messages(category)


def messages():
    rows = []
    for category in system.get_message_categories():
        for message in system.get_message_objects(category):
            rows.append({'severity': str(message.severity), 'text': str(message),
                         'number': int(message.number) if message.number is not None else None,
                         'prefix': str(message.prefix) if message.prefix is not None else None})
    return rows


def errors(rows):
    return [m for m in rows if m['severity'] in ('Error', 'FatalError')]


def main_program(app):
    programs = [o for o in app.find('PLC_PRG', True)
                if getattr(o, 'has_textual_declaration', False)]
    if len(programs) != 1: raise ValueError('Expected one editable PLC_PRG')
    return programs[0]


with io.open(os.environ['PLC_CODESYS_BANK_JOB'], 'r', encoding='utf-8') as stream:
    job = json.load(stream)
environment = {'status': 'tool_error', 'run_id': job['run_id']}
project = None
try:
    project = projects.open(job['base_project'])
    for device in project.get_children(True):
        if getattr(device, 'is_device', False) and device.get_name() == 'PLCWinNT':
            device.update(**job['device'])
    app = project.active_application
    if app is None: raise ValueError('No active application')
    program = main_program(app)
    program.textual_declaration.replace('PROGRAM PLC_PRG\nVAR\nEND_VAR')
    program.textual_implementation.replace('')
    clear()
    app.generate_code()
    positive = messages()
    if errors(positive): raise ValueError('Clean template does not compile: ' + str(errors(positive)))
    program.textual_implementation.replace('MissingBankCompilerControl := TRUE;')
    clear()
    app.generate_code()
    negative = messages()
    if not errors(negative): raise ValueError('Invalid-code control was accepted')
    program.textual_implementation.replace('')
    clear()
    app.generate_code()
    if errors(messages()): raise ValueError('Clean template could not be restored')
    environment.update(status='pass', positive_messages=positive,
                       negative_control={'rejected': True, 'messages': negative},
                       libraries=list(app.get_library_manager().get_libraries()), device=job['device'])
    project.save()
    project.close()
    project = None
except Exception:
    environment['error'] = traceback.format_exc()
    if project is not None:
        try: project.close()
        except Exception: pass
write(job['environment_path'], environment)

if environment['status'] == 'pass':
    for task in job['tasks']:
        started = time.time()
        result = {'run_id': job['run_id'], 'question_id': task['question_id'],
                  'source_sha256': task['source_sha256'], 'stage': 'starting', 'status': 'tool_error'}
        write(task['result_path'], result)
        project = None
        try:
            if task.get('import_error'): raise ValueError(task['import_error'])
            shutil.copy2(job['base_project'], task['project_path'])
            project = projects.open(task['project_path'])
            app = project.active_application
            for unit in task['units']:
                if unit['kind'] == 'TYPE':
                    obj = app.create_dut(name=unit['name'])
                else:
                    kwargs = {'name': unit['name'], 'type': {'FUNCTION_BLOCK': PouType.FunctionBlock,
                              'FUNCTION': PouType.Function, 'PROGRAM': PouType.Program}[unit['kind']]}
                    if unit.get('return_type'): kwargs['return_type'] = unit['return_type']
                    obj = app.create_pou(**kwargs)
                obj.textual_declaration.replace(unit['declaration'])
                if 'implementation' in unit: obj.textual_implementation.replace(unit['implementation'])
            program = main_program(app)
            program.textual_declaration.replace(task['caller']['declaration'])
            program.textual_implementation.replace(task['caller']['implementation'])
            result['stage'] = 'compiling'
            write(task['result_path'], result)
            clear()
            app.generate_code()
            rows = messages()
            result.update(status='compile_error' if errors(rows) else 'pass', stage='compiled',
                          errors=errors(rows), warnings=[m for m in rows if m['severity'] == 'Warning'],
                          messages=rows)
            project.save()
        except Exception:
            result.update(status='import_error' if task.get('import_error') else 'tool_error',
                          message=traceback.format_exc())
        finally:
            if project is not None:
                try: project.close()
                except Exception: result['close_error'] = traceback.format_exc()
        result['seconds'] = round(time.time() - started, 3)
        write(task['result_path'], result)
        print('CODESYS task ' + task['question_id'] + ': ' + result['status'])
