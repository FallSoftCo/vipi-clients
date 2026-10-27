#!/usr/bin/env python3
"""Summarize complete native dictionary replays without exposing corpus text."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def identity(row):return row['dataset'],row['id'],row['source'],row['target']
def quantile(values,p):
    values=sorted(values)
    return round(values[min(len(values)-1,int((len(values)-1)*p))],3) if values else None

def read(root,path):
    manifest=json.loads((root/'manifest.json').read_text())
    assert manifest['cases_sha256']==sha(root/'cases.json')
    cases=json.loads((root/'cases.json').read_text());expected={identity(r):r for r in cases}
    assert len(expected)==len(cases)==manifest['cases']
    report=json.loads(path.read_text())
    assert report['schema']=='vipi-lexical-coverage-1' and report['complete']
    assert report['manifest_sha256']==sha(root/'manifest.json')
    actual={identity(r):r for r in report['outcomes']}
    assert set(actual)==set(expected) and len(actual)==len(report['outcomes'])==report['cases']
    failures=[]
    for key,row in actual.items():
        case=expected[key];spans=row['spans']
        for span in spans:
            for text_key,start,end,focus in [('original','start','end','source'),('translation','target_start','target_end','target')]:
                text=case[text_key].encode('utf-16-le')
                assert 0<=span[start]<span[end]<=len(text)//2
                assert text[2*span[start]:2*span[end]].decode('utf-16-le')==span[focus]
            if case['target'] in {'ar','zh','ja','ko'}:assert span['reading'] and span['reading'].strip()
        if 'forbidden_source' in case and any(s['source']==case['forbidden_source'] and s['target']==case['forbidden_target'] for s in spans):failures.append(list(key))
        if 'expected_source' in case and not any(s['source']==case['expected_source'] and s['target']==case['expected_target'] for s in spans):failures.append(list(key))
    assert report['passed']==(not failures)
    groups=defaultdict(list)
    for row in actual.values():
        groups[row['dataset']].append(row)
        groups[row['dataset']+':'+row['source']+'-'+row['target']].append(row)
    summary={}
    for group,rows in sorted(groups.items()):
        baseline=sum(r['baseline_spans']>0 for r in rows);dictionary=sum(bool(r['spans']) for r in rows)
        extra=sum(bool(r['spans']) and not r['baseline_spans'] for r in rows)
        diagnostics=Counter()
        for row in rows:diagnostics.update(row.get('diagnostics',{}))
        summary[group]=dict(cases=len(rows),baseline_messages=baseline,dictionary_messages=dictionary,
            additional_messages=extra,union_messages=baseline+extra,union_percent=round(100*(baseline+extra)/len(rows),2),
            selected_spans=sum(len(r['spans']) for r in rows),lookup_median_ms=quantile([r['elapsed_ms'] for r in rows],.5),
            lookup_p95_ms=quantile([r['elapsed_ms'] for r in rows],.95),diagnostics=dict(diagnostics))
    return dict(platform=report['platform'],report_sha256=sha(path),manifest_sha256=report['manifest_sha256'],
        complete=True,passed=not failures,failures=failures,groups=summary),actual

def main(a):
    result,rows=read(a.fixture,a.report)
    if a.compare:
        other,against=read(a.fixture,a.compare);assert set(rows)==set(against)
        differences=[]
        for key,row in rows.items():
            left=sorted(row['spans'],key=lambda s:(s['start'],s['end'],s['target']))
            right=sorted(against[key]['spans'],key=lambda s:(s['start'],s['end'],s['target']))
            if left!=right:differences.append(list(key))
        result['parity']=dict(other_platform=other['platform'],other_sha256=other['report_sha256'],
            cases=len(rows),differing_cases=len(differences),differences=differences)
    result.update(schema='vipi-lexical-coverage-summary-1',independent_semantic_acceptance=False,
        limitation='Reused native translations and dictionary-unit mechanics; message availability is not semantic accuracy or general-population coverage.')
    with a.output.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='groups'}))
    print(json.dumps({k:v for k,v in result['groups'].items() if ':' not in k}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['fixture','report','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--compare',type=Path);main(p.parse_args())
