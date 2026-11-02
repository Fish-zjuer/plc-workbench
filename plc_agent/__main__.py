"""One application entry: web UI, plus CODESYS environment utilities."""
from __future__ import annotations
import argparse
import sys


def main():
    if sys.argv[1:2] == ['tia']:
        from .tia_cli import main as tia_main
        return tia_main(sys.argv[2:])
    if sys.argv[1:2] == ['web']:
        from .web import main as web_main
        return web_main(args[1:])
    if args[0]=='codesys':
        from .codesys_cli import main as codesys_main
        return codesys_main(args[1:])
    parser=argparse.ArgumentParser(description='PLC Workbench: start the web app or configure CODESYS')
    parser.add_argument('command',choices=('web','codesys'),nargs='?',help='Default: web; historical tools: python -m plc_agent.legacy --help')
    parser.parse_args(args)
    return 0


if __name__=='__main__':raise SystemExit(main())
