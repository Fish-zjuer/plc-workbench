"""Independently replay every published SMT query without model calls or a compiler."""
import argparse
import hashlib
import json
from pathlib import Path
from plc_agent.config import ROOT
from plc_agent.formal_verify import replay_query

def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',nargs='?',type=Path,default=ROOT/'experiments/formal_r7');args=parser.parse_args()
    reports=queries=0
    for report in args.root.rglob('formal.json'):
        value=json.loads(report.read_text(encoding='utf-8'));reports+=1
        for item in value['queries']:
            path=(report.parent/item['file']).resolve()
            if path.parent!=report.parent.resolve():raise ValueError('Invalid evidence path')
            if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Query changed: '+str(path))
            actual=replay_query(path)
            if actual!=item['result']:raise ValueError('Solver result changed: '+str(path))
            queries+=1
    print(json.dumps({'status':'verified','reports':reports,'queries':queries,'model_calls':0}))

if __name__=='__main__':main()
