"""Observed limits of the pinned backend; do not treat a missing backend as good code."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from plc_probe.config import toolchain_dir
from .config import ROOT


def preflight(question):
    manifest_path=ROOT/'docs/backend_capabilities.json'
    if not manifest_path.exists():return None
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    for relative,expected in manifest['fingerprints'].items():
        path=toolchain_dir()/relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:return None
    text=question['text']
    for rule in manifest['unsupported']:
        if re.search(rule['pattern'],text,re.I):
            return {'status':rule['status'],'feature':rule['feature'],'message':rule['message'],
                    'basis':rule['evidence'],'behavior_tested':False,'candidate_correctness':'not_established'}
    return None


def candidate_warnings(code,question_id):
    if question_id!='18':return []
    clean=re.sub(r'\(\*.*?\*\)|//[^\n]*','',code,flags=re.S)
    body=re.sub(r'\bVAR(?:_INPUT|_OUTPUT|_IN_OUT)?\b.*?\bEND_VAR\b','',clean,flags=re.I|re.S)
    missing=[name for name in ('item','buffer') if not re.search(r'\b'+name+r'\b',body,re.I)]
    if missing:
        return [{'kind':'missing_required_data_access','fields':missing,
                 'message':'FIFO正文未访问这些数据参数；仅维护计数或状态不能实现题目要求的元素存取。需修复，不能只归因于后端不支持。'}]
    return []
