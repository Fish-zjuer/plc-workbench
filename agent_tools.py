"""Absolute-path entry point for local MCP stdio clients."""
import sys
from plc_probe.server import serve

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    serve()
