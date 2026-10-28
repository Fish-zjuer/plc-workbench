"""Run inside CODESYS, never in the normal Python interpreter."""
from __future__ import print_function
import io
import json
import os
import traceback
from scriptengine import PouType, Severity

job_file = os.environ['PLC_CODESYS_JOB']
with io.open(job_file, 'r', encoding='utf-8') as stream:
    job = json.load(stream)
result = {'status': 'tool_error', 'stage': 'started'}

def save():
    with io.open(job['output'], 'w', encoding='utf-8') as stream:
        stream.write(unicode(json.dumps(result, ensure_ascii=True, indent=2)))

save()
try:
    project = projects.open(job['project'])
    # The shipped Standard.project contains a legacy PLCWinNT target. Upgrade
    # only our copied test project to the locally installed compiler target.
    for device in project.get_children(True):
        if getattr(device, 'is_device', False) and device.get_name() == 'PLCWinNT':
            device.update(type=4096, id='0000 0004', version='3.5.22.40')
    app = project.active_application
    if app is None:
        raise ValueError('Template has no active application')
    result['stage'] = 'opened'
    libman = app.get_library_manager()
    result['libraries_before'] = list(libman.get_libraries())
    for library in list(libman.get_libraries()):
        if library.startswith('IoStandard, 3.1.3.1'):
            libman.remove_library(library)
            libman.add_library('IoStandard, 3.5.22.0 (System)')
    result['libraries'] = list(libman.get_libraries())
    save()
    pou = app.create_pou(name='ProbeFB', type=PouType.FunctionBlock)
    pou.textual_declaration.replace(job['declaration'])
    pou.textual_implementation.replace(job['implementation'])
    programs = [o for o in app.find('PLC_PRG', True)
                if getattr(o, 'has_textual_declaration', False)]
    if len(programs) != 1:
        raise ValueError('Expected one editable PLC_PRG')
    programs[0].textual_declaration.replace('PROGRAM PLC_PRG\nVAR\n  uut : ProbeFB;\nEND_VAR')
    programs[0].textual_implementation.replace('uut();')
    for category in system.get_message_categories():
        system.clear_messages(category)
    result['stage'] = 'compiling'
    save()
    app.generate_code()
    errors = []
    messages = []
    for category in system.get_message_categories():
        for message in system.get_message_objects(category):
            row = {'severity': str(message.severity), 'text': str(message)}
            messages.append(row)
            if message.severity in (Severity.Error, Severity.FatalError):
                errors.append(row)
    result.update(status='compile_error' if errors else 'pass', stage='compiled',
                  errors=errors, messages=messages)
    if result['status'] == 'pass' and job.get('negative_control', False):
        # Verify the adapter also rejects a deliberately invalid program.
        pou.textual_implementation.replace('MissingInstallationProbeSymbol := TRUE;')
        for category in system.get_message_categories():
            system.clear_messages(category)
        app.generate_code()
        rejected = []
        for category in system.get_message_categories():
            for message in system.get_message_objects(category):
                if message.severity in (Severity.Error, Severity.FatalError):
                    rejected.append(str(message))
        result['negative_control'] = {'rejected': bool(rejected), 'errors': rejected}
        if not rejected:
            result['status'] = 'tool_error'
            result['error'] = 'Compiler accepted an intentionally invalid program'
        pou.textual_implementation.replace(job['implementation'])
    project.save()
    project.close()
except Exception:
    result.update(status='tool_error', error=traceback.format_exc())
save()
