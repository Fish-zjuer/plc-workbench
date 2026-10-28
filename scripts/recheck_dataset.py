"""Double native replay of frozen saved candidates; zero model calls."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path
from plc_agent import dataset
from plc_agent.config import ROOT
from plc_agent.storage import atomic_json

def main():
    out=ROOT/'experiments/dataset_r8/final_recheck';out.mkdir(parents=True,exist_ok=True);rows=[]
    def one(entry):
        ident=entry['id'];task=dataset.load(ident);source=ROOT/'experiments/dataset_r8/tasks'/ident/'final.st'
        first=dataset.evaluate(source,task);second=dataset.evaluate(source,task)
        if first!=second:raise ValueError('Non-deterministic replay: '+ident)
        directory=out/ident;directory.mkdir(exist_ok=True)
        atomic_json(directory/'evaluation_1.json',first);atomic_json(directory/'evaluation_2.json',second)
        print(ident+' '+first['status'],flush=True)
        return {k:v for k,v in first.items() if k!='cases'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(one,t) for t in dataset.catalog()['tasks']]):
            rows.append(future.result());rows.sort(key=lambda r:r['task_id'])
            atomic_json(out/'results.json',{'model_calls':0,'replays_per_task':2,'results':rows,
                'scope':'Same saved model programs recompiled/replayed on current code. Supplied finite tests, not independent regeneration or full LTL proof.'})

if __name__=='__main__':main()
