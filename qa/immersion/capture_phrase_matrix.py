#!/usr/bin/env python3
"""Adapt a complete actual phrase capture to the native signed-pack replay format."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from conversation_corpus import sha_file, write_json


def convert(corpus,protocol,capture,protocol_sha):
    if not capture['complete'] or capture['cases_expected']!=len(protocol['samples']):raise ValueError('Incomplete capture')
    if capture['protocol_sha256']!=protocol_sha:raise ValueError('Wrong protocol')
    if capture['cases_completed']!=len(capture['results']):raise ValueError('Capture count mismatch')
    expected={(s['source'],s['target'],s['case']):s for s in protocol['samples']}
    if len(expected)!=len(protocol['samples']):raise ValueError('Duplicate protocol case')
    originals={(lang,c['id']):text for c in corpus['cases'] for lang,text in c['text'].items()}
    pairs=defaultdict(list);seen=set()
    for row in capture['results']:
        identity=(row['source'],row['target'],row['case'])
        if identity in seen or identity not in expected:raise ValueError('Unexpected/duplicate capture case')
        seen.add(identity)
        if row['status']!='executed' or not isinstance(row['translation'],str) or not row['translation'].strip():raise ValueError('Unexecuted translation')
        if row['original']!=expected[identity]['original'] or row['original']!=originals[(row['source'],row['case'])]:raise ValueError('Source mismatch')
        pairs[(row['source'],row['target'])].append({'id':row['case'],'original':row['original'],'translation':row['translation'],'status':'executed'})
    if seen!=set(expected):raise ValueError('Missing capture cases')
    if len(pairs)!=corpus['expected_pairs']:raise ValueError('Wrong pair set')
    return [{'source':source,'target':target,'status':'executed','samples':samples} for (source,target),samples in sorted(pairs.items())]


def main(a):
    corpus=json.loads(a.corpus.read_text());protocol=json.loads(a.protocol.read_text());capture=json.loads(a.capture.read_text())
    pairs=convert(corpus,protocol,capture,sha_file(a.protocol))
    report={'schema':1,'provider':capture['provider'],'platform':a.platform,'source_only':True,
        'source_languages':sorted({p['source'] for p in pairs}),'languages':corpus['languages'],
        'expected_pairs':corpus['expected_pairs'],'evidence':'actual_native_translation_capture_of_frozen_public_message_probe',
        'corpus_version':corpus['version'],
        'raw_capture_sha256':sha_file(a.capture),'corpus_sha256':sha_file(a.corpus),
        'protocol_sha256':sha_file(a.protocol),'adapter_sha256':sha_file(Path(__file__)),
        'network_absence_verified':capture['network_absence_verified'],'linguistic_acceptance':False,
        'attribution':corpus['attribution'],'results':pairs}
    if a.output.exists():raise ValueError('Preserve capture conversion')
    write_json(a.output,report)
    print(json.dumps({'pairs':len(pairs),'samples':sum(len(p['samples']) for p in pairs),'sha256':sha_file(a.output)}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('corpus','protocol','capture','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--platform',choices=['Android','Physical iOS device'],required=True)
    main(p.parse_args())
