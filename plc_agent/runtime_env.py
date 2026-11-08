"""Discover existing local toolchains for double-click launches (no installation)."""
import os
from pathlib import Path
import shutil
from plc_agent.config import ROOT


def configure_tools():
    # Desktop-launched processes may omit Windows PowerShell from PATH even
    # though it is installed. The pinned Codex CLI uses powershell.exe for tools.
    if os.name=='nt' and not shutil.which('powershell.exe'):
        shell=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
        if shell.is_file():
            os.environ['PATH']=str(shell.parent)+os.pathsep+os.environ.get('PATH','')
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
