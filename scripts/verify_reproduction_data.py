"""Offline verification of portable dataset bytes; no model or compiler calls."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    manifest=json.loads((ROOT/'datasets/reproduction_manifest.json').read_text(encoding='utf-8'))
    failures=[]
    for name,entry in manifest['files'].items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():failures.append(name);continue
        data=path.read_bytes()
        if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:failures.append(name)
    for path in (ROOT/'datasets/importable').glob('*.json'):
        bank=json.loads(path.read_text(encoding='utf-8-sig'));tasks=bank['tasks']
        ids=[t['id'] for t in tasks]
        if len(ids)!=len(set(ids)):failures.append(str(path)+': duplicate IDs')
        print(path.name, len(tasks),'tasks',sum(len(t.get('scenarios',[])) for t in tasks),'scenarios')
    if failures:raise SystemExit('FAILED: '+', '.join(failures))
    print('PASS:',len(manifest['files']),'input files verified')

if __name__=='__main__':main()
