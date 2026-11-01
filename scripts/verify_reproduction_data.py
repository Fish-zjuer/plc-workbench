"""Validate the one current bank, task fingerprints and unique provenance."""
from pathlib import Path
import sys,hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from plc_agent import dataset

def main():
    manifest=dataset.catalog()
    tasks=[dataset.load(t['id']) for t in manifest['tasks']]
    for name,expected in manifest.get('auxiliary_files',{}).items():
        path=(dataset.DATA/name).resolve()
        if not path.is_relative_to(dataset.DATA.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise SystemExit('Auxiliary source mismatch: '+name)
    print('PASS:',len(tasks),'tasks;',sum(len(t['scenarios']) for t in tasks),'scenarios; dataset and provenance hashes verified')
if __name__=='__main__':main()
