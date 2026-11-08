#!/usr/bin/env python3
"""Compile complete dictionary heads within R02 top-overall grow contexts.

This never searches lower-ranked target alternatives when the top one fails.
All head alternatives/rejections and independent masks are retained in evidence.
"""
import collections
import gzip
import json
import sqlite3
import time
from pathlib import Path
from extract_pgv import OUT,HERE,sha,guards,process_hwm,encoded
from context_heads import derive_heads,clear_unit_cache

DICTIONARIES=OUT.parent/'noun-boundary-arms'
HASHES={'en':'5b16dafff9b2a27474792104bad11195ba8aff2236c134cf0265257b92727d68',
        'es':'fcae976ecf9a8eb79c4ea0e4e214e19894db12c8eb21959270e1b9ce78ab1e8e',
        'sw':'3d44e3f098d2d00f8a0907a1f8b1fa29955921832e6afb244cba0b2259cac6bf'}

def links(line):
    return [list(map(int,p.split('-'))) for p in line.split()]

def main():
    start=time.monotonic();directory=OUT/'projection-r02'
    destination=directory/'heads-r02';destination.mkdir(exist_ok=False)
    receipt=json.loads((directory/'catalog-receipt.json').read_text())
    assert receipt['complete']
    for name,record in receipt['outputs'].items():assert sha(directory/name)==record['sha256']
    align=json.loads((OUT/'alignments/receipt.json').read_text())
    for result in align['results']:
        if result['kind']=='alignment':assert sha(Path(result['output']))==result['output_sha256']
    dbs={}
    for lang,digest in HASHES.items():
        path=DICTIONARIES/f'd-{lang}.sqlite';assert sha(path)==digest
        dbs[lang]=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
        dbs[lang].execute('PRAGMA cache_size=-16384')
    index=collections.defaultdict(list)
    with gzip.open(directory/'catalog.jsonl.gz','rt') as stream:
        for line in stream:
            row=json.loads(line)
            if row['choice_kind']=='raw' and row['arm']=='grow-diag-final-and':
                index[row['pair'],row['example_pair_index']].append(row)
    assert index, 'No matching context arm; never report an empty compilation as useful completion'
    frozen=dict(production=False,compiler_sha256=sha(Path(__file__)),helper_sha256=sha(HERE/'context_heads.py'),
                catalog_sha256=sha(directory/'catalog.jsonl.gz'),dictionaries=HASHES,
                contexts=sum(map(len,index.values())),policy='R02 top-overall grow context only; no target backfill; explicit shared complete noun/adj/adv heads. All alternatives, rejected units and masks retained. Actual message masks recomputed separately.')
    (destination/'heads-freeze.json').write_text(json.dumps(frozen,indent=2)+'\n')
    counts=collections.Counter();complete=False;error=None
    try:
        with gzip.open(destination/'heads-evidence.jsonl.gz','xt',encoding='utf-8') as evidence,gzip.open(destination/'heads-catalog.jsonl.gz','xt',encoding='utf-8') as output:
            for pair in ['en-sw','en-es']:
                with gzip.open(OUT/(pair+'-pairs.jsonl.gz'),'rt') as pairs,(OUT/'alignments'/f'{pair}-forward.align').open() as forward,(OUT/'alignments'/f'{pair}-reverse.align').open() as reverse:
                    for line,fl,rl in zip(pairs,forward,reverse,strict=True):
                        raw=json.loads(line);rows=index.get((pair,raw['index']))
                        if not rows:continue
                        s,t=raw['source'],raw['target'];f,r=links(fl),links(rl)
                        for row in rows:
                            result=derive_heads(s['text'],t['text'],s['tokens'],t['tokens'],row['source_context_tokens'],row['target_context_tokens'],f,r,dbs['en'],dbs[pair[3:]])
                            proof=dict(catalog_id=row['catalog_id'],pair_id=raw['pair_id'],result=result)
                            evidence.write(encoded(proof)+'\n')
                            counts[pair+':contexts']+=1;counts[pair+':all_heads']+=len(result['heads'])
                            for head in result['heads']:
                                for reason in head['reasons']:counts[pair+':reject:'+reason]+=1
                                if not head['structural_eligible']:continue
                                eligible=[m for m in head['shared_senses'] if m['structural_eligible']]
                                a,b=head['source_tokens'];base=row['source_context_tokens'][0]
                                candidate=dict(row,head_id=head['head_id'],source_focus_relative_tokens=[a-base,b-base],
                                               target_face=head['target_text'],source_head=head['source_text'],
                                               target_focus_tokens=head['target_tokens'],target_focus_utf16=head['target_utf16'],
                                               target_focus_codepoints=head['target_codepoints'],
                                               head_shared_senses=eligible,head_readings=head['readings'],
                                               source_pos=sorted({m['source_pos'] for m in eligible}),
                                               proof_id=row['catalog_id']+':'+head['head_id'])
                                output.write(encoded(candidate)+'\n');counts[pair+':eligible_heads']+=1
                            if sum(v for k,v in counts.items() if k.endswith(':contexts'))%100==0:
                                guards(start,900)
                        if sum(v for k,v in counts.items() if k.endswith(':contexts'))%500==0:print(encoded(dict(counts=counts,seconds=time.monotonic()-start)),flush=True)
        complete=True
    except Exception as exc:
        error=repr(exc);raise
    finally:
        clear_unit_cache()
        for db in dbs.values():db.close()
        result=dict(complete=complete,error=error,production=False,freeze_sha256=sha(destination/'heads-freeze.json'),counts=counts,seconds=time.monotonic()-start,process_vm_hwm_bytes=process_hwm(),outputs={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in destination.glob('heads-*.jsonl.gz')})
        (destination/'heads-receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(encoded(result),flush=True)

if __name__=='__main__':main()
