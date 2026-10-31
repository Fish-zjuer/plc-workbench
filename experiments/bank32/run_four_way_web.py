"""CLI equivalent of the web 2x2 runner. Does not start paid work without --execute."""
import argparse
import json
from pathlib import Path
import time
from plc_agent.campaign import Campaigns, preflight, dataset_catalog
from plc_agent.config import STATE_ROOT

def main():
    parser=argparse.ArgumentParser(description='self/Codex × two DMXAPI models')
    parser.add_argument('--model-a',required=True);parser.add_argument('--model-b',required=True)
    parser.add_argument('--ids',default='all',help='all or comma-separated built-in/imported IDs')
    parser.add_argument('--home',type=Path,default=STATE_ROOT)
    parser.add_argument('--local-only',action='store_true',help='Pilot only, not CODESYS assignment evidence')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--concurrency',type=int,default=16,metavar='N',help='Maximum simultaneous tasks (default: 16)')
    args=parser.parse_args()
    info=preflight(args.home,not args.local_only)
    print(json.dumps(info,ensure_ascii=False,indent=2))
    if not args.execute:return 0
    runner=Campaigns(args.home)
    ids=[t['id'] for t in dataset_catalog()] if args.ids=='all' else args.ids.split(',')
    job=runner.start({'models':[args.model_a,args.model_b],'task_ids':ids,'codesys':not args.local_only,'concurrency':args.concurrency})
    try:
        while True:
            state=runner.read(job['id'])
            print(state['status'],state['completed'],'/',state['total'],flush=True)
            if state['status']!='running':break
            time.sleep(5)
    except KeyboardInterrupt:
        runner.stop(job['id'])
        while job['id'] in runner.active:time.sleep(.25)
        return 130
    print(json.dumps(state['summary'],ensure_ascii=False,indent=2))
    return 0 if state['status']=='completed' else 1

if __name__=='__main__':raise SystemExit(main())
