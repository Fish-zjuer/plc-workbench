"""Validate saved R2 evidence without model calls or changing test predicates."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from .config import ROOT, ModelConfig
from .deepseek_credentials import candidates
from .storage import atomic_json, now


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    folder=ROOT/'experiments/workflow_r2'
    log=(folder/'regression_tests.log').read_text(encoding='utf-8-sig',errors='replace')
    match=re.search(r'Ran (\d+) tests in ([\d.]+)s',log)
    regression={'count':int(match[1]) if match else None,
                'duration_seconds':float(match[2]) if match else None,
                'passed':bool(match and re.search(r'\nOK\s*$',log))}
    frozen=read(ROOT/'experiments/deepseek_20/test_protocol.json')['implementation_sha256']
    frozen_checks={name:digest(ROOT/name)==expected for name,expected in frozen.items()}
    saved=read(folder/'verification.json')
    struct_protocol=read(folder/'struct_protocol.json')
    struct_checks={'protocol_matches_replay':digest(folder/'struct_protocol.json')==saved['struct_protocol_sha256'],
                   'implementation_matches_protocol':digest(ROOT/'plc_agent/struct_checks.py')==struct_protocol['implementation_sha256']}
    replay={row['question_id']:row for row in saved['results']}
    results=read(folder/'results.json')['results']
    source_checks={}
    for row in results:
        qid=row['question_id']; receipt=row['receipt']
        if receipt['status']!='verified':continue
        recorded=read(Path(row['receipt_path']))
        final=folder/'tasks'/qid/'final.st'
        live=ROOT/'agent_data/projects'/row['project_id']/'workspace'/receipt['source']
        source_checks[qid]={
            'final_and_project_match_receipt':digest(final)==digest(live)==receipt['source_sha256'],
            'saved_receipt_matches_result':recorded==receipt,
            'final_evaluation_passed':receipt['final_evaluation']['status']=='pass',
            'two_replays_passed':replay[qid]['statuses']==['pass','pass'] and replay[qid]['source_matches_receipt']}
    # Compare exact authorized secrets in memory. Never serialize the values or hashes.
    secrets={key.encode() for key,_ in candidates(Path.home()/'Desktop/API keys')}
    configured=ModelConfig.load().api_key
    if configured:secrets.add(configured.encode())
    hits=[];scanned=0
    for path in ROOT.rglob('*'):
        if not path.is_file():continue
        relative=path.relative_to(ROOT)
        if relative.parts[:2]==('agent_data','private') or any(part in ('__pycache__','.git','.venv') for part in relative.parts):continue
        data=path.read_bytes();scanned+=1
        if any(secret in data for secret in secrets):hits.append(str(relative))
    all_checks=(regression['passed'] and all(frozen_checks.values()) and all(struct_checks.values())
                and len(source_checks)==16 and all(all(row.values()) for row in source_checks.values()) and not hits)
    output={'checked_at':now(),'status':'pass' if all_checks else 'fail',
            'regression':regression,'frozen_original_predicates_unchanged':frozen_checks,
            'supplementary_struct_checks':struct_checks,'verified_source_identity':source_checks,
            'exact_secret_scan':{'files_scanned':scanned,'secrets_available_for_comparison':len(secrets),
                                 'excluded':'Local agent_data/private credential storage; interpreter/cache directories',
                                 'matches':hits},
            'runtime_sha256':{str(path.relative_to(ROOT)):digest(path) for path in sorted((ROOT/'plc_agent').glob('*.py'))},
            'limits':'Checks saved finite-test evidence, code identity and regression log; no CODESYS or formal proof.'}
    atomic_json(folder/'final_validation.json',output)
    print(json.dumps({'status':output['status'],'regression':regression,'verified_sources':len(source_checks),
                      'secret_matches':len(hits),'files_scanned':scanned}))
    return 0 if all_checks else 1


if __name__=='__main__':raise SystemExit(main())
