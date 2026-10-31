"""Discover existing local toolchains for double-click launches (no installation)."""
import os
from pathlib import Path
import shutil
from .config import ROOT


def configure_tools():
    candidates=[ROOT/'.runtime/mingw64/bin/g++.exe',
                Path.home()/'.cache/plc-workbench-toolchains/mingw64/bin/g++.exe']
    cxx=os.environ.get('CXX') or shutil.which('g++')
    if not cxx:
        cxx=next((str(p) for p in candidates if p.is_file()),None)
        if cxx:os.environ['CXX']=cxx
    if cxx:
        folder=str(Path(cxx).resolve().parent)
        if folder.lower() not in [p.lower() for p in os.environ.get('PATH','').split(os.pathsep)]:
            os.environ['PATH']=folder+os.pathsep+os.environ.get('PATH','')
    return {'cxx':cxx}
