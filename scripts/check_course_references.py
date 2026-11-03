"""Real tool regression for PUBLIC_08/18, including payload/frame mutants."""
import argparse
import json
from pathlib import Path
import tempfile

from plc_agent.config import ROOT
from plc_agent.dataset import load
from plc_agent.plcverif_backend import DEFAULTS, discover_tools, verify


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--temp-root',required=True)
    p.add_argument('--output',default='outputs/course-reference-regression')
    p.add_argument('--numeric-domain',choices=['ieee','boundary'],default='boundary')
    p.add_argument('--fifo-bound',type=int,default=4)
    p.add_argument('--timeout',type=int,default=180)
    p.add_argument('--tasks',choices=['08','18','all'],default='all')
    args=p.parse_args()
    temporary=Path(args.temp_root).resolve()
    if not temporary.is_dir() or not str(temporary).isascii():p.error('--temp-root must be an existing ASCII writable directory')
    tempfile.tempdir=str(temporary)
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    q08=(ROOT/'examples/formal/Q08.st').read_text(encoding='utf-8')
    q18=(ROOT/'examples/formal/Q18.st').read_text(encoding='utf-8')
    # Mutations alter only candidate code, never the frozen requirements or
    # observers. These are integration checks, not a native vendor ABI test.
    raw_marker='aLower := LOWER_BOUND(analogValues, 1);'
    cfg_marker='cLower := LOWER_BOUND(channels, 1);'
    assert raw_marker in q08 and cfg_marker in q08 and 'PV_WRITE(buffer, diTail, item)' in q18
    checks=[('08_correct','PUBLIC_08',q08,'bounded_pass'),
            ('18_correct','PUBLIC_18',q18,'bounded_pass'),
            ('08_raw_write','PUBLIC_08',q08.replace(raw_marker,raw_marker+'\nanalogValues[aLower] := INT#0;'),'counterexample'),
            ('08_config_write','PUBLIC_08',q08.replace(cfg_marker,cfg_marker+'\nchannels[cLower].hiLIM := 0.0;'),'counterexample'),
            ('18_count_only','PUBLIC_18',q18.replace('PV_WRITE(buffer, diTail, item)','TRUE'),'counterexample'),
            ('18_missing_read','PUBLIC_18',q18.replace('PV_READ(buffer, diHead, item)','TRUE'),'counterexample'),
            ('18_wrong_empty_status','PUBLIC_18',q18.replace('status := 16#8001;','status := 16#8002;'),'counterexample')]
    summary=[]
    for name,ident,source,expected in checks:
        if args.tasks!='all' and ident!='PUBLIC_'+args.tasks:continue
        path=out/(name+'.st');path.write_text(source,encoding='utf-8')
        cfg={**DEFAULTS,**discover_tools(),'bound':3 if ident=='PUBLIC_08' else args.fifo_bound,
             'unwind':16,'timeout_seconds':args.timeout,'reference_numeric_domain':args.numeric_domain}
        result=verify(load(ident),path,out/name,config=cfg)
        row={'case':name,'expected':expected,'actual':result['status'],'ok':result['status']==expected,
             'numeric_domain':args.numeric_domain if ident=='PUBLIC_08' else 'all_payload_bits','bound':cfg['bound'],'seconds':result['seconds'],
             'properties':{p['id']:p['status'] for p in result['properties']}}
        summary.append(row);print(json.dumps(row),flush=True)
        (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return 0 if all(row['ok'] for row in summary) else 1


if __name__=='__main__':raise SystemExit(main())
