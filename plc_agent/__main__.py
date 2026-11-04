"""One application entry: web UI, plus CODESYS and TIA environment utilities."""
from __future__ import annotations
import argparse
import sys


def main():
    args=sys.argv[1:]
    if not args:
        from .web import main as web_main
        return web_main(['--port','18765','--open-browser'])
    if args[0]=='tia':
        from .tia_cli import main as tia_main
        return tia_main(args[1:])
    if args[0]=='web':
        from .web import main as web_main
        return web_main(args[1:])
    if args[0]=='codesys':
        from .codesys_cli import main as codesys_main
        return codesys_main(args[1:])
    parser=argparse.ArgumentParser(description='PLC Workbench: start the web app or configure CODESYS/TIA')
    parser.add_argument('command',choices=('web','codesys','tia'),nargs='?',help='Default: web; historical tools: python -m plc_agent.legacy --help')
    parser.parse_args(args)
    return 0


if __name__=='__main__':raise SystemExit(main())
