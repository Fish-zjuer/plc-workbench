"""Build and select a pinned source extension; keep the release backend intact."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from functools import lru_cache

from plc_probe.config import base_cache_dir,backend_profile_path,cache_dir,toolchain_dir
from .config import ROOT
from .storage import atomic_json

COMMIT='fcccfbdf53704fad1f5e71dd2a05d440b9028b47'
REPO='https://github.com/Autonomy-Logic/STruCpp.git'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args,cwd,timeout=300):
    temporary=Path(cwd)/'.tmp';temporary.mkdir(exist_ok=True)
    result=subprocess.run(list(map(str,args)),cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout,
                          env={**os.environ,'TEMP':'.tmp','TMP':'.tmp','TMPDIR':'.tmp'})
    if result.returncode:raise RuntimeError(' '.join(map(str,args[:3]))+' failed:\n'+result.stderr[-5000:]+result.stdout[-2000:])
    return result.stdout


def build():
    if os.name!='nt':raise ValueError('Current R4 launcher build targets Windows; compiler patch/runtime remain portable')
    base=base_cache_dir();base.mkdir(parents=True,exist_ok=True);source=base/'upstream-strucpp';home=base/'strucpp-r4'
    patch=ROOT/'backend_extensions/strucpp_r4.patch'
    created=not source.exists()
    if created:
        run(['git','clone','--no-checkout',REPO,source],base)
        run(['git','-C',source,'checkout','--detach',COMMIT],base)
    head=run(['git','rev-parse','HEAD'],source).strip()
    if head!=COMMIT:raise ValueError('Compiler source is on a different commit; preserving existing checkout')
    check=subprocess.run(['git','apply','--check',str(patch)],cwd=source,capture_output=True)
    if check.returncode==0:run(['git','apply',patch],source)
    elif subprocess.run(['git','apply','--reverse','--check',str(patch)],cwd=source,capture_output=True).returncode:
        raise ValueError('Source differs from the pinned R4 patch; preserving local edits')
    npm=shutil.which('npm.cmd');node=shutil.which('node');cxx=os.environ.get('CXX') or shutil.which('g++')
    if not npm or not node or not cxx:raise ValueError('Need Node >=22, npm, git and g++ to rebuild R4')
    if not (source/'node_modules/typescript/bin/tsc').is_file():run([npm,'ci','--ignore-scripts','--no-audit','--no-fund'],source)
    log=run([npm,'run','build'],source)+run([node,'scripts/bundle.mjs'],source)
    home.mkdir(exist_ok=True)
    shutil.copy2(source/'dist/strucpp-bundle.cjs',home/'compiler.cjs')
    shutil.copytree(source/'src/runtime',home/'runtime',dirs_exist_ok=True)
    shutil.copytree(source/'libs',home/'libs',dirs_exist_ok=True,ignore=shutil.ignore_patterns('sources'))
    shutil.copy2(ROOT/'backend_extensions/compiler_shim.cpp',home/'shim.cpp')
    (home/'node-path.txt').write_text(node,encoding='utf-8')
    (home/'cli-path.txt').write_text(str(home/'compiler.cjs'),encoding='utf-8')
    run([cxx,'-std=c++17','-O2','-static','-municode','shim.cpp','-o','strucpp.exe'],home)
    hashes={str(p.relative_to(home)):sha(p) for p in [home/'strucpp.exe',home/'compiler.cjs',home/'shim.cpp',home/'node-path.txt',home/'cli-path.txt',
                                                     *sorted((home/'runtime/include').glob('*.hpp')),*sorted((home/'libs').glob('*.stlib'))]}
    manifest={'schema':1,'extension':'plc-workbench-r4-v1','variant_api':'PV1','source_commit':COMMIT,'upstream':REPO,
              'patch_sha256':sha(patch),'package_lock_sha256':sha(source/'package-lock.json'),
              'node_version':run([node,'--version'],home).strip(),'cxx_version':run([cxx,'--version'],home).splitlines()[0],
              'artifacts_sha256':hashes,'label':'STruC++ development fcccfbdf + PLC-R4; local reference ABI; not CODESYS'}
    manifest['fingerprint']=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
    atomic_json(home/'plc-r4.json',manifest)
    (home/'build.log').write_text(log,encoding='utf-8')
    for name in ('LICENSE','COPYING','COPYING.RUNTIME'):shutil.copy2(source/name,home/name)
    return home,manifest


def activate(home):
    manifest=json.loads((home/'plc-r4.json').read_text(encoding='utf-8'))
    if manifest.get('extension')!='plc-workbench-r4-v1':raise ValueError('Not a PLC-R4 backend')
    if not all(sha(home/path)==digest for path,digest in manifest['artifacts_sha256'].items()):raise ValueError('R4 artifact fingerprint mismatch; rebuild before selecting')
    atomic_json(backend_profile_path(),{'schema':1,'home':str(home),'fingerprint':manifest['fingerprint'],'label':manifest['label']})
    return manifest


def info():
    path=toolchain_dir()/'plc-r4.json'
    if not path.exists():return None
    metadata=json.loads(path.read_text(encoding='utf-8'))
    artifacts=[toolchain_dir()/relative for relative in metadata['artifacts_sha256']]
    if any(not p.is_file() for p in artifacts):raise ValueError('Selected R4 backend is incomplete; rebuild or select legacy')
    signature=tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in [path,*artifacts])
    return _verified_info(signature)


@lru_cache(maxsize=4)
def _verified_info(signature):
    path=Path(signature[0][0]);metadata=json.loads(path.read_text(encoding='utf-8'))
    if not all(sha(path.parent/relative)==digest for relative,digest in metadata['artifacts_sha256'].items()):
        raise ValueError('Selected R4 compiler/runtime changed without rebuilding its manifest; choose a verified backend')
    return metadata


def notes():
    if not info():return None
    return [
      'Backend is pinned STruC++ development fcccfbdf plus PLC-R4 source patch, not CODESYS or Siemens. Preserve the original task interface.',
      'LTIME and LT#/LTIME# literals are supported with signed int64 nanosecond storage. Duration literals emit exact integers. TIME_TO_LINT returns MILLISECONDS; LTIME_TO_LINT returns NANOSECONDS. LINT_TO_TIME expects milliseconds; LINT_TO_LTIME expects nanoseconds. TIME_TO_LTIME preserves duration. Prefer LTIME internal accumulators for long totals.',
      'ARRAY[*] has actual caller-owned reference binding, preserves each array lower bound. Match ordinal positions using each separate LOWER_BOUND. Do not mutate raw inputs/configuration. Promote INT to REAL or DINT BEFORE addition to avoid 16-bit overflow.',
      'VARIANT is the local PV1 typed reference descriptor. PV_COUNT(buffer) returns actual array length as DINT; PV_COMPATIBLE(buffer,item) checks array/scalar element type. PV_WRITE(buffer,index,item) stores item into the buffer; PV_READ(buffer,index,item) copies that buffer element into caller item. INDEX is zero-based ORDINAL position, not a ST array subscript. Both functions return BOOL and reject bounds/type errors without writes. Queue algorithm/state/edge detection must be implemented in ST, not by these helpers.',
      'For Q12 the frozen finite-check convention releases an alarm on the first valid clear scan after 500ms from its initial trigger; the text only specifies a minimum, so declare this timing assumption. Invalid signal clears holding immediately.',
      'TON starts elapsed=0 at first eligible invocation. STRING indexing .at() remains unsupported; use standard string operations. Native finite checks are not full vendor semantics or formal proof.',
    ]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('build','activate','status','legacy'));args=parser.parse_args()
    if args.command=='build':home,manifest=build();print(json.dumps({'home':str(home),'fingerprint':manifest['fingerprint']}))
    elif args.command=='activate':manifest=activate(base_cache_dir()/'strucpp-r4');print(json.dumps({'selected':manifest['label'],'cache':str(cache_dir())}))
    elif args.command=='legacy':backend_profile_path().unlink(missing_ok=True);print('Selected preserved release backend')
    else:print(json.dumps({'home':str(toolchain_dir()),'cache':str(cache_dir()),'r4':info()},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
