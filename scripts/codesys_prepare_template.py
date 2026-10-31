"""Run ONLY inside installed CODESYS V3.5 SP22 Patch 4 scripting engine.
Copies Standard.project and upgrades legacy PLCWinNT/IoStandard references.
Requires WB_TEMPLATE_SOURCE and WB_TEMPLATE_TARGET environment variables.
Never connects to a PLC. Always run positive/negative controls afterwards.
"""
from scriptengine import projects, system
import os, shutil
source=os.environ['WB_TEMPLATE_SOURCE']; target=os.environ['WB_TEMPLATE_TARGET']
if os.path.abspath(source)==os.path.abspath(target) or os.path.exists(target):
 raise RuntimeError('Choose a new target path; source and existing projects are preserved')
shutil.copyfile(source,target)
p=projects.open(target)
try:
 for d in p.get_children(True):
  if getattr(d,'is_device',False) and d.get_name()=='PLCWinNT':
   d.update(type=4096,id='0000 0004',version='3.5.22.40')
 app=p.active_application
 lm=app.get_library_manager()
 for lib in list(lm.get_libraries()):
  if lib.startswith('IoStandard, 3.1.3.1'):
   lm.remove_library(lib); lm.add_library('IoStandard, 3.5.22.0 (System)')
 programs=[o for o in app.find('PLC_PRG',True) if getattr(o,'has_textual_declaration',False)]
 if len(programs)!=1:raise RuntimeError('Expected one editable PLC_PRG')
 programs[0].textual_declaration.replace('PROGRAM PLC_PRG\nVAR\nEND_VAR')
 programs[0].textual_implementation.replace('')
 p.save()
finally:p.close()
