"""Extract and exercise a team source ZIP without using any model credentials."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from plc_probe.config import toolchain_dir,base_cache_dir


def run(command,cwd,env,timeout=180):
    result=subprocess.run(list(map(str,command)),cwd=cwd,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
    if result.returncode:raise RuntimeError('Package check failed: '+str(command[:3])+'\n'+result.stderr[-3000:]+'\n'+result.stdout[-3000:])
    return result.stdout


def main():
    parser=argparse.ArgumentParser();parser.add_argument('archive',type=Path);args=parser.parse_args()
    archive=args.archive.resolve()
    qa_root=base_cache_dir().parent/'plc-agent/package-qa';qa_root.mkdir(parents=True,exist_ok=True)
    temporary=Path(tempfile.mkdtemp(prefix='PLC-team-package-中文-',dir=qa_root))
    with zipfile.ZipFile(archive) as package:
        assert package.testzip() is None
        names=package.namelist();top=names[0].split('/')[0]
        for name in names:
            target=(temporary/name).resolve()
            if not target.is_relative_to(temporary.resolve()):raise ValueError('Archive traversal')
            if any(part in ('agent_data','.venv','.runtime','__pycache__','node_modules','.git') for part in Path(name).parts):raise ValueError('Private/cache member found')
        package.extractall(temporary)
    project=temporary/top
    manifest=json.loads((project/'PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
    for name,expected in manifest['files'].items():
        data=(project/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=expected['sha256']:raise ValueError('Package manifest mismatch: '+name)
    env={k:v for k,v in os.environ.items() if not k.startswith('PLC_AGENT_') and k not in ('STRUC_PP_HOME','PLC_PROBE_CACHE')}
    env['PYTHONUTF8']='1'
    shell=shutil.which('powershell.exe') or shutil.which('pwsh')
    setup=run([shell,'-NoProfile','-ExecutionPolicy','Bypass','-File',project/'scripts/setup.ps1','-ProjectLocal'],project,env)
    python=project/'.venv/Scripts/python.exe'
    assert python.is_file()
    (temporary/'setup.log').write_text(setup,encoding='utf-8')
    doctor=json.loads(run([python,'-B','-m','plc_agent','doctor'],project,env))
    assert doctor['status']=='setup_required' and doctor['has_api_key'] is False
    launch=json.loads(run([shell,'-NoProfile','-ExecutionPolicy','Bypass','-File',project/'scripts/launch.ps1','-CheckOnly'],project,env))
    assert launch['status']=='setup_required' and launch['has_api_key'] is False
    fixture=temporary/'smoke.py'
    fixture.write_text('''import asyncio,json
from pathlib import Path
from plc_agent.config import ModelConfig
from plc_agent.storage import Project,Session
from plc_agent.attachments import attach
from plc_agent.bank_contracts import questions
from plc_agent.toolbox import Toolbox
from plc_agent.tui import Workbench
async def main():
 cfg=ModelConfig.load();assert cfg.api_key=="" and cfg.base_url==""
 project=Project.create("分享包自检");session=Session.create(project)
 data=Path("README.md")
 assert attach(project,data)[0]["status"]=="ready"
 assert len(questions())==20
 tools=Toolbox(session)
 assert tools.call("write_file",{"path":"blocked.st","content":"forbidden"})["status"]=="blocked_by_plan_mode"
 app=Workbench(session,cfg)
 async with app.run_test(size=(120,40)) as pilot:
  app.command("/solve 05")
  for _ in range(50):
   await pilot.pause(.05)
   if not app.busy:break
  assert not app.busy and session.data["plan"] and not (project.workspace/"candidate.st").exists()
 print(json.dumps({"ui_mounted":True,"upload":True,"plan_only":True,"questions":20,"model_calls":0}))
asyncio.run(main())
''',encoding='utf-8')
    smoke_env={**env,'PYTHONPATH':str(project)}
    smoke=json.loads(run([python,'-B',fixture],project,smoke_env))
    # The package intentionally does not ship a compiler; exercise relocation
    # against this host's explicitly verified R4 backend, without model calls.
    replay_env={**env,'STRUC_PP_HOME':str(toolchain_dir()),'PLC_PROBE_CACHE':str(temporary/'build-cache')}
    replay=run([python,'-B','-m','plc_agent.check_bank','--ids','03,08,18','--output',temporary/'bank_check.json'],project,replay_env,timeout=180)
    rows=[json.loads(line) for line in replay.splitlines() if line.startswith('{')]
    assert len(rows)==3 and all(row['status']=='pass' for row in rows)
    result={'archive':str(archive),'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
            'status':'pass','zip_crc':True,'manifest_files_checked':len(manifest['files']),
            'fresh_project_local_venv':True,'windows_powershell_startup_checked':True,'model_key_present':False,
            'tui_and_upload_and_plan':smoke,'offline_candidate_replay':rows,'model_calls':0,
            'compiler_note':'Used host R4 backend only for relocation replay. No compiler or private backend selection is inside the ZIP.',
            'qa_directory':str(temporary)}
    archive.with_suffix('.validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'pass','files_checked':len(manifest['files']),'fresh_venv':True,'model_calls':0,'offline_replay_questions':[r['question_id'] for r in rows]},ensure_ascii=False))


if __name__=='__main__':main()
