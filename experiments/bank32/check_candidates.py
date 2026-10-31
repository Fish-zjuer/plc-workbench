"""Batch-check existing ST files, without any model call."""
import argparse
import json
from pathlib import Path
import threading
from plc_agent.campaign import validate_vendor_environment
from plc_agent.codesys_dataset import evaluate_candidate
from plc_agent import codesys
from plc_agent.config import STATE_ROOT
from plc_agent.imported_bank import ImportedBank
from plc_agent.storage import atomic_json


def main():
    parser=argparse.ArgumentParser(description='Batch local tests + actual CODESYS compilation of saved ST')
    parser.add_argument('--manifest',required=True,type=Path,help='JSON list of {task_id, source}')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--home',type=Path,default=STATE_ROOT)
    parser.add_argument('--local-only',action='store_true')
    args=parser.parse_args()
    entries=json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    if not isinstance(entries,list) or not entries:raise ValueError('Nonempty list required')
    if args.output.exists():raise ValueError('Output directory already exists; choose a new one')
    bank=ImportedBank(args.home)
    jobs=[]
    for entry in entries:
        task=bank.load(entry['task_id']);source=Path(entry['source'])
        if not source.is_absolute():source=args.manifest.resolve().parent/source
        if not source.is_file():raise ValueError('Source missing: '+str(source))
        jobs.append((task,source))
    vendor=None if args.local_only else codesys.load_config(args.home)
    if vendor is not None:codesys.validate_config(vendor)
    args.output.mkdir(parents=True)
    if vendor is not None:validate_vendor_environment(vendor,args.output/'vendor_environment',threading.Event())
    results=[]
    for index,(task,source) in enumerate(jobs):
        folder=args.output/str(index);folder.mkdir()
        snapshot=folder/'candidate.st';snapshot.write_bytes(source.read_bytes())
        atomic_json(folder/'task_snapshot.json',task)
        result=evaluate_candidate(snapshot,task,vendor)
        result.update(task_id=task['id'],dataset_sha256=task['dataset_sha256'],model_calls=0)
        atomic_json(folder/'evaluation.json',result);results.append(result)
        atomic_json(args.output/'results.json',{'results':results,'model_calls':0,'vendor_required':not args.local_only})
        print(task['id'],result['status'],result.get('target_compile'),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
