#!/usr/bin/env python3
"""A content-bound pair view of frozen captures; never new translation evidence."""
import argparse
import copy
import json
from pathlib import Path
from conversation_corpus import sha_file,write_json


def subset(corpus,capture,source,target):
    if source==target or source not in corpus['languages'] or target not in corpus['languages']:raise ValueError('Invalid direction')
    cases=[c for c in corpus['cases'] if source in c['text']]
    expected={c['id']:c['text'][source] for c in cases}
    if not expected or len(expected)!=len(cases):raise ValueError('Empty/duplicate source cases')
    pairs=[p for p in capture['results'] if p['source']==source and p['target']==target]
    if len(pairs)!=1:raise ValueError('Missing/duplicate captured pair')
    observed={s['id']:s for s in pairs[0]['samples']}
    if observed.keys()!=expected.keys() or len(observed)!=len(pairs[0]['samples']):raise ValueError('Capture case mismatch')
    if any(s['original']!=expected[i] or s['status']!='executed' for i,s in observed.items()):raise ValueError('Changed/failed source capture')
    view=copy.deepcopy(corpus);view.update(version=corpus['version']+'-pair-'+source+'-'+target,
        languages=[source,target],expected_pairs=1,cases=[{'id':c['id'],'text':{source:c['text'][source]}} for c in cases])
    report=copy.deepcopy(capture);report.update(source_languages=[source],languages=[source,target],expected_pairs=1,results=pairs)
    return view,report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('corpus','android','apple','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--source',required=True);p.add_argument('--target',required=True);a=p.parse_args()
    corpus=json.loads(a.corpus.read_text());a.output.mkdir(parents=True,exist_ok=False)
    if not corpus.get('source_only'):raise ValueError('Source-only frozen probe required')
    previous=None;outputs=[]
    for platform,path in [('android',a.android),('apple',a.apple)]:
        capture=json.loads(path.read_text())
        if capture['corpus_sha256']!=sha_file(a.corpus):raise ValueError('Wrong parent corpus binding')
        view,report=subset(corpus,capture,a.source,a.target)
        if previous is not None and view!=previous:raise ValueError('Different platform corpus')
        if previous is None:write_json(a.output/'corpus.json',view)
        previous=view;report.update(corpus_sha256=sha_file(a.output/'corpus.json'),
            parent_corpus_sha256=sha_file(a.corpus),parent_capture_sha256=sha_file(path),
            capture_view='Exact pair subset; original translation evidence retained; no new translation execution')
        output=a.output/(platform+'-translations.json');write_json(output,report)
        outputs.append({'platform':platform,'sha256':sha_file(output),'parent_capture_sha256':sha_file(path)})
    write_json(a.output/'receipt.json',{'schema':'vipi-native-probe-pair-view-1','source':a.source,'target':a.target,
        'messages':len(previous['cases']),'parent_corpus_sha256':sha_file(a.corpus),'corpus_sha256':sha_file(a.output/'corpus.json'),
        'captures':outputs,'adapter_sha256':sha_file(Path(__file__)),'new_translation_execution':False})
