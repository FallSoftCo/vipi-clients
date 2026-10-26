#!/usr/bin/env python3
"""Compare native pack revisions on identical, provenance-bound translations."""
import argparse
import json
from pathlib import Path
from conversation_corpus import sha_file,write_json
from evaluate_sms_pipeline import summarize


def compare(before,after):
    if before['platform']!=after['platform']:raise ValueError('Different native platforms')
    def rows(report):
        result={}
        for p in report['results']:
            for s in p['samples']:
                k=(p['source'],p['target'],s['id'])
                if k in result or s['status']!='executed':raise ValueError('Duplicate or failed case')
                result[k]=s
        return result
    old,new=rows(before),rows(after)
    if old.keys()!=new.keys():raise ValueError('Different native case sets')
    changes=[]
    for identity,b in old.items():
        a=new[identity]
        if (a['original'],a['translation'])!=(b['original'],b['translation']):raise ValueError('Translations changed')
        differences={}
        for field in ('spans','context_candidates'):
            left={json.dumps(s,sort_keys=True,ensure_ascii=False) for s in b.get(field,[])}
            right={json.dumps(s,sort_keys=True,ensure_ascii=False) for s in a.get(field,[])}
            if left!=right:differences[field]={'added':[json.loads(s) for s in sorted(right-left)],'removed':[json.loads(s) for s in sorted(left-right)]}
        if differences:changes.append({'pair':identity[0]+'-'+identity[1],'id':identity[2],
            'original':a['original'],'translation':a['translation'],'differences':differences})
    return changes


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('before','after','capture','corpus','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();before=json.loads(a.before.read_text());after=json.loads(a.after.read_text())
    capture=json.loads(a.capture.read_text());corpus=json.loads(a.corpus.read_text())
    if after['translation_capture_sha256']!=sha_file(a.capture) or before['translation_capture_sha256']!=capture['parent_capture_sha256']:
        raise ValueError('Unbound parent/replay capture')
    if capture['corpus_sha256']!=sha_file(a.corpus):raise ValueError('Unbound subset corpus')
    pairs={(r['source'],r['target']) for r in after['results']}
    before_view=dict(before,results=[r for r in before['results'] if (r['source'],r['target']) in pairs])
    if a.output.exists():raise ValueError('Preserve comparison receipt')
    write_json(a.output,{'schema':'vipi-native-probe-comparison-1','platform':after['platform'],
        'before_sha256':sha_file(a.before),'after_sha256':sha_file(a.after),'capture_sha256':sha_file(a.capture),
        'corpus_sha256':sha_file(a.corpus),'comparator_sha256':sha_file(Path(__file__)),
        'before':summarize(before_view,corpus),'after':summarize(after,corpus),
        'changes':compare(before_view,after),'meaning_accuracy':None,'linguistic_acceptance':False})
