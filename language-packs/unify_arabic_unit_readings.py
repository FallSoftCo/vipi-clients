#!/usr/bin/env python3
"""Reconcile two explicitly equivalent apostrophe spellings, not pronunciation.

Native forms, scopes, sentence references and meaning descriptions stay intact.
This is a content-bound data repair; the native conflicting-reading veto stays.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from build_wiktextract import canonical, digest_file
from mapping_catalog import validate

EXPORT_SHA='9deac7383170ed70c0aa00b525dc1d826f515f212d09c735e0916ee3f0781a4f'
READINGS={'ماء':('mā’',"mā'"),'مطعم':('maṭ’am',"maṭ'am")}

def records(export):
    if digest_file(export)!=EXPORT_SHA:raise ValueError('Changed source export')
    for line in export.read_text().splitlines():
        row=json.loads(line)['record']
        if row['target_language']!='ar' or row['target'] not in READINGS:continue
        old,new=READINGS[row['target']]
        if row['reading']==new:continue
        if row['reading']!=old:raise ValueError('Unassessed spelling')
        row=deepcopy(row);row['reading']=new;validate(row);yield row

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();rows=list(records(args.input));args.output.mkdir(parents=True,exist_ok=False)
    path=args.output/'records.jsonl';path.write_text(''.join(canonical(r)+'\n' for r in rows))
    print(canonical({'records':len(rows),'records_sha256':digest_file(path),
        'authoring_source_sha256':digest_file(Path(__file__)),'release_ready':False}))
