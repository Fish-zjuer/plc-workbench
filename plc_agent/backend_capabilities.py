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
    warnings=[]
    try:
        from .st_source import mask_noncode
        clean=mask_noncode(code)
    except ValueError:
        clean=code
    if re.search(r'\bCONTINUE\b',clean,re.I):
        warnings.append({'kind':'unsupported_continue',
                         'message':'行为后端 STruC++ 0.7.0 不支持 CONTINUE；请用嵌套 IF/ELSIF 或布尔标志实现跳过逻辑。'})
    if re.search(r'\bELSE\s*:',clean,re.I):
        warnings.append({'kind':'case_else_colon',
                         'message':'CASE 的 ELSE 分支不写冒号：用 ELSE，不要用 ELSE:。'})
    if question_id=='14':
        bad=[]
        if re.search(r'\bCHAR\b',clean,re.I):bad.append('CHAR')
        if '.at(' in clean:bad.append('.at()')
        if re.search(r'\bipText\s*\[',clean,re.I):bad.append('ipText[]')
        if re.search(r'[A-Za-z_]\w*\s*\^',clean):bad.append('^ dereference')
        if bad:
            warnings.append({'kind':'unsupported_string_syntax','features':bad,
                             'message':'该目标不支持这些 STRING 语法。请用 p := ADR(ipText); b := p[i]; n := LEN(ipText) 的 BYTE 指针索引方式，并删除 CHAR/^/ipText[]/.at()。'})
    elif question_id=='18':
        body=re.sub(r'\bVAR(?:_INPUT|_OUTPUT|_IN_OUT)?\b.*?\bEND_VAR\b','',clean,flags=re.I|re.S)
        missing=[name for name in ('item','buffer') if not re.search(r'\b'+name+r'\b',body,re.I)]
        if missing:
            warnings.append({'kind':'missing_required_data_access','fields':missing,
                             'message':'FIFO正文未访问这些数据参数；仅维护计数或状态不能实现题目要求的元素存取。需修复，不能只归因于后端不支持。'})
    return warnings
