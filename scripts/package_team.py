"""Create an allowlisted team source ZIP; no local state or account data."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from plc_agent.config import ModelConfig
from plc_agent.deepseek_credentials import candidates

FOLDERS=('plc_agent','plc_probe','tests','scripts','docs','backend_extensions','examples','experiments','reports')
ROOT_FILES=('launch.cmd','requirements.lock','.env.example','.gitignore','AGENT_README.md','README_TEAM.md')
OMIT_PARTS={'__pycache__','.git','.venv','.runtime','agent_data','node_modules'}
ACCOUNT_KEYS={'balance','balance_after','before_balance','after_balance','balance_infos',
              'credential_file','credential_fingerprint','credentials','credential_discovery'}


def digest(data):return hashlib.sha256(data).hexdigest()


def public_json(value):
    if isinstance(value,dict):return {k:public_json(v) for k,v in value.items() if k not in ACCOUNT_KEYS}
    if isinstance(value,list):return [public_json(v) for v in value]
    return value


def make_zip(stage,archive):
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as output:
        for path in sorted(stage.rglob('*')):
            if path.is_file():output.write(path,stage.name+'/'+path.relative_to(stage).as_posix())
    with zipfile.ZipFile(archive) as verify:
        bad=verify.testzip()
        if bad:raise ValueError('ZIP CRC failed: '+bad)
    checksum=digest(archive.read_bytes())
    archive.with_suffix('.zip.sha256').write_text(checksum+'  '+archive.name+'\n',encoding='ascii')
    return checksum


def contains_secret(data,secrets,depth=0):
    if any(key in data for key in secrets):return True
    if depth<2 and data[:2]==b'PK':
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zipped:
                if sum(f.file_size for f in zipped.infolist())>64*1024*1024:return False
                return any(contains_secret(zipped.read(info),secrets,depth+1) for info in zipped.infolist() if not info.is_dir())
        except zipfile.BadZipFile:pass
    return False


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output-root',type=Path,default=ROOT.parents[1]/'分享包')
    parser.add_argument('--name',default='PLC-Workbench-R4-team-20261027');args=parser.parse_args()
    if Path(args.name).name!=args.name or not args.name.startswith('PLC-Workbench-'):raise ValueError('Invalid release folder name')
    output_root=args.output_root.resolve();output_root.mkdir(parents=True,exist_ok=True)
    stage=output_root/args.name
    if stage.exists():raise ValueError('Release folder already exists; choose a new name to preserve it')
    stage.mkdir();files=[];scrubbed=[]
    for folder in FOLDERS:
        for path in sorted((ROOT/folder).rglob('*')):
            if not path.is_file() or path.is_symlink():continue
            rel=path.relative_to(ROOT)
            if any(part in OMIT_PARTS for part in rel.parts) or path.suffix in ('.pyc','.pyo','.exe','.o','.dll'):continue
            if path.name=='preflight.json' or 'balance' in path.name.lower() and path.suffix=='.json':continue
            files.append((path,rel))
    files.extend((ROOT/name,Path(name)) for name in ROOT_FILES)
    files.append((ROOT/'README.md',Path('README_DEV.md')))
    files.append((ROOT/'README_TEAM.md',Path('README.md')))
    for original,rel in files:
        destination=stage/rel;destination.parent.mkdir(parents=True,exist_ok=True)
        data=original.read_bytes()
        if rel.suffix=='.json' and rel.parts[0] in ('experiments','reports'):
            try:
                value=json.loads(data.decode('utf-8-sig'));public=public_json(value)
                if public!=value:
                    data=(json.dumps(public,ensure_ascii=False,indent=2)+'\n').encode('utf-8');scrubbed.append(rel.as_posix())
            except (UnicodeError,ValueError):pass
        destination.write_bytes(data)
    course=ROOT/'course_materials' if (ROOT/'course_materials').is_dir() else ROOT.parents[2]/'输入'
    material_names=('Final project_CHINESE.docx','Final project_ENGLISH.docx','大作业题库json.zip','大作业题库.pdf')
    (stage/'course_materials').mkdir()
    for name in material_names:shutil.copy2(course/name,stage/'course_materials'/name)
    dependencies=json.loads((ROOT/'scripts/dependencies.json').read_text(encoding='utf-8'))
    wheel_folder=stage/'vendor/wheels';wheel_folder.mkdir(parents=True)
    existing=ROOT/'vendor/wheels' if (ROOT/'vendor/wheels').is_dir() else next((p/'_cache/plc-agent/wheels' for p in ROOT.parents if (p/'_cache/plc-agent/wheels').is_dir()),None)
    if existing is None:raise ValueError('Validated dependency wheels unavailable')
    for dependency in dependencies:
        wheel=existing/dependency['filename'];data=wheel.read_bytes()
        if digest(data)!=dependency['sha256']:raise ValueError('Wheel checksum mismatch: '+wheel.name)
        (wheel_folder/wheel.name).write_bytes(data)
    (stage/'AGENT_README.md').write_text('> 这是开发过程的详细使用记录；新电脑请先按根目录README.md启动。原机已配置/已导入的状态未随包携带。\n\n'+(stage/'AGENT_README.md').read_text(encoding='utf-8'),encoding='utf-8')
    secrets={key.encode() for key,_ in candidates(Path.home()/'Desktop/API keys')}
    configured=ModelConfig.load().api_key
    if configured:secrets.add(configured.encode())
    scanned=0
    for path in stage.rglob('*'):
        if path.is_file():
            scanned+=1
            if contains_secret(path.read_bytes(),secrets):raise ValueError('Private credential matched in '+str(path.relative_to(stage)))
    manifest={'schema':'plc-workbench-team-source-v1','release':'R4 team preview','created_date':'2026-10-27',
              'contains':'Source, course materials, historical public evidence, pinned Python wheels; no preinstalled compiler/runtime or model configuration.',
              'excludes':['agent_data','API credentials','account balance records','virtual environments','compiler/build caches','Node/npm dependencies'],
              'historical_json_account_fields_removed':scrubbed,
              'secret_scan':{'files_scanned':scanned,'exact_matches':0,'nested_zip_and_wheel_contents_checked':True},
              'files':{p.relative_to(stage).as_posix():{'size':p.stat().st_size,'sha256':digest(p.read_bytes())} for p in sorted(stage.rglob('*')) if p.is_file()}}
    (stage/'PACKAGE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    archive=output_root/(stage.name+'.zip');checksum=make_zip(stage,archive)
    print(json.dumps({'archive':str(archive),'readme':str(stage/'README.md'),'size_bytes':archive.stat().st_size,'files':len(manifest['files'])+1,'sha256':checksum},ensure_ascii=False))


if __name__=='__main__':main()
