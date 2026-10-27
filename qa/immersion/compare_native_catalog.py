#!/usr/bin/env python3
"""Compare actual native selections on the same authored catalog, without MT.

Parity is a diagnostic, not a linguistic correctness score. Inputs must be the
complete matching reference capture, in catalog order, with UTF-16 ranges.
"""
import argparse
import hashlib
import json
from pathlib import Path

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def substring(text,start,end):
    if not isinstance(start,int) or not isinstance(end,int) or not 0 <= start < end <= len(text.encode('utf-16-le'))//2:
        raise ValueError('Invalid native range')
    return text.encode('utf-16-le')[start*2:end*2].decode('utf-16-le')

def capture(path,catalog,catalog_hash):
    data=json.loads(path.read_text())
    if data['schema']!='vipi-native-catalog-parity-1' or data['catalog_sha256']!=catalog_hash:
        raise ValueError('Native capture uses a different catalog')
    rows=data['cases']
    if len(rows)!=len(catalog['references']):raise ValueError('Incomplete native capture')
    for i,(row,reference) in enumerate(zip(rows,catalog['references'],strict=True)):
        if row['index']!=i or any(row[key]!=reference[key] for key in ('pair','original','translation')):
            raise ValueError('Reference order/content changed')
        for span in row['spans']:
            if substring(row['original'],span['start'],span['end'])!=span['original']:
                raise ValueError('Incorrect source focus range')
            if substring(row['translation'],span['target_start'],span['target_end'])!=span['translated']:
                raise ValueError('Incorrect target focus range')
    return rows

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('left','right','catalog','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();catalog=json.loads(args.catalog.read_text());h=sha(args.catalog)
    left=capture(args.left,catalog,h);right=capture(args.right,catalog,h)
    changes=[dict(index=a['index'],pair=a['pair'],original=a['original'],translation=a['translation'],left=a['spans'],right=b['spans'])
        for a,b in zip(left,right,strict=True) if a['spans']!=b['spans']]
    report=dict(schema='vipi-native-catalog-parity-summary-1',catalog_sha256=h,left_sha256=sha(args.left),right_sha256=sha(args.right),
        references=len(left),left_spans=sum(len(r['spans']) for r in left),right_spans=sum(len(r['spans']) for r in right),
        differing_references=len(changes),changes=changes,semantic_acceptance=False)
    with args.output.open('x') as out:json.dump(report,out,ensure_ascii=False,indent=2);out.write('\n')
    print(json.dumps({k:v for k,v in report.items() if k!='changes'}))
